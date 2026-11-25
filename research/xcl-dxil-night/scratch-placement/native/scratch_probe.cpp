// SPDX-License-Identifier: MIT
#include "guard.h"

#include <d3d12.h>
#include <d3d12sdklayers.h>
#include <dxgi1_6.h>
#include <wrl/client.h>

#include <array>
#include <cstdio>
#include <cstdlib>
#include <limits>

namespace {
using Microsoft::WRL::ComPtr;

constexpr UINT resource_count = 16;
constexpr UINT64 buffer_bytes = D3D12_DEFAULT_RESOURCE_PLACEMENT_ALIGNMENT;
constexpr UINT64 total_bytes = resource_count * buffer_bytes;
constexpr unsigned pairs = 4;
constexpr auto worker_limit = 512 * guard::mib;
constexpr auto worker_timeout = std::chrono::milliseconds(3000);
constexpr auto adapter_name = L"NVIDIA GeForce RTX 4070 Ti SUPER";
static_assert(total_bytes == 1048576);

struct Sample {
    std::int64_t heap_ticks{}, resource_ticks{};
    unsigned trial{}, placed{}, created{}, checked_bytes{}, mismatches{};
    unsigned first_bad_word{}, actual_word{}, expected_word{};
};

struct Report {
    std::array<Sample, pairs * 2> samples{};
    std::int64_t qpc_frequency{};
    UINT64 allocation_size{}, allocation_alignment{};
    unsigned started{}, complete{}, debug{}, debug_status{}, diagnostics{}, first_debug_id{}, hresult{};
    char failure[72]{};
};

struct Failure {
    HRESULT code;
    const char* step;
};

void check(HRESULT result, const char* step) {
    if (FAILED(result)) throw Failure{result, step};
}

void require(bool ok, const char* step) {
    if (!ok) throw Failure{E_FAIL, step};
}

bool send_report(const Report& report) {
    DWORD wrote{};
    return WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), &report, sizeof(report), &wrote, nullptr)
        && wrote == sizeof(report);
}

void set_failure(Report& report, Failure failure) {
    report.hresult = static_cast<unsigned>(failure.code);
    std::snprintf(report.failure, sizeof(report.failure), "%s", failure.step);
}

[[noreturn]] void abandon_submitted_work(Report& report, Failure failure) {
    // No proven fence means releasing any of the submitted resources is unsafe.
    // This is the isolated child; preserve its report and let the OS reclaim its handles.
    set_failure(report, failure);
    const auto status = send_report(report) ? 0 : 2;
    TerminateProcess(GetCurrentProcess(), status);
    std::abort();
}

std::int64_t ticks() {
    LARGE_INTEGER sample{};
    require(QueryPerformanceCounter(&sample) != FALSE, "QueryPerformanceCounter");
    return sample.QuadPart;
}

ComPtr<IDXGIAdapter1> select_adapter() {
    ComPtr<IDXGIFactory4> factory;
    check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)), "CreateDXGIFactory1");
    for (UINT index = 0; ; ++index) {
        ComPtr<IDXGIAdapter1> adapter;
        const auto result = factory->EnumAdapters1(index, &adapter);
        if (result == DXGI_ERROR_NOT_FOUND) throw Failure{result, "hardware adapter mismatch"};
        check(result, "EnumAdapters1");
        DXGI_ADAPTER_DESC1 desc{};
        check(adapter->GetDesc1(&desc), "GetDesc1");
        if (desc.VendorId == 0x10de && desc.DeviceId == 0x2705 && !(desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE)
            && std::wstring_view(desc.Description) == adapter_name) return adapter;
    }
}

D3D12_RESOURCE_DESC buffer_desc(UINT64 bytes, D3D12_RESOURCE_FLAGS flags) {
    D3D12_RESOURCE_DESC desc{};
    desc.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
    desc.Width = bytes;
    desc.Height = desc.DepthOrArraySize = desc.MipLevels = desc.SampleDesc.Count = 1;
    desc.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    desc.Flags = flags;
    return desc;
}

D3D12_HEAP_PROPERTIES heap_props(D3D12_HEAP_TYPE type) {
    D3D12_HEAP_PROPERTIES props{};
    props.Type = type;
    props.CreationNodeMask = props.VisibleNodeMask = 1;
    return props;
}

ComPtr<ID3D12Resource> staging_buffer(ID3D12Device& device, D3D12_HEAP_TYPE type, D3D12_RESOURCE_STATES state) {
    auto props = heap_props(type);
    auto desc = buffer_desc(total_bytes, D3D12_RESOURCE_FLAG_NONE);
    ComPtr<ID3D12Resource> buffer;
    check(device.CreateCommittedResource(&props, D3D12_HEAP_FLAG_NONE, &desc, state, nullptr,
                                         IID_PPV_ARGS(&buffer)), "Create staging buffer");
    return buffer;
}

// Odd multipliers make each source word unique within a trial. The trial term changes every word.
std::uint32_t payload(UINT word, unsigned trial) {
    return (word * 0x9E37'79B1u) ^ (trial * 0x85EB'CA77u + 0x4D21'36F9u);
}

void fill_upload(ID3D12Resource& upload, unsigned trial) {
    void* pointer{};
    const D3D12_RANGE no_reads{0, 0};
    check(upload.Map(0, &no_reads, &pointer), "Map upload");
    auto* words = static_cast<std::uint32_t*>(pointer);
    for (UINT i = 0; i < total_bytes / sizeof(*words); ++i) words[i] = payload(i, trial);
    const D3D12_RANGE wrote{0, total_bytes};
    upload.Unmap(0, &wrote);
}

void verify_readback(ID3D12Resource& readback, Sample& sample) {
    const D3D12_RANGE reads{0, total_bytes};
    void* pointer{};
    check(readback.Map(0, &reads, &pointer), "Map readback");
    const auto* words = static_cast<const std::uint32_t*>(pointer);
    for (UINT i = 0; i < total_bytes / sizeof(*words); ++i) {
        const auto expected = payload(i, sample.trial);
        if (words[i] != expected) {
            if (!sample.mismatches) {
                sample.first_bad_word = i;
                sample.actual_word = words[i];
                sample.expected_word = expected;
            }
            ++sample.mismatches;
        }
        sample.checked_bytes += sizeof(*words);
    }
    const D3D12_RANGE no_writes{0, 0};
    readback.Unmap(0, &no_writes);
    require(!sample.mismatches, "buffer readback differs");
}

using Buffers = std::array<ComPtr<ID3D12Resource>, resource_count>;

void validate_addresses(const Buffers& buffers) {
    std::array<UINT64, resource_count> addresses{};
    for (UINT i = 0; i < resource_count; ++i) {
        const auto address = buffers[i]->GetGPUVirtualAddress();
        require(address && address % D3D12_RAW_UAV_SRV_BYTE_ALIGNMENT == 0 &&
                address <= std::numeric_limits<UINT64>::max() - buffer_bytes, "invalid GPU address");
        for (UINT j = 0; j < i; ++j) {
            require(buffers[i].Get() != buffers[j].Get(), "reused resource identity");
            require(address >= addresses[j] + buffer_bytes || addresses[j] >= address + buffer_bytes,
                    "overlapping GPU addresses");
        }
        addresses[i] = address;
    }
}

// Placed resources start inactive under the simple model. Every range is disjoint and written before reading.
void record(ID3D12GraphicsCommandList& list, const Buffers& buffers,
            ID3D12Resource& upload, ID3D12Resource& readback, bool placed) {
    std::array<D3D12_RESOURCE_BARRIER, resource_count> barriers{};
    if (placed) {
        for (UINT i = 0; i < resource_count; ++i) {
            barriers[i].Type = D3D12_RESOURCE_BARRIER_TYPE_ALIASING;
            barriers[i].Aliasing = {nullptr, buffers[i].Get()};
        }
        list.ResourceBarrier(resource_count, barriers.data());
    }
    for (UINT i = 0; i < resource_count; ++i) {
        barriers[i].Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        barriers[i].Transition = {buffers[i].Get(), D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,
                                  D3D12_RESOURCE_STATE_UNORDERED_ACCESS, D3D12_RESOURCE_STATE_COPY_DEST};
    }
    list.ResourceBarrier(resource_count, barriers.data());
    for (UINT i = 0; i < resource_count; ++i) {
        list.CopyBufferRegion(buffers[i].Get(), 0, &upload, i * buffer_bytes, buffer_bytes);
        barriers[i].Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        barriers[i].Transition = {buffers[i].Get(), D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,
                                  D3D12_RESOURCE_STATE_COPY_DEST, D3D12_RESOURCE_STATE_COPY_SOURCE};
    }
    list.ResourceBarrier(resource_count, barriers.data());
    for (UINT i = 0; i < resource_count; ++i)
        list.CopyBufferRegion(&readback, i * buffer_bytes, buffers[i].Get(), 0, buffer_bytes);
}

struct Context {
    ComPtr<ID3D12CommandQueue> queue;
    ComPtr<ID3D12CommandAllocator> allocator;
    ComPtr<ID3D12GraphicsCommandList> list;
    ComPtr<ID3D12Fence> fence;
    guard::Handle event{CreateEventW(nullptr, FALSE, FALSE, nullptr)};
    UINT64 serial{};
};

void init_context(ID3D12Device& device, Context& ctx) {
    require(static_cast<bool>(ctx.event), "CreateEventW");
    const D3D12_COMMAND_QUEUE_DESC queue_desc{D3D12_COMMAND_LIST_TYPE_DIRECT, 0, D3D12_COMMAND_QUEUE_FLAG_NONE, 0};
    check(device.CreateCommandQueue(&queue_desc, IID_PPV_ARGS(&ctx.queue)), "CreateCommandQueue");
    check(device.CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, IID_PPV_ARGS(&ctx.allocator)),
          "CreateCommandAllocator");
    check(device.CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, ctx.allocator.Get(), nullptr,
                                   IID_PPV_ARGS(&ctx.list)), "CreateCommandList");
    check(ctx.list->Close(), "Close empty list");
    check(device.CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&ctx.fence)), "CreateFence");
}

void wait_for_copy(ID3D12Device& device, Context& ctx, Report& report) {
    ID3D12CommandList* lists[]{ctx.list.Get()};
    ctx.queue->ExecuteCommandLists(1, lists);
    try {
        ++ctx.serial;
        check(ctx.queue->Signal(ctx.fence.Get(), ctx.serial), "Signal GPU fence");
        check(ctx.fence->SetEventOnCompletion(ctx.serial, ctx.event.value), "Register GPU fence event");
        const auto waited = WaitForSingleObject(ctx.event.value, 700);
        if (waited != WAIT_OBJECT_0)
            throw Failure{HRESULT_FROM_WIN32(waited == WAIT_TIMEOUT ? ERROR_TIMEOUT : GetLastError()), "Wait for GPU copies"};
        check(device.GetDeviceRemovedReason(), "Check device removed reason");
        require(ctx.fence->GetCompletedValue() >= ctx.serial, "Unexpected GPU fence value");
    } catch (const Failure& failure) {
        abandon_submitted_work(report, failure);
    }
}

void check_messages(ID3D12InfoQueue* queue, Report& report) {
    if (!queue) return;
    const auto count = queue->GetNumStoredMessages();
    require(count <= 256 && queue->GetNumMessagesDiscardedByMessageCountLimit() == 0, "debug messages overflow");
    for (UINT64 i = 0; i < count; ++i) {
        SIZE_T bytes{};
        check(queue->GetMessage(i, nullptr, &bytes), "Read D3D12 debug message size");
        alignas(D3D12_MESSAGE) unsigned char storage[4096]{};
        require(bytes <= sizeof(storage), "debug message exceeds report limit");
        auto* message = reinterpret_cast<D3D12_MESSAGE*>(storage);
        check(queue->GetMessage(i, message, &bytes), "Read D3D12 debug message");
        if (message->Severity <= D3D12_MESSAGE_SEVERITY_WARNING) {
            if (!report.diagnostics) report.first_debug_id = static_cast<unsigned>(message->ID);
            ++report.diagnostics;
        }
    }
    queue->ClearStoredMessages();
    require(!report.diagnostics, "D3D12 debug diagnostics");
}

void run_arm(ID3D12Device& device, Context& ctx, ID3D12Resource& upload, ID3D12Resource& readback,
             const D3D12_RESOURCE_DESC& desc, Sample& sample, ID3D12InfoQueue* info, Report& report) {
    const auto props = heap_props(D3D12_HEAP_TYPE_DEFAULT);
    constexpr auto state = D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
    // Destruction order keeps the heap alive for every placed resource.
    ComPtr<ID3D12Heap> heap;
    Buffers buffers;
    if (sample.placed) {
        const D3D12_HEAP_DESC heap_desc{total_bytes, props, buffer_bytes, D3D12_HEAP_FLAG_ALLOW_ONLY_BUFFERS};
        const auto start = ticks();
        const auto result = device.CreateHeap(&heap_desc, IID_PPV_ARGS(&heap));
        sample.heap_ticks = ticks() - start;
        check(result, "CreateHeap");
    }
    auto result = S_OK;
    const auto start = ticks();
    for (UINT i = 0; i < resource_count; ++i) {
        if (sample.placed)
            result = device.CreatePlacedResource(heap.Get(), i * buffer_bytes, &desc, state,
                                                 nullptr, IID_PPV_ARGS(&buffers[i]));
        else
            result = device.CreateCommittedResource(&props, D3D12_HEAP_FLAG_NONE, &desc, state,
                                                    nullptr, IID_PPV_ARGS(&buffers[i]));
        if (FAILED(result)) break;
        ++sample.created;
    }
    sample.resource_ticks = ticks() - start;
    check(result, sample.placed ? "CreatePlacedResource" : "CreateCommittedResource");
    validate_addresses(buffers);
    check(ctx.allocator->Reset(), "Reset idle allocator");
    check(ctx.list->Reset(ctx.allocator.Get(), nullptr), "Reset command list");
    record(*ctx.list.Get(), buffers, upload, readback, sample.placed != 0);
    check(ctx.list->Close(), "Close copy list");
    check_messages(info, report);
    wait_for_copy(device, ctx, report);
    verify_readback(readback, sample);
    check_messages(info, report);
}

Report run(std::wstring_view mode) {
    Report report;
    try {
        LARGE_INTEGER frequency{};
        require(QueryPerformanceFrequency(&frequency) != FALSE && frequency.QuadPart > 0, "read QPC frequency");
        report.qpc_frequency = frequency.QuadPart;
        const bool verify = mode == L"verify";
        ComPtr<ID3D12Debug> debug;
        if (verify) {
            const auto result = D3D12GetDebugInterface(IID_PPV_ARGS(&debug));
            report.debug_status = static_cast<unsigned>(result);
            if (SUCCEEDED(result)) {
                debug->EnableDebugLayer();
                report.debug = 1;
            } else if (result != DXGI_ERROR_SDK_COMPONENT_MISSING && result != E_NOINTERFACE) {
                check(result, "Get D3D12 debug interface");
            }
        }
        auto adapter = select_adapter();
        ComPtr<ID3D12Device> device;
        check(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_12_0, IID_PPV_ARGS(&device)), "D3D12CreateDevice");
        ComPtr<ID3D12InfoQueue> info;
        if (report.debug) check(device.As(&info), "Get D3D12 info queue");
        const auto desc = buffer_desc(buffer_bytes, D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS);
        const auto allocation = device->GetResourceAllocationInfo(0, 1, &desc);
        report.allocation_size = allocation.SizeInBytes;
        report.allocation_alignment = allocation.Alignment;
        require(allocation.Alignment == buffer_bytes && allocation.SizeInBytes == buffer_bytes,
                "unexpected buffer allocation size or alignment");

        auto upload = staging_buffer(*device.Get(), D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        const auto output_a = staging_buffer(*device.Get(), D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        const auto output_b = staging_buffer(*device.Get(), D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        Context ctx;
        init_context(*device.Get(), ctx);
        bool placed_first = mode == L"measure-ba";
        for (unsigned trial = 1; trial <= (verify ? 1 : pairs); ++trial) {
            fill_upload(*upload.Get(), trial);
            for (const bool placed : {placed_first, !placed_first}) {
                auto& sample = report.samples[report.started++];
                sample.trial = trial;
                sample.placed = placed;
                run_arm(*device.Get(), ctx, *upload.Get(), *(placed ? output_b.Get() : output_a.Get()), desc,
                        sample, info.Get(), report);
                ++report.complete;
            }
            placed_first = !placed_first;
        }
    } catch (const Failure& failure) {
        set_failure(report, failure);
    }
    return report;
}

bool valid_mode(std::wstring_view mode) {
    return mode == L"verify" || mode == L"measure-ab" || mode == L"measure-ba";
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc == 3 && std::wstring_view(argv[1]) == L"--worker" && valid_mode(argv[2])) {
        if (!guard::worker_limits(worker_limit)) return 2;
        const auto report = run(argv[2]);
        return send_report(report) ? 0 : 2;
    }
    if (argc != 2 || !valid_mode(argv[1])) return 2;
    const auto result = guard::run<Report>(worker_limit, true, worker_timeout, {L"--worker", argv[1]});
    std::printf("guard=%s reaped=%d child_exit=%lu win_error=%lu job_peak_bytes=%zu\n", result.status,
                result.reaped, result.exit_code, result.win_error, result.job_peak);
    if (std::string_view(result.status) != "returned" || !result.reaped || result.exit_code) return 2;
    const auto& r = result.report;
    std::printf("mode=%ls adapter=%ls debug=%u debug_status=%08x diagnostics=%u first_debug_id=%u "
                "hresult=%08x failure=%s complete=%u started=%u qpc_hz=%lld size=%llu alignment=%llu\n",
                argv[1], adapter_name, r.debug, r.debug_status, r.diagnostics, r.first_debug_id,
                r.hresult, r.failure, r.complete, r.started, static_cast<long long>(r.qpc_frequency),
                static_cast<unsigned long long>(r.allocation_size), static_cast<unsigned long long>(r.allocation_alignment));
    if (r.started > r.samples.size()) return 2;
    std::puts("trial,arm,create_heap_ticks,create_buffers_ticks,create_total_ticks,buffers_created,bytes_checked,"
              "mismatched_words,first_bad_word,actual_word,expected_word");
    for (unsigned i = 0; i < r.started; ++i) {
        const auto& s = r.samples[i];
        std::printf("%u,%s,%lld,%lld,%lld,%u,%u,%u,%u,%08x,%08x\n", s.trial, s.placed ? "placed" : "committed",
                    static_cast<long long>(s.heap_ticks), static_cast<long long>(s.resource_ticks),
                    static_cast<long long>(s.heap_ticks + s.resource_ticks), s.created, s.checked_bytes,
                    s.mismatches, s.first_bad_word, s.actual_word, s.expected_word);
    }
    return !r.hresult && !r.diagnostics && r.complete == (std::wstring_view(argv[1]) == L"verify" ? 2 : pairs * 2) ? 0 : 1;
}
