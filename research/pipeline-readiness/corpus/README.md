# Read Guard Fusion on public pixel shaders

The XCL pass changed one of 72 validated external shader entries with a one-window heap. It changed none of the same entries with four heap windows. An experimental companion pass for four root UAV windows also changed none. The result establishes that an independently written shader can reach the original pass through XCL, with narrow applicability in this sample.

| Input set and window layout | Eligible for comparison | Changed |
| --- | ---: | ---: |
| MiniEngine HLSL, one heap window | 22 | 0 |
| Naga SPIR-V snapshots, one heap window | 50 | 1 |
| Same external sources, four heap windows | 72 | 0 |
| Same external sources, four root UAV windows, read-switch prototype | 72 | 0 |
| Existing public XCL test fixtures, profiles selected by each test | 27 | 0 |
| Explicit XCL equal and unequal predicate controls | 2 | 1 |

The sole external hit is Naga's binding-array conformance shader. Read Guard Fusion removed four basic blocks and two conditional branches while preserving 209 PHIs and 60 raw read calls. DXIL container size fell from 38,628 to 38,608 bytes. The source uses descriptor arrays with uniform and varying indices, texture reads and writes. With four heap windows its generated DXIL was byte-identical between arms. [WGSL source](https://github.com/gfx-rs/wgpu/blob/c76dea031c688ecef0050dbf60506fff128fb23f/naga/tests/in/wgsl/binding-arrays.wgsl) · [Compiled SPIR-V snapshot](https://github.com/gfx-rs/wgpu/blob/c76dea031c688ecef0050dbf60506fff128fb23f/naga/tests/out/spv/wgsl-binding-arrays.spvasm)

The four-window dump explains one rejected group in the same shader. Offsets 496, 652, and 332 share an address base and lane predicate, but XCL computes a separate address carry and bounds check for each offset. For a low address word of `0xfffffda8`, the 496-byte offset stays in its original memory window while the 652-byte offset carries into the next window. At the final accessible window, the two reads can have different validity. The root-UAV build also emits separate switch selectors. Proving a common address range in the translator would be necessary before a narrower shared predicate could be reused for these loads. The replay commands below emit these disassemblies in entry 029 of their output folders.

All 288 external heap DXIL outputs, 144 root-UAV DXIL outputs, and 58 XCL fixture outputs passed independent Microsoft DXV validation. The paired heap trials used one XCL binary and changed only `XCL_DXIL_NO_OPT=read-guards`. The paired root-UAV trials used one separate XCL binary and changed only `XCL_DXIL_SWITCH_READ_FUSION=1`. The root-UAV baseline emitted at least one switch for 35 entries and at least two for 26 entries. The equal-predicate positive control removed three conditional branches and retained all seven raw reads. No native D3D12 code, draw timing, Vulkan output, or XCL application behavior was measured by this experiment.


Source patches and the Rust example are provided under the [XCL GPL-2.0-only license](../../xcl-compact-scratch-adoption/LICENSE-GPL-2.0-only). The corpus files record metadata and hashes. Vendor tools and source shader inputs are obtained from their pinned upstreams.


## Source provenance and scope

- MiniEngine uses every Pixel `FxCompile` entry in the pinned project, compiled with DXC 1.9.2609.5, Shader Model 6.2, HLSL 2021 and HLSL optimization enabled. Its 24 attempted entries include postprocessing, motion blur, upsampling, particles and rendering overlays. Two bicubic shaders require executable relocations for a constant table and cannot be safely extracted as standalone shader instructions by this adapter. [MiniEngine project](https://github.com/microsoft/DirectX-Graphics-Samples/blob/68a2b1e97f71642924e74c7757ca21756ad221b5/MiniEngine/Core/Core.vcxproj) · [MIT license](https://github.com/microsoft/DirectX-Graphics-Samples/blob/68a2b1e97f71642924e74c7757ca21756ad221b5/LICENSE)
- Naga uses every Fragment entry in its pinned SPIR-V snapshots, assembled for each declared SPIR-V version. Two of 52 attempted entries failed validation under the selected Vulkan 1.2 environment. The JSON preserves the uniform-buffer layout and SampleMask diagnostics. Some of the 72 entries share generated code. They represent 56 distinct RDNA instruction hashes. Forty entries emitted at least two raw read calls in the one-window baseline. [Naga snapshot directory](https://github.com/gfx-rs/wgpu/tree/c76dea031c688ecef0050dbf60506fff128fb23f/naga/tests/out/spv) · [MIT](https://github.com/gfx-rs/wgpu/blob/c76dea031c688ecef0050dbf60506fff128fb23f/LICENSE.MIT) · [Apache-2.0](https://github.com/gfx-rs/wgpu/blob/c76dea031c688ecef0050dbf60506fff128fb23f/LICENSE.APACHE)
- The XCL test observer records already existing source-authored fixtures, including helper-lane masking, atomics/stores with ROVs, texture operations, raw loads, and a 1,500-load input. The positive and negative predicate cases are the test pair added with Read Guard Fusion. The observer is built only into the test executable and writes nothing unless `XCL_OPEN_PS_DUMP` is set. [XCL baseline source](https://github.com/xcl-dev/xcl/tree/6d12f58a229bc73889878a448c64dc3af25eeba0)

The experiment uses AMD's standalone `amdllpc` shipped with Radeon GPU Analyzer 2.12. It compiles the validated SPIR-V to gfx1030 PAL ELF. The probe extracts `_amdgpu_ps_main` only if its instructions require no text relocations. It uses the PAL wave size, input enable flags, interpolant count, and color and depth exports for a synthetic XCL signature. All 72 successful external inputs compiled in Wave64. Vulkan resource descriptors, exact varying interpolation and D3D12 pipeline bindings have no implementation in this probe. Treat the data as a structural census of actual XCL DXIL output. The 1/72 figure describes this selected sample. Runtime prevalence, semantic agreement with the source shader and physical-device performance require separate evidence. [AMD standalone compiler](https://github.com/GPUOpen-Drivers/llpc/blob/dev/llpc/docs/amdllpc.md) · [ELF code objects](https://llvm.org/docs/AMDGPUUsage.html#elf-code-object) · [AMD register metadata for gfx103](https://chromium.googlesource.com/chromiumos/third_party/mesa/%2B/a11d1bd247df18057ecb9945e01bf39ff85d8d9d/src/amd/registers/gfx103.json)

## Reproduce

Check out XCL at `8e4c4a63143702d5e5da79484273143e0b76eb92` from the original PortBridge Read Guard Fusion bundle. This revision contains the optimization in `9d461646a51429d364ec03c4660a875a4b1e0c69`. Use an isolated Windows checkout. Place `readguard_open_ps.rs` under `crates/xcl/examples/` and build it using `cargo build -p xcl --example readguard_open_ps`. For the fixtures, apply `xcl-fixture-observer.patch` and use `cargo test -p xcl --lib --no-run`. The evidence build used rustc `1.100.0` (`0ef1bc386`, `x86_64-pc-windows-gnullvm`). The example uses only public XCL library functions.

Use Python 3.12, pinned source checkouts, DXC 1.9.2609.5, DXV from the DXC 1.9.2602 x64 package, SPIRV-Tools v2026.4-119 (`g3c8fd352`) and `llvm-readobj.exe` from Radeon GPU Analyzer 2.15. Download RGA 2.12 for its `utils/amdllpc.exe` (`928501ebdafcb4c1e20af5c39fed45cd69a402aaa73be453d2d6de50eae9215a`). The RGA 2.12 ZIP SHA-256 is `31b25e1b3398a2ebaadb2531034e431252c5acdca16ebd7b407ff19062527516`. Both paths use portable tools from the vendor packages. RGA 2.15's compiler rejects gfx1030. [RGA 2.12](https://github.com/GPUOpen-Tools/radeon_gpu_analyzer/releases/tag/2.12) · [RGA 2.15](https://github.com/GPUOpen-Tools/radeon_gpu_analyzer/releases/tag/2.15) · [DXC releases](https://github.com/microsoft/DirectXShaderCompiler/releases)

```powershell
python -B fixture_census.py --xcl-tests <xcl-test.exe> --dxc <dxc.exe> --dxv <dxv.exe> --output fixtures
python -B open_pixel_census.py --mini <MiniEngine-repository> --naga <wgpu-repository> --dxc <dxc.exe> --dxv <dxv.exe> --asm <spirv-as.exe> --val <spirv-val.exe> --llpc <amdllpc.exe> --readobj <llvm-readobj.exe> --xcl <readguard_open_ps.exe> --out open-pixels
python -B replay_root_switch.py --input open-pixels/open-pixel.json --xcl <switch-enabled-example.exe> --dxc <dxc.exe> --dxv <dxv.exe> --patch xcl-root-switch-probe.patch --out root-switch
```

For the root-switch experiment apply `xcl-root-switch-probe.patch` to an isolated XCL checkout before building the same example. The patch's SHA-256 is `c901a9cf6900b2f2ac59c62d113366dc60397b3c036a1d665aa9bcdda4836c0c`. The runner asserts that every retained RDNA input hash matches the preceding census and compares emitted bytes after validation.

[In-tree fixture evidence](fixture-census-complete/fixtures.json) · [External census](open-pixel-census-final/open-pixel.json) · [Four root windows](switch-census-final/root-switch.json)
