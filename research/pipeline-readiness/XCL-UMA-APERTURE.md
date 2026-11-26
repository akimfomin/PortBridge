# Proved UMA aperture specialization for XCL pixel reads

XCL emits up to four copy-shaped read arms when an address may select any of four root memory windows. Some shader addresses have a zero high word before a single carry or borrow. A public pixel shader exposed the problem with adjacent offsets of 496, 652 and 332. At low word 0xfffffda8, the offset 652 carries and 496 does not. A corpus census found 19 adjacent pairs with a shared low base and different constant offsets. Conservative interval and known-bits checks proved none of the 19 equivalent. [Address census](evidence/xcl-address-corpus-census.json) · [Earlier Read Guard Fusion result](XCL-READ-GUARD-VALIDATION.md)

## Design

The prototype retains the carry. Its caller supplies the high word of the UMA base already bound in the shader ABI. If the base is at least two and adding the window count cannot wrap, neither a high word of one nor all ones can select a valid window. The original high-word-zero rule still aliases a read to window zero. If the address arithmetic proves the high word is zero or one of those two adjacent values, a four-arm switch becomes one guarded read from window zero. The root path keeps the lazy EXEC select, so inactive lanes do not observe an undefined selector. Stores and atomics keep their selector. The general API and unsupported address shapes keep the original path.

This is a proof about the effective window, independent of whether different loads alias. No loads are introduced on an inactive branch. The low byte address and per-lane order remain unchanged. The independent review checked 383,730 modeled carry/borrow/EXEC cases and counterexamples outside the precondition. The current XCL UMA allocator produces suitable apertures. The prototype requires explicit opt-in from its caller. Integrating it into ordinary XCL runtime compilation requires coupling that proof to the actual bound ABI and keeping generic and specialized shader cache identities distinct. [Compiler source patch](xcl-uma-aperture.patch) · [XCL UMA](https://github.com/xcl-dev/xcl/blob/e1d84b7d9153f86a97d2ec5d209d196046fc0bea/crates/xcl/src/gpu/uma.rs)

LLVM ConstantRange and LazyValueInfo, DXC ValueTracking, Mesa NIR range analysis, and SPIRV-Tools conditional propagation provide generic tools for reasoning about arithmetic and control flow. In a separate scalar model LLVM 22.1.0 -O2 retained the four read arms even when the base load carried a permitted-range annotation. The new lowering uses the XCL-specific window alias contract directly. [LLVM ConstantRange](https://llvm.org/doxygen/classllvm_1_1ConstantRange.html) · [LLVM LazyValueInfo](https://llvm.org/doxygen/classllvm_1_1LazyValueInfo.html) · [DXC ValueTracking](https://github.com/microsoft/DirectXShaderCompiler/blob/main/lib/Analysis/ValueTracking.cpp) · [Mesa NIR](https://docs.mesa3d.org/nir/index.html) · [SPIRV-Tools passes](https://github.com/KhronosGroup/SPIRV-Tools/blob/main/include/spirv-tools/optimizer.hpp)

## Structural coverage

| Four root windows | Accepted inputs | Inputs with fewer switches | Switches | Basic blocks | DXIL bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| MiniEngine and Naga | 72 | 25 | 140 → 101 | 1,514 → 1,397 | 560,236 → 552,388 |
| Independent Khronos Vulkan Samples | 122 | 65 | 823 → 720 | 5,089 → 4,780 | 1,565,776 → 1,545,976 |

All 388 root-mode containers passed independent DXV. Across the two cohorts the pass replaced 142 four-arm switches with a condition. Raw load callsites fell from 5,461 to 4,741. This counts static callsites across alternative paths. In heap mode the same 194 inputs passed both arms. CFG totals stayed equal and DXIL shrank by 8,060 bytes across the cohorts. The Khronos census attempted all 138 pinned fragments. Fourteen inputs were excluded before XCL and two were rejected in both arms. The PAL source adapter uses a synthetic XCL signature without Vulkan resource bindings. The result establishes structural coverage for these shader entries. [Corpus provenance and replay](corpus/APERTURE-CORPUS.md)

## Physical D3D12 on RTX 4070 Ti SUPER

Seven affected open shaders were selected for matching minimal PSO creation. They cover two open-source cohorts and both inexpensive and heavy native compiles. Fresh guarded processes alternated order for five pairs per shader. D3D12 accepted the implicit shader cache disable request. Vendor-managed cache disable is advisory. Times stop at CreateGraphicsPipelineState return. The timing carrier draws no frames and uses no Vulkan resources.

| Source entry | Cold creation, ms | Paired wins | Opaque PSO cache bytes |
| --- | ---: | ---: | ---: |
| MiniEngine MotionBlurFinalPassPS | 37.101 → 35.490 | 4/5 | 11,714 → 11,218 |
| Naga binding buffer arrays | 17.507 → 16.959 | 4/5 | 6,722 → 6,322 |
| Naga texture comparison | 15.896 → 12.774 | 5/5 | 5,170 → 4,114 |
| Naga texture gather | 17.412 → 15.116 | 5/5 | 5,730 → 4,498 |
| Khronos local-read composite | 28.247 → 26.223 | 5/5 | 10,066 → 8,818 |
| Khronos mobile NeRF 071 | 1,673.747 → 1,670.243 | 3/5 | 370,786 → 369,650 |
| Khronos mobile NeRF 073 | 1,737.005 → 1,682.093 | 4/5 | 372,114 → 370,466 |

The reduction is reproducible for several lightweight pipelines. The two heaviest measurements improved by 0.2% and 3.2%. Their median process peak private commit fell by about 1.1 and 1.8 MiB. Process peak includes the harness and compiler, and is separate from any driver heap. The exact native pixel instruction extent remains unavailable. The combined PSO cache payload provides a distinct measurement. Complete application latency, runtime of these open workloads, and the device-removal threshold remain unmeasured. [Per-process data](evidence/xcl-aperture-rtx4070tis.json) · [Microsoft D3D12 cache container](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ns-d3d12-d3d12_cached_pipeline_state)

The separate physical correctness fixture checked 1,664 RGBA32F pixels across root and heap layouts, signed borrow, active and inactive EXEC, and a base of one where the original generic path must keep a read that carries. The small warm draw measured 0.288 μs on both arms, near timestamp granularity. This only checks that fixture. XCL's filtered DXIL module and core suite plus the aperture boundary test passed 37 tests with one existing ignore and zero skips.

## Current upstream

XCL #2496 can change cross-window address semantics. This prototype keeps the per-access carry. #2427 changes compute lowering and may read a real fallback resource in inactive lanes. #2446 handles repeated scalar reloads. #2438 supplies a complementary cold PSO timing approach. #2526 and #2403 concern pipeline residency and opaque cached data. They provide context, while the effect on live native code allocations remains open. [#2496](https://github.com/xcl-dev/xcl/pull/2496) · [#2427](https://github.com/xcl-dev/xcl/pull/2427) · [#2446](https://github.com/xcl-dev/xcl/pull/2446) · [#2438](https://github.com/xcl-dev/xcl/pull/2438) · [#2526](https://github.com/xcl-dev/xcl/pull/2526) · [#2403](https://github.com/xcl-dev/xcl/issues/2403)

## Reproduction

Apply [the compiler patch](xcl-uma-aperture.patch) to XCL e1d84b7d9153f86a97d2ec5d209d196046fc0bea. It reproduces 6f67464c15f2b660c7a018daf6dc91aa06c4b82a's tree. [The test patch](xcl-uma-aperture-tests.patch) adds the test carrier. Build cargo test --locked -p xcl --lib --no-run with the installed DXC. Set XCL_APERTURE_TEST_ROOT and XCL_READ_GUARD_TEST_ROOT_WINDOWS to 1 for root testing and 0 for heap testing, then run gpu::dxil::aperture_tests::aperture_carry_and_borrow_preserve_window_and_exec. The [guarded launcher](guarded-test.cpp) starts an exact test with time and memory limits. For the cold sample test use XCL_APERTURE_SAMPLE_PS with the replayed DXIL file, XCL_APERTURE_SAMPLE_VARYINGS with its count of TEXCOORD inputs and gpu::dxil::aperture_tests::aperture_open_pixel_pso. Use a single float color output and no depth output. The patches follow XCL GPL-2.0-only. [License](../xcl-compact-scratch-adoption/LICENSE-GPL-2.0-only)
