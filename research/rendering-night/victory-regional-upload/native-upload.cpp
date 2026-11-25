// SPDX-License-Identifier: GPL-3.0-or-later
#include "guard.h"

#include <d3d12.h>
#include <d3d12sdklayers.h>
#include <dxgi1_6.h>
#include <wrl/client.h>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {
using Microsoft::WRL::ComPtr;
#include "copy-case.inc"

constexpr auto memory_limit = 512 * guard::mib;
constexpr auto deadline = std::chrono::milliseconds(3000);
constexpr auto expected_adapter = L"NVIDIA GeForce RTX 4070 Ti SUPER";
constexpr auto format = DXGI_FORMAT_R8G8B8A8_UNORM;
constexpr unsigned full_bytes = width * height * 4;
constexpr unsigned partial_bytes =
    (dirty_region.right - dirty_region.left) * (dirty_region.bottom - dirty_region.top) * 4;
static_assert(full_bytes == 1048576 && partial_bytes == 65536);
static_assert(dirty_region.front == 0 && dirty_region.back == 1 &&
              dirty_region.right <= width && dirty_region.bottom <= height);

struct Report {
    unsigned completed{}, debug{}, debug_errors{}, hresult{}, checked{}, modified{}, mismatches{};
    char step[64]{};
};

struct Failure {
    HRESULT code;
    const char* step;
};

void check(HRESULT code, const char* step) {
    if (FAILED(code)) throw Failure{code, step};
}

ComPtr<IDXGIAdapter1> select_adapter() {
    ComPtr<IDXGIFactory4> factory;
    check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)), "CreateDXGIFactory1");
    for (UINT i = 0; ; ++i) {
        ComPtr<IDXGIAdapter1> adapter;
        const auto status = factory->EnumAdapters1(i, &adapter);
        if (status == DXGI_ERROR_NOT_FOUND) break;
        check(status, "EnumAdapters1");
        DXGI_ADAPTER_DESC1 desc{};
        check(adapter->GetDesc1(&desc), "GetDesc1");
        if (desc.VendorId == 0x10de && desc.DeviceId == 0x2705 &&
            !(desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) &&
            std::wstring_view(desc.Description) == expected_adapter) return adapter;
    }
    throw Failure{DXGI_ERROR_NOT_FOUND, "RTX adapter identity mismatch"};
}

D3D12_RESOURCE_DESC description(D3D12_RESOURCE_DIMENSION dimension, UINT64 resource_width,
                                UINT resource_height) {
    D3D12_RESOURCE_DESC out{};
    out.Dimension = dimension;
    out.Width = resource_width;
    out.Height = resource_height;
    out.DepthOrArraySize = 1;
    out.MipLevels = 1;
    out.SampleDesc.Count = 1;
    if (dimension == D3D12_RESOURCE_DIMENSION_BUFFER) {
        out.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    } else {
        out.Format = format;
    }
    return out;
}

ComPtr<ID3D12Resource> create(ID3D12Device& device, const D3D12_RESOURCE_DESC& desc,
                             D3D12_HEAP_TYPE type, D3D12_RESOURCE_STATES state) {
    D3D12_HEAP_PROPERTIES heap{};
    heap.Type = type;
    heap.CreationNodeMask = heap.VisibleNodeMask = 1;
    ComPtr<ID3D12Resource> resource;
    check(device.CreateCommittedResource(&heap, D3D12_HEAP_FLAG_NONE, &desc, state,
                                         nullptr, IID_PPV_ARGS(&resource)), "CreateCommittedResource");
    return resource;
}

void upload(ID3D12GraphicsCommandList& list, ID3D12Resource* texture, ID3D12Resource* source,
            const D3D12_PLACED_SUBRESOURCE_FOOTPRINT& footprint, const D3D12_BOX* region) {
    D3D12_TEXTURE_COPY_LOCATION to{}, from{};
    to.pResource = texture;
    to.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    from.pResource = source;
    from.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
    from.PlacedFootprint = footprint;
    list.CopyTextureRegion(&to, region ? region->left : 0, region ? region->top : 0, 0, &from, region);
}

void readback(ID3D12GraphicsCommandList& list, ID3D12Resource* texture, ID3D12Resource* buffer,
              const D3D12_PLACED_SUBRESOURCE_FOOTPRINT& footprint) {
    D3D12_RESOURCE_BARRIER barrier{};
    barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    barrier.Transition = {texture, D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,
                          D3D12_RESOURCE_STATE_COPY_DEST, D3D12_RESOURCE_STATE_COPY_SOURCE};
    list.ResourceBarrier(1, &barrier);
    D3D12_TEXTURE_COPY_LOCATION to{}, from{};
    to.pResource = buffer;
    to.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
    to.PlacedFootprint = footprint;
    from.pResource = texture;
    from.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    list.CopyTextureRegion(&to, 0, 0, 0, &from, nullptr);
}

bool dirty(unsigned x, unsigned y) {
    return dirty_region.left <= x && x < dirty_region.right &&
           dirty_region.top <= y && y < dirty_region.bottom;
}

std::uint8_t old_byte(unsigned x, unsigned y, unsigned channel) {
    return static_cast<std::uint8_t>(x * 71u + y * 29u + channel * 113u + (x ^ (y >> 2)));
}

void fill(ID3D12Resource& buffer, unsigned pitch, bool changed) {
    void* map{};
    const D3D12_RANGE no_read{0, 0};
    check(buffer.Map(0, &no_read, &map), "Map upload");
    auto* data = static_cast<std::uint8_t*>(map);
    for (unsigned y = 0; y < height; ++y) {
        for (unsigned x = 0; x < width; ++x) {
            for (unsigned c = 0; c < 4; ++c) {
                const auto old = old_byte(x, y, c);
                data[y * pitch + x * 4 + c] = changed && dirty(x, y) ? old ^ 0xffu : old;
            }
        }
    }
    buffer.Unmap(0, nullptr);
}

void finish(ID3D12CommandQueue& queue, ID3D12GraphicsCommandList& list, ID3D12Fence& fence,
            HANDLE event, UINT64 value) {
    check(list.Close(), "Close command list");
    ID3D12CommandList* lists[]{&list};
    queue.ExecuteCommandLists(1, lists);
    check(queue.Signal(&fence, value), "Signal fence");
    check(fence.SetEventOnCompletion(value, event), "SetEventOnCompletion");
    if (WaitForSingleObject(event, 700) != WAIT_OBJECT_0)
        throw Failure{HRESULT_FROM_WIN32(ERROR_TIMEOUT), "Wait for copy"};
}

void verify(Report& report, ID3D12Resource& full, ID3D12Resource& partial, unsigned pitch) {
    const D3D12_RANGE read{0, (height - 1) * pitch + width * 4};
    void *full_bytes_map{}, *partial_bytes_map{};
    check(full.Map(0, &read, &full_bytes_map), "Map full readback");
    check(partial.Map(0, &read, &partial_bytes_map), "Map partial readback");
    const auto* baseline = static_cast<const std::uint8_t*>(full_bytes_map);
    const auto* candidate = static_cast<const std::uint8_t*>(partial_bytes_map);
    for (unsigned y = 0; y < height; ++y) {
        for (unsigned x = 0; x < width; ++x) {
            for (unsigned c = 0; c < 4; ++c) {
                const auto at = y * pitch + x * 4 + c;
                const auto old = old_byte(x, y, c);
                const auto expected = dirty(x, y) ? old ^ 0xffu : old;
                report.checked += 1;
                report.modified += candidate[at] != old;
                report.mismatches += baseline[at] != expected || candidate[at] != expected;
            }
        }
    }
    const D3D12_RANGE no_write{0, 0};
    full.Unmap(0, &no_write);
    partial.Unmap(0, &no_write);
}

Report run() {
    Report report;
    try {
        ComPtr<ID3D12Debug> debug;
        if (SUCCEEDED(D3D12GetDebugInterface(IID_PPV_ARGS(&debug)))) {
            debug->EnableDebugLayer();
            report.debug = 1;
        }
        auto adapter = select_adapter();
        ComPtr<ID3D12Device> device;
        check(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_12_0, IID_PPV_ARGS(&device)), "Create device");
        const auto desc = description(D3D12_RESOURCE_DIMENSION_TEXTURE2D, width, height);
        D3D12_PLACED_SUBRESOURCE_FOOTPRINT footprint{};
        UINT64 staging_bytes{};
        device->GetCopyableFootprints(&desc, 0, 1, 0, &footprint, nullptr, nullptr, &staging_bytes);
        if (footprint.Offset || footprint.Footprint.Width != width || footprint.Footprint.Height != height
            || footprint.Footprint.Depth != 1 || footprint.Footprint.Format != format
            || footprint.Footprint.RowPitch != width * 4 || staging_bytes != full_bytes)
            throw Failure{E_FAIL, "unexpected copy footprint"};

        const auto buffer = description(D3D12_RESOURCE_DIMENSION_BUFFER, staging_bytes, 1);
        auto initial = create(*device.Get(), buffer, D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        auto updated = create(*device.Get(), buffer, D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        auto whole = create(*device.Get(), desc, D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_COPY_DEST);
        auto region = create(*device.Get(), desc, D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_COPY_DEST);
        auto whole_read = create(*device.Get(), buffer, D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        auto region_read = create(*device.Get(), buffer, D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        fill(*initial.Get(), footprint.Footprint.RowPitch, false);
        fill(*updated.Get(), footprint.Footprint.RowPitch, true);

        ComPtr<ID3D12CommandQueue> queue;
        const D3D12_COMMAND_QUEUE_DESC queue_desc{D3D12_COMMAND_LIST_TYPE_DIRECT, 0, D3D12_COMMAND_QUEUE_FLAG_NONE, 0};
        check(device->CreateCommandQueue(&queue_desc, IID_PPV_ARGS(&queue)), "Create queue");
        ComPtr<ID3D12CommandAllocator> allocator;
        check(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, IID_PPV_ARGS(&allocator)), "Create allocator");
        ComPtr<ID3D12GraphicsCommandList> list;
        check(device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, allocator.Get(), nullptr,
                                        IID_PPV_ARGS(&list)), "Create list");
        ComPtr<ID3D12Fence> fence;
        check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence)), "Create fence");
        guard::Handle event{CreateEventW(nullptr, FALSE, FALSE, nullptr)};
        if (!event) throw Failure{HRESULT_FROM_WIN32(GetLastError()), "Create event"};

        upload(*list.Get(), whole.Get(), initial.Get(), footprint, nullptr);
        upload(*list.Get(), region.Get(), initial.Get(), footprint, nullptr);
        finish(*queue.Get(), *list.Get(), *fence.Get(), event.value, 1);
        check(allocator->Reset(), "Reset allocator");
        check(list->Reset(allocator.Get(), nullptr), "Reset list");
        upload(*list.Get(), whole.Get(), updated.Get(), footprint, nullptr);
        upload(*list.Get(), region.Get(), updated.Get(), footprint, &dirty_region);
        readback(*list.Get(), whole.Get(), whole_read.Get(), footprint);
        readback(*list.Get(), region.Get(), region_read.Get(), footprint);
        finish(*queue.Get(), *list.Get(), *fence.Get(), event.value, 2);
        check(device->GetDeviceRemovedReason(), "Check device");
        verify(report, *whole_read.Get(), *region_read.Get(), footprint.Footprint.RowPitch);

        ComPtr<ID3D12InfoQueue> info;
        if (report.debug && SUCCEEDED(device.As(&info))) {
            for (UINT64 i = 0; i < info->GetNumStoredMessages(); ++i) {
                SIZE_T bytes = 0;
                check(info->GetMessage(i, nullptr, &bytes), "D3D12 message size");
                std::vector<std::uint8_t> store(bytes);
                auto* message = reinterpret_cast<D3D12_MESSAGE*>(store.data());
                check(info->GetMessage(i, message, &bytes), "D3D12 message");
                report.debug_errors += message->Severity <= D3D12_MESSAGE_SEVERITY_WARNING;
            }
        }
        report.completed = 1;
    } catch (const Failure& failure) {
        report.hresult = static_cast<unsigned>(failure.code);
        std::snprintf(report.step, sizeof(report.step), "%s", failure.step);
    }
    return report;
}
}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc != 2) return 2;
    const std::wstring_view mode(argv[1]);
    if (mode == L"--worker") {
        if (!guard::worker_limits(memory_limit)) return 2;
        const auto report = run();
        DWORD bytes{};
        return WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), &report, sizeof(report), &bytes, nullptr)
            && bytes == sizeof(report) ? 0 : 2;
    }
    if (mode != L"--hardware") return 2;
    const auto result = guard::run<Report>(memory_limit, true, deadline, {L"--worker"});
    std::printf("guard=%s reaped=%d peak_job=%zu exit=%lu error=%lu\n",
                result.status, result.reaped, result.job_peak, result.exit_code, result.win_error);
    if (std::string_view(result.status) != "returned" || !result.reaped || result.exit_code ||
        result.job_peak == 0 || result.job_peak > memory_limit) return 2;
    const auto& r = result.report;
    std::printf("adapter=RTX 4070 Ti SUPER completed=%u debug=%u warnings_or_errors=%u result=%08x step=%s\n",
                r.completed, r.debug, r.debug_errors, r.hresult, r.step);
    std::printf("update_bytes=%u/%u checked_bytes=%u changed_bytes=%u mismatches=%u\n",
                full_bytes, partial_bytes, r.checked, r.modified, r.mismatches);
    return r.completed && !r.debug_errors && !r.mismatches &&
           r.checked == full_bytes && r.modified == partial_bytes ? 0 : 1;
}
