# VIctory #1997 — preserve three typed compositor source formats

Based on Calvix2k’s [VIctory #1997](https://github.com/Marvisak/VIctory/pull/1997) at `d732465f64dd868dd0d71811d5596519cdcba889`, which carries the multi-plane compositor by Yaekai, swarm and Blitz Studios. The compositor uses `swap_format` both for swap-chain storage and for the shader resource view of each source texture. The latter use rewrites three fully typed, filterable texture formats into prohibited legacy Direct3D 12 view formats. [Pinned code](https://github.com/Marvisak/VIctory/blob/d732465f64dd868dd0d71811d5596519cdcba889/crates/victory-gpu/src/host.rs#L2810-L2843) · [Swap-chain format map](https://github.com/Marvisak/VIctory/blob/d732465f64dd868dd0d71811d5596519cdcba889/crates/victory-gpu/src/host.rs#L2273-L2285)

| Typed source | Original SRV | Patched SRV |
| --- | --- | --- |
| `R16G16B16A16_UNORM` (11) | `R16G16B16A16_FLOAT` (10) | 11 |
| `R16G16B16A16_SNORM` (13) | `R16G16B16A16_FLOAT` (10) | 13 |
| `R8G8B8A8_SNORM` (31) | `R8G8B8A8_UNORM` (28) | 31 |

Direct3D 12’s relaxed legacy typed-casting rules still prohibit FLOAT ↔ non-FLOAT and SNORM ↔ UNORM. Its feature level 12.0 requires all three source formats to support Texture2D sampling with filtering. VIctory creates its device at that level. A typed source can supply its own format and a typeless family needs a typed view, as distinguished in the API documentation. [D3D12 casting rules](https://microsoft.github.io/DirectX-Specs/d3d/RelaxedCasting.html#casting-rules-for-rs2-drivers) · [Feature level 12.0 formats](https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/hardware-support-for-direct3d-12-0-formats) · [D3D12 SRV](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device-createshaderresourceview) · [D3D11 SRV convention](https://learn.microsoft.com/en-us/windows/win32/api/d3d11/nf-d3d11-id3d11device-createshaderresourceview)

The patch applies only the three typed source exceptions. The nine comparison cases keep the current selection, including RGBA8 28 used by both observed Series S planes, BGRA8, float, typeless family defaults and the current sRGB policy. The recorded Series S report concerns format 28, so it gives no evidence of these three formats appearing in that title. The pre-existing first-frame fallback and shared-texture alias proposals have independent reproductions. [Failed-frame follow-up](https://github.com/Marvisak/VIctory/pull/1997#issuecomment-7151240824) · [Shared-alias follow-up](https://github.com/Marvisak/VIctory/pull/1997#issuecomment-7151390086)

## CPU check

The harness extracts the actual format function and compositor SRV selection from the pinned and modified source. The pinned source picks three prohibited views. The patch picks the resource’s own typed view in each case. The CPU model also projects opaque blue RGBA8 plus a premultiplied red UNORM16 overlay to `[64, 0, 127, 255]`, using the compositor’s source-over blend. This pixel is a calculation. [CPU results](cpu-results.txt) · [Patch](victory-1997-typed-srv.patch)

```text
git clone --filter=blob:none --no-checkout https://github.com/Marvisak/VIctory.git victory-open
git -C victory-open fetch --no-tags --filter=blob:none origin refs/pull/1997/head
git -C victory-open sparse-checkout set --no-cone /crates/victory-gpu/src/host.rs
git -C victory-open checkout --detach d732465f64dd868dd0d71811d5596519cdcba889
git -C victory-open apply --check ../victory-1997-typed-srv.patch
git -C victory-open apply ../victory-1997-typed-srv.patch
python run_cpu.py --repo victory-open
```

The optional Windows sampling fixture independently selects fully typed resource/SRV pairs and checks `D3D12_FEATURE_FORMAT_SUPPORT` for Texture2D and shader sampling before creating resources. Its CPU oracle passed four numeric controls and a corrupted-result check. In one guarded RTX run all four capability checks succeeded and three formats matched all expected float32 words. `R8G8B8A8_SNORM` exceeded the strict numeric tolerance, so the fixture returned 1. The run measured individual texture samples. [CPU oracle](native-cpu-oracle.txt) · [Native run and limits](NATIVE.md)

Generated source incorporates GPL-3.0-or-later VIctory code. The Windows worker guard is distributed under its included MIT license. [Guard license](LICENSE.guard)
