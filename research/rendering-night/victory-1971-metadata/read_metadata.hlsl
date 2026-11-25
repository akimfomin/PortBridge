// SPDX-License-Identifier: GPL-3.0-or-later
// Independent consumer of the published t1 / space2 row ABI in VIctory #1971.

ByteAddressBuffer metadata : register(t1, space2);
RWByteAddressBuffer results : register(u0);

[RootSignature("SRV(t1, space=2), UAV(u0)")]
[numthreads(5, 1, 1)]
void main(uint lane : SV_GroupIndex)
{
    uint slots = metadata.Load(0);
    uint index = lane == 1 ? 1 : lane == 2 ? 2 : lane == 3 ? 4 : 0xffffffff;
    uint row = index < slots ? index + 2 : 1;
    uint offset = lane == 0 ? 0 : row * 16;
    results.Store4(lane * 16, metadata.Load4(offset));
}
