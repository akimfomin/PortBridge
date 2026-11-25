// SPDX-License-Identifier: MIT
// Three-dispatch control for words live on every crossing.
#define send unused_two_dispatch_send
#define receive unused_two_dispatch_receive
#include "transport.hlsl"
#undef send
#undef receive

#define SHARED_WORDS 16
#define OLD_DYNAMIC 7
#define NEW_DYNAMIC 19

uint plane_address(uint group, uint lane, uint offset) {
    return (base_word(group) + offset * THREADS + lane) * 4;
}

uint common_address(uint group, uint lane, uint dynamic_count, uint i) {
#if TILED
    return plane_address(group, lane, 1 + i);
#else
    return plane_address(group, lane, 1 + dynamic_count + i);
#endif
}

uint dynamic_address(uint group, uint lane, uint i) {
#if TILED
    return plane_address(group, lane, 1 + SHARED_WORDS + i);
#else
    return plane_address(group, lane, 1 + i);
#endif
}

[WaveSize(32)]
[numthreads(THREADS, 1, 1)]
void send(uint3 gid : SV_GroupID, uint lane : SV_GroupIndex) {
    uint group = linear_group(gid);
    uint tag = edge_for(group, lane);
    if (tag != 0) {
        uint dynamic_count = tag == 1 ? OLD_DYNAMIC : NEW_DYNAMIC;
        [unroll]
        for (uint i = 0; i < SHARED_WORDS; ++i)
            Scratch.Store(common_address(group, lane, dynamic_count, i), data_word(group, lane, i));
        [unroll]
        for (uint j = 0; j < NEW_DYNAMIC; ++j)
            if (j < dynamic_count)
                Scratch.Store(dynamic_address(group, lane, j), data_word(group, lane, SHARED_WORDS + j));
    }
    Scratch.Store(plane_address(group, lane, 0), tag);
}

uint evolve(uint word, uint slot) {
    return word ^ (slot + 1) * 0x45d9f3bu ^ Seed;
}

[WaveSize(32)]
[numthreads(THREADS, 1, 1)]
void forward(uint3 gid : SV_GroupID, uint lane : SV_GroupIndex) {
    uint group = linear_group(gid);
    if (Scratch.Load(plane_address(group, lane, 0)) != 1) return;
    uint old[OLD_DYNAMIC];
    [unroll]
    for (uint i = 0; i < OLD_DYNAMIC; ++i)
        old[i] = Scratch.Load(dynamic_address(group, lane, i));
#if !TILED
    uint common[SHARED_WORDS];
    [unroll]
    for (uint j = 0; j < SHARED_WORDS; ++j)
        common[j] = Scratch.Load(common_address(group, lane, OLD_DYNAMIC, j));
#endif
    [unroll]
    for (uint k = 0; k < NEW_DYNAMIC; ++k)
        Scratch.Store(dynamic_address(group, lane, k), evolve(old[k % OLD_DYNAMIC], k));
#if !TILED
    [unroll]
    for (uint m = 0; m < SHARED_WORDS; ++m)
        Scratch.Store(common_address(group, lane, NEW_DYNAMIC, m), common[m]);
#endif
    Scratch.Store(plane_address(group, lane, 0), 3);
}

[WaveSize(32)]
[numthreads(THREADS, 1, 1)]
void receive(uint3 gid : SV_GroupID, uint lane : SV_GroupIndex) {
    uint group = linear_group(gid);
    uint tag = Scratch.Load(plane_address(group, lane, 0));
    uint digest = 2166136261u ^ tag;
    if (tag == 2 || tag == 3) {
        [unroll]
        for (uint i = 0; i < SHARED_WORDS; ++i)
            digest = fold_word(digest, Scratch.Load(common_address(group, lane, NEW_DYNAMIC, i)));
        [unroll]
        for (uint j = 0; j < NEW_DYNAMIC; ++j)
            digest = fold_word(digest, Scratch.Load(dynamic_address(group, lane, j)));
    }
    Output.Store((OutputSlice + group * THREADS + lane) * 4, digest);
}
