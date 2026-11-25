// SPDX-License-Identifier: GPL-3.0-or-later
Texture2D<float4> Unorm8 : register(t0);
Texture2D<float4> Unorm16 : register(t1);
Texture2D<float4> Snorm16 : register(t2);
Texture2D<float4> Snorm8 : register(t3);
SamplerState LinearSampler : register(s0);
RWStructuredBuffer<float4> Readback : register(u0);

[numthreads(1, 1, 1)]
void main()
{
    const float2 uv = float2(0.5, 0.5);
    Readback[0] = Unorm8.SampleLevel(LinearSampler, uv, 0.0);
    Readback[1] = Unorm16.SampleLevel(LinearSampler, uv, 0.0);
    Readback[2] = Snorm16.SampleLevel(LinearSampler, uv, 0.0);
    Readback[3] = Snorm8.SampleLevel(LinearSampler, uv, 0.0);
}
