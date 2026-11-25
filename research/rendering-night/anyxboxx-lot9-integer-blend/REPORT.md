# AnyXboxX lot 9 · Integer render target blend port

LooperSalty reported two refusal classes on NVIDIA in AnyXboxX #186. His local Wave64 port addresses the 15 compute refusals. The remaining graphics pipeline uses `R8_UINT` with blending enabled. AnyXboxX #187 pins its integrated VIctory at `130bf10e1c70278a50ea828954a0e52acde1730a`. PortBridge's public preflight snapshot did not yet index #186 or #187, so the investigation used the original reports and exact source. [Issue #186](https://github.com/LooperSalty/AnyXboxX/issues/186) · [Lot 9 integration #187](https://github.com/LooperSalty/AnyXboxX/pull/187) · [Exact VIctory pin](https://github.com/LooperSalty/victory/commit/130bf10e1c70278a50ea828954a0e52acde1730a)

## Transfer and authorship

pablogonz12 authored the normalizer in VIctory #1152. FrancescoGelosoEterea ported it to victory-fork #51 and reported a successful RTX 5070 Ti check on that fork. The normalizer source in both diffs matches exactly. The original #51 diff fails a direct apply on lot 9 at the mesh hunk. Lot 9 has a second mesh descriptor for depth bounds, and both paths forward `g.blend` directly. The adaptation copies the authored helper verbatim, calls it in ordinary graphics and both mesh paths, and keeps the existing graphics depth-bounds forwarding of the prepared blend descriptor. [Authored #1152](https://github.com/Marvisak/VIctory/pull/1152) · [Fork #51](https://github.com/fxceless/victory-fork/pull/51) · [Lot 9 mesh variants](https://github.com/LooperSalty/victory/blob/130bf10e1c70278a50ea828954a0e52acde1730a/crates/victory-gpu/src/pipeline/host.rs#L855-L917)

D3D12 reads slot 0 for all active targets when independent blending is disabled. Turning off slot 0 alone would incorrectly affect floating targets in a shared descriptor. The helper expands that descriptor to per-target state, then disables blending on the active integer targets. [Microsoft blend descriptor rules](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ns-d3d12-d3d12_blend_desc) · [Render target blend fields](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ns-d3d12-d3d12_render_target_blend_desc)

## Synthetic CPU result

The fixture uses the real Windows 0.62.2 D3D12 descriptor types with the blend expressions extracted from lot 9 and the patched file. Each arm passed four tests covering six input cases on four paths. The counters below are enabled integer slots per path.

| Input | `130bf10` | With adaptation |
| --- | ---: | ---: |
| Shared blend, `R8_UINT` first, float and signed integer targets follow | 2 | 0 |
| Shared blend, `R8_UINT` follows UNORM and float targets | 1 | 0 |
| Independent blend, mixed signed/unsigned and float with different slot state | 2 | 0 |
| Integer already disabled, legal uniform logic operation, or only float and sRGB | 0 | 0 |

Floating/normalized target state, active write masks, and alpha state were preserved. Each already legal test compares the entire descriptor. The fixture models graphics with depth bounds as the forwarding of the descriptor prepared by ordinary graphics. [Baseline log](ab/baseline/test.log) · [Adaptation log](ab/candidate/test.log)

A separate guarded RTX 4070 Ti SUPER run used the same ordinary graphics blend expressions and two original Shader Model 6.0 shaders. With both targets' blending enabled, `CreateGraphicsPipelineState` returned `E_INVALIDARG` (`0x80070057`). The adaptation preserved floating-target blending and returned `S_OK`. Both workers exited cleanly, and both device status checks passed. This establishes the synthetic ordinary graphics PSO result. Integrated mesh creation, rendering impact and timing remain unmeasured. [Native method and logs](native/README.md)

Lot 9 already derives pipeline names from the guest blend descriptor. This adaptation keeps that naming scheme. D3D12 additionally checks the descriptor on load. A library entry from before the patch can miss if its stored descriptor differs. The bundled fork #280 takes the broader route of hashing effective blend state. An initial driver check of the adapted #51 can use a separate empty library, then repeat on the library it populated. [D3D12 load matching](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12pipelinelibrary-loadgraphicspipeline) · [Fork #280](https://github.com/fxceless/victory-fork/pull/280)

## Reproduce

Put this `proof` folder under a checkout at `130bf10e1c70278a50ea828954a0e52acde1730a`. `prepare.py` checks the revision, compares the two original helper texts, adapts the exact file in that checkout, and emits the source-extracted test inputs. `verify.ps1` runs preparation and both small CPU tests using a compatible `windows` 0.62.2 library with `Win32_Graphics_Direct3D12` and `Win32_Graphics_Dxgi_Common`. It takes the Rust 1.100 gnullvm compiler, LLVM-MinGW linker, Windows rlib and its dependency directories as arguments. Use a scratch checkout because preparation writes `host.rs`.

The [local adaptation](anyxboxx-lot9-integer-blend-port.patch) passed both forward checking against the pinned index and reverse checking against the patched file. SHA-256 `d88c03c33be159eb2be7e472c7d7556a9620debb12224b278cdd3e19c20a7545`. [Fixture](fixture.rs) · [Preparation](prepare.py) · [Verification](verify.ps1)
