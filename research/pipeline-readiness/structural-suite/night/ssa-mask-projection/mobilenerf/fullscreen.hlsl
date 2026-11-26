// SPDX-License-Identifier: MIT
struct Output
{
    float4 position : SV_Position;
    float4 uv : TEXCOORD0;
};

Output main(uint id : SV_VertexID)
{
    float2 xy = id == 0 ? float2(-1, -1) : id == 1 ? float2(-1, 3) : float2(3, -1);
    Output o;
    o.position = float4(xy, 0, 1);
    o.uv = float4(xy * float2(0.5, -0.5) + 0.5, 0, 1);
    return o;
}
