// SPDX-License-Identifier: MIT
#ifndef CACHE_KEY
#error CACHE_KEY must be a positive trace identity
#endif

struct Draw {
    float4 translate;
    float4 rotation;
    float4 base;
    uint4 textures;
    uint4 controls;
};
[[vk::push_constant]] ConstantBuffer<Draw> draw;
[[vk::binding(0,0)]] Texture2DArray<float4> textures;
[[vk::binding(1,0)]] SamplerState linearWrap;
[[vk::constant_id(0)]] const uint variant = 0;

float3 rotate(float3 vector, float4 quaternion) {
    float3 twice = 2 * cross(quaternion.xyz, vector);
    return vector + quaternion.w * twice + cross(quaternion.xyz, twice);
}

float3 eye(uint camera) {
    if (camera == 1) return float3(-0.71, 0.49, 0.76);
    if (camera == 2) return float3(0.29, 0.86, -0.54);
    return float3(0.61, 0.48, 0.72);
}

struct VertexIn {
    [[vk::location(0)]] float3 position : POSITION;
    [[vk::location(1)]] float3 normal : NORMAL;
    [[vk::location(2)]] float2 uv : TEXCOORD0;
};

struct VertexOut {
    float4 clip : SV_Position;
    float3 world : TEXCOORD0;
    float3 normal : TEXCOORD1;
    float2 uv : TEXCOORD2;
};

VertexOut vertex(VertexIn input) {
    float3 position = rotate(input.position, draw.rotation) + draw.translate.xyz;
    if (draw.controls.x == CACHE_KEY) position = -position;
    float3 camera = eye(draw.controls.y);
    float3 forward = normalize(float3(0, 0.06, 0) - camera);
    float3 right = normalize(cross(forward, float3(0, 1, 0)));
    float3 up = cross(right, forward);
    float3 relative = position - camera;
    float z = dot(relative, forward);
    VertexOut output;
    output.clip = float4(dot(relative, right) * 1.9538, -dot(relative, up) * 2.6051,
                         (z - 0.02) * 1.00251, z);
    output.world = position;
    output.normal = rotate(input.normal, draw.rotation);
    output.uv = input.uv;
    return output;
}

float3 normalSample(VertexOut input) {
    float3 n = normalize(input.normal);
    float3 dp1 = ddx(input.world), dp2 = ddy(input.world);
    float2 duv1 = ddx(input.uv), duv2 = ddy(input.uv);
    float3 tangent = cross(dp2, n) * duv1.x + cross(n, dp1) * duv2.x;
    float3 bitangent = cross(dp2, n) * duv1.y + cross(n, dp1) * duv2.y;
    float scale = rsqrt(max(max(dot(tangent, tangent), dot(bitangent, bitangent)), 1e-16));
    float3 normalTexel = textures.Sample(linearWrap, float3(input.uv, draw.textures.y)).xyz * 2 - 1;
    return normalize(normalTexel.x * tangent * scale + normalTexel.y * bitangent * scale + normalTexel.z * n);
}

float4 pixel(VertexOut input) : SV_Target {
    float3 n = normalSample(input);
    float3 orm = textures.Sample(linearWrap, float3(input.uv, draw.textures.z)).xyz;
    const float alpha = variant / 3 == 1 ? 0.48 : 1.0;
    if (variant % 3 == 1) return float4(n * 0.5 + 0.5, alpha);
    if (variant % 3 == 2) return float4(orm, alpha);
    float3 baseColor = pow(textures.Sample(linearWrap, float3(input.uv, draw.textures.x)).rgb, 2.2) * draw.base.rgb;
    float3 l = normalize(float3(-0.36, 0.91, 0.2));
    float3 v = normalize(eye(draw.controls.y) - input.world);
    float3 halfDirection = normalize(l + v);
    float lambert = saturate(dot(n, l));
    float roughness = clamp(orm.y, 0.065, 1.0);
    float a2 = roughness * roughness * roughness * roughness;
    float ndh = saturate(dot(n, halfDirection));
    float specular = a2 / max(3.14159 * pow(ndh * ndh * (a2 - 1) + 1, 2), 0.0005);
    float3 fresnel = lerp(0.04.xxx, baseColor, orm.z);
    float3 result = baseColor * (0.2 * orm.x + (1 - orm.z) * lambert * 0.96);
    result += fresnel * min(specular, 3.0) * lambert * 0.45;
    if (draw.controls.x == CACHE_KEY) result.bgr = result;
    return float4(pow(saturate(result), 1 / 2.2), alpha);
}
