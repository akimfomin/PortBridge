// SPDX-License-Identifier: MIT
// Source-generated surrogate for one producer/consumer edge in XCL #2080.
#define CAPACITY 35
#define SHORT_PAYLOAD 3

RWByteAddressBuffer Scratch : register(u0);
RWByteAddressBuffer Output : register(u1);
cbuffer DispatchInfo : register(b0) {
    uint Width, Height, Seed, OutputSlice;
};

uint linear_group(uint3 group) {
    return (group.z * Height + group.y) * Width + group.x;
}

uint edge_for(uint group, uint lane) {
    uint route = (group * 3 + lane + Seed) % 9;
    return route == 0 ? 0 : route <= 3 ? 1 : 2;
}

uint data_word(uint group, uint lane, uint slot) {
    uint value = (group + 1) * 0x82a2b175u ^ (lane + 1) * 0x7feb352du
                 ^ (slot + 1) * 0x846ca68bu ^ Seed;
    value = (value ^ (value >> 16)) * 0x21f0aaadu;
    return value ^ (value >> 15);
}

uint fold_word(uint digest, uint value) {
    return (digest ^ value) * 16777619u + 13u;
}

uint base_word(uint group) {
    return group * (1 + CAPACITY) * THREADS;
}

uint slot_address(uint group, uint lane, uint first) {
#if TILED
    uint lane_stride = min(4u, CAPACITY - first);
    return (base_word(group) + (1u + first) * THREADS + lane * lane_stride) * 4;
#else
    return (base_word(group) + (1u + first) * THREADS + lane) * 4;
#endif
}

void send_payload(uint group, uint lane, uint count) {
#if TILED
    [unroll]
    for (uint first = 0; first < count; first += 4) {
        uint width = min(4u, count - first);
        uint offset = slot_address(group, lane, first);
        uint a = data_word(group, lane, first);
        if (width == 1) Scratch.Store(offset, a);
        else {
            uint b = data_word(group, lane, first + 1);
            if (width == 2) Scratch.Store2(offset, uint2(a, b));
            else {
                uint c = data_word(group, lane, first + 2);
                if (width == 3) Scratch.Store3(offset, uint3(a, b, c));
                else Scratch.Store4(offset, uint4(a, b, c, data_word(group, lane, first + 3)));
            }
        }
    }
#else
    [unroll]
    for (uint slot = 0; slot < count; ++slot)
        Scratch.Store(slot_address(group, lane, slot), data_word(group, lane, slot));
#endif
}

uint receive_payload(uint group, uint lane, uint count, uint digest) {
#if TILED
    [unroll]
    for (uint first = 0; first < count; first += 4) {
        uint width = min(4u, count - first);
        uint offset = slot_address(group, lane, first);
        uint4 words = 0;
        if (width == 1) words.x = Scratch.Load(offset);
        else if (width == 2) words.xy = Scratch.Load2(offset);
        else if (width == 3) words.xyz = Scratch.Load3(offset);
        else words = Scratch.Load4(offset);
        [unroll]
        for (uint i = 0; i < width; ++i)
            digest = fold_word(digest, words[i]);
    }
#else
    [unroll]
    for (uint slot = 0; slot < count; ++slot)
        digest = fold_word(digest, Scratch.Load(slot_address(group, lane, slot)));
#endif
    return digest;
}

[WaveSize(32)]
[numthreads(THREADS, 1, 1)]
void send(uint3 gid : SV_GroupID, uint lane : SV_GroupIndex) {
    uint group = linear_group(gid);
    uint edge = edge_for(group, lane);
    if (edge == 1) send_payload(group, lane, SHORT_PAYLOAD);
    else if (edge == 2) send_payload(group, lane, CAPACITY);
    Scratch.Store((base_word(group) + lane) * 4, edge);
}

[WaveSize(32)]
[numthreads(THREADS, 1, 1)]
void receive(uint3 gid : SV_GroupID, uint lane : SV_GroupIndex) {
    uint group = linear_group(gid);
    uint edge = Scratch.Load((base_word(group) + lane) * 4);
    uint digest = 2166136261u ^ edge;
    if (edge == 1) digest = receive_payload(group, lane, SHORT_PAYLOAD, digest);
    else if (edge == 2) digest = receive_payload(group, lane, CAPACITY, digest);
    Output.Store((OutputSlice + group * THREADS + lane) * 4, digest);
}
