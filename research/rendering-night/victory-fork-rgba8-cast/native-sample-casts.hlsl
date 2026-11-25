// SPDX-License-Identifier: GPL-3.0-or-later
Texture2D<float4> UnormOwn : register(t0);
Texture2D<float4> UnormAsSrgb : register(t1);
Texture2D<float4> SrgbAsUnorm : register(t2);
Texture2D<float4> SrgbOwn : register(t3);
SamplerState PointSampler : register(s0);
RWStructuredBuffer<float4> Readback : register(u0);

[numthreads(1, 1, 1)]
void main()
{
    const float2 uv = float2(0.5, 0.5);
    Readback[0] = UnormOwn.SampleLevel(PointSampler, uv, 0.0);
    Readback[1] = UnormAsSrgb.SampleLevel(PointSampler, uv, 0.0);
    Readback[2] = SrgbAsUnorm.SampleLevel(PointSampler, uv, 0.0);
    Readback[3] = SrgbOwn.SampleLevel(PointSampler, uv, 0.0);
}
