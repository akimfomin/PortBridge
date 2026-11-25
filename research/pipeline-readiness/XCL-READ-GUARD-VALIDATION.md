# Read Guard Fusion on physical D3D12 and open shaders

Read Guard Fusion combines consecutive reads guarded by the same value. It preserves the read order and the inactive path. On an RTX 4070 Ti SUPER it cut cold D3D12 pipeline creation from **4,168.748 to 412.822 ms** for a synthetic shader whose pixels select different memory windows. The ready pipeline took **86.528 and 86.016 μs per draw**. The fixture deliberately repeats the eligible shape. The open corpus found one of 72 affected shaders with one heap window and zero with four heap windows. [Original measurement](XCL-READ-GUARDS.md) · [Corpus and provenance](corpus/README.md)

## Physical measurements

Each row is the median of three paired fresh processes. D3D12 accepted the implicit cache-disable request and XCL's translated cache was disabled. Direct queue timestamps cover 16 identical draws after a priming draw. Each process checks 16,512 RGBA32F output pixels against an explicit CPU result, including separate root-buffer EXEC controls. The smallest fixture is close to timestamp granularity.

| Four-window heap fixture | Cold pipeline, ms | GPU draw, μs | DXIL bytes | Opaque PSO cache bytes |
| --- | ---: | ---: | ---: | ---: |
| Divergent, 1 group | 5.680 → 5.636 | 0.384 → 0.384 | 3,012 → 2,992 | 2,806 → 2,822 |
| Divergent, 32 groups | 38.117 → 32.368 | 12.416 → 12.416 | 18,800 → 17,764 | 9,478 → 10,006 |
| Divergent, 96 groups | 272.662 → 110.127 | 37.440 → 36.992 | 53,564 → 50,560 | 25,798 → 24,662 |
| Divergent, 224 groups | 4,168.748 → 412.822 | 86.528 → 86.016 | 124,524 → 116,140 | 57,958 → 53,622 |
| Mixed guest EXEC, 32 groups | 42.071 → 34.931 | 7.104 → 7.040 | 19,596 → 18,560 | 10,438 → 11,030 |
| Uniform, 224 groups | 3,903.329 → 361.648 | 10.752 → 10.944 | 118,516 → 110,140 | 55,174 → 51,654 |

At 224 divergent groups, basic blocks fell from 1,793 to 447 and conditional branches from 896 to 223. All 896 PHIs were retained. DXIL shrank by 6.7%, and native creation time fell by 90.1%. This supports control-flow structure as an important driver compilation cost for this fixture. Opaque cache size can grow or shrink. Exact native pixel instruction size remains unmeasured. The D3D12 cache payload covers the whole pipeline. The effect on the device-removal threshold in XCL #2403 remains open. [Per-run physical data](evidence/xcl-read-guard-validation-rtx4070tis.json) · [D3D12 cache format contract](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ns-d3d12-d3d12_cached_pipeline_state) · [XCL #2403](https://github.com/xcl-dev/xcl/issues/2403)

## Standard XCL root-window path

The opt-in companion fuses consecutive root-UAV switches with identical SSA selectors and case keys. The default edge still performs no reads, and the corresponding cases retain their read order and PHI inputs. On four root windows at 96 groups it reduced switches from 384 to 95 and blocks from 1,921 to 476. Native creation fell from **531.532 to 246.251 ms**, ready draw from **9.856 to 8.768 μs**, and opaque PSO cache data from **146,582 to 68,726 bytes**. All 384 PHIs were retained. The hardware run also checked mixed guest EXEC, and a separate edge run verified the zero alias, two valid windows and an invalid window. [Four-window prototype patch](xcl-root-read-switch.patch) · [Per-run physical data](evidence/xcl-root-read-switch-rtx4070tis.json)

The root prototype did not change any of the 72 external fixtures, including 26 whose baseline had at least two switches. The single-window Naga hit explains a generic limit: nearby offsets can produce different address carries and different window bounds. A broader rule needs a proof about the actual address ranges. The test adapter replays independently compiled open RDNA2 code through XCL's real converter and validates its DXIL. Its synthetic graphics signature does not reproduce Vulkan descriptor bindings or the source application's rendered outputs. [Corpus boundaries and replay](corpus/README.md)

The seeded review matched output and modeled read order in 81,920 conditional cases and 32,768 switch cases. It exercised differing selectors, case maps, extra edges, dependent addresses, PHIs, stores, atomics, derivatives, wave calls and barriers. The direct core and module suite passed 42 tests on the validation tree and 45 on the switch tree. Each suite had one existing ignored test and zero skips. Independent GPU results, native pixel code size and startup timing of an XCL application remain open.

## Upstream interaction

- With XCL #2446 scalar reload CSE and #2496 using ordinary address carry, the heavy heap experiment improved from 4,194.685 to 414.128 ms. With #2496's optional no-carry mode it improved from 4,120.494 to 405.120 ms. The test's vector reads stay within their windows and do not exercise repeated scalar reloads. No-carry is off by default and can change boundary behavior. [XCL #2446](https://github.com/xcl-dev/xcl/pull/2446) · [XCL #2496](https://github.com/xcl-dev/xcl/pull/2496)
- XCL #2427 excludes direct pixel shaders from flat heap lowering. XCL #2438 provides an independent timing approach with a minimal graphics PSO. Both stacks were checked for source conflicts. [XCL #2427](https://github.com/xcl-dev/xcl/pull/2427) · [XCL #2438](https://github.com/xcl-dev/xcl/pull/2438)
- The external trace establishes that serial graphics creation can dominate startup. Its shader workload was not measured with this pass. [Reference trace](https://github.com/xcl-dev/xcl/issues/2088#issuecomment-7174029302) · [Maintainer's routing](https://github.com/xcl-dev/xcl/issues/2088#issuecomment-7171228065)

## Reproduce and compare

Start with XCL `6d12f58a229bc73889878a448c64dc3af25eeba0` and apply [the original patch](xcl-read-guards.patch), then [the validation patch](xcl-read-guard-validation.patch). The measured source tree is `da9041c146fca228df78cf41a7a25cc8d9fbbc85`, commit `f1e2aa4462e129edd1b025ec5fac3af9709cb934`. The original compiler diff is `9d461646a51429d364ec03c4660a875a4b1e0c69`. For the root experiment also apply [the opt-in patch](xcl-root-read-switch.patch), measured at `e426b25f529acce2945ff38b9d5f17b03c747bae`. [GPL-2.0-only license](../xcl-compact-scratch-adoption/LICENSE-GPL-2.0-only)

Build `cargo test --locked -p xcl --lib --no-run` and use the resulting test executable. Build [guarded-test.cpp](guarded-test.cpp) as in the [original instructions](XCL-READ-GUARDS.md). The launcher enforces time and memory limits. Use a fresh log for each process.

```powershell
$testName = 'gpu::dxil::core_tests::graphics_read_guards_match_cpu_pixels'
$env:XCL_TRANSLATED_CACHE = '0'
$env:XCL_READ_GUARD_TEST_COLD = '1'
$env:XCL_READ_GUARD_TEST_FIRST_ONLY = '1'
$env:XCL_READ_GUARD_TEST_DIVERGENT = '1'
$env:XCL_READ_GUARD_TEST_GROUPS = '224'
$env:XCL_READ_GUARD_TEST_GPU_SIZE = '128'
$env:XCL_READ_GUARD_TEST_GPU_DRAWS = '16'
$env:XCL_READ_GUARD_TEST_STRUCTURE = '1'
$env:XCL_READ_GUARD_TEST_PSO_BLOB = '1'
$env:XCL_DXIL_NO_OPT = 'read-guards'
./guarded-test.exe $xclTestExe baseline.log $testName
Remove-Item Env:XCL_DXIL_NO_OPT
./guarded-test.exe $xclTestExe fused.log $testName
```

Alternate run order. Use 32 groups and `XCL_READ_GUARD_TEST_MIXED_EXEC=1` for the mixed mask control. For the root prototype use 96 groups, set `XCL_READ_GUARD_TEST_ROOT_WINDOWS=1` and `XCL_DXIL_NO_OPT=read-guards` for both arms, then compare `XCL_DXIL_SWITCH_READ_FUSION=0` and `1`. For the four root-window boundary check use one group, unset `XCL_READ_GUARD_TEST_GPU_DRAWS`, and set `XCL_READ_GUARD_TEST_DIVERGENT=0` and `XCL_READ_GUARD_TEST_FIRST_ONLY=0`.

For independent results share GPU and driver, exact revision, pixel-validation status, timing medians and aggregate affected-shader counts from permitted workloads. Each AMD or Intel result is valuable even if it finds no affected shader. A runtime PR needs the matching title-smoke runs and full hardware suite required by XCL. [XCL submission rules](https://github.com/xcl-dev/xcl/blob/6d12f58a229bc73889878a448c64dc3af25eeba0/CONTRIBUTING.md)
