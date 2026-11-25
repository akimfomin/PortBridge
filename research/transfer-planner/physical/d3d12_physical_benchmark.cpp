// SPDX-License-Identifier: MIT
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d12.h>
#include <d3dcompiler.h>
#include <dxgi1_4.h>

#include "planner.hpp"
#include "physical_trace.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <memory>
#include <optional>
#include <span>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;
using transfer::Range;
using transfer::Strategy;
constexpr std::size_t bytes_per_unit = 64;
constexpr transfer::Cost default_cost{8, 1};

void check(HRESULT status, const char* operation) {
    if (FAILED(status)) {
        std::ostringstream details;
        details << operation << " failed (HRESULT 0x" << std::hex << static_cast<unsigned long>(status) << ')';
        throw std::runtime_error(details.str());
    }
}

template<class T>
class Com {
public:
    Com() = default;
    Com(const Com&) = delete;
    Com& operator=(const Com&) = delete;
    ~Com() { if (pointer_) pointer_->Release(); }

    T* operator->() const { return pointer_; }
    T* get() const { return pointer_; }
    T** output() { return &pointer_; }

private:
    T* pointer_ = nullptr;
};

struct CloseEvent {
    void operator()(void* handle) const { CloseHandle(handle); }
};

struct Fixture {
    std::string name;
    uint32_t extent;
    uint32_t max_units;
    std::vector<uint32_t> dirty;
    std::vector<Range> islands;
};

std::vector<Fixture> fixtures() {
    constexpr uint32_t extent = 8192;
    std::vector<Fixture> result;
    Fixture clusters{"clustered", extent, 64, {}, {{0, extent}}};
    for (uint32_t unit = 0; unit < extent; unit += 256) {
        for (uint32_t delta = 0; delta < 31; delta += 2) clusters.dirty.push_back(unit + delta);
    }
    result.push_back(std::move(clusters));
    Fixture holes{"protected-holes", extent, 64, {}, {}};
    for (uint32_t unit = 0; unit < extent; unit += 64) {
        holes.islands.push_back({unit, unit + 31});
        holes.islands.push_back({unit + 33, unit + 63});
        for (uint32_t delta : {3u, 15u, 30u, 33u, 45u, 62u}) holes.dirty.push_back(unit + delta);
    }
    result.push_back(std::move(holes));
    Fixture anti_greedy{"anti-greedy-cap", extent, 64, {}, {{0, extent}}};
    for (uint32_t unit = 0; unit < extent; unit += 128) {
        for (uint32_t delta : {0u, 8u, 16u, 24u, 32u, 40u, 48u, 56u, 63u, 64u, 65u, 66u, 67u}) {
            anti_greedy.dirty.push_back(unit + delta);
        }
    }
    result.push_back(std::move(anti_greedy));
    Fixture sparse{"wide-sparse", extent, 64, {}, {{0, extent}}};
    for (uint32_t unit = 0; unit < extent; unit += 127) sparse.dirty.push_back(unit);
    result.push_back(std::move(sparse));
    Fixture dense{"dense", extent, 64, {}, {{0, extent}}};
    for (uint32_t unit = 0; unit < extent; ++unit) dense.dirty.push_back(unit);
    result.push_back(std::move(dense));
    return result;
}

struct Bytes {
    std::vector<uint8_t> initial;
    std::vector<uint8_t> source;
    std::vector<uint8_t> expected;
};

Bytes make_bytes(const Fixture& fixture) {
    const std::size_t size = fixture.extent * bytes_per_unit;
    Bytes bytes{std::vector<uint8_t>(size), std::vector<uint8_t>(size), std::vector<uint8_t>(size)};
    std::vector<bool> dirty(fixture.extent);
    std::vector<bool> authoritative(fixture.extent);
    for (auto unit : fixture.dirty) dirty.at(unit) = true;
    for (auto range : fixture.islands) {
        for (uint32_t unit = range.begin; unit < range.end; ++unit) authoritative.at(unit) = true;
    }
    for (std::size_t index = 0; index < size; ++index) {
        const auto unit = index / bytes_per_unit;
        const auto initial = static_cast<uint8_t>(unit * 131 + index * 17 + 3);
        bytes.initial[index] = initial;
        bytes.expected[index] = dirty[unit] ? initial ^ 0xa5 : initial;
        bytes.source[index] = authoritative[unit] ? bytes.expected[index] : initial ^ 0x5a;
    }
    return bytes;
}

std::string utf8(const wchar_t* name) {
    const int size = WideCharToMultiByte(CP_UTF8, 0, name, -1, nullptr, 0, nullptr, nullptr);
    if (size <= 0) throw std::runtime_error("could not encode the DXGI adapter name");
    std::string result(static_cast<std::size_t>(size), '\0');
    if (!WideCharToMultiByte(CP_UTF8, 0, name, -1, result.data(), size, nullptr, nullptr)) {
        throw std::runtime_error("could not encode the DXGI adapter name");
    }
    result.pop_back();
    return result;
}

DXGI_ADAPTER_DESC1 select_adapter(IDXGIFactory4& factory, bool physical, Com<IDXGIAdapter1>& selected) {
    if (!physical) {
        // https://learn.microsoft.com/windows/win32/api/dxgi1_4/nf-dxgi1_4-idxgifactory4-enumwarpadapter
        check(factory.EnumWarpAdapter(IID_PPV_ARGS(selected.output())), "EnumWarpAdapter");
        DXGI_ADAPTER_DESC1 description{};
        check(selected->GetDesc1(&description), "GetDesc1");
        if (!(description.Flags & DXGI_ADAPTER_FLAG_SOFTWARE)) {
            throw std::runtime_error("EnumWarpAdapter returned an adapter without the DXGI software flag");
        }
        return description;
    }

    // Enumerate and identify the requested adapter explicitly using vendor and the exact model.
    // https://learn.microsoft.com/windows/win32/api/dxgi/nf-dxgi-idxgifactory1-enumadapters1
    DXGI_ADAPTER_DESC1 match{};
    for (UINT index = 0;; ++index) {
        Com<IDXGIAdapter1> candidate;
        const auto status = factory.EnumAdapters1(index, candidate.output());
        if (status == DXGI_ERROR_NOT_FOUND) break;
        check(status, "EnumAdapters1");
        DXGI_ADAPTER_DESC1 description{};
        check(candidate->GetDesc1(&description), "GetDesc1");
        const std::wstring_view model(description.Description);
        const bool identified = model == L"NVIDIA GeForce RTX 4070 Ti SUPER" ||
                                model == L"GeForce RTX 4070 Ti SUPER";
        if (description.VendorId != 0x10de ||
            (description.Flags & (DXGI_ADAPTER_FLAG_REMOTE | DXGI_ADAPTER_FLAG_SOFTWARE)) || !identified) continue;
        if (selected.get()) throw std::runtime_error("more than one RTX 4070 Ti SUPER is available");
        check(candidate->QueryInterface(IID_PPV_ARGS(selected.output())), "select physical DXGI adapter");
        match = description;
    }
    if (!selected.get()) throw std::runtime_error("physical NVIDIA GeForce RTX 4070 Ti SUPER not found");
    return match;
}

constexpr char consumer_shader[] = R"hlsl(
ByteAddressBuffer source_words : register(t0);
RWByteAddressBuffer output_words : register(u0);
cbuffer Parameters : register(b0) { uint word_count; uint stride; };

[numthreads(64, 1, 1)]
void main(uint3 id : SV_DispatchThreadID) {
    for (uint index = id.x; index < word_count; index += stride) {
        uint value = source_words.Load(index * 4);
        output_words.Store(index * 4, ((value ^ 0x9e3779b9u) * 0x85ebca6bu) ^ index);
    }
}
)hlsl";

class Device {
public:
    explicit Device(bool physical = false, bool consumer = false) : with_consumer(consumer) {
        Com<IDXGIFactory4> factory;
        Com<IDXGIAdapter1> adapter;
        check(CreateDXGIFactory2(0, IID_PPV_ARGS(factory.output())), "CreateDXGIFactory2");
        description = select_adapter(*factory.get(), physical, adapter);
        name = utf8(description.Description);
        check(D3D12CreateDevice(adapter.get(), D3D_FEATURE_LEVEL_11_0, IID_PPV_ARGS(device.output())),
              "D3D12CreateDevice");
        D3D12_COMMAND_QUEUE_DESC queue_description{};
        queue_description.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
        check(device->CreateCommandQueue(&queue_description, IID_PPV_ARGS(queue.output())), "CreateCommandQueue");
        check(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, IID_PPV_ARGS(allocator.output())),
              "CreateCommandAllocator");
        check(device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, allocator.get(), nullptr,
                                        IID_PPV_ARGS(list.output())), "CreateCommandList");
        check(list->Close(), "Close initial command list");
        check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(fence.output())), "CreateFence");
        event.reset(CreateEventW(nullptr, FALSE, FALSE, nullptr));
        if (!event) throw std::runtime_error("CreateEventW failed");
        // DIRECT queue timestamp support and units.
        // https://learn.microsoft.com/windows/win32/direct3d12/timing
        check(queue->GetTimestampFrequency(&frequency), "GetTimestampFrequency");
        if (!frequency) throw std::runtime_error("zero D3D12 timestamp frequency");
        D3D12_QUERY_HEAP_DESC query_description{};
        query_description.Type = D3D12_QUERY_HEAP_TYPE_TIMESTAMP;
        query_description.Count = 2;
        check(device->CreateQueryHeap(&query_description, IID_PPV_ARGS(query.output())), "CreateQueryHeap");
        buffer(timestamps, 2 * sizeof(uint64_t), D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        if (consumer) create_consumer();
    }

    void buffer(Com<ID3D12Resource>& holder, UINT64 size, D3D12_HEAP_TYPE type,
                D3D12_RESOURCE_STATES state, D3D12_RESOURCE_FLAGS flags = D3D12_RESOURCE_FLAG_NONE) {
        D3D12_HEAP_PROPERTIES heap{};
        heap.Type = type;
        heap.CreationNodeMask = 1;
        heap.VisibleNodeMask = 1;
        D3D12_RESOURCE_DESC description{};
        description.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
        description.Width = size;
        description.Height = 1;
        description.DepthOrArraySize = 1;
        description.MipLevels = 1;
        description.SampleDesc.Count = 1;
        description.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
        description.Flags = flags;
        check(device->CreateCommittedResource(&heap, D3D12_HEAP_FLAG_NONE, &description, state,
                                              nullptr, IID_PPV_ARGS(holder.output())), "CreateCommittedResource");
    }

    void record() {
        check(allocator->Reset(), "Reset command allocator");
        check(list->Reset(allocator.get(), nullptr), "Reset command list");
    }

    void submit() {
        check(list->Close(), "Close command list");
        ID3D12CommandList* commands[] = {list.get()};
        queue->ExecuteCommandLists(1, commands);
        check(queue->Signal(fence.get(), ++value), "Signal fence");
        check(fence->SetEventOnCompletion(value, event.get()), "SetEventOnCompletion");
        if (WaitForSingleObject(event.get(), 10'000) != WAIT_OBJECT_0) {
            throw std::runtime_error("D3D12 fence wait timed out or failed");
        }
        check(device->GetDeviceRemovedReason(), "GetDeviceRemovedReason");
    }

    void copy(ID3D12Resource* dst, UINT64 dst_offset, ID3D12Resource* src, UINT64 src_offset, UINT64 size) {
        list->CopyBufferRegion(dst, dst_offset, src, src_offset, size);
    }

    void consume(ID3D12Resource* target, ID3D12Resource* result, uint32_t words) {
        constexpr uint32_t lanes = 64;
        const auto groups = std::min((words + lanes - 1) / lanes, 65535u);
        const std::array<uint32_t, 2> constants{words, groups * lanes};
        // Raw, untyped buffer descriptors are supported in a root signature.
        // https://learn.microsoft.com/windows/win32/direct3d12/using-descriptors-directly-in-the-root-signature
        list->SetComputeRootSignature(root.get());
        list->SetPipelineState(pipeline.get());
        list->SetComputeRootShaderResourceView(0, target->GetGPUVirtualAddress());
        list->SetComputeRootUnorderedAccessView(1, result->GetGPUVirtualAddress());
        list->SetComputeRoot32BitConstants(2, static_cast<UINT>(constants.size()), constants.data(), 0);
        list->Dispatch(groups, 1, 1);
    }

    void transition(ID3D12Resource* resource, D3D12_RESOURCE_STATES before, D3D12_RESOURCE_STATES after) {
        // Buffers may decay to COMMON between submissions; each explicit transition follows
        // a copy in the same list which promotes the buffer to the stated prior usage.
        // https://learn.microsoft.com/windows/win32/direct3d12/using-resource-barriers-to-synchronize-resource-states-in-direct3d-12
        D3D12_RESOURCE_BARRIER barrier{};
        barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        barrier.Transition.pResource = resource;
        barrier.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        barrier.Transition.StateBefore = before;
        barrier.Transition.StateAfter = after;
        list->ResourceBarrier(1, &barrier);
    }

    void timestamp(UINT index) { list->EndQuery(query.get(), D3D12_QUERY_TYPE_TIMESTAMP, index); }

    void resolve_timestamps() {
        list->ResolveQueryData(query.get(), D3D12_QUERY_TYPE_TIMESTAMP, 0, 2, timestamps.get(), 0);
    }

    double timestamp_us() {
        // Readback Map is not a synchronization point. submit() has waited for the fence.
        // https://learn.microsoft.com/windows/win32/direct3d12/readback-data-using-heaps
        const D3D12_RANGE extent{0, 2 * sizeof(uint64_t)};
        void* mapped = nullptr;
        check(timestamps->Map(0, &extent, &mapped), "Map timestamps");
        std::array<uint64_t, 2> ticks{};
        std::memcpy(ticks.data(), mapped, sizeof(ticks));
        const D3D12_RANGE no_writes{0, 0};
        timestamps->Unmap(0, &no_writes);
        if (ticks[1] < ticks[0]) throw std::runtime_error("nonmonotonic D3D12 timestamps");
        return double(ticks[1] - ticks[0]) * 1e6 / double(frequency);
    }

    std::string name;
    DXGI_ADAPTER_DESC1 description{};
    const bool with_consumer;
    UINT64 frequency = 0;

private:
    void create_consumer() {
        D3D12_ROOT_PARAMETER bindings[3]{};
        bindings[0].ParameterType = D3D12_ROOT_PARAMETER_TYPE_SRV;
        bindings[1].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
        bindings[2].ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
        bindings[2].Constants.Num32BitValues = 2;
        D3D12_ROOT_SIGNATURE_DESC layout{};
        layout.NumParameters = 3;
        layout.pParameters = bindings;
        Com<ID3DBlob> serialized, vs_error;
        check(D3D12SerializeRootSignature(&layout, D3D_ROOT_SIGNATURE_VERSION_1, serialized.output(),
                                          vs_error.output()), "D3D12SerializeRootSignature");
        check(device->CreateRootSignature(0, serialized->GetBufferPointer(), serialized->GetBufferSize(),
                                          IID_PPV_ARGS(root.output())), "CreateRootSignature");
        Com<ID3DBlob> binary, error;
        // https://learn.microsoft.com/windows/win32/api/d3dcompiler/nf-d3dcompiler-d3dcompile
        const auto status = D3DCompile(consumer_shader, sizeof(consumer_shader) - 1, "transfer-consumer",
                                       nullptr, nullptr, "main", "cs_5_1",
                                       D3DCOMPILE_ENABLE_STRICTNESS | D3DCOMPILE_OPTIMIZATION_LEVEL3, 0,
                                       binary.output(), error.output());
        if (FAILED(status) && error.get()) {
            throw std::runtime_error("D3DCompile: " + std::string(
                static_cast<const char*>(error->GetBufferPointer()), error->GetBufferSize()));
        }
        check(status, "D3DCompile");
        D3D12_COMPUTE_PIPELINE_STATE_DESC description{};
        description.pRootSignature = root.get();
        description.CS = {binary->GetBufferPointer(), binary->GetBufferSize()};
        check(device->CreateComputePipelineState(&description, IID_PPV_ARGS(pipeline.output())),
              "CreateComputePipelineState");
    }

    Com<ID3D12Device> device;
    Com<ID3D12CommandQueue> queue;
    Com<ID3D12CommandAllocator> allocator;
    Com<ID3D12GraphicsCommandList> list;
    Com<ID3D12Fence> fence;
    Com<ID3D12QueryHeap> query;
    Com<ID3D12Resource> timestamps;
    Com<ID3D12RootSignature> root;
    Com<ID3D12PipelineState> pipeline;
    std::unique_ptr<void, CloseEvent> event;
    UINT64 value = 0;
};

struct Sample {
    double chain_us;
    double planning_us;
    double stage_us;
    double api_us;
    double timestamp_us;
    std::size_t ranges;
    std::size_t units;
};

double elapsed(Clock::time_point a, Clock::time_point b) {
    return std::chrono::duration<double, std::micro>(b - a).count();
}

class Trial {
public:
    Trial(Device& backend, const Fixture& fixture, transfer::Cost cost = default_cost)
        : warp_(backend), fixture_(fixture), cost_(cost), bytes_(make_bytes(fixture)), dirty_(fixture.dirty) {
        const auto size = bytes_.initial.size();
        warp_.buffer(initial_, size, D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        warp_.buffer(upload_, size, D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
        warp_.buffer(destination_, size, D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_COPY_DEST);
        warp_.buffer(readback_, size, D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
        if (warp_.with_consumer) {
            warp_.buffer(consumed_, size, D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_COMMON,
                         D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS);
            warp_.buffer(consumed_readback_, size, D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
            expected_consumed_.resize(size / sizeof(uint32_t));
            update_expected_consumed({0, fixture.extent});
        }
        const D3D12_RANGE no_reads{0, 0};
        void* mapped = nullptr;
        check(initial_->Map(0, &no_reads, &mapped), "Map reset upload");
        std::memcpy(mapped, bytes_.initial.data(), size);
        const D3D12_RANGE all_bytes{0, size};
        initial_->Unmap(0, &all_bytes);
        check(upload_->Map(0, &no_reads, &mapped), "Map benchmark upload");
        mapped_upload_ = static_cast<uint8_t*>(mapped);
    }

    ~Trial() {
        if (mapped_upload_) upload_->Unmap(0, nullptr);
    }

    void set_epoch(std::span<const uint32_t> dirty_atoms) {
        auto write = [this](uint32_t atom, bool modified) {
            const auto start = atom * bytes_per_unit;
            for (auto offset = start; offset < start + bytes_per_unit; ++offset) {
                const auto origin = bytes_.initial[offset];
                const uint8_t updated = modified ? origin ^ 0xa5 : origin;
                bytes_.source[offset] = updated;
                bytes_.expected[offset] = updated;
            }
            update_expected_consumed({atom, atom + 1});
        };
        for (uint32_t atom : dirty_) write(atom, false);
        dirty_ = dirty_atoms;
        for (uint32_t atom : dirty_) write(atom, true);
    }

    Sample run(Strategy strategy, bool use_timestamps) {
        reset();
        const auto begin = Clock::now();
        const transfer::Problem problem{fixture_.extent, fixture_.max_units, cost_,
                                        dirty_, fixture_.islands};
        const auto ranges = transfer::plan(problem, strategy);
        const auto planned = Clock::now();
        return execute(ranges, begin, planned, use_timestamps);
    }

    Sample run_fixed(std::span<const Range> ranges) {
        reset();
        const auto begin = Clock::now();
        return execute(ranges, begin, begin, false);
    }

    void test_negative_control() {
        reset();
        // Replace precisely two exact ranges with a forbidden bridge and keep every other update.
        const Range illegal{fixture_.islands.at(0).end - 1, fixture_.islands.at(1).begin + 1};
        const transfer::Problem problem{fixture_.extent, fixture_.max_units, cost_,
                                        dirty_, fixture_.islands};
        auto ranges = transfer::plan(problem, Strategy::exact);
        const auto removed = std::erase_if(ranges, [illegal](Range range) {
            return illegal.begin <= range.begin && range.end <= illegal.end;
        });
        if (removed != 2) throw std::logic_error("negative fixture must have two endpoints");
        for (const auto range : ranges) stage(range);
        stage(illegal);
        warp_.record();
        for (const auto range : ranges) copy(range);
        copy(illegal);
        prepare_readback_after_copy(true);
        warp_.submit();
        const auto first_guard_byte = fixture_.islands.at(0).end * bytes_per_unit;
        if (compare() != first_guard_byte + 1) {
            throw std::runtime_error("protected-hole negative control did not identify the exact poisoned byte");
        }
    }

private:
    void prepare_readback_after_copy(bool copied) {
        const auto prior_usage = copied ? D3D12_RESOURCE_STATE_COPY_DEST : D3D12_RESOURCE_STATE_COMMON;
        if (!warp_.with_consumer) {
            warp_.transition(destination_.get(), prior_usage, D3D12_RESOURCE_STATE_COPY_SOURCE);
            return;
        }
        warp_.transition(destination_.get(), prior_usage, D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
        warp_.transition(consumed_.get(), D3D12_RESOURCE_STATE_COMMON, D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
        warp_.consume(destination_.get(), consumed_.get(), static_cast<uint32_t>(expected_consumed_.size()));
        warp_.transition(consumed_.get(), D3D12_RESOURCE_STATE_UNORDERED_ACCESS, D3D12_RESOURCE_STATE_COPY_SOURCE);
        warp_.transition(destination_.get(), D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE,
                         D3D12_RESOURCE_STATE_COPY_SOURCE);
    }

    void update_expected_consumed(Range atoms) {
        if (expected_consumed_.empty()) return;
        constexpr auto words_per_atom = bytes_per_unit / sizeof(uint32_t);
        const auto first = atoms.begin * words_per_atom;
        const auto last = atoms.end * words_per_atom;
        for (auto index = first; index < last; ++index) {
            uint32_t value = 0;
            std::memcpy(&value, bytes_.expected.data() + index * sizeof(value), sizeof(value));
            expected_consumed_[index] = ((value ^ 0x9e3779b9u) * 0x85ebca6bu) ^
                                       static_cast<uint32_t>(index);
        }
    }

    Sample execute(std::span<const Range> ranges, Clock::time_point begin, Clock::time_point planned,
                   bool use_timestamps) {
        std::size_t units = 0;
        for (const auto range : ranges) {
            if (range.end <= range.begin || range.end > fixture_.extent) {
                throw std::runtime_error("planner produced an invalid buffer range");
            }
            stage(range);
            units += range.end - range.begin;
        }
        const auto staged = Clock::now();
        warp_.record();
        if (use_timestamps) warp_.timestamp(0);
        for (const auto range : ranges) copy(range);
        if (use_timestamps) {
            warp_.timestamp(1);
            warp_.resolve_timestamps();
        }
        prepare_readback_after_copy(!ranges.empty());
        warp_.submit();
        const auto finished = Clock::now();
        const double timestamp = use_timestamps ? warp_.timestamp_us() : 0.0;
        if (const auto changed = compare(); changed != 0) {
            throw std::runtime_error(std::string(fixture_.name) + " whole-buffer mismatch at byte " +
                                     std::to_string(changed - 1));
        }
        return {elapsed(begin, finished), elapsed(begin, planned), elapsed(planned, staged),
                elapsed(staged, finished), timestamp, ranges.size(), units};
    }

    void reset() {
        warp_.record();
        warp_.copy(destination_.get(), 0, initial_.get(), 0, bytes_.initial.size());
        warp_.submit();
    }

    void stage(Range range) {
        const auto offset = range.begin * bytes_per_unit;
        std::memcpy(mapped_upload_ + offset, bytes_.source.data() + offset,
                    (range.end - range.begin) * bytes_per_unit);
    }

    void copy(Range range) {
        const auto offset = range.begin * bytes_per_unit;
        warp_.copy(destination_.get(), offset, upload_.get(), offset, (range.end - range.begin) * bytes_per_unit);
    }

    std::size_t compare() {
        warp_.record();
        warp_.copy(readback_.get(), 0, destination_.get(), 0, bytes_.expected.size());
        if (warp_.with_consumer) {
            warp_.copy(consumed_readback_.get(), 0, consumed_.get(), 0, bytes_.expected.size());
        }
        warp_.transition(destination_.get(), D3D12_RESOURCE_STATE_COPY_SOURCE, D3D12_RESOURCE_STATE_COPY_DEST);
        warp_.submit();
        const D3D12_RANGE requested{0, bytes_.expected.size()};
        void* data = nullptr;
        check(readback_->Map(0, &requested, &data), "Map validation readback");
        const auto different = std::mismatch(bytes_.expected.begin(), bytes_.expected.end(),
                                             static_cast<const uint8_t*>(data)).first;
        const D3D12_RANGE no_writes{0, 0};
        readback_->Unmap(0, &no_writes);
        if (different != bytes_.expected.end()) {
            return static_cast<std::size_t>(different - bytes_.expected.begin()) + 1;
        }
        if (warp_.with_consumer) {
            check(consumed_readback_->Map(0, &requested, &data), "Map compute validation readback");
            const auto matching = std::memcmp(expected_consumed_.data(), data, bytes_.expected.size()) == 0;
            consumed_readback_->Unmap(0, &no_writes);
            if (!matching) throw std::runtime_error(fixture_.name + " whole compute output mismatch");
        }
        return 0;
    }

    Device& warp_;
    const Fixture& fixture_;
    transfer::Cost cost_;
    Bytes bytes_;
    std::span<const uint32_t> dirty_;
    std::vector<uint32_t> expected_consumed_;
    Com<ID3D12Resource> initial_;
    Com<ID3D12Resource> upload_;
    Com<ID3D12Resource> destination_;
    Com<ID3D12Resource> readback_;
    Com<ID3D12Resource> consumed_;
    Com<ID3D12Resource> consumed_readback_;
    uint8_t* mapped_upload_ = nullptr;
};

double rank(std::vector<double> values, unsigned percentile) {
    std::sort(values.begin(), values.end());
    return values.at((values.size() * percentile + 99) / 100 - 1);
}

void metrics(const std::vector<Sample>& samples, const std::vector<double>& ticks, transfer::Cost cost) {
    std::vector<double> chain, planning, staging, api;
    for (const auto sample : samples) {
        chain.push_back(sample.chain_us);
        planning.push_back(sample.planning_us);
        staging.push_back(sample.stage_us);
        api.push_back(sample.api_us);
    }
    const auto first = samples.front();
    std::cout << R"(,"regions":)" << first.ranges << R"(,"copied_bytes":)" << first.units * bytes_per_unit
              << R"(,"modeled_score":)" << cost.setup * first.ranges + cost.unit * first.units
              << R"(,"chain_p50_us":)" << rank(chain, 50) << R"(,"chain_p95_us":)" << rank(chain, 95)
              << R"(,"plan_p50_us":)" << rank(planning, 50) << R"(,"stage_p50_us":)" << rank(staging, 50)
              << R"(,"record_submit_fence_p50_us":)" << rank(api, 50)
              << R"(,"separate_warp_timestamp_p50_us":)" << rank(ticks, 50)
              << R"(,"separate_warp_timestamp_p95_us":)" << rank(ticks, 95) << '}';
}

void transport_controls(Device& warp, unsigned repeats) {
    std::cout << R"(,"transport_controls":[)";
    bool first = true;
    for (bool vary_regions : {true, false}) {
        // Change only the number of contiguous copy commands or only the byte count.
        const std::array<uint32_t, 6> points = vary_regions
            ? std::array<uint32_t, 6>{8, 16, 32, 64, 128, 256}
            : std::array<uint32_t, 6>{128, 256, 512, 1024, 2048, 4096};
        for (uint32_t point : points) {
            const uint32_t count = vary_regions ? point : 64;
            const uint32_t units = vary_regions ? 1024 : point;
            constexpr uint32_t extent = 8192;
            Fixture fixture{"transport-control", extent, extent, {}, {{0, extent}}};
            for (uint32_t unit = 0; unit < units; ++unit) fixture.dirty.push_back(unit);
            const uint32_t width = units / count;
            std::vector<Range> ranges;
            for (uint32_t start = 0; start < units; start += width) {
                ranges.push_back({start, start + width});
            }
            Trial trial(warp, fixture);
            for (unsigned i = 0; i < 3; ++i) trial.run_fixed(ranges);
            std::vector<double> chain, api;
            for (unsigned i = 0; i < repeats; ++i) {
                const auto sample = trial.run_fixed(ranges);
                chain.push_back(sample.chain_us);
                api.push_back(sample.api_us);
            }
            if (!first) std::cout << ',';
            first = false;
            std::cout << R"({"vary":)" << std::quoted(vary_regions ? "regions" : "bytes")
                      << R"(,"regions":)" << count << R"(,"copied_bytes":)" << units * bytes_per_unit
                      << R"(,"wall_without_planning_p50_us":)" << rank(chain, 50)
                      << R"(,"wall_without_planning_p95_us":)" << rank(chain, 95)
                      << R"(,"record_submit_fence_p50_us":)" << rank(api, 50) << '}';
        }
    }
    std::cout << ']';
}

uint64_t unsigned_argument(std::string_view value, const char* description) {
    uint64_t result{};
    const auto end = value.data() + value.size();
    const auto [remaining, error] = std::from_chars(value.data(), end, result);
    if (remaining != end || error != std::errc{}) {
        throw std::invalid_argument(std::string(description) + " must be a nonnegative integer");
    }
    return result;
}

struct Options {
    unsigned repeats = 24;
    unsigned frame_limit = 16;
    uint64_t setup = default_cost.setup;
    std::optional<uint32_t> cap_atoms;
    std::filesystem::path trace;
    bool hardware = false;
    bool probe = false;
};

unsigned bounded_argument(std::string_view value, const char* description, unsigned max) {
    const auto result = unsigned_argument(value, description);
    if (result == 0 || result > max) {
        throw std::invalid_argument(std::string(description) + " out of range");
    }
    return static_cast<unsigned>(result);
}

Options read_options(int argc, char** argv) {
    Options result;
    if (argc <= 1) return result;
    if (!std::string_view(argv[1]).starts_with("--")) {
        if (argc > 3) throw std::invalid_argument("usage: warp_benchmark [samples-per-strategy] [setup-units]");
        result.repeats = bounded_argument(argv[1], "sample count", 120);
        if (result.repeats < 3) throw std::invalid_argument("WARP sample count must be at least 3");
        if (argc > 2) result.setup = unsigned_argument(argv[2], "setup cost");
        return result;
    }

    result.repeats = 3;
    for (int argument = 1; argument < argc; ++argument) {
        const std::string_view option = argv[argument];
        if (option == "--hardware") {
            result.hardware = true;
        } else if (option == "--probe-hardware") {
            result.probe = true;
        } else if (argument + 1 == argc) {
            throw std::invalid_argument("missing value for " + std::string(option));
        } else {
            const std::string_view value = argv[++argument];
            if (option == "--trace") {
                result.trace = value;
            } else if (option == "--samples") {
                result.repeats = bounded_argument(value, "sample count", 120);
            } else if (option == "--frame-limit") {
                result.frame_limit = bounded_argument(value, "frame limit", 4096);
            } else if (option == "--setup") {
                result.setup = unsigned_argument(value, "setup cost");
            } else if (option == "--cap-bytes") {
                const auto cap = unsigned_argument(value, "size cap");
                if (cap == 0 || cap % bytes_per_unit || cap / bytes_per_unit > UINT32_MAX) {
                    throw std::invalid_argument("size cap must be a positive multiple of 64 bytes");
                }
                result.cap_atoms = static_cast<uint32_t>(cap / bytes_per_unit);
            } else {
                throw std::invalid_argument("unknown option: " + std::string(option));
            }
        }
    }
    if (result.probe && argc != 2) throw std::invalid_argument("--probe-hardware must be used alone");
    if (!result.probe && result.trace.empty()) {
        throw std::invalid_argument("trace mode requires --trace <path>; add --hardware to use RTX 4070 Ti SUPER");
    }
    return result;
}

void adapter_fields(const DXGI_ADAPTER_DESC1& description) {
    const auto software = (description.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) != 0;
    std::cout << R"("adapter":)" << std::quoted(utf8(description.Description))
              << R"(,"software":)" << (software ? "true" : "false")
              << R"(,"vendor_id":)" << description.VendorId
              << R"(,"device_id":)" << description.DeviceId
              << R"(,"adapter_luid_low":)" << description.AdapterLuid.LowPart
              << R"(,"adapter_luid_high":)" << description.AdapterLuid.HighPart
              << R"(,"dedicated_video_bytes":)" << description.DedicatedVideoMemory;
}

void probe_hardware() {
    Com<IDXGIFactory4> factory;
    Com<IDXGIAdapter1> adapter;
    check(CreateDXGIFactory2(0, IID_PPV_ARGS(factory.output())), "CreateDXGIFactory2");
    const auto description = select_adapter(*factory.get(), true, adapter);
    std::cout << R"({"enumeration_only":true,)";
    adapter_fields(description);
    std::cout << "}\n";
}

constexpr std::array strategies{Strategy::exact, Strategy::greedy, Strategy::optimal};
constexpr std::array<const char*, 3> names{"exact", "greedy", "optimal"};

void trace_epoch(Trial& trial, std::size_t index, const physical::Epoch& epoch, const Options& options) {
    trial.set_epoch(epoch.dirty);
    std::array<std::vector<Sample>, 3> samples;
    for (unsigned round = 0; round < options.repeats; ++round) {
        const auto turn = index + round;
        for (std::size_t offset = 0; offset < strategies.size(); ++offset) {
            const auto step = ((turn / strategies.size()) % 2 == 0) ? offset : strategies.size() - offset;
            const auto arm = (turn + step) % strategies.size();
            samples[arm].push_back(trial.run(strategies[arm], false));
        }
    }
    std::cout << R"({"index":)" << index << R"(,"frame":)" << epoch.id << R"(,"dirty_atoms":)"
              << epoch.dirty.size() << R"(,"verified":true,"plans":[)";
    for (std::size_t arm = 0; arm < strategies.size(); ++arm) {
        if (arm) std::cout << ',';
        const auto& records = samples[arm];
        std::cout << R"({"strategy":)" << std::quoted(names[arm])
                  << R"(,"regions":)" << records.front().ranges
                  << R"(,"copied_bytes":)" << records.front().units * bytes_per_unit
                  << R"(,"model_score":)" << options.setup * records.front().ranges + records.front().units
                  << R"(,"samples":[)";
        for (std::size_t sample = 0; sample < records.size(); ++sample) {
            if (sample) std::cout << ',';
            const auto& record = records[sample];
            std::cout << '[' << record.chain_us << ',' << record.planning_us << ','
                      << record.stage_us << ',' << record.api_us << ']';
        }
        std::cout << "]}";
    }
    std::cout << "]}";
}

void run_trace(const Options& options) {
    const auto trace = physical::read_trace(options.trace);
    constexpr uint32_t max_extent = 64u * 1024u * 1024u / bytes_per_unit;
    for (const auto& workload : trace.cases) {
        if (workload.extent > max_extent) {
            throw std::invalid_argument("trace buffers must be at most 64 MiB per case");
        }
    }
    Device backend(options.hardware, true);
    std::cout << std::fixed << std::setprecision(3) << R"({"backend":"D3D12",)";
    adapter_fields(backend.description);
    std::cout << R"(,"bytes_per_atom":)" << trace.atom_bytes
              << R"(,"samples_per_strategy":)" << options.repeats
              << R"(,"epoch_selection":"uniform_midpoint_if_limited","single_submission":true,)"
              << R"("setup_units":)" << options.setup
              << R"(,"sample_columns_us":["plan_to_consumer_fence","plan","stage","record_submit_consume_fence"],"cases":[)";
    for (std::size_t number = 0; number < trace.cases.size(); ++number) {
        const auto& workload = trace.cases[number];
        if (number) std::cout << ',';
        const auto cap = std::min(workload.cap, options.cap_atoms.value_or(workload.cap));
        const Fixture fixture{workload.name, workload.extent, cap, {}, workload.islands};
        Trial trial(backend, fixture, {options.setup, 1});
        const auto total = workload.epochs.size();
        const auto selected = std::min(total, static_cast<std::size_t>(options.frame_limit));
        trial.set_epoch(workload.epochs[total / (2 * selected)].dirty);
        for (const auto strategy : strategies) trial.run(strategy, false);
        std::cout << R"({"name":)" << std::quoted(workload.name) << R"(,"extent_atoms":)" << workload.extent
                  << R"(,"cap_atoms":)" << cap << R"(,"available_frames":)" << total
                  << R"(,"selected_frames":)" << selected << R"(,"epochs":[)";
        for (std::size_t rank = 0; rank < selected; ++rank) {
            const auto index = ((2 * rank + 1) * total) / (2 * selected);
            if (rank) std::cout << ',';
            trace_epoch(trial, index, workload.epochs[index], options);
        }
        std::cout << "]}";
    }
    std::cout << "]}\n";
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const auto options = read_options(argc, argv);
        if (options.probe) {
            probe_hardware();
            return 0;
        }
        if (!options.trace.empty()) {
            run_trace(options);
            return 0;
        }
        const auto repeats = options.repeats;
        const transfer::Cost cost{options.setup, 1};
        constexpr unsigned timestamp_repeats = 9;
        Device warp;
        std::cout << std::fixed << std::setprecision(3)
                  << R"({"adapter":)" << std::quoted(warp.name)
                  << R"(,"software":true,"bytes_per_unit":)" << bytes_per_unit
                  << R"(,"time_samples":)" << repeats << R"(,"timestamp_samples":)" << timestamp_repeats
                  << R"(,"warp_ticks_per_second":)" << warp.frequency << R"(,"cases":[)";
        const auto cases = fixtures();
        for (std::size_t test = 0; test < cases.size(); ++test) {
            const auto& fixture = cases[test];
            Trial trial(warp, fixture, cost);
            for (unsigned warmup = 0; warmup < 3; ++warmup) {
                for (const auto strategy : strategies) trial.run(strategy, false);
            }
            std::array<std::vector<Sample>, 3> samples;
            std::array<std::vector<double>, 3> timestamps;
            for (unsigned iteration = 0; iteration < repeats; ++iteration) {
                for (unsigned offset = 0; offset < strategies.size(); ++offset) {
                    const auto strategy = (iteration + offset) % strategies.size();
                    samples[strategy].push_back(trial.run(strategies[strategy], false));
                }
            }
            for (unsigned iteration = 0; iteration < timestamp_repeats; ++iteration) {
                for (unsigned offset = 0; offset < strategies.size(); ++offset) {
                    const auto strategy = (iteration + offset) % strategies.size();
                    timestamps[strategy].push_back(trial.run(strategies[strategy], true).timestamp_us);
                }
            }
            const bool negative_control = fixture.islands.size() > 1;
            if (negative_control) trial.test_negative_control();
            if (test) std::cout << ',';
            std::cout << R"({"workload":)" << std::quoted(fixture.name)
                      << R"(,"extent_units":)" << fixture.extent
                      << R"(,"max_range_units":)" << fixture.max_units
                      << R"(,"modeled_setup_units":)" << cost.setup
                      << R"(,"modeled_per_unit":)" << cost.unit
                      << R"(,"dirty_units":)" << fixture.dirty.size()
                      << R"(,"protected_hole_control":)" << (negative_control ? "true" : "null")
                      << R"(,"whole_buffers_verified":true,"plans":[)";
            for (unsigned strategy = 0; strategy < strategies.size(); ++strategy) {
                if (strategy) std::cout << ',';
                std::cout << R"({"strategy":)" << std::quoted(names[strategy]);
                metrics(samples[strategy], timestamps[strategy], cost);
            }
            std::cout << "]}";
        }
        std::cout << ']';
        transport_controls(warp, repeats);
        std::cout << "}\n";
    } catch (const std::exception& error) {
        std::cerr << "D3D12 benchmark: " << error.what() << '\n';
        return 1;
    }
}
