// SPDX-License-Identifier: GPL-3.0-or-later
// Reuse the fixed image fixture's resource setup and resident-copy helpers.
#define wmain portable_full_image_proof_entry
#include "native-upload.cpp"
#undef wmain

#include <array>
#include <chrono>

namespace {
constexpr unsigned pairs = 12;
constexpr unsigned per_case_queries = (pairs + 1) * 4;

struct Case {
    const char* name;
    unsigned bytes;
    unsigned boxes;
    std::array<D3D12_BOX, 8> regions;
};

constexpr Case cases[]{
#include "timing-cases.inc"
};

struct TimingReport {
    Report status;
    UINT64 frequency{};
    std::array<std::array<UINT64, per_case_queries>, std::size(cases)> ticks{};
    std::array<unsigned, std::size(cases)> matched_bytes{};
};

constexpr bool valid_cases() {
    for (const auto& shape : cases) {
        if (shape.boxes == 0 || shape.boxes > shape.regions.size()) return false;
        unsigned bytes{};
        for (unsigned i = 0; i < shape.boxes; ++i) {
            const auto& r = shape.regions[i];
            if (r.left >= r.right || r.top >= r.bottom || r.right > width || r.bottom > height
                || r.front != 0 || r.back != 1) return false;
            bytes += 4 * (r.right - r.left) * (r.bottom - r.top);
            for (unsigned j = 0; j < i; ++j) {
                const auto& other = shape.regions[j];
                if (r.left < other.right && other.left < r.right &&
                    r.top < other.bottom && other.top < r.bottom) return false;
            }
        }
        if (bytes != shape.bytes || bytes >= full_bytes) return false;
    }
    return true;
}
static_assert(valid_cases());

bool changed_pixel(const Case& shape, unsigned x, unsigned y) {
    for (unsigned r = 0; r < shape.boxes; ++r) {
        const auto& box = shape.regions[r];
        if (box.left <= x && x < box.right && box.top <= y && y < box.bottom) return true;
    }
    return false;
}

void update_staging(ID3D12Resource& buffer, unsigned pitch, const Case& shape) {
    fill(buffer, pitch, false);
    const D3D12_RANGE no_read{0, 0};
    void* map{};
    check(buffer.Map(0, &no_read, &map), "Map staged update");
    auto* data = static_cast<std::uint8_t*>(map);
    for (unsigned i = 0; i < shape.boxes; ++i) {
        const auto& r = shape.regions[i];
        for (unsigned y = r.top; y < r.bottom; ++y) {
            for (unsigned x = r.left; x < r.right; ++x) {
                for (unsigned c = 0; c < 4; ++c) data[y * pitch + x * 4 + c] = old_byte(x, y, c) ^ 0xffu;
            }
        }
    }
    buffer.Unmap(0, nullptr);
}

unsigned verify_case(ID3D12Resource& whole, ID3D12Resource& subregion, unsigned pitch, const Case& shape) {
    void *a{}, *b{};
    const D3D12_RANGE read{0, (height - 1) * pitch + width * 4};
    check(whole.Map(0, &read, &a), "Map full texture");
    check(subregion.Map(0, &read, &b), "Map regional texture");
    const auto* stock = static_cast<const std::uint8_t*>(a);
    const auto* candidate = static_cast<const std::uint8_t*>(b);
    unsigned compared{};
    for (unsigned y = 0; y < height; ++y) {
        for (unsigned x = 0; x < width; ++x) {
            const bool changed = changed_pixel(shape, x, y);
            for (unsigned c = 0; c < 4; ++c) {
                const auto old = old_byte(x, y, c);
                const unsigned expected = changed ? old ^ 0xffu : old;
                const auto index = y * pitch + x * 4 + c;
                compared += stock[index] == expected && candidate[index] == expected;
            }
        }
    }
    const D3D12_RANGE no_write{0, 0};
    whole.Unmap(0, &no_write);
    subregion.Unmap(0, &no_write);
    return compared;
}

void restore_destination(ID3D12GraphicsCommandList& list, ID3D12Resource* resource) {
    D3D12_RESOURCE_BARRIER barrier{};
    barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    barrier.Transition = {resource, D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,
                          D3D12_RESOURCE_STATE_COPY_SOURCE, D3D12_RESOURCE_STATE_COPY_DEST};
    list.ResourceBarrier(1, &barrier);
}

TimingReport run_timing() {
    TimingReport result;
    auto& status = result.status;
    try {
        auto adapter = select_adapter();
        ComPtr<ID3D12Device> device;
        check(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_12_0, IID_PPV_ARGS(&device)), "Create device");
        const auto desc = description(D3D12_RESOURCE_DIMENSION_TEXTURE2D, width, height);
        D3D12_PLACED_SUBRESOURCE_FOOTPRINT fp{};
        UINT64 bytes{};
        device->GetCopyableFootprints(&desc, 0, 1, 0, &fp, nullptr, nullptr, &bytes);
        if (fp.Offset || fp.Footprint.Width != width || fp.Footprint.Height != height ||
            fp.Footprint.Depth != 1 || fp.Footprint.Format != format ||
            fp.Footprint.RowPitch != width * 4 || bytes != full_bytes)
            throw Failure{E_FAIL, "unexpected copy footprint"};
        auto buf = description(D3D12_RESOURCE_DIMENSION_BUFFER, bytes, 1);
        auto old = create(*device.Get(), buf, D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        auto new_data = create(*device.Get(), buf, D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        auto full = create(*device.Get(), desc, D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_COPY_DEST);
        auto parts = create(*device.Get(), desc, D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_COPY_DEST);
        auto full_read = create(*device.Get(), buf, D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        auto parts_read = create(*device.Get(), buf, D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        constexpr auto tick_bytes = per_case_queries * sizeof(UINT64);
        const auto query_buffer = description(D3D12_RESOURCE_DIMENSION_BUFFER, tick_bytes, 1);
        auto ticks = create(*device.Get(), query_buffer, D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        ComPtr<ID3D12QueryHeap> queries;
        const D3D12_QUERY_HEAP_DESC query_spec{D3D12_QUERY_HEAP_TYPE_TIMESTAMP, per_case_queries, 0};
        check(device->CreateQueryHeap(&query_spec, IID_PPV_ARGS(&queries)), "Create timestamp heap");

        ComPtr<ID3D12CommandQueue> queue;
        const D3D12_COMMAND_QUEUE_DESC queue_desc{D3D12_COMMAND_LIST_TYPE_DIRECT, 0, D3D12_COMMAND_QUEUE_FLAG_NONE, 0};
        check(device->CreateCommandQueue(&queue_desc, IID_PPV_ARGS(&queue)), "Create queue");
        check(queue->GetTimestampFrequency(&result.frequency), "Read queue frequency");
        if (!result.frequency) throw Failure{E_FAIL, "zero queue clock frequency"};
        ComPtr<ID3D12CommandAllocator> allocator;
        check(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, IID_PPV_ARGS(&allocator)), "Create allocator");
        ComPtr<ID3D12GraphicsCommandList> list;
        check(device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, allocator.Get(), nullptr,
                                        IID_PPV_ARGS(&list)), "Create list");
        ComPtr<ID3D12Fence> fence;
        check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence)), "Create fence");
        guard::Handle event{CreateEventW(nullptr, FALSE, FALSE, nullptr)};
        if (!event) throw Failure{HRESULT_FROM_WIN32(GetLastError()), "Create event"};
        fill(*old.Get(), fp.Footprint.RowPitch, false);

        const auto reset = [&] {
            check(allocator->Reset(), "Reset allocator");
            check(list->Reset(allocator.Get(), nullptr), "Reset list");
        };
        for (unsigned index = 0; index < std::size(cases); ++index) {
            const auto& shape = cases[index];
            if (index) {
                reset();
                restore_destination(*list.Get(), full.Get());
                restore_destination(*list.Get(), parts.Get());
            }
            update_staging(*new_data.Get(), fp.Footprint.RowPitch, shape);
            upload(*list.Get(), full.Get(), old.Get(), fp, nullptr);
            upload(*list.Get(), parts.Get(), old.Get(), fp, nullptr);
            finish(*queue.Get(), *list.Get(), *fence.Get(), event.value, 2 * index + 1);
            reset();

            UINT query = 0;
            for (unsigned pair = 0; pair <= pairs; ++pair) {
                for (unsigned arm = 0; arm < 2; ++arm) {
                    const bool regional = ((pair + arm + index) & 1) != 0;
                    list->EndQuery(queries.Get(), D3D12_QUERY_TYPE_TIMESTAMP, query++);
                    if (regional) {
                        for (unsigned i = 0; i < shape.boxes; ++i)
                            upload(*list.Get(), parts.Get(), new_data.Get(), fp, &shape.regions[i]);
                    } else {
                        upload(*list.Get(), full.Get(), new_data.Get(), fp, nullptr);
                    }
                    list->EndQuery(queries.Get(), D3D12_QUERY_TYPE_TIMESTAMP, query++);
                }
            }
            if (query != per_case_queries) throw Failure{E_FAIL, "not all timestamp queries were recorded"};
            list->ResolveQueryData(queries.Get(), D3D12_QUERY_TYPE_TIMESTAMP, 0, query, ticks.Get(), 0);
            readback(*list.Get(), full.Get(), full_read.Get(), fp);
            readback(*list.Get(), parts.Get(), parts_read.Get(), fp);
            finish(*queue.Get(), *list.Get(), *fence.Get(), event.value, 2 * index + 2);
            check(device->GetDeviceRemovedReason(), "Check device");
            result.matched_bytes[index] = verify_case(*full_read.Get(), *parts_read.Get(), fp.Footprint.RowPitch, shape);
            if (result.matched_bytes[index] != full_bytes)
                throw Failure{E_FAIL, "whole image readback mismatch"};

            const D3D12_RANGE read{0, tick_bytes}, no_write{0, 0};
            void* map{};
            check(ticks->Map(0, &read, &map), "Map timestamps");
            std::memcpy(result.ticks[index].data(), map, tick_bytes);
            ticks->Unmap(0, &no_write);
        }
        status.completed = 1;
    } catch (const Failure& failure) {
        status.hresult = static_cast<unsigned>(failure.code);
        std::snprintf(status.step, sizeof(status.step), "%s", failure.step);
    }
    return result;
}
}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc != 2) return 2;
    const std::wstring_view mode(argv[1]);
    if (mode == L"--timestamp-worker") {
        if (!guard::worker_limits(memory_limit)) return 2;
        const auto result = run_timing();
        DWORD bytes{};
        return WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), &result, sizeof(result), &bytes, nullptr)
            && bytes == sizeof(result) ? 0 : 2;
    }
    if (mode != L"--hardware-timing") return 2;
    const auto result = guard::run<TimingReport>(memory_limit, true, deadline, {L"--timestamp-worker"});
    std::printf("guard=%s reaped=%d peak_job=%zu exit=%lu error=%lu\n",
                result.status, result.reaped, result.job_peak, result.exit_code, result.win_error);
    if (std::string_view(result.status) != "returned" || !result.reaped || result.exit_code ||
        result.job_peak == 0 || result.job_peak > memory_limit) return 2;
    const auto& report = result.report;
    std::printf("status=%u result=%08x step=%s frequency=%llu\n", report.status.completed,
                report.status.hresult, report.status.step,
                static_cast<unsigned long long>(report.frequency));
    if (!report.status.completed) return 1;
    std::printf("case,pair,order,boxes,regional_bytes,full_ticks,region_ticks,matched_bytes\n");
    for (unsigned index = 0; index < std::size(cases); ++index) {
        for (unsigned pair = 0; pair <= pairs; ++pair) {
            const auto& row = report.ticks[index];
            const auto at = pair * 4;
            if (!row[at] || row[at] >= row[at + 1] || row[at + 1] > row[at + 2] ||
                row[at + 2] >= row[at + 3]) return 1;
            const auto first = row[at + 1] - row[at];
            const auto second = row[at + 3] - row[at + 2];
            const bool regional_first = ((pair + index) & 1) != 0;
            std::printf("%s,%u,%s,%u,%u,%llu,%llu,%u\n", cases[index].name, pair,
                        regional_first ? "RF" : "FR", cases[index].boxes, cases[index].bytes,
                        static_cast<unsigned long long>(regional_first ? second : first),
                        static_cast<unsigned long long>(regional_first ? first : second),
                        report.matched_bytes[index]);
        }
    }
    return 0;
}
