// SPDX-License-Identifier: MIT
// DXC SPIR-V mode binding and push-constant annotations:
// https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/SPIR-V.rst
[[vk::binding(0, 0)]] StructuredBuffer<uint> source_words;
[[vk::binding(1, 0)]] RWStructuredBuffer<uint> output_words;

struct Parameters {
    uint word_count;
    uint stride;
};
[[vk::push_constant]] ConstantBuffer<Parameters> parameters;

[numthreads(64, 1, 1)]
void main(uint3 id : SV_DispatchThreadID) {
    for (uint index = id.x; index < parameters.word_count; index += parameters.stride) {
        output_words[index] = ((source_words[index] ^ 0x9e3779b9u) * 0x85ebca6bu) ^ index;
    }
}
