// SPDX-License-Identifier: MIT
// Original deterministic disk-light quadrature with a GGX BRDF.
// Disk nodes use concentric equal-area radial placement with golden-angle rotation.
// The GGX distribution and correlated Smith visibility are the material terms in
// Khronos glTF 2.0 Appendix B: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#appendix-b-brdf-implementation

#ifndef PORTBRIDGE_AREA_NODES
#define PORTBRIDGE_AREA_NODES 32
#endif

#if PORTBRIDGE_AREA_NODES < 1 || PORTBRIDGE_AREA_NODES > 256
#error PORTBRIDGE_AREA_NODES must be between 1 and 256
#endif

float3 integrateDiskLight(float3 world, float3 n, float3 v, float3 baseColor,
                          float roughness, float metallic) {
    const float pi = 3.141592653589793;
    const float radius = 0.27;
    const float3 center = float3(-0.23, 0.91, 0.20);
    const float3 f0 = lerp(float3(0.04, 0.04, 0.04), baseColor, metallic);
    const float3 diffuse = (1 - metallic) * baseColor / pi;
    const float alpha2 = roughness * roughness * roughness * roughness;
    const float noV = max(saturate(dot(n, v)), 0.0001);
    const float smithV = noV * noV * (1 - alpha2) + alpha2;
    precise float3 radiance = float3(0, 0, 0);
#if PORTBRIDGE_AREA_UNROLL
    [unroll]
#else
    [loop]
#endif
    for (uint j = 0; j < PORTBRIDGE_AREA_NODES; ++j) {
        const float angle = float(j) * 2.399963229728653;
        const float r = radius * sqrt((float(j) + 0.5) / PORTBRIDGE_AREA_NODES);
        const float3 delta = center + r * float3(cos(angle), 0, sin(angle)) - world;
        const float distance2 = max(dot(delta, delta), 0.0001);
        const float3 l = delta * rsqrt(distance2);
        const float noL = saturate(dot(n, l));
        const float3 halfVector = v + l;
        const float3 h = halfVector * rsqrt(max(dot(halfVector, halfVector), 0.0001));
        const float noH = saturate(dot(n, h));
        const float voH = saturate(dot(v, h));
        const float ggx = noH * noH * (alpha2 - 1) + 1;
        const float distribution = alpha2 / max(pi * ggx * ggx, 0.000001);
        const float smithL = noL * noL * (1 - alpha2) + alpha2;
        const float visibility = 0.5 / max(noL * sqrt(smithV) + noV * sqrt(smithL), 0.0001);
        const float f = 1 - voH;
        const float f2 = f * f;
        const float3 fresnel = f0 + (1 - f0) * (f2 * f2 * f);
        const float solidAngle = saturate(l.y) * (pi * radius * radius / PORTBRIDGE_AREA_NODES) / distance2;
        radiance += (diffuse * (1 - fresnel) + fresnel * distribution * visibility) * noL * solidAngle;
    }
    return radiance * 2.3;
}
