// SPDX-License-Identifier: MIT
#ifndef FIXTURE_SALT
#error FIXTURE_SALT selects the generated recipe
#endif

[[vk::binding(0, 0)]] RWStructuredBuffer<uint> output_data;

[numthreads(32, 1, 1)]
void main(uint3 id : SV_DispatchThreadID) {
    output_data[id.x + 1] = id.x ^ FIXTURE_SALT;
}
