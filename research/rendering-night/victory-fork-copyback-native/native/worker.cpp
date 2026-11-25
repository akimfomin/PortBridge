// SPDX-License-Identifier: GPL-3.0-or-later
#include "guard.h"
#include <d3d12.h>
#include <dxgi1_6.h>
#include <wrl/client.h>
#include <array>
#include <cstdio>
#include <cstring>

namespace {
using Microsoft::WRL::ComPtr;
constexpr auto memory_limit = 512 * guard::mib;
constexpr auto deadline = std::chrono::milliseconds(3000);
constexpr unsigned pairs = 8;
constexpr unsigned source_bytes = 2 * 1024 * 1024;
constexpr unsigned margin = 256;
constexpr unsigned window = 1024 * 1024 + 2 * margin;
constexpr std::uint8_t sentinel = 0xc7;

struct Copy { unsigned from, bytes, dest; };
struct Case {
    const char* name;
    unsigned stock_count, packed_count, stock_bytes, packed_bytes;
    Copy stock[16], packed[16];
    unsigned logical_dest[16];
};
constexpr Case cases[]{
#include "relay-cases.inc"
};
constexpr unsigned case_count = std::size(cases);
constexpr unsigned samples = case_count * (pairs + 1) * 2;
constexpr unsigned total_bytes = samples * window;

constexpr bool valid() {
    for (const auto& shape : cases) {
        if (!shape.stock_count || shape.stock_count > 16 || !shape.packed_count || shape.packed_count > 16)
            return false;
        for (unsigned arm = 0; arm < 2; ++arm) {
            const auto* plan = arm ? shape.packed : shape.stock;
            const auto count = arm ? shape.packed_count : shape.stock_count;
            const auto total = arm ? shape.packed_bytes : shape.stock_bytes;
            unsigned end{};
            for (unsigned i = 0; i < count; ++i) {
                const auto [from, bytes, dest] = plan[i];
                if (!bytes || from > source_bytes || bytes > source_bytes - from || dest != end) return false;
                end += bytes;
            }
            if (end != total || total > window - 2 * margin) return false;
        }
        for (unsigned i = 0; i < shape.stock_count; ++i) {
            const auto piece = shape.stock[i];
            const auto at = shape.logical_dest[i];
            bool matched = false;
            for (unsigned j = 0; j < shape.packed_count; ++j) {
                const auto copy = shape.packed[j];
                if (at >= copy.dest && at - copy.dest <= copy.bytes && piece.bytes <= copy.bytes - (at - copy.dest) &&
                    piece.from == copy.from + (at - copy.dest)) matched = true;
            }
            if (!matched) return false;
        }
    }
    return true;
}
static_assert(case_count == 3 && valid());

struct Report {
    unsigned ok{}, code{}, validated_windows{};
    char step[96]{};
    UINT64 frequency{};
    std::uint64_t checked_bytes{};
    std::array<std::uint64_t, samples> cpu_ns{};
    std::array<UINT64, 2 * samples> ticks{};
};
struct Failure { HRESULT code; const char* step; };
void check(HRESULT code, const char* step) { if (FAILED(code)) throw Failure{code, step}; }

ComPtr<IDXGIAdapter1> adapter() {
    ComPtr<IDXGIFactory4> factory;
    check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)), "Create DXGI factory");
    for (UINT index = 0; ; ++index) {
        ComPtr<IDXGIAdapter1> candidate;
        const auto result = factory->EnumAdapters1(index, &candidate);
        if (result == DXGI_ERROR_NOT_FOUND) break;
        check(result, "Enumerate adapter");
        DXGI_ADAPTER_DESC1 desc{};
        check(candidate->GetDesc1(&desc), "Read adapter identity");
        if (desc.VendorId == 0x10de && desc.DeviceId == 0x2705 && !(desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) &&
            std::wstring_view(desc.Description) == L"NVIDIA GeForce RTX 4070 Ti SUPER") return candidate;
    }
    throw Failure{DXGI_ERROR_NOT_FOUND, "RTX adapter identity mismatch"};
}

ComPtr<ID3D12Resource> buffer(ID3D12Device& device, UINT64 size, D3D12_HEAP_TYPE type, D3D12_RESOURCE_STATES state) {
    D3D12_HEAP_PROPERTIES heap{};
    heap.Type = type;
    heap.CreationNodeMask = heap.VisibleNodeMask = 1;
    D3D12_RESOURCE_DESC desc{};
    desc.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
    desc.Width = size;
    desc.Height = desc.DepthOrArraySize = desc.MipLevels = desc.SampleDesc.Count = 1;
    desc.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    ComPtr<ID3D12Resource> value;
    check(device.CreateCommittedResource(&heap, D3D12_HEAP_FLAG_NONE, &desc, state, nullptr,
                                         IID_PPV_ARGS(&value)), "Allocate buffer");
    return value;
}

void write(ID3D12Resource& upload, const std::uint8_t* data, std::size_t count) {
    void* mapping{};
    const D3D12_RANGE no_read{0, 0}, written{0, count};
    check(upload.Map(0, &no_read, &mapping), "Map upload");
    std::memcpy(mapping, data, count);
    upload.Unmap(0, &written);
}

const std::uint8_t* read(ID3D12Resource& buffer, std::size_t count) {
    void* mapping{};
    const D3D12_RANGE bytes{0, count};
    check(buffer.Map(0, &bytes, &mapping), "Map readback");
    return static_cast<const std::uint8_t*>(mapping);
}

unsigned pair_order(unsigned shape, unsigned pair, bool reverse) { return (pair + shape + reverse) & 1; }
unsigned slot(unsigned shape, unsigned pair, unsigned arm, bool reverse) {
    // Independent destination crossover and command execution crossover.
    return (shape * (pairs + 1) + pair) * 2 + (arm ^ ((pair / 2 + shape + reverse) & 1));
}

Report trial(bool reverse) {
    Report result;
    try {
        if (!guard::headroom(4096 * guard::mib, 6144 * guard::mib))
            throw Failure{E_OUTOFMEMORY, "Worker admission before device"};
        auto gpu = adapter();
        ComPtr<ID3D12Device> device;
        check(D3D12CreateDevice(gpu.Get(), D3D_FEATURE_LEVEL_12_0, IID_PPV_ARGS(&device)), "Create device");
        std::vector<std::uint8_t> source(source_bytes), blank(window, sentinel);
        std::uint32_t rng = reverse ? 0x0238d194 : 0xbd5d3dd0;
        for (auto& byte : source) {
            rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
            byte = static_cast<std::uint8_t>(rng >> 16);
        }
        auto data = buffer(*device.Get(), source_bytes, D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_COPY_DEST);
        auto init = buffer(*device.Get(), source_bytes, D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        auto reset = buffer(*device.Get(), window, D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        auto output = buffer(*device.Get(), total_bytes, D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        auto ticks = buffer(*device.Get(), sizeof(result.ticks), D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        write(*init.Get(), source.data(), source.size());
        write(*reset.Get(), blank.data(), blank.size());

        ComPtr<ID3D12CommandQueue> queue;
        const D3D12_COMMAND_QUEUE_DESC qdesc{D3D12_COMMAND_LIST_TYPE_DIRECT, 0, D3D12_COMMAND_QUEUE_FLAG_NONE, 0};
        check(device->CreateCommandQueue(&qdesc, IID_PPV_ARGS(&queue)), "Create DIRECT queue");
        check(queue->GetTimestampFrequency(&result.frequency), "Read timestamp frequency");
        if (!result.frequency) throw Failure{E_FAIL, "Invalid timestamp frequency"};
        ComPtr<ID3D12QueryHeap> queries;
        const D3D12_QUERY_HEAP_DESC qspec{D3D12_QUERY_HEAP_TYPE_TIMESTAMP, 2 * samples, 0};
        check(device->CreateQueryHeap(&qspec, IID_PPV_ARGS(&queries)), "Create timestamp heap");
        ComPtr<ID3D12CommandAllocator> allocator;
        check(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, IID_PPV_ARGS(&allocator)), "Create allocator");
        ComPtr<ID3D12GraphicsCommandList> list;
        check(device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, allocator.Get(), nullptr,
                                         IID_PPV_ARGS(&list)), "Create command list");
        ComPtr<ID3D12Fence> fence;
        check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence)), "Create fence");
        guard::Handle completion(CreateEventW(nullptr, FALSE, FALSE, nullptr));
        if (!completion) throw Failure{HRESULT_FROM_WIN32(GetLastError()), "Create fence event"};

        list->CopyBufferRegion(data.Get(), 0, init.Get(), 0, source_bytes);
        D3D12_RESOURCE_BARRIER ready{};
        ready.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        ready.Transition = {data.Get(), D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,
                            D3D12_RESOURCE_STATE_COPY_DEST, D3D12_RESOURCE_STATE_COPY_SOURCE};
        list->ResourceBarrier(1, &ready);
        for (unsigned i = 0; i < samples; ++i)
            list->CopyBufferRegion(output.Get(), UINT64(i) * window, reset.Get(), 0, window);

        for (unsigned order = 0; order < case_count; ++order) {
            const unsigned shape = reverse ? case_count - 1 - order : order;
            const auto& plan = cases[shape];
            for (unsigned pair = 0; pair <= pairs; ++pair) {
                for (unsigned step = 0; step < 2; ++step) {
                    const auto arm = step ^ pair_order(shape, pair, reverse);
                    const auto index = slot(shape, pair, arm, reverse);
                    const auto base = UINT64(index) * window + margin;
                    const auto count = arm ? plan.packed_count : plan.stock_count;
                    const auto* copies = arm ? plan.packed : plan.stock;
                    list->EndQuery(queries.Get(), D3D12_QUERY_TYPE_TIMESTAMP, index * 2);
                    const auto started = std::chrono::steady_clock::now();
                    for (unsigned k = 0; k < count; ++k) {
                        const auto [from, bytes, dest] = copies[k];
                        list->CopyBufferRegion(output.Get(), base + dest, data.Get(), from, bytes);
                    }
                    result.cpu_ns[index] = std::chrono::duration_cast<std::chrono::nanoseconds>(
                        std::chrono::steady_clock::now() - started).count();
                    list->EndQuery(queries.Get(), D3D12_QUERY_TYPE_TIMESTAMP, index * 2 + 1);
                }
            }
        }
        list->ResolveQueryData(queries.Get(), D3D12_QUERY_TYPE_TIMESTAMP, 0, 2 * samples, ticks.Get(), 0);
        check(list->Close(), "Close command list");
        ID3D12CommandList* lists[]{list.Get()};
        queue->ExecuteCommandLists(1, lists);
        check(queue->Signal(fence.Get(), 1), "Signal fence");
        check(fence->SetEventOnCompletion(1, completion.value), "Register fence event");
        if (WaitForSingleObject(completion.value, 1700) != WAIT_OBJECT_0 || fence->GetCompletedValue() != 1)
            throw Failure{E_FAIL, "Unproven timestamp fence completion"};
        check(device->GetDeviceRemovedReason(), "Device status after readback");

        const D3D12_RANGE no_write{0, 0};
        std::memcpy(result.ticks.data(), read(*ticks.Get(), sizeof(result.ticks)), sizeof(result.ticks));
        ticks->Unmap(0, &no_write);
        UINT64 last_tick{};
        for (unsigned order = 0; order < case_count; ++order) {
            const unsigned shape = reverse ? case_count - 1 - order : order;
            for (unsigned pair = 0; pair <= pairs; ++pair) {
                for (unsigned step = 0; step < 2; ++step) {
                    const auto arm = step ^ pair_order(shape, pair, reverse);
                    const auto index = slot(shape, pair, arm, reverse);
                    const auto start = result.ticks[index * 2], end = result.ticks[index * 2 + 1];
                    if (!start || start < last_tick || end <= start)
                        throw Failure{E_FAIL, "Invalid timestamp interval or schedule"};
                    last_tick = end;
                }
            }
        }
        const auto* actual = read(*output.Get(), total_bytes);
        for (unsigned shape = 0; shape < case_count; ++shape) {
            const auto& plan = cases[shape];
            for (unsigned pair = 0; pair <= pairs; ++pair) {
                for (unsigned arm = 0; arm < 2; ++arm) {
                    const auto index = slot(shape, pair, arm, reverse);
                    const auto p = actual + index * window;
                    const auto payload = arm ? plan.packed_bytes : plan.stock_bytes;
                    const auto untouched = [](const std::uint8_t* a, const std::uint8_t* b) {
                        return std::all_of(a, b, [](std::uint8_t v) { return v == sentinel; });
                    };
                    if (!untouched(p, p + margin) || !untouched(p + margin + payload, p + window))
                        throw Failure{E_FAIL, "Unexpected write outside payload"};
                    for (unsigned i = 0; i < plan.stock_count; ++i) {
                        const auto expected = plan.stock[i];
                        const auto dest = arm ? plan.logical_dest[i] : expected.dest;
                        if (std::memcmp(p + margin + dest, source.data() + expected.from, expected.bytes))
                            throw Failure{E_FAIL, "Logical readback differs"};
                    }
                    ++result.validated_windows;
                    result.checked_bytes += window;
                }
            }
        }
        output->Unmap(0, &no_write);
        result.ok = 1;
    } catch (const Failure& e) {
        result.code = static_cast<unsigned>(e.code);
        std::snprintf(result.step, sizeof(result.step), "%s", e.step);
    }
    return result;
}
}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc != 2) return 2;
    const std::wstring_view mode(argv[1]);
    if (mode == L"--cpu") {
        std::printf("source-only cases=%u windows=%u bytes=%u\n", case_count, samples, total_bytes);
        return 0;
    }
    if (mode == L"--worker-a" || mode == L"--worker-b") {
        if (!guard::worker_limits(memory_limit)) return 2;
        const auto result = trial(mode == L"--worker-b");
        DWORD bytes{};
        return WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), &result, sizeof(result), &bytes, nullptr) &&
               bytes == sizeof(result) ? 0 : 2;
    }
    if (mode != L"--hardware-a" && mode != L"--hardware-b") return 2;
    const bool reverse = mode == L"--hardware-b";
    const auto result = guard::run<Report>(memory_limit, true, deadline,
                                           {reverse ? L"--worker-b" : L"--worker-a"});
    std::printf("guard=%s reaped=%d peak_job=%zu exit=%lu error=%lu\n",
                result.status, result.reaped, result.job_peak, result.exit_code, result.win_error);
    if (std::string_view(result.status) != "returned" || !result.reaped || result.exit_code ||
        !result.job_peak || result.job_peak > memory_limit) return 2;
    const auto& r = result.report;
    std::printf("status=%u code=%08x step=%s polarity=%c frequency=%llu windows=%u checked_bytes=%llu\n",
                r.ok, r.code, r.step, reverse ? 'b' : 'a', static_cast<unsigned long long>(r.frequency),
                r.validated_windows, static_cast<unsigned long long>(r.checked_bytes));
    if (!r.ok || r.validated_windows != samples || r.checked_bytes != total_bytes) return 1;
    std::puts("case,pair,order,stock_slot,packed_slot,stock_commands,packed_commands,stock_bytes,packed_bytes,stock_cpu_ns,packed_cpu_ns,stock_gpu_ticks,packed_gpu_ticks");
    for (unsigned shape = 0; shape < case_count; ++shape) {
        const auto& plan = cases[shape];
        for (unsigned pair = 0; pair <= pairs; ++pair) {
            const auto a = slot(shape, pair, 0, reverse), b = slot(shape, pair, 1, reverse);
            std::printf("%s,%u,%s,%u,%u,%u,%u,%u,%u,%llu,%llu,%llu,%llu\n", plan.name, pair,
                        pair_order(shape, pair, reverse) ? "PS" : "SP", a, b, plan.stock_count,
                        plan.packed_count, plan.stock_bytes, plan.packed_bytes,
                        static_cast<unsigned long long>(r.cpu_ns[a]), static_cast<unsigned long long>(r.cpu_ns[b]),
                        static_cast<unsigned long long>(r.ticks[2 * a + 1] - r.ticks[2 * a]),
                        static_cast<unsigned long long>(r.ticks[2 * b + 1] - r.ticks[2 * b]));
        }
    }
    return 0;
}
