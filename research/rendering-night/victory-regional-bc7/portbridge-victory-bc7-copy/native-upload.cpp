// SPDX-License-Identifier: GPL-3.0-or-later
// BC7 direct-copy control adapted from the PortBridge RGBA8 upload probe.
#include "guard.h"

#include <d3d12.h>
#include <d3d12sdklayers.h>
#include <dxgi1_6.h>
#include <wrl/client.h>
#include <array>
#include <cstdio>
#include <cstring>

namespace {
using Microsoft::WRL::ComPtr;
#include "copy-case.inc"

constexpr auto memory_limit = 512 * guard::mib;
constexpr auto deadline = std::chrono::milliseconds(3000);
constexpr auto expected_adapter = L"NVIDIA GeForce RTX 4070 Ti SUPER";
constexpr auto format = DXGI_FORMAT_BC7_UNORM;
constexpr unsigned block_side = 4, block_bytes = 16;
constexpr unsigned subresources = array_size * mip_levels;
constexpr unsigned full_bytes = width / block_side * (height / block_side) * block_bytes;
constexpr unsigned partial_bytes = (dirty_region.right - dirty_region.left) / block_side *
                                   ((dirty_region.bottom - dirty_region.top) / block_side) * block_bytes;
constexpr unsigned payload_bytes = array_size * (full_bytes + full_bytes / 4);
static_assert(width == 1024 && height == 1024 && array_size == 2 && mip_levels == 2 && target == 2);
static_assert(full_bytes == 1048576 && partial_bytes == 65536 && payload_bytes == 2621440);
static_assert(dirty_region.front == 0 && dirty_region.back == 1 &&
              dirty_region.left < dirty_region.right && dirty_region.top < dirty_region.bottom &&
              dirty_region.right < width && dirty_region.bottom < height &&
              (dirty_region.left | dirty_region.top | dirty_region.right | dirty_region.bottom) % 16 == 0);

using Block = std::array<std::uint8_t, block_bytes>;
using Footprints = std::array<D3D12_PLACED_SUBRESOURCE_FOOTPRINT, subresources>;

struct Report {
    unsigned completed{}, debug{}, debug_errors{}, hresult{}, checked_bytes{}, changed_blocks{};
    unsigned untouched_blocks{}, wrong_words{}, luid_low{}, luid_high{};
    std::uint64_t driver{};
    char step[64]{};
};

struct Failure {
    HRESULT code;
    const char* step;
};

void check(HRESULT code, const char* step) {
    if (FAILED(code)) throw Failure{code, step};
}

ComPtr<IDXGIAdapter1> select_adapter(Report& report) {
    ComPtr<IDXGIFactory4> factory;
    check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)), "CreateDXGIFactory1");
    ComPtr<IDXGIAdapter1> selected;
    for (UINT i = 0; i < 64; ++i) {
        ComPtr<IDXGIAdapter1> adapter;
        const auto status = factory->EnumAdapters1(i, &adapter);
        if (status == DXGI_ERROR_NOT_FOUND) break;
        check(status, "EnumAdapters1");
        DXGI_ADAPTER_DESC1 desc{};
        check(adapter->GetDesc1(&desc), "GetDesc1");
        if (desc.VendorId != 0x10de || desc.DeviceId != 0x2705 ||
            (desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) ||
            std::wstring_view(desc.Description) != expected_adapter) continue;
        if (selected) throw Failure{E_FAIL, "RTX adapter identity ambiguous"};
        LARGE_INTEGER version{};
        check(adapter->CheckInterfaceSupport(__uuidof(IDXGIDevice), &version), "Get adapter driver");
        report.driver = static_cast<std::uint64_t>(version.QuadPart);
        report.luid_low = desc.AdapterLuid.LowPart;
        report.luid_high = static_cast<unsigned>(desc.AdapterLuid.HighPart);
        selected = adapter;
    }
    if (!selected) throw Failure{DXGI_ERROR_NOT_FOUND, "RTX adapter identity mismatch"};
    return selected;
}

D3D12_RESOURCE_DESC description(D3D12_RESOURCE_DIMENSION dimension, UINT64 resource_width) {
    D3D12_RESOURCE_DESC out{};
    out.Dimension = dimension;
    out.Width = resource_width;
    out.SampleDesc.Count = 1;
    if (dimension == D3D12_RESOURCE_DIMENSION_BUFFER) {
        out.Height = 1;
        out.DepthOrArraySize = 1;
        out.MipLevels = 1;
        out.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    } else {
        out.Height = height;
        out.DepthOrArraySize = array_size;
        out.MipLevels = mip_levels;
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

std::array<unsigned, 2> mip_extent(unsigned index) {
    const auto mip = index % mip_levels;
    return {width >> mip, height >> mip};
}

UINT64 footprints_for(ID3D12Device& device, const D3D12_RESOURCE_DESC& desc, Footprints& footprints) {
    UINT64 total{};
    std::array<UINT, subresources> rows{};
    std::array<UINT64, subresources> row_bytes{};
    device.GetCopyableFootprints(&desc, 0, subresources, 0, footprints.data(),
                                 rows.data(), row_bytes.data(), &total);
    UINT64 used{};
    for (unsigned i = 0; i < subresources; ++i) {
        const auto [tx, ty] = mip_extent(i);
        const auto& placed = footprints[i];
        const auto& f = placed.Footprint;
        const auto row_payload = tx / block_side * block_bytes;
        if (placed.Offset < used || placed.Offset % D3D12_TEXTURE_DATA_PLACEMENT_ALIGNMENT ||
            f.Width != tx || f.Height != ty || f.Depth != 1 || f.Format != format ||
            rows[i] != ty / block_side || row_bytes[i] != row_payload ||
            f.RowPitch != row_payload || f.RowPitch % D3D12_TEXTURE_DATA_PITCH_ALIGNMENT)
            throw Failure{E_FAIL, "unexpected BC7 copy footprint"};
        used = placed.Offset + UINT64(rows[i]) * f.RowPitch;
    }
    if (used != total || total != payload_bytes) throw Failure{E_FAIL, "unexpected BC7 total"};
    return total;
}

void upload(ID3D12GraphicsCommandList& list, ID3D12Resource* texture, ID3D12Resource* source,
            const Footprints& footprints, unsigned index, const D3D12_BOX* box = nullptr) {
    D3D12_TEXTURE_COPY_LOCATION to{}, from{};
    to.pResource = texture;
    to.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    to.SubresourceIndex = index;
    from.pResource = source;
    from.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
    from.PlacedFootprint = footprints[index];
    list.CopyTextureRegion(&to, box ? box->left : 0, box ? box->top : 0, 0, &from, box);
}

void readback(ID3D12GraphicsCommandList& list, ID3D12Resource* texture, ID3D12Resource* buffer,
              const Footprints& footprints) {
    D3D12_RESOURCE_BARRIER barrier{};
    barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    barrier.Transition = {texture, D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,
                          D3D12_RESOURCE_STATE_COPY_DEST, D3D12_RESOURCE_STATE_COPY_SOURCE};
    list.ResourceBarrier(1, &barrier);
    for (unsigned i = 0; i < subresources; ++i) {
        D3D12_TEXTURE_COPY_LOCATION to{}, from{};
        to.pResource = buffer;
        to.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
        to.PlacedFootprint = footprints[i];
        from.pResource = texture;
        from.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
        from.SubresourceIndex = i;
        list.CopyTextureRegion(&to, 0, 0, 0, &from, nullptr);
    }
}

bool dirty(unsigned index, unsigned x, unsigned y) {
    return index == target && dirty_region.left <= x * block_side && x * block_side < dirty_region.right &&
           dirty_region.top <= y * block_side && y * block_side < dirty_region.bottom;
}

Block mode6(unsigned index, unsigned x, unsigned y, bool replacement) {
    // Prefix selects mode 6. Its eight endpoint components have seven bits
    // each. Both P bits and the complete index stream are zero.
    Block block{};
    block[0] = 0x40;
    unsigned bit = 7;
    const std::array<unsigned, 4> channels = {
        x * 29u + y * 7u + index * 13u,
        y * 31u + x * 17u + index * 23u,
        (x ^ y) * 19u + index * 41u,
        127u,
    };
    const std::array<unsigned, 4> alternate = {0x45, 0x32, 0x69, 0};
    for (unsigned c = 0; c < channels.size(); ++c) {
        const auto value = channels[c] ^ (replacement ? alternate[c] : 0);
        for (unsigned endpoint = 0; endpoint < 2; ++endpoint) {
            for (unsigned b = 0; b < 7; ++b, ++bit) {
                block[bit / 8] |= static_cast<std::uint8_t>(((value >> b) & 1u) << (bit % 8));
            }
        }
    }
    return block;
}

std::size_t at(const Footprints& footprints, unsigned index, unsigned x, unsigned y) {
    const auto& f = footprints[index];
    return static_cast<std::size_t>(f.Offset) + y * f.Footprint.RowPitch + x * block_bytes;
}

enum class Contents { initial, full_reference, distinct_regional_source };

void fill(ID3D12Resource& buffer, const Footprints& footprints, Contents contents) {
    void* map{};
    const D3D12_RANGE no_read{0, 0};
    check(buffer.Map(0, &no_read, &map), "Map upload");
    auto* data = static_cast<std::uint8_t*>(map);
    for (unsigned i = 0; i < subresources; ++i) {
        const auto [tx, ty] = mip_extent(i);
        for (unsigned y = 0; y < ty / block_side; ++y) {
            for (unsigned x = 0; x < tx / block_side; ++x) {
                const auto replacement = contents == Contents::distinct_regional_source ||
                    (contents == Contents::full_reference && dirty(i, x, y));
                const auto block = mode6(i, x, y, replacement);
                std::memcpy(data + at(footprints, i, x, y), block.data(), block.size());
            }
        }
    }
    buffer.Unmap(0, nullptr);
}

void finish(ID3D12CommandQueue& queue, ID3D12GraphicsCommandList& list,
            ID3D12Fence& fence, HANDLE event, UINT64 value) {
    check(list.Close(), "Close command list");
    ID3D12CommandList* lists[]{&list};
    queue.ExecuteCommandLists(1, lists);
    if (FAILED(queue.Signal(&fence, value)) || FAILED(fence.SetEventOnCompletion(value, event)))
        ExitProcess(123);
    if (WaitForSingleObject(event, 700) != WAIT_OBJECT_0)
        ExitProcess(124);
}

void verify(Report& report, ID3D12Resource& whole, ID3D12Resource& partial,
            const Footprints& footprints) {
    const D3D12_RANGE read{0, payload_bytes};
    void *whole_map{}, *partial_map{};
    check(whole.Map(0, &read, &whole_map), "Map full readback");
    check(partial.Map(0, &read, &partial_map), "Map partial readback");
    const auto* baseline = static_cast<const std::uint8_t*>(whole_map);
    const auto* candidate = static_cast<const std::uint8_t*>(partial_map);
    for (unsigned i = 0; i < subresources; ++i) {
        const auto [tx, ty] = mip_extent(i);
        for (unsigned y = 0; y < ty / block_side; ++y) {
            for (unsigned x = 0; x < tx / block_side; ++x) {
                const auto offset = at(footprints, i, x, y);
                const auto old = mode6(i, x, y, false);
                const bool changed = dirty(i, x, y);
                const auto expected = changed ? mode6(i, x, y, true) : old;
                const auto actual_changed = std::memcmp(candidate + offset, old.data(), block_bytes) != 0;
                report.changed_blocks += actual_changed;
                report.untouched_blocks += !changed && !actual_changed;
                report.checked_bytes += block_bytes;
                for (unsigned word = 0; word < block_bytes; word += 4) {
                    report.wrong_words +=
                        std::memcmp(baseline + offset + word, expected.data() + word, 4) != 0 ||
                        std::memcmp(candidate + offset + word, expected.data() + word, 4) != 0;
                }
            }
        }
    }
    const D3D12_RANGE no_write{0, 0};
    whole.Unmap(0, &no_write);
    partial.Unmap(0, &no_write);
}

bool source_patterns() {
    unsigned expected_changes{};
    const auto valid = [](const Block& block) {
        return (block[0] & 0x7f) == 0x40 && !(block[7] & 0x80) &&
            std::all_of(block.begin() + 8, block.end(), [](auto byte) { return byte == 0; });
    };
    for (unsigned i = 0; i < subresources; ++i) {
        const auto [tx, ty] = mip_extent(i);
        for (unsigned y = 0; y < ty / block_side; ++y) {
            for (unsigned x = 0; x < tx / block_side; ++x) {
                const auto old = mode6(i, x, y, false);
                const auto replacement = mode6(i, x, y, true);
                if (!valid(old) || !valid(replacement) || old == replacement)
                    return false;
                expected_changes += dirty(i, x, y);
            }
        }
    }
    return expected_changes == partial_bytes / block_bytes;
}

Report run() {
    Report report;
    try {
        ComPtr<ID3D12Debug> debug;
        if (SUCCEEDED(D3D12GetDebugInterface(IID_PPV_ARGS(&debug)))) {
            debug->EnableDebugLayer();
            report.debug = 1;
        }
        auto adapter = select_adapter(report);
        ComPtr<ID3D12Device> device;
        check(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_12_0, IID_PPV_ARGS(&device)), "Create device");
        const auto luid = device->GetAdapterLuid();
        if (luid.LowPart != report.luid_low || static_cast<unsigned>(luid.HighPart) != report.luid_high)
            throw Failure{E_FAIL, "Opened device's LUID differs"};
        D3D12_FEATURE_DATA_FORMAT_SUPPORT support{};
        support.Format = format;
        check(device->CheckFeatureSupport(D3D12_FEATURE_FORMAT_SUPPORT, &support, sizeof(support)), "Check BC7 support");
        if (!(support.Support1 & D3D12_FORMAT_SUPPORT1_TEXTURE2D))
            throw Failure{DXGI_ERROR_UNSUPPORTED, "BC7 Texture2D unsupported"};
        const auto desc = description(D3D12_RESOURCE_DIMENSION_TEXTURE2D, width);
        Footprints footprints{};
        const auto size = footprints_for(*device.Get(), desc, footprints);
        const auto buffer = description(D3D12_RESOURCE_DIMENSION_BUFFER, size);
        auto initial = create(*device.Get(), buffer, D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        auto updated = create(*device.Get(), buffer, D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        auto patch = create(*device.Get(), buffer, D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        auto whole = create(*device.Get(), desc, D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_COPY_DEST);
        auto region = create(*device.Get(), desc, D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_COPY_DEST);
        auto whole_read = create(*device.Get(), buffer, D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        auto region_read = create(*device.Get(), buffer, D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        fill(*initial.Get(), footprints, Contents::initial);
        fill(*updated.Get(), footprints, Contents::full_reference);
        fill(*patch.Get(), footprints, Contents::distinct_regional_source);

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
        for (unsigned i = 0; i < subresources; ++i) {
            upload(*list.Get(), whole.Get(), initial.Get(), footprints, i);
            upload(*list.Get(), region.Get(), initial.Get(), footprints, i);
        }
        finish(*queue.Get(), *list.Get(), *fence.Get(), event.value, 1);
        check(device->GetDeviceRemovedReason(), "Check after initial copies");
        check(allocator->Reset(), "Reset allocator");
        check(list->Reset(allocator.Get(), nullptr), "Reset list");
        upload(*list.Get(), whole.Get(), updated.Get(), footprints, target);
        upload(*list.Get(), region.Get(), patch.Get(), footprints, target, &dirty_region);
        readback(*list.Get(), whole.Get(), whole_read.Get(), footprints);
        readback(*list.Get(), region.Get(), region_read.Get(), footprints);
        finish(*queue.Get(), *list.Get(), *fence.Get(), event.value, 2);
        check(device->GetDeviceRemovedReason(), "Check after readback");
        verify(report, *whole_read.Get(), *region_read.Get(), footprints);

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
    if (mode == L"--cpu") {
        if (!source_patterns()) return 1;
        std::puts("BC7 mode-6 patterns and dirty block count passed");
        return 0;
    }
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
    std::printf("adapter=RTX 4070 Ti SUPER luid=%08x:%08x driver=%016llx completed=%u debug=%u warnings_or_errors=%u result=%08x step=%s\n",
                r.luid_high, r.luid_low, static_cast<unsigned long long>(r.driver), r.completed,
                r.debug, r.debug_errors, r.hresult, r.step);
    std::printf("subresources=%u target=%u update_bytes=%u/%u checked_bytes=%u changed_blocks=%u untouched_blocks=%u wrong_words=%u\n",
                subresources, target, full_bytes, partial_bytes, r.checked_bytes, r.changed_blocks,
                r.untouched_blocks, r.wrong_words);
    return r.completed && !r.debug_errors && !r.wrong_words && r.checked_bytes == payload_bytes &&
           r.changed_blocks == partial_bytes / block_bytes &&
           r.untouched_blocks == (payload_bytes - partial_bytes) / block_bytes ? 0 : 1;
}
