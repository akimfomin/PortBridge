// SPDX-License-Identifier: GPL-3.0-or-later
// Reuse adapter gating, buffer creation, queue wait and the existing guard.
#define wmain portable_texture_proof_entry
#include "../portbridge-victory-dirty-tile-upload/native-upload.cpp"
#undef wmain

#include <array>
#include <iterator>
#include <span>
#include "programs.inc"

namespace {
constexpr unsigned payload_capacity = 35;
constexpr unsigned measured_pairs = 8;
constexpr unsigned epochs = measured_pairs + 1;
constexpr unsigned query_count = epochs * 4;

struct Geometry {
    UINT x, y, z, lanes;
    unsigned groups() const { return x * y * z; }
    unsigned words() const { return groups() * lanes; }
};

constexpr Geometry shapes[]{{32, 4, 3, 32}, {64, 4, 8, 64}};

struct ScratchResult {
    Report status;
    UINT64 frequency{};
    std::array<std::array<UINT64, query_count>, std::size(shapes)> ticks{};
    std::array<unsigned, std::size(shapes)> checked_words{};
};

struct Program {
    std::span<const unsigned char> send;
    std::span<const unsigned char> receive;
#if defined(PORTBRIDGE_STICKY)
    std::span<const unsigned char> forward;
#endif
};

const Program programs[][2]{
#if defined(PORTBRIDGE_STICKY)
    {{send_32_scalar, receive_32_scalar, forward_32_scalar}, {send_32_tiled, receive_32_tiled, forward_32_tiled}},
    {{send_64_scalar, receive_64_scalar, forward_64_scalar}, {send_64_tiled, receive_64_tiled, forward_64_tiled}},
#else
    {{send_32_scalar, receive_32_scalar}, {send_32_tiled, receive_32_tiled}},
    {{send_64_scalar, receive_64_scalar}, {send_64_tiled, receive_64_tiled}},
#endif
};

ComPtr<ID3D12RootSignature> root_signature(ID3D12Device& device) {
    D3D12_ROOT_PARAMETER params[3]{};
    params[0].ParameterType = params[1].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
    params[0].Descriptor = {0, 0};
    params[1].Descriptor = {1, 0};
    params[2].ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
    params[2].Constants = {0, 0, 4};
    const D3D12_ROOT_SIGNATURE_DESC desc{3, params, 0, nullptr, D3D12_ROOT_SIGNATURE_FLAG_NONE};
    ComPtr<ID3DBlob> signature;
    check(D3D12SerializeRootSignature(&desc, D3D_ROOT_SIGNATURE_VERSION_1, &signature, nullptr),
          "Serialize root signature");
    ComPtr<ID3D12RootSignature> root;
    check(device.CreateRootSignature(0, signature->GetBufferPointer(), signature->GetBufferSize(),
                                    IID_PPV_ARGS(&root)), "Create root signature");
    return root;
}

ComPtr<ID3D12PipelineState> pipeline(ID3D12Device& device, ID3D12RootSignature* root,
                                    std::span<const unsigned char> binary) {
    D3D12_COMPUTE_PIPELINE_STATE_DESC desc{};
    desc.pRootSignature = root;
    desc.CS = {binary.data(), binary.size_bytes()};
    ComPtr<ID3D12PipelineState> pso;
    check(device.CreateComputePipelineState(&desc, IID_PPV_ARGS(&pso)), "Create transport PSO");
    return pso;
}

void uav_barrier(ID3D12GraphicsCommandList& list, ID3D12Resource* resource) {
    D3D12_RESOURCE_BARRIER barrier{};
    barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_UAV;
    barrier.UAV = {resource};
    list.ResourceBarrier(1, &barrier);
}

void output_copy(ID3D12GraphicsCommandList& list, ID3D12Resource* out,
                 ID3D12Resource* read, UINT64 bytes) {
    D3D12_RESOURCE_BARRIER barrier{};
    barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    barrier.Transition = {out, D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,
                          D3D12_RESOURCE_STATE_UNORDERED_ACCESS, D3D12_RESOURCE_STATE_COPY_SOURCE};
    list.ResourceBarrier(1, &barrier);
    list.CopyBufferRegion(read, 0, out, 0, bytes);
}

static UINT seed_for(unsigned pair) { return 0x79b9u + pair * 3391u; }

UINT input_word(unsigned group, unsigned lane, unsigned at, UINT seed) {
    UINT word = (group + 1) * 0x82a2b175u ^ (lane + 1) * 0x7feb352du ^ (at + 1) * 0x846ca68bu ^ seed;
    word = (word ^ (word >> 16)) * 0x21f0aaadu;
    return word ^ (word >> 15);
}

UINT expected_word(unsigned group, unsigned lane, UINT seed) {
    const auto route = (group * 3 + lane + seed) % 9;
    const auto edge = route == 0 ? 0u : route <= 3 ? 1u : 2u;
#if defined(PORTBRIDGE_STICKY)
    UINT hash = 2166136261u ^ (edge == 1 ? 3u : edge);
    if (edge == 0) return hash;
    for (unsigned i = 0; i < payload_capacity; ++i) {
        UINT word = input_word(group, lane, i, seed);
        if (edge == 1 && i >= 16) {
            const auto slot = i - 16;
            word = input_word(group, lane, 16 + (slot % 7), seed) ^ (slot + 1) * 0x45d9f3bu ^ seed;
        }
        hash = (hash ^ word) * 16777619u + 13u;
    }
#else
    UINT hash = 2166136261u ^ edge;
    const unsigned length = edge == 0 ? 0 : edge == 1 ? 3 : payload_capacity;
    for (unsigned i = 0; i < length; ++i)
        hash = (hash ^ input_word(group, lane, i, seed)) * 16777619u + 13u;
#endif
    return hash;
}

unsigned verify_words(ID3D12Resource& a, ID3D12Resource& b, Geometry g) {
    const D3D12_RANGE read{0, g.words() * epochs * sizeof(UINT)};
    const D3D12_RANGE none{0, 0};
    void* a_data{};
    void* b_data{};
    check(a.Map(0, &read, &a_data), "Map scalar readback");
    check(b.Map(0, &read, &b_data), "Map tiled readback");
    const auto* scalar = static_cast<const UINT*>(a_data);
    const auto* tiled = static_cast<const UINT*>(b_data);
    unsigned same{};
    for (unsigned i = 0; i < epochs; ++i)
        for (unsigned group = 0; group < g.groups(); ++group)
            for (unsigned lane = 0; lane < g.lanes; ++lane) {
                const auto index = i * g.words() + group * g.lanes + lane;
                const auto expected = expected_word(group, lane, seed_for(i));
                same += scalar[index] == expected && tiled[index] == expected;
            }
    a.Unmap(0, &none);
    b.Unmap(0, &none);
    return same;
}

ScratchResult measure_transport() {
    ScratchResult result;
    auto& status = result.status;
    try {
        ComPtr<ID3D12Debug> debug;
        if (SUCCEEDED(D3D12GetDebugInterface(IID_PPV_ARGS(&debug)))) {
            debug->EnableDebugLayer();
            status.debug = 1;
        }
        auto adapter = select_adapter();
        ComPtr<ID3D12Device> device;
        check(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_12_0, IID_PPV_ARGS(&device)), "Create device");
        D3D12_FEATURE_DATA_D3D12_OPTIONS1 wave{};
        check(device->CheckFeatureSupport(D3D12_FEATURE_D3D12_OPTIONS1, &wave, sizeof(wave)), "Check wave ops");
        if (!wave.WaveOps || wave.WaveLaneCountMin != 32 || wave.WaveLaneCountMax != 32)
            throw Failure{E_FAIL, "Require fixed wave32 hardware"};
        auto root = root_signature(*device.Get());
        ComPtr<ID3D12CommandQueue> queue;
        D3D12_COMMAND_QUEUE_DESC queue_desc{};
        queue_desc.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
        check(device->CreateCommandQueue(&queue_desc, IID_PPV_ARGS(&queue)), "Create queue");
        check(queue->GetTimestampFrequency(&result.frequency), "Get queue frequency");
        if (!result.frequency) throw Failure{E_FAIL, "Missing queue frequency"};
        ComPtr<ID3D12CommandAllocator> allocator;
        check(device->CreateCommandAllocator(queue_desc.Type, IID_PPV_ARGS(&allocator)), "Create allocator");
        ComPtr<ID3D12GraphicsCommandList> list;
        check(device->CreateCommandList(0, queue_desc.Type, allocator.Get(), nullptr,
                                        IID_PPV_ARGS(&list)), "Create list");
        ComPtr<ID3D12Fence> fence;
        check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence)), "Create fence");
        guard::Handle event{CreateEventW(nullptr, FALSE, FALSE, nullptr)};
        if (!event) throw Failure{HRESULT_FROM_WIN32(GetLastError()), "Create event"};

        ComPtr<ID3D12QueryHeap> queries;
        const D3D12_QUERY_HEAP_DESC query_desc{D3D12_QUERY_HEAP_TYPE_TIMESTAMP, query_count, 0};
        check(device->CreateQueryHeap(&query_desc, IID_PPV_ARGS(&queries)), "Create timestamp heap");
        constexpr auto tick_bytes = query_count * sizeof(UINT64);
        const D3D12_RANGE tick_range{0, tick_bytes}, no_write{0, 0};
        auto ticks = create(*device.Get(), description(D3D12_RESOURCE_DIMENSION_BUFFER, tick_bytes, 1),
                            D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);

        for (unsigned n = 0; n < std::size(shapes); ++n) {
            const auto g = shapes[n];
            const auto scratch_bytes = UINT64(g.words()) * (1 + payload_capacity) * sizeof(UINT);
            const auto output_bytes = UINT64(g.words()) * epochs * sizeof(UINT);
            auto scratch_desc = description(D3D12_RESOURCE_DIMENSION_BUFFER, scratch_bytes, 1);
            scratch_desc.Flags = D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS;
            auto out_desc = description(D3D12_RESOURCE_DIMENSION_BUFFER, output_bytes, 1);
            auto read_desc = out_desc;
            out_desc.Flags = D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS;
            std::array<ComPtr<ID3D12Resource>, 2> scratch, output, read;
            std::array<ComPtr<ID3D12PipelineState>, 2> sender, receiver;
#if defined(PORTBRIDGE_STICKY)
            std::array<ComPtr<ID3D12PipelineState>, 2> forwarder;
#endif
            for (unsigned arm = 0; arm < 2; ++arm) {
                scratch[arm] = create(*device.Get(), scratch_desc, D3D12_HEAP_TYPE_DEFAULT,
                                      D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
                output[arm] = create(*device.Get(), out_desc, D3D12_HEAP_TYPE_DEFAULT,
                                     D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
                read[arm] = create(*device.Get(), read_desc, D3D12_HEAP_TYPE_READBACK,
                                   D3D12_RESOURCE_STATE_COPY_DEST);
                sender[arm] = pipeline(*device.Get(), root.Get(), programs[n][arm].send);
                receiver[arm] = pipeline(*device.Get(), root.Get(), programs[n][arm].receive);
#if defined(PORTBRIDGE_STICKY)
                forwarder[arm] = pipeline(*device.Get(), root.Get(), programs[n][arm].forward);
#endif
            }
            if (n) {
                check(allocator->Reset(), "Reset allocator");
                check(list->Reset(allocator.Get(), nullptr), "Reset list");
            }
            list->SetComputeRootSignature(root.Get());
            unsigned query{};
            for (unsigned pair = 0; pair < epochs; ++pair) {
                const UINT constants[]{g.x, g.y, seed_for(pair), pair * g.words()};
                for (unsigned rank = 0; rank < 2; ++rank) {
                    const auto arm = (pair + rank + n) & 1;
                    list->SetComputeRootUnorderedAccessView(0, scratch[arm]->GetGPUVirtualAddress());
                    list->SetComputeRootUnorderedAccessView(1, output[arm]->GetGPUVirtualAddress());
                    list->SetComputeRoot32BitConstants(2, 4, constants, 0);
                    list->SetPipelineState(sender[arm].Get());
                    list->EndQuery(queries.Get(), D3D12_QUERY_TYPE_TIMESTAMP, query++);
                    list->Dispatch(g.x, g.y, g.z);
                    uav_barrier(*list.Get(), scratch[arm].Get());
#if defined(PORTBRIDGE_STICKY)
                    list->SetPipelineState(forwarder[arm].Get());
                    list->Dispatch(g.x, g.y, g.z);
                    uav_barrier(*list.Get(), scratch[arm].Get());
#endif
                    list->SetPipelineState(receiver[arm].Get());
                    list->Dispatch(g.x, g.y, g.z);
                    list->EndQuery(queries.Get(), D3D12_QUERY_TYPE_TIMESTAMP, query++);
                    uav_barrier(*list.Get(), scratch[arm].Get());
                    uav_barrier(*list.Get(), output[arm].Get());
                }
            }
            list->ResolveQueryData(queries.Get(), D3D12_QUERY_TYPE_TIMESTAMP, 0, query, ticks.Get(), 0);
            for (unsigned arm = 0; arm < 2; ++arm)
                output_copy(*list.Get(), output[arm].Get(), read[arm].Get(), output_bytes);
            finish(*queue.Get(), *list.Get(), *fence.Get(), event.value, n + 1);
            check(device->GetDeviceRemovedReason(), "Check device");
            result.checked_words[n] = verify_words(*read[0].Get(), *read[1].Get(), g);
            if (result.checked_words[n] != g.words() * epochs)
                throw Failure{E_FAIL, "Transport readback mismatch"};

            void* data{};
            check(ticks->Map(0, &tick_range, &data), "Map query times");
            std::memcpy(result.ticks[n].data(), data, tick_bytes);
            ticks->Unmap(0, &no_write);
        }
        status.completed = 1;
    } catch (const Failure& failure) {
        status.hresult = static_cast<unsigned>(failure.code);
        std::snprintf(status.step, sizeof(status.step), "%s", failure.step);
    }
    return result;
}
}

int wmain(int argc, wchar_t** argv) {
    if (argc != 2) return 2;
    const std::wstring_view mode(argv[1]);
    if (mode == L"--transport-worker") {
        if (!guard::worker_limits(memory_limit)) return 2;
        const auto row = measure_transport();
        DWORD bytes{};
        return WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), &row, sizeof(row), &bytes, nullptr)
               && bytes == sizeof(row) ? 0 : 2;
    }
    if (mode != L"--hardware-transport") return 2;
    const auto result = guard::run<ScratchResult>(memory_limit, true, deadline, {L"--transport-worker"});
    std::printf("guard=%s reaped=%d peak_job=%zu exit=%lu error=%lu\n",
                result.status, result.reaped, result.job_peak, result.exit_code, result.win_error);
    if (std::string_view(result.status) != "returned" || !result.reaped || result.exit_code ||
        result.win_error || result.job_peak == 0 || result.job_peak > memory_limit) return 2;
    const auto& data = result.report;
    std::printf("status=%u debug=%u result=%08x step=%s frequency=%llu\n", data.status.completed,
                data.status.debug, data.status.hresult, data.status.step,
                static_cast<unsigned long long>(data.frequency));
    for (unsigned n = 0; n < std::size(shapes); ++n)
        std::printf("lanes=%u grid=%ux%ux%u matched_words_per_arm=%u\n",
                    shapes[n].lanes, shapes[n].x, shapes[n].y, shapes[n].z, data.checked_words[n]);
    if (!data.status.completed) return 1;
    std::puts("lanes,pair,order,scalar_ticks,tiled_ticks");
    for (unsigned n = 0; n < std::size(shapes); ++n) {
        const auto& row = data.ticks[n];
        for (unsigned i = 0; i < epochs; ++i) {
            unsigned at = 4 * i;
            if (!row[at] || row[at] >= row[at + 1] || row[at + 1] > row[at + 2] ||
                row[at + 2] >= row[at + 3]) return 1;
            const auto first = row[at + 1] - row[at];
            const auto second = row[at + 3] - row[at + 2];
            const bool tiled_first = ((i + n) & 1) != 0;
            std::printf("%u,%u,%s,%llu,%llu\n", shapes[n].lanes, i, tiled_first ? "TS" : "ST",
                        static_cast<unsigned long long>(tiled_first ? second : first),
                        static_cast<unsigned long long>(tiled_first ? first : second));
        }
    }
    return 0;
}
