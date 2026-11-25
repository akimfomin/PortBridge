# Preserve typed RGBA8 linear and sRGB shader views

The proposed victory-fork patch preserves an explicit `R8G8B8A8_UNORM` or `R8G8B8A8_UNORM_SRGB` shader-resource view when the resource uses the other format and the adapter reports fully typed format casting in D3D12 Options3. Other pairs and older adapters retain the existing policy. It targets fork commit `c96b4f2b8365bf43d54ab074940923ef8267f4c6` and source blob `b2c27c5342488a93364aa483f4498d38b30ffff2`. [Previous descriptor policy](https://github.com/fxceless/victory-fork/blob/c96b4f2b8365bf43d54ab074940923ef8267f4c6/crates/victory-gpu/src/descriptor/host.rs#L1788-L1845) · [PortBridge Test Lab](https://akimfomin.github.io/PortBridge/#/lab)

Microsoft's D3D12 casting rules let capable drivers create compatible views of a fully typed resource within the same family. The spec illustrates UNORM → sRGB. The reverse pair is in the same family and falls under neither the FLOAT restriction nor the SNORM/UNORM restriction. Options3 is queried once for the singleton host device. [D3D12 typed-casting rules](https://microsoft.github.io/DirectX-Specs/d3d/RelaxedCasting.html) · [Options3 capability](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ns-d3d12-d3d12_feature_data_d3d12_options3)

The CPU differential extracted the exact descriptor-policy code from the two source states. A compatible host's requested sRGB view was reduced to UNORM before the patch and preserved afterwards. Reciprocal, failed-query, unsupported-adapter, typeless, implicit view, UAV, denied SRV and incompatible-family controls passed. The candidate function signatures and feature query also compiled against the actual Windows Rust bindings 0.62.2.

## One synthetic hardware witness

On a GeForce RTX 4070 Ti SUPER, driver `32.0.16.1714`, Windows 11 build `28000`, a single compute dispatch sampled the same `0x80` texel through four views. Options3 reported support. The D3D12 debug layer was unavailable.

| Resource | Explicit view | Observed RGB float bits | Observed alpha float bits |
| --- | --- | --- | --- |
| Typed UNORM | UNORM | `3f008081` | `3f008081` |
| Typed UNORM | sRGB | `3e5d0000` | `3f008081` |
| Typed sRGB | UNORM | `3f008081` | `3f008081` |
| Typed sRGB | sRGB | `3e5d0000` | `3f008081` |

The linear value is about 0.50196. The sRGB samples returned 0.2158203125, within the specified half-code tolerance of the ideal 0.21586050. The two casts matched their same-view-format controls bit for bit. Alpha stayed linear. The witness covers a sampled texture view and its transfer function. Links to missing walls or other world-rendering symptoms remain unverified. [GPU log](GPU-PROOF.txt) · [Direct3D sRGB conversion rules, section 3.2.3.7](https://microsoft.github.io/DirectX-Specs/d3d/archive/D3D11_3_FunctionalSpec.htm)

## Reproduce

The CPU script needs Python 3 and Rust 1.88 or newer. It runs the real source policy against a mock D3D12 capability query. It exits with a failing assertion on the original source and passes after the patch is applied.

```powershell
python -B descriptor_proof.py --repo ../victory-fork --out out/descriptor-proof
```

To independently test D3D12 view sampling on the exact adapter, build the source-only witness with DXC and a Clang Windows toolchain. The CPU oracle runs without creating a device. The explicit hardware mode selects the stated RTX model only, checks Options3 before allocating test textures, and runs one dispatch in a Windows job with a 512 MiB memory limit and a three-second deadline.

```powershell
dxc -WX -T cs_6_0 -E main -Fo native-sample-casts.dxil native-sample-casts.hlsl
python -B embed_shader.py native-sample-casts.dxil native-sample-casts.inc
clang++ -std=c++20 -O2 -fms-extensions -municode -static native-cast.cpp -o native-cast.exe -ld3d12 -ldxgi -ldxguid -lpsapi
./native-cast.exe --cpu-oracle
./native-cast.exe --hardware
```

The source patch and fixture are GPL-3.0-or-later. The included Windows worker guard retains its MIT license. [Project license](LICENSE) · [Guard license](LICENSE.guard)
