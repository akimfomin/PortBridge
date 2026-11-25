# XCL structural compiler study

UMA Aperture Specialization changed 115 of 194 open pixel entry points under each tested four-window layout. Read Guard Fusion and Root Read Switch Fusion contributed zero additional byte changes in the eight root-window combinations. On two heavy shader entries the three passes together produced no consistent cold compilation gain. A separate reduction in wave mask work cut native pipeline creation by 2.65–2.78× on the same shader inputs. [Lane-local mask evidence](LANE-MASKS.md)

## Corpus and compiler baseline

Every comparison uses XCL main `e1d84b7d9153f86a97d2ec5d209d196046fc0bea` and retains the direct pixel shader scalar reload CSE from #2446. The 194 accepted entries come from pinned Khronos Vulkan Samples, Naga and MiniEngine sources. Microsoft DXV independently validated all eight root-window outputs and all four heap-window outputs for each accepted entry. Exclusions and per-entry hashes are in the manifests. The entries include some identical source compilations. The same synthetic XCL interface is used for every configuration of an entry. [XCL #2446](https://github.com/xcl-dev/xcl/pull/2446) · [Corpus and tool provenance](PROVENANCE.md)

| Comparison | Four root windows | Four heap windows |
| --- | ---: | ---: |
| UMA changed DXIL, alone or combined | 115/194 | 115/194 |
| Read Guard Fusion changed DXIL, including after UMA | 0/194 | 0/194 |
| Root Read Switch Fusion changed DXIL, including after UMA | 0/194 | Outside measured scope |
| Total emitted switches | 963 → 821 | 0 → 0 |
| Total emitted blocks | 6,603 → 6,177 | 3,714 → 3,714 |
| Total emitted raw read call sites | 5,461 → 4,741 | 1,876 → 1,807 |
| Total emitted DXIL bytes | 2,126,012 → 2,098,364 | 1,927,608 → 1,919,548 |

On the root path UMA often replaces a window switch with a single conditional path. The corpus has 142 more conditional branches as well as 142 fewer switches. Static graph size and executed cost need separate measurements. No tested heap output contained an explicit switch.

## Physical cold pipeline creation

Both entries are independently authored Khronos Mobile NeRF shader variants. The D3D12 carrier used the same root signature, placeholder vertex shader and PSO state within each pair. NVIDIA GeForce RTX 4070 Ti SUPER, driver 617.14, Windows build 28000. Five alternating pairs per entry. Each arm runs in a fresh process, supplies no cached PSO, and requires D3D12 to accept disabling its two implicit shader-cache flags. Other internal driver reuse remains possible. The timed interval is `CreateGraphicsPipelineState`. [Raw measurements](heavy-native.json) · [Cache controls](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device9-shadercachecontrol)

| Entry | Baseline median | Combined median | Median paired saving | Opaque PSO cache bytes baseline → combined |
| --- | ---: | ---: | ---: | ---: |
| 071 | 1,762.3 ms | 1,752.3 ms | 26.7 ms | 370,786 → 369,650 |
| 073 | 1,778.9 ms | 1,802.1 ms | 1.9 ms | 372,114 → 370,466 |

Each heavy entry has two exact DXIL hashes across all eight configurations. The four with UMA share one hash and the four without it share the other. Native results therefore cover the byte-distinct treatments. The timing ranges overlap. D3D12 cache bytes are opaque and process commit includes initialization and validation. Neither number establishes native code size or VRAM use. This carrier does not bind the scene resources or draw the original shaders. First-use time, output and GPU execution for these heavy application shaders remain open. [D3D12 GetCachedBlob](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12pipelinestate-getcachedblob)

## Why the combined passes leave the heavy path intact

The passes remove 78 of approximately 44,200 static statements per heavy shader. The unchanged work includes 1,737 wave ballots, 798 quad operations and over 20,000 elementary bit operations per shader. A backward liveness census finds 532 ballot results and 399 quad-operation results per shader with no path to its measured sinks. These are properties of the translated DXIL. The census alone cannot attribute a percentage of driver time to them, or justify dropping helper-lane work, wave feature metadata or any operation with an observable effect. The follow-up isolates mask reconstruction with one change and tests the same heavyweight inputs. [Instruction and liveness counts](heavy-structure.json) · [Physical follow-up](LANE-MASKS.md)

The latest XCL work addresses related but distinct costs. #2535 tests oversized compute shader caching and #2532 reserves scratch for concurrent compute allocations. #2533 reduces per-draw mirror copying, #2530 changes small DirectStorage buffer reuse, and #2526 evicts idle NVIDIA compute pipelines. None implements this pixel mask lowering. #2438 supplies graphics PSO timing. XCL #2368 also records an important negative control: a different root-switch flattening made a 200-load synthetic pixel shader markedly slower on NVIDIA. [#2535](https://github.com/xcl-dev/xcl/pull/2535) · [#2532](https://github.com/xcl-dev/xcl/pull/2532) · [#2533](https://github.com/xcl-dev/xcl/pull/2533) · [#2530](https://github.com/xcl-dev/xcl/pull/2530) · [#2526](https://github.com/xcl-dev/xcl/pull/2526) · [#2438](https://github.com/xcl-dev/xcl/pull/2438) · [#2368](https://github.com/xcl-dev/xcl/pull/2368)

## Ordinary XCL runtime integration

The opt-in patch applies UMA specialization only to the ordinary translated pixel path when the runtime proves a supported aperture and binds the same high address word on draws. Its condition proves that high address words zero and one are outside the aperture and that the aperture cannot wrap. The generated shader still reads the actual base from the draw ABI. All qualifying base addresses therefore share the specialized cache identity. Root and heap layouts, portable and specialized translations, and their failure-cache entries stay distinct. Native graphics cache identity covers the resulting shader bytes. An unsupported ABI or compiler failure uses the generic translation. Native invalid argument retries the generic pipeline once. Device removal and memory exhaustion retain their existing handling.

Use `XCL_DIRECT_DXIL=all` and `XCL_DXIL_PIXEL_READS=1` to select the experiment. Default graphics, offline compilation and two-pass geometry retain the generic path. Both fusion passes remain explicit offline options. The opt-in is provided for review and reproduction. The measured benefit does not warrant upstream adoption on the evidence here. The physical controls check the same 832 expected pixels under each layout, including carry, borrow, disabled EXEC and an unsupported aperture. After building the authored XCL test title, the full XCL workspace run on this GPU reported 1,435 passed, 0 failed and 46 ignored, including tests that executed without their optional Wave64, heap-window or D3D12 debug-layer subcases. A full title smoke comparison and independent AMD or Intel runtime evidence remain open.

## Reproduce

Apply [the matrix patch](xcl-matrix.patch) to the exact XCL main revision above in an isolated checkout. The resulting source tree is `1fd38bfb71473b9d3daea95828245e48108dd84d`. Copy [the aperture example](../corpus/readguard_uma_aperture.rs) into `crates/xcl/examples`, then build it with `cargo build -p xcl --example readguard_uma_aperture`. Feed each pinned extraction manifest to [the matrix runner](combined_matrix.py) with the built example, DXC and DXV. The fully populated per-entry records are available as gzip-compressed JSON. [Khronos root](khronos-root4.json.gz) · [Khronos heap](khronos-heap4.json.gz) · [Naga and MiniEngine root](naga-mini-root4.json.gz) · [Naga and MiniEngine heap](naga-mini-heap4.json.gz)

For the runtime build, apply [the runtime patch](xcl-runtime.patch) after the matrix patch. Local commit `bdc69cfecd1fb462432e14a8343a392299325418` has tree `9204a844d1e9a038224987867e17ebef2bfe91d5`. Build the workspace before running its tests so the repository's authored test title and its DLL exist. Run the aperture read control with `XCL_READ_GUARD_TEST_ROOT_WINDOWS=1` for root views and `0` for the descriptor heap. For cold creation set `XCL_APERTURE_SAMPLE_PS` to a matrix DXIL file and `XCL_APERTURE_SAMPLE_VARYINGS` to its recorded input count. Run only `gpu::dxil::aperture_tests::aperture_open_pixel_pso` in a fresh test process for each arm.

Patches to XCL follow its [GPL-2.0-only license](../../xcl-compact-scratch-adoption/LICENSE-GPL-2.0-only). Shader files and tools come from their original upstreams. The bundle carries descriptions, hashes, source patches and results.
