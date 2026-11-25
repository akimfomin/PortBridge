// SPDX-License-Identifier: MIT
#include "probe.h"

#include <bcrypt.h>
#include <d3d12.h>
#include <dxgi1_4.h>
#include <psapi.h>
#include <wrl/client.h>

#include <array>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string_view>
#include <vector>

namespace {
using Microsoft::WRL::ComPtr;

std::vector<char> read_bytes(const std::filesystem::path& path, std::streamsize maximum) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    const auto size = file.tellg();
    if (size <= 0 || size > maximum) return {};
    std::vector<char> bytes(static_cast<std::size_t>(size));
    if (!file.seekg(0).read(bytes.data(), static_cast<std::streamsize>(size))) return {};
    return bytes;
}

std::vector<char> read_dx_container(const wchar_t* path, std::streamsize maximum) {
    auto bytes = read_bytes(path, maximum);
    if (bytes.size() < 32 || std::memcmp(bytes.data(), "DXBC", 4) != 0) return {};
    return bytes;
}

bool write_bytes(const std::filesystem::path& path, const void* data, std::size_t bytes) {
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out.write(static_cast<const char*>(data), static_cast<std::streamsize>(bytes)))
        return false;
    out.close();
    return bool(out);
}

bool hash_bytes(std::vector<char>& bytes, BYTE (&hash)[32]) {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0) return false;
    BCRYPT_HASH_HANDLE handle = nullptr;
    NTSTATUS status = BCryptCreateHash(algorithm, &handle, nullptr, 0, nullptr, 0, 0);
    if (status >= 0) {
        status = BCryptHashData(handle, reinterpret_cast<PUCHAR>(bytes.data()), static_cast<ULONG>(bytes.size()), 0);
        if (status >= 0) status = BCryptFinishHash(handle, hash, sizeof(hash), 0);
        BCryptDestroyHash(handle);
    }
    BCryptCloseAlgorithmProvider(algorithm, 0);
    return status >= 0;
}

bool contains_ordinal(std::wstring_view text, std::wstring_view needle) {
    if (needle.empty() || needle.size() > text.size()) return false;
    const int length = static_cast<int>(needle.size());
    for (std::size_t offset = 0; offset + needle.size() <= text.size(); ++offset) {
        if (CompareStringOrdinal(text.data() + offset, length, needle.data(), length, TRUE) == CSTR_EQUAL)
            return true;
    }
    return false;
}

void sample_commit(SIZE_T& current, SIZE_T& peak) {
    PROCESS_MEMORY_COUNTERS_EX memory{};
    memory.cb = sizeof(memory);
    if (GetProcessMemoryInfo(GetCurrentProcess(), reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&memory), sizeof(memory))) {
        current = memory.PrivateUsage;
        peak = memory.PeakPagefileUsage;
    }
}

bool open_adapter(Report& report, const wchar_t* selector, ComPtr<ID3D12Device>& device) {
    report.stage = Stage::adapter;
    ComPtr<IDXGIFactory1> factory;
    report.error = CreateDXGIFactory1(IID_PPV_ARGS(&factory));
    if (FAILED(report.error)) return false;
    ComPtr<IDXGIAdapter1> chosen;
    for (UINT index = 0;; ++index) {
        ComPtr<IDXGIAdapter1> candidate;
        report.error = factory->EnumAdapters1(index, &candidate);
        if (report.error == DXGI_ERROR_NOT_FOUND) break;
        if (FAILED(report.error)) return false;
        DXGI_ADAPTER_DESC1 desc{};
        report.error = candidate->GetDesc1(&desc);
        if (FAILED(report.error)) return false;
        if ((desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) != 0 || !contains_ordinal(desc.Description, selector))
            continue;
        if (chosen) {
            report.error = HRESULT_FROM_WIN32(ERROR_DUP_NAME);
            return false;
        }
        chosen = candidate;
        report.luid = desc.AdapterLuid;
        report.vendor = desc.VendorId;
        report.device = desc.DeviceId;
        std::memcpy(report.adapter, desc.Description, sizeof(report.adapter));
    }
    if (!chosen) return false;
    LARGE_INTEGER driver{};
    if (SUCCEEDED(chosen->CheckInterfaceSupport(__uuidof(IDXGIDevice), &driver)))
        report.dxgi_driver_version = static_cast<std::uint64_t>(driver.QuadPart);

    report.stage = Stage::device;
    report.error = D3D12CreateDevice(chosen.Get(), D3D_FEATURE_LEVEL_12_0, IID_PPV_ARGS(&device));
    return SUCCEEDED(report.error);
}
} // namespace

Report measure(const wchar_t* selector, const wchar_t* root_path, const wchar_t* shader_path, bool smoke) {
    Report report;
    if (!has_worker_limits(smoke ? smoke_limit : process_limit)) return report;

    report.stage = Stage::input;
    auto root_bytes = read_dx_container(root_path, 64 * 1024);
    auto shader = read_dx_container(shader_path, (smoke ? 4 : 128) * 1024);
    report.error = E_INVALIDARG;
    if (shader.empty() || root_bytes.empty() || !hash_bytes(root_bytes, report.root_sha) ||
        !hash_bytes(shader, report.shader_sha)) return report;
    report.shader_bytes = static_cast<DWORD>(shader.size());
    ComPtr<ID3D12Device> device;
    if (!open_adapter(report, selector, device)) return report;

    if (!smoke) {
        report.stage = Stage::cache;
        ComPtr<ID3D12Device9> cache;
        report.error = device.As(&cache);
        if (FAILED(report.error)) return report;
        const auto kinds = D3D12_SHADER_CACHE_KIND_FLAG_IMPLICIT_D3D_CACHE_FOR_DRIVER |
                           D3D12_SHADER_CACHE_KIND_FLAG_IMPLICIT_DRIVER_MANAGED;
        report.error = cache->ShaderCacheControl(kinds, D3D12_SHADER_CACHE_CONTROL_FLAG_DISABLE);
        if (FAILED(report.error)) return report;
    }

    report.stage = Stage::root_signature;
    ComPtr<ID3D12RootSignature> root;
    report.error = device->CreateRootSignature(0, root_bytes.data(), root_bytes.size(), IID_PPV_ARGS(&root));
    if (FAILED(report.error)) return report;

    report.stage = Stage::pipeline;
    D3D12_COMPUTE_PIPELINE_STATE_DESC desc{};
    desc.pRootSignature = root.Get();
    desc.CS = {shader.data(), shader.size()};
    ComPtr<ID3D12PipelineState> pipeline;
    sample_commit(report.private_before, report.lifetime_peak_before);
    const auto start = std::chrono::steady_clock::now();
    report.error = device->CreateComputePipelineState(&desc, IID_PPV_ARGS(&pipeline));
    report.pso_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
    sample_commit(report.private_after, report.lifetime_peak_after);
    if (SUCCEEDED(report.error)) report.stage = Stage::complete;
    return report;
}

Report measure_library(const wchar_t* selector, const wchar_t* root_path, wchar_t* const* paths,
                       CacheAction action, const wchar_t* archive_path) {
    constexpr unsigned count = 6;
    constexpr std::size_t cache_limit = 16 * mib;
    constexpr const wchar_t* names[count] = {L"p0", L"p1", L"p2", L"p3", L"p4", L"p5"};
    Report report;
    if (!has_worker_limits(smoke_limit)) return report;
    report.stage = Stage::input;
    report.error = E_INVALIDARG;
    auto root_bytes = read_dx_container(root_path, 64 * 1024);
    if (root_bytes.empty() || !hash_bytes(root_bytes, report.root_sha)) return report;
    std::array<std::vector<char>, count> shaders;
    std::vector<char> bundle;
    bundle.reserve(count * (4 * 1024 + sizeof(std::uint32_t)));
    for (unsigned i = 0; i < count; ++i) {
        shaders[i] = read_dx_container(paths[i], 4 * 1024);
        if (shaders[i].empty()) return report;
        for (unsigned j = 0; j < i; ++j) {
            if (shaders[i] == shaders[j]) return report;
        }
        const auto size = static_cast<std::uint32_t>(shaders[i].size());
        for (unsigned shift = 0; shift < 32; shift += 8)
            bundle.push_back(static_cast<char>((size >> shift) & 0xff));
        bundle.insert(bundle.end(), shaders[i].begin(), shaders[i].end());
        report.shader_bytes += size;
    }
    if (!hash_bytes(bundle, report.shader_sha)) return report;

    ComPtr<ID3D12Device> device;
    if (!open_adapter(report, selector, device)) return report;
    report.stage = Stage::root_signature;
    ComPtr<ID3D12RootSignature> root;
    report.error = device->CreateRootSignature(0, root_bytes.data(), root_bytes.size(), IID_PPV_ARGS(&root));
    if (FAILED(report.error)) return report;

    report.stage = Stage::cache;
    ComPtr<ID3D12Device1> factory;
    report.error = device.As(&factory);
    if (FAILED(report.error)) return report;
    const std::filesystem::path archive = archive_path ? archive_path : L"";
    const auto blob_path = [&](unsigned i) { return archive / (std::string("p") + std::to_string(i) + ".blob"); };
    // The serialized buffer must outlive any library opened from it.
    std::vector<char> library_blob;
    ComPtr<ID3D12PipelineLibrary> library;
    std::array<D3D12_COMPUTE_PIPELINE_STATE_DESC, count> descs{};
    std::array<ComPtr<ID3DBlob>, count> blobs;
    std::array<std::vector<char>, count> stored_blobs;
    sample_commit(report.private_before, report.lifetime_peak_before);
    for (unsigned i = 0; i < count; ++i) {
        auto& desc = descs[i];
        desc.pRootSignature = root.Get();
        desc.CS = {shaders[i].data(), shaders[i].size()};
    }

    const auto now = std::chrono::steady_clock::now;
    const auto elapsed = [&](auto start) { return std::chrono::duration<double, std::milli>(now() - start).count(); };
    const auto replay_library = [&] {
        const auto open = now();
        report.error = factory->CreatePipelineLibrary(library_blob.data(), library_blob.size(), IID_PPV_ARGS(&library));
        report.library_open_ms = elapsed(open);
        if (FAILED(report.error)) return false;
        const auto start = now();
        for (unsigned i = 0; i < count; ++i) {
            ComPtr<ID3D12PipelineState> pipe;
            report.error = library->LoadComputePipeline(names[i], &descs[i], IID_PPV_ARGS(&pipe));
            if (FAILED(report.error)) return false;
        }
        report.library_replay_ms = elapsed(start);
        return true;
    };
    const auto create_pipelines = [&](bool use_blobs, double& total_ms) {
        const auto start = now();
        for (unsigned i = 0; i < count; ++i) {
            auto desc = descs[i];
            if (use_blobs) {
                if (blobs[i])
                    desc.CachedPSO = {blobs[i]->GetBufferPointer(), blobs[i]->GetBufferSize()};
                else
                    desc.CachedPSO = {stored_blobs[i].data(), stored_blobs[i].size()};
            }
            ComPtr<ID3D12PipelineState> pipe;
            report.error = device->CreateComputePipelineState(&desc, IID_PPV_ARGS(&pipe));
            if (FAILED(report.error)) return false;
        }
        total_ms = elapsed(start);
        return true;
    };
    if (action == CacheAction::replay_plain) {
        if (!create_pipelines(false, report.warm_create_ms)) return report;
    } else if (action == CacheAction::replay_blobs) {
        report.error = E_INVALIDARG;
        for (unsigned i = 0; i < count; ++i) {
            stored_blobs[i] = read_bytes(blob_path(i), cache_limit - report.individual_cache_bytes);
            if (stored_blobs[i].empty()) return report;
            report.individual_cache_bytes += stored_blobs[i].size();
        }
        if (!create_pipelines(true, report.individual_replay_ms)) return report;
    } else if (action == CacheAction::replay_library) {
        report.error = E_INVALIDARG;
        library_blob = read_bytes(archive / "library.blob", cache_limit);
        if (library_blob.empty()) return report;
        report.library_bytes = library_blob.size();
        if (!replay_library()) return report;
    } else {
        report.error = factory->CreatePipelineLibrary(nullptr, 0, IID_PPV_ARGS(&library));
        if (FAILED(report.error)) return report;
        for (unsigned i = 0; i < count; ++i) {
            ComPtr<ID3D12PipelineState> pipe;
            report.error = device->CreateComputePipelineState(&descs[i], IID_PPV_ARGS(&pipe));
            if (FAILED(report.error)) return report;
            report.error = pipe->GetCachedBlob(blobs[i].GetAddressOf());
            if (FAILED(report.error)) return report;
            const auto size = blobs[i]->GetBufferSize();
            if (!size || size > cache_limit - report.individual_cache_bytes ||
                (action == CacheAction::seed && !write_bytes(blob_path(i), blobs[i]->GetBufferPointer(), size))) {
                report.error = E_FAIL;
                return report;
            }
            report.individual_cache_bytes += size;
            report.error = library->StorePipeline(names[i], pipe.Get());
            if (FAILED(report.error)) return report;
        }
        report.library_bytes = library->GetSerializedSize();
        if (!report.library_bytes || report.library_bytes > cache_limit) {
            report.error = E_FAIL;
            return report;
        }
        library_blob.resize(static_cast<std::size_t>(report.library_bytes));
        report.error = library->Serialize(library_blob.data(), library_blob.size());
        if (FAILED(report.error)) return report;
        library.Reset();
        if (action == CacheAction::seed) {
            if (!write_bytes(archive / "library.blob", library_blob.data(), library_blob.size())) {
                report.error = E_FAIL;
                return report;
            }
        } else {
            const auto replay_individual = [&] { return create_pipelines(true, report.individual_replay_ms); };
            const bool library_first = action == CacheAction::library_first;
            if (library_first ? (!replay_library() || !replay_individual()) : (!replay_individual() || !replay_library()))
                return report;
            if (!create_pipelines(false, report.warm_create_ms)) return report;
        }
    }
    sample_commit(report.private_after, report.lifetime_peak_after);
    report.library_pipelines = count;
    report.stage = Stage::complete;
    return report;
}
