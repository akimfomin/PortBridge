// SPDX-License-Identifier: GPL-3.0-or-later
float4 vs_main(uint vertex_id : SV_VertexID) : SV_Position {
    const float2 positions[3] = {float2(-1.0, -1.0), float2(-1.0, 1.0), float2(1.0, -1.0)};
    return float4(positions[vertex_id], 0.0, 1.0);
}

struct Outputs {
    uint code : SV_Target0;
    float4 color : SV_Target1;
};

Outputs ps_main() {
    Outputs output;
    output.code = 37;
    output.color = float4(0.25, 0.50, 0.75, 0.50);
    return output;
}
