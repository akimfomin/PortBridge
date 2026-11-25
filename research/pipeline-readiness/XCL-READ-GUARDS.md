# Coalesce identical read guards in XCL pixel shaders

On XCL main `6d12f58a229bc73889878a448c64dc3af25eeba0`, #2118 defers eligible compute waits while graphics recording can still wait for a native pipeline. Separate RTX 5090 measurements reported 14 serial cold graphics creation calls lasting 2.1–4.3 s apiece while the pipeline workers were idle. The same report removed 33 cold compute builds with #2404 and still observed a presentation stall. The title-thread stack establishes the native graphics call but leaves the precise entry through foreground creation or inline resolution open. [XCL measurements](https://github.com/xcl-dev/xcl/issues/2088#issuecomment-7174029302) · [XCL #2118](https://github.com/xcl-dev/xcl/pull/2118) · [Upstream #1833](https://github.com/xcl-dev/xcl/issues/1833)

XCL #2001 already works on removing caller-side native compiles. Continued has shipped bounded parallel exact-PSO creation before submit-side replay. A wider recording rewrite in XCL would have to preserve CPU descriptor contents, references, query/render-pass state, allocators and command order through slots that currently forward directly to the driver. This experiment changes a different stage. It compacts XCL's direct pixel translation without changing command recording or the pipeline creation API. [XCL #2001](https://github.com/xcl-dev/xcl/pull/2001) · [Continued #1547](https://github.com/ubiquitarianism/leonida/pull/1547) · [D3D12 command list semantics](https://learn.microsoft.com/en-us/windows/win32/direct3d12/recording-command-lists-and-bundles)

The prior [PortBridge recording experiment](ORDERED-GRAPHICS.md) measured many expensive native builds on a full open scene. A compact-loop control lowered the absolute cost much further and changed one pixel by one channel unit. That made exact structural compaction in the transcompiler a distinct hypothesis worth testing.

## Implementation boundary

The patch recognizes consecutive guarded regions that use the **same SSA predicate** after the existing optimizer has canonicalized the condition. Each taken arm must contain ordinary read-only DXIL buffer operations and safe bookkeeping. It combines the taken arms in original order while the original inactive path still skips every read. It remaps each join phi to the correct incoming value. Independent integer arithmetic may move ahead of the guard. Read-dependent result selects move after the final join only when they are unused by the second read region or its phi edges. The pass also excludes ROVs, wave operations, derivatives, stores, atomics and additional predecessors.

The proof depends on actual selector equality. Identical shader text, similar registers or offsets within one page do not establish it. An address carry can change windows and therefore make the next guard different. The eligible scope is direct DXIL pixel shaders. HLSL, vertex, mesh and compute paths retain their established optimizers. XCL's translation source hash invalidates its older direct outputs after a rebuild. Diagnostic A/B runs disable the translated cache for both arms. [LLVM SSA and phi semantics](https://llvm.org/docs/LangRef.html#phi-instruction) · [DirectX intermediate language](https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst)

This is an XCL-specific read-region transform. General correlated-branch simplification already exists in compiler passes such as LLVM's jump threading. XCL's new restriction preserves read effects and exact window selection in its own direct translator. [LLVM jump threading](https://llvm.org/docs/Passes.html#jump-threading-jump-threading)

## Measurements on physical D3D12

The workload encodes synthetic RDNA pixel programs with distinct aligned buffer reads and a shared dynamic window selector. The production XCL encoder, decoder and direct DXIL backend translate each program. The D3D12 test creates a graphics pipeline with the resulting shader, renders an RGBA32F image and checks every component against the CPU values. It binds four distinct buffer regions. The small test checked disabled EXEC, address high zero, two nonzero windows and an out-of-range window. With four distinct reads, the shared condition used one branch instead of four. Four different conditions still used four branches and all builds retained all four reads.

The timing campaign on RTX 4070 Ti SUPER, driver 617.14 and Windows 11 build 28000 uses fresh processes with one timed heap shader per arm. Except for the separate warm control, D3D12 accepted requests to disable the implicit D3D and driver-managed shader caches. The vendor-managed control is advisory. Both arms disabled the XCL translated cache. The Windows job capped private commit at 2 GiB. The launcher stopped a run at the system-memory floor or 20-second deadline. An earlier 288-group four-create run stopped before it completed and is excluded. The single-create timing campaign completed all arms. [D3D12 cache controls](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ne-d3d12-d3d12_shader_cache_kind_flags) · [Windows job limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information)

| 224 groups of four reads, median of five process pairs | XCL with pass disabled | XCL with read-guard fusion |
| --- | ---: | ---: |
| Native `CreateGraphicsPipelineState` | 4.084 s | 0.358 s |
| Create, draw and verified readback | 4.115 s | 0.384 s |
| Direct DXIL translation | 128 ms | 128 ms |
| DXIL bytes | 118,516 | 110,140 |
| Peak process private commit | 161 MiB | 148 MiB |

Fusion won each of the five pairs. The median paired native gain was 3.726 s. The distinct-size sweep measured 0.258 → 0.100 s at 96 groups and 15.142 → 1.010 s at 512 groups. Each size in that sweep has one pair. The warm control then recreated the same exact pipeline inside each process in 0.8–1.3 ms. The full timing campaign verified 4,608 pixels against known values. [Per-process data and SHA-256](evidence/xcl-read-guards-rtx4070tis.json)

This measures the full create-and-observe operation in an XCL synthetic graphics test. A native driver speedup from a small byte reduction is possible when the compiler avoids many conditional regions. The input intentionally repeats the eligible shape. Its prevalence, complete application startup benefit, independent AMD behavior and performance on other shader graphs remain unmeasured. XCL #2446 acts on scalar reloads and stays relevant in programs where that is the larger source of redundant work. The timed program uses distinct vector-addressed loads. Compatible exact warmup remains faster when a reusable native pipeline already exists.

The [follow-up](XCL-READ-GUARD-VALIDATION.md) records broader applicability, exact output controls, GPU execution and opaque pipeline cache sizes.

## Reproduce against XCL

The compiler change is `9d461646a51429d364ec03c4660a875a4b1e0c69`. The test revision is `8e4c4a63143702d5e5da79484273143e0b76eb92`, tree `288f0ecc888aa66ac515d4509266768d3a5fd3a0`. Apply the [source-only patch](xcl-read-guards.patch) in a clean checkout of XCL at `6d12f58a229bc73889878a448c64dc3af25eeba0`. The patch carries XCL's [GPL-2.0-only license](../xcl-compact-scratch-adoption/LICENSE-GPL-2.0-only).

```powershell
git apply --index $xclPatch
cargo test --locked -p xcl --lib --no-run
& $clang -std=c++20 -Wall -Wextra -Werror -O2 -static -municode $guardSource -o guarded-test.exe -lpsapi
$testName = 'gpu::dxil::core_tests::graphics_read_guards_match_cpu_pixels'
$env:XCL_READ_GUARD_TEST_GROUPS = '224'
$env:XCL_READ_GUARD_TEST_COLD = '1'
$env:XCL_READ_GUARD_TEST_FIRST_ONLY = '1'
$env:XCL_TRANSLATED_CACHE = '0'
$env:XCL_DXIL_NO_OPT = 'read-guards'
./guarded-test.exe $xclTestExe baseline.log $testName
[Environment]::SetEnvironmentVariable('XCL_DXIL_NO_OPT', $null)
./guarded-test.exe $xclTestExe fused.log $testName
```

Use the test executable path printed by Cargo and [guarded-test.cpp](guarded-test.cpp) as `$guardSource`. Leave `XCL_READ_GUARD_TEST_FIRST_ONLY` unset to exercise all four heap-window controls. The cache API check is explicit. Use a separate process and fresh log for each arm, alternating order for repeats. The draft candidate has not been reviewed by XCL maintainers. XCL requires its own full test and title-smoke gate for an upstream runtime PR.

## Other work checked

| Project | Prior work relevant to this experiment |
| --- | --- |
| XCL | #2446 removes duplicate scalar reloads in vertex and pixel shaders. #2427 replaces guarded heap reads with a different compute-only lowering. #2438 provides native pixel pipeline timing. [Reload CSE](https://github.com/xcl-dev/xcl/pull/2446) · [Compute heap reads](https://github.com/xcl-dev/xcl/pull/2427) · [Timing](https://github.com/xcl-dev/xcl/pull/2438) |
| Continued and Xenia Canary | Continued parallelizes ready-to-submit exact keys. Xenia has a D3D12 software command stream that waits for ready pipelines before materialization. [Continued implementation](https://github.com/ubiquitarianism/leonida/pull/1547) · [Xenia source](https://github.com/xenia-canary/xenia-canary/blob/2da25198960769ccc2baa97529f77485351732fe/src/xenia/gpu/d3d12/d3d12_command_processor.cc#L3952-L3973) |
| VIctory and victory-fork | VIctory has a warm-prebuild change. The fork records bounded upload windows and frame-capture work. [VIctory #2787](https://github.com/Marvisak/VIctory/pull/2787) · [Fork commit](https://github.com/fxceless/victory-fork/commit/79cfdd963aff1b43cac65cb78fd8f0c544f81c70) |
| XBVK and KLBF Lab | XBVK has a concurrent pipeline library and a frame budget. KLBF's current driver workaround is for compute correctness on RDNA4. [XBVK progress](https://github.com/0x0007b/XBVK/issues/3#issuecomment-7156836842) · [KLBF Lab #2](https://github.com/PastiiJay/klbf-lab/pull/2) |
| TuxBox and AnyXboxX | TuxBox improved HLSL-to-DXIL compilation of large pixel shaders. AnyXboxX's current hardware questions concern RDNA2 numerical behavior. [TuxBox #141](https://github.com/brcly/TuxBox/pull/141) · [AnyXboxX #235](https://github.com/LooperSalty/AnyXboxX/pull/235) |
