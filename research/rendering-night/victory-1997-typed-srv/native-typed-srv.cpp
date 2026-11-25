// SPDX-License-Identifier: GPL-3.0-or-later
#include "guard.h"
#include "native-typed-srv.inc"

#include <d3d12.h>
#include <d3d12sdklayers.h>
#include <dxgi1_6.h>
#include <wrl/client.h>
#include <array>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstring>

namespace {
using Microsoft::WRL::ComPtr;
constexpr auto job_limit = 512 * guard::mib;
constexpr auto deadline = std::chrono::milliseconds(3000);
constexpr auto adapter_name = L"NVIDIA GeForce RTX 4070 Ti SUPER";

struct Sample {
    DXGI_FORMAT format;
    unsigned bytes;
    std::uint64_t packed;
    std::array<float, 4> expected;
};

constexpr std::array<Sample, 4> samples{{
    {DXGI_FORMAT_R8G8B8A8_UNORM, 4, 0x80ff0020, {32.0f / 255, 0, 1, 128.0f / 255}},
    {DXGI_FORMAT_R16G16B16A16_UNORM, 8, 0x8000000000004000, {16384.0f / 65535, 0, 0, 32768.0f / 65535}},
    {DXGI_FORMAT_R16G16B16A16_SNORM, 8, 0x40007fff2000c000, {-16384.0f / 32767, 8192.0f / 32767, 1, 16384.0f / 32767}},
    {DXGI_FORMAT_R8G8B8A8_SNORM, 4, 0x407f20c0, {-64.0f / 127, 32.0f / 127, 1, 64.0f / 127}},
}};
constexpr auto texture_placement = D3D12_TEXTURE_DATA_PLACEMENT_ALIGNMENT;

struct Report {
    unsigned status{}, feature{}, debug{}, debug_errors{}, hresult{};
    char step[48]{};
    std::array<unsigned, 4> sample_support{};
    std::array<std::uint32_t, 16> values{};
};

struct Failure { HRESULT error; const char* step; };

void check(HRESULT result, const char* step) {
    if (FAILED(result)) throw Failure{result, step};
}

D3D12_RESOURCE_DESC buffer_desc(UINT64 bytes, D3D12_RESOURCE_FLAGS flags) {
    D3D12_RESOURCE_DESC desc{};
    desc.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
    desc.Width = bytes;
    desc.Height = 1;
    desc.DepthOrArraySize = 1;
    desc.MipLevels = 1;
    desc.SampleDesc.Count = 1;
    desc.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    desc.Flags = flags;
    return desc;
}

D3D12_RESOURCE_DESC texture_desc(DXGI_FORMAT format) {
    D3D12_RESOURCE_DESC desc{};
    desc.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
    desc.Width = 1;
    desc.Height = 1;
    desc.DepthOrArraySize = 1;
    desc.MipLevels = 1;
    desc.Format = format;
    desc.SampleDesc.Count = 1;
    return desc;
}

ComPtr<ID3D12Resource> resource(ID3D12Device* device, const D3D12_RESOURCE_DESC& desc,
                                D3D12_HEAP_TYPE type, D3D12_RESOURCE_STATES state) {
    D3D12_HEAP_PROPERTIES heap{};
    heap.Type = type;
    heap.CreationNodeMask = 1;
    heap.VisibleNodeMask = 1;
    ComPtr<ID3D12Resource> result;
    check(device->CreateCommittedResource(&heap, D3D12_HEAP_FLAG_NONE, &desc, state,
                                           nullptr, IID_PPV_ARGS(&result)), "CreateCommittedResource");
    return result;
}

void transition(ID3D12GraphicsCommandList* list, ID3D12Resource* resource,
                D3D12_RESOURCE_STATES before, D3D12_RESOURCE_STATES after) {
    D3D12_RESOURCE_BARRIER barrier{};
    barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    barrier.Transition = {resource, D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES, before, after};
    list->ResourceBarrier(1, &barrier);
}

ComPtr<ID3D12RootSignature> root_signature(ID3D12Device* device) {
    const D3D12_DESCRIPTOR_RANGE textures{D3D12_DESCRIPTOR_RANGE_TYPE_SRV, 4, 0, 0, 0};
    D3D12_ROOT_PARAMETER params[2]{};
    params[0].ParameterType = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
    params[0].DescriptorTable = {1, &textures};
    params[1].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
    params[1].Descriptor = {0, 0};
    D3D12_STATIC_SAMPLER_DESC sampler{};
    sampler.Filter = D3D12_FILTER_MIN_MAG_MIP_LINEAR;
    sampler.AddressU = sampler.AddressV = sampler.AddressW = D3D12_TEXTURE_ADDRESS_MODE_CLAMP;
    sampler.MaxAnisotropy = 1;
    sampler.ComparisonFunc = D3D12_COMPARISON_FUNC_ALWAYS;
    sampler.MaxLOD = D3D12_FLOAT32_MAX;
    const D3D12_ROOT_SIGNATURE_DESC root{2, params, 1, &sampler, D3D12_ROOT_SIGNATURE_FLAG_NONE};
    ComPtr<ID3DBlob> blob;
    check(D3D12SerializeRootSignature(&root, D3D_ROOT_SIGNATURE_VERSION_1, &blob, nullptr), "SerializeRootSignature");
    ComPtr<ID3D12RootSignature> result;
    check(device->CreateRootSignature(0, blob->GetBufferPointer(), blob->GetBufferSize(), IID_PPV_ARGS(&result)),
          "CreateRootSignature");
    return result;
}

Report sample() {
    Report report;
    try {
        ComPtr<IDXGIFactory1> factory;
        check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)), "CreateDXGIFactory1");
        ComPtr<IDXGIAdapter1> adapter;
        for (UINT index = 0; index < 32; ++index) {
            const auto hr = factory->EnumAdapters1(index, &adapter);
            if (hr == DXGI_ERROR_NOT_FOUND) break;
            check(hr, "EnumAdapters1");
            DXGI_ADAPTER_DESC1 info{};
            check(adapter->GetDesc1(&info), "GetDesc1");
            if ((info.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) == 0 && info.VendorId == 0x10de && info.DeviceId == 0x2705
                && std::wstring_view(info.Description) == adapter_name) break;
            adapter.Reset();
        }
        if (!adapter) throw Failure{DXGI_ERROR_NOT_FOUND, "Explicit RTX adapter"};
        ComPtr<ID3D12Debug> debug;
        if (SUCCEEDED(D3D12GetDebugInterface(IID_PPV_ARGS(&debug)))) {
            debug->EnableDebugLayer();
            report.debug = 1;
        }
        ComPtr<ID3D12Device> device;
        check(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_12_0, IID_PPV_ARGS(&device)), "D3D12CreateDevice");
        constexpr unsigned required = static_cast<unsigned>(D3D12_FORMAT_SUPPORT1_TEXTURE2D)
            | static_cast<unsigned>(D3D12_FORMAT_SUPPORT1_SHADER_SAMPLE);
        for (unsigned i = 0; i < samples.size(); ++i) {
            D3D12_FEATURE_DATA_FORMAT_SUPPORT format_support{samples[i].format};
            const auto support = device->CheckFeatureSupport(D3D12_FEATURE_FORMAT_SUPPORT, &format_support, sizeof(format_support));
            report.sample_support[i] = static_cast<unsigned>(format_support.Support1);
            if (FAILED(support) || (report.sample_support[i] & required) != required) {
                report.status = 77;
                report.hresult = static_cast<unsigned>(support);
                std::snprintf(report.step, sizeof(report.step), "No Texture2D sample support for format %u", static_cast<unsigned>(samples[i].format));
                return report;
            }
            report.feature |= 1u << i;
        }
        auto root = root_signature(device.Get());
        D3D12_COMPUTE_PIPELINE_STATE_DESC pso_desc{};
        pso_desc.pRootSignature = root.Get();
        pso_desc.CS = {native_cast_dxil, sizeof(native_cast_dxil)};
        ComPtr<ID3D12PipelineState> pso;
        check(device->CreateComputePipelineState(&pso_desc, IID_PPV_ARGS(&pso)), "CreateComputePipelineState");
        auto upload = resource(device.Get(), buffer_desc(samples.size() * texture_placement, D3D12_RESOURCE_FLAG_NONE),
                               D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        auto output = resource(device.Get(), buffer_desc(sizeof(report.values), D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS),
                               D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
        auto readback = resource(device.Get(), buffer_desc(sizeof(report.values), D3D12_RESOURCE_FLAG_NONE),
                                 D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        void* mapped{};
        const D3D12_RANGE no_read{};
        check(upload->Map(0, &no_read, &mapped), "Map upload");
        for (unsigned i = 0; i < samples.size(); ++i) {
            std::memcpy(static_cast<std::byte*>(mapped) + i * texture_placement, &samples[i].packed, samples[i].bytes);
        }
        const D3D12_RANGE wrote_texel{0, (samples.size() - 1) * texture_placement + samples.back().bytes};
        upload->Unmap(0, &wrote_texel);
        std::array<ComPtr<ID3D12Resource>, samples.size()> textures;
        for (unsigned i = 0; i < textures.size(); ++i) {
            textures[i] = resource(device.Get(), texture_desc(samples[i].format),
                                   D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_COPY_DEST);
        }
        ComPtr<ID3D12DescriptorHeap> heap;
        D3D12_DESCRIPTOR_HEAP_DESC desc{};
        desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
        desc.NumDescriptors = 4;
        desc.Flags = D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
        check(device->CreateDescriptorHeap(&desc, IID_PPV_ARGS(&heap)), "CreateDescriptorHeap");
        auto cpu = heap->GetCPUDescriptorHandleForHeapStart();
        const auto step = device->GetDescriptorHandleIncrementSize(desc.Type);
        for (unsigned i = 0; i < samples.size(); ++i) {
            D3D12_SHADER_RESOURCE_VIEW_DESC view{};
            view.Format = samples[i].format;
            view.ViewDimension = D3D12_SRV_DIMENSION_TEXTURE2D;
            view.Shader4ComponentMapping = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
            view.Texture2D.MipLevels = 1;
            device->CreateShaderResourceView(textures[i].Get(), &view, cpu);
            cpu.ptr += step;
        }
        D3D12_COMMAND_QUEUE_DESC queue_desc{};
        queue_desc.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
        ComPtr<ID3D12CommandQueue> queue;
        check(device->CreateCommandQueue(&queue_desc, IID_PPV_ARGS(&queue)), "CreateCommandQueue");
        ComPtr<ID3D12CommandAllocator> allocator;
        check(device->CreateCommandAllocator(queue_desc.Type, IID_PPV_ARGS(&allocator)), "CreateCommandAllocator");
        ComPtr<ID3D12GraphicsCommandList> list;
        check(device->CreateCommandList(0, queue_desc.Type, allocator.Get(), pso.Get(), IID_PPV_ARGS(&list)),
              "CreateCommandList");
        for (unsigned i = 0; i < textures.size(); ++i) {
            D3D12_TEXTURE_COPY_LOCATION from{}, to{};
            from.pResource = upload.Get();
            from.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
            const auto texture = texture_desc(samples[i].format);
            UINT rows{};
            UINT64 row_bytes{}, footprint_bytes{};
            device->GetCopyableFootprints(&texture, 0, 1, i * texture_placement,
                &from.PlacedFootprint, &rows, &row_bytes, &footprint_bytes);
            if (rows != 1 || row_bytes != samples[i].bytes || from.PlacedFootprint.Offset != i * texture_placement
                || from.PlacedFootprint.Footprint.RowPitch > texture_placement || footprint_bytes == UINT64_MAX)
                throw Failure{E_FAIL, "Unexpected copy footprint"};
            to.pResource = textures[i].Get();
            to.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
            list->CopyTextureRegion(&to, 0, 0, 0, &from, nullptr);
            transition(list.Get(), textures[i].Get(), D3D12_RESOURCE_STATE_COPY_DEST,
                       D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
        }
        ID3D12DescriptorHeap* heaps[]{heap.Get()};
        list->SetDescriptorHeaps(1, heaps);
        list->SetComputeRootSignature(root.Get());
        list->SetComputeRootDescriptorTable(0, heap->GetGPUDescriptorHandleForHeapStart());
        list->SetComputeRootUnorderedAccessView(1, output->GetGPUVirtualAddress());
        list->Dispatch(1, 1, 1);
        transition(list.Get(), output.Get(), D3D12_RESOURCE_STATE_UNORDERED_ACCESS, D3D12_RESOURCE_STATE_COPY_SOURCE);
        list->CopyBufferRegion(readback.Get(), 0, output.Get(), 0, sizeof(report.values));
        check(list->Close(), "Close list");
        ComPtr<ID3D12Fence> fence;
        check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence)), "CreateFence");
        guard::Handle event(CreateEventW(nullptr, FALSE, FALSE, nullptr));
        if (!event) throw Failure{HRESULT_FROM_WIN32(GetLastError()), "CreateEvent"};
        check(fence->SetEventOnCompletion(1, event.value), "SetEventOnCompletion");
        ID3D12CommandList* lists[]{list.Get()};
        queue->ExecuteCommandLists(1, lists);
        check(queue->Signal(fence.Get(), 1), "Signal fence");
        if (WaitForSingleObject(event.value, 1200) != WAIT_OBJECT_0)
            throw Failure{HRESULT_FROM_WIN32(ERROR_TIMEOUT), "Fence wait"};
        check(device->GetDeviceRemovedReason(), "Device state");
        const D3D12_RANGE result_range{0, sizeof(report.values)};
        check(readback->Map(0, &result_range, &mapped), "Map readback");
        std::memcpy(report.values.data(), mapped, sizeof(report.values));
        readback->Unmap(0, &no_read);
        ComPtr<ID3D12InfoQueue> messages;
        if (report.debug && SUCCEEDED(device.As(&messages))) {
            report.debug_errors = static_cast<unsigned>(messages->GetNumStoredMessages());
        }
        report.status = 1;
    } catch (const Failure& failure) {
        report.hresult = static_cast<unsigned>(failure.error);
        std::snprintf(report.step, sizeof(report.step), "%s", failure.step);
    }
    return report;
}

bool validate(const std::array<std::uint32_t, 16>& words) {
    for (unsigned slot = 0; slot < samples.size(); ++slot) {
        for (unsigned channel = 0; channel < 4; ++channel) {
            const float actual = std::bit_cast<float>(words[4 * slot + channel]);
            if (!std::isfinite(actual) || std::abs(actual - samples[slot].expected[channel]) > 2e-6f) return false;
        }
    }
    return true;
}
}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc != 2) return 2;
    const std::wstring_view mode(argv[1]);
    if (mode == L"--cpu-oracle") {
        std::array<std::uint32_t, 16> ideal{};
        for (unsigned slot = 0; slot < samples.size(); ++slot)
            for (unsigned channel = 0; channel < 4; ++channel)
                ideal[4 * slot + channel] = std::bit_cast<std::uint32_t>(samples[slot].expected[channel]);
        auto stale = ideal;
        stale[4] = 0;
        std::printf("typed_normalized_own_format_controls=%zu negative_cpu_control=%d\n", samples.size(), !validate(stale));
        return validate(ideal) && !validate(stale) ? 0 : 1;
    }
    if (mode == L"--worker") {
        if (!guard::worker_limits(job_limit)) return 2;
        const auto report = sample();
        DWORD bytes{};
        return WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), &report, sizeof(report), &bytes, nullptr)
            && bytes == sizeof(report) ? 0 : 2;
    }
    if (mode != L"--hardware") return 2;
    const auto result = guard::run<Report>(job_limit, true, deadline, {L"--worker"});
    std::printf("guard=%s reaped=%d job_peak=%zu exit=%lu error=%lu\n",
                result.status, result.reaped, result.job_peak, result.exit_code, result.win_error);
    if (std::string_view(result.status) != "returned" || !result.reaped || result.exit_code
        || result.job_peak == 0 || result.job_peak > job_limit) return 2;
    const auto& report = result.report;
    std::printf("adapter=NVIDIA GeForce RTX 4070 Ti SUPER precise_sample_support_mask=%u debug=%u messages=%u "
                "hresult=%08x stage=%s\n", report.feature, report.debug, report.debug_errors, report.hresult, report.step);
    if (report.status == 77) return 77;
    if (report.status != 1 || report.feature != (1u << samples.size()) - 1 || report.debug_errors) return 1;
    for (unsigned slot = 0; slot < samples.size(); ++slot) {
        std::printf("format=%u support1=%08x values=%08x %08x %08x %08x\n", static_cast<unsigned>(samples[slot].format),
                    report.sample_support[slot], report.values[4 * slot],
                    report.values[4 * slot + 1], report.values[4 * slot + 2], report.values[4 * slot + 3]);
    }
    return validate(report.values) ? 0 : 1;
}
