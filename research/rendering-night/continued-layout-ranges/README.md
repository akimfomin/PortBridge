# Continued layout range coalescing

This test and patch target Continued main at [`b4b7756e8c64e7ae8b310288d543db0e428c0796`](https://github.com/ubiquitarianism/leonida/commit/b4b7756e8c64e7ae8b310288d543db0e428c0796). Its layout tracker emits one piece for a uniform range and one per selected subresource for a mixed range. The patch folds adjacent initialized cells with the same actual Vulkan layout into rectangles within one aspect. Small or unmergeable ranges keep the original path. First-use `UNDEFINED` initialization keeps its existing granularity.

This shares a header with Continued #1284. That PR removes whole-tracker copies during submission. This patch reduces records when a query partitions a mixed layout range. Both improvements can be reviewed independently. [Continued #1284](https://github.com/ubiquitarianism/leonida/pull/1284) · [Vulkan subresource range](https://docs.vulkan.org/refpages/latest/refpages/source/VkImageSubresourceRange.html) · [Vulkan old layout requirement](https://docs.vulkan.org/refpages/latest/refpages/source/VkImageMemoryBarrier2.html)

## Results

The CPU oracle and both registered tests passed. The oracle covers 96 deterministic partial queries, mixed texture layouts, split and coupled depth/stencil, and the ordering of first-use initialization and enhanced transitions. The native Vulkan test used the same two enhanced barriers, with an actual write between them, and checked all texels on an RTX 4070 Ti SUPER. [CPU oracle log](evidence/candidate-v2-layout_range_oracle.log) · [State-map test](evidence/candidate-v2-d3d12_state_map_test.log) · [Barrier replay test](evidence/candidate-v2-replay_texture_barrier_test.log)

| Native Vulkan observation | Baseline | V2 |
| --- | ---: | ---: |
| Enhanced barrier calls | 2 | 2 |
| Enhanced image barrier records | 97 | 13 |
| Correct readback texels | 699,040 | 699,040 |
| Legacy first-use transitions | 16 | 16 |
| First-use zero clears | 8 | 8 |
| Khronos synchronization errors or warnings | 0 | 0 |

Both readbacks had hash `9bb0febb05a89f85`. The fixture uses a 128 × 128 integer texture with eight mips and 32 array layers. It creates no shaders or pipelines. [Native results and provenance](evidence/vulkan-layout-v2-results.json) · [Baseline log](evidence/baseline-vulkan-layout-v2.log) · [V2 log](evidence/candidate-v2-vulkan-layout-v2.log)

| CPU fixture | Pieces, baseline → V2 | Median ns/query, baseline → V2 | Median paired change |
| --- | ---: | ---: | ---: |
| Two-cell mixed | 2 → 2 | 14.25 → 11.77 | −21.4% |
| Uniform, 8 mips × 32 layers | 1 → 1 | 91.22 → 87.16 | −9.4% |
| Repeated mip stripes, 10 × 64 | 640 → 2 | 1,896.00 → 965.34 | −48.9% |
| Repeated layer stripes, 10 × 64 | 640 → 2 | 1,850.27 → 1,030.86 | −42.6% |
| One outlier, 10 × 64 | 640 → 5 | 1,744.04 → 1,132.17 | −37.1% |
| Checkerboard, 10 × 64 | 640 → 640 | 2,030.77 → 2,155.35 | +2.0% |
| Mostly uninitialized, 8 × 32 | 256 → 256 | 749.80 → 875.88 | +10.7% |

The benchmark measures `LayoutTracker::pieces()` with a fresh production output container. It uses eight alternating baseline-first and V2-first pairs on logical CPU 2 of an Intel i5-13600KF. Across all three sizes, the stripe cases improved by 41–69%. The checkerboard paired medians were −2.2% to +2.0% with substantial per-run variation. The mostly uninitialized case still pays an adjacency scan. The distribution of layout patterns in application submissions and the effect on frame time remain open. [All 18 cases](evidence/layout-benchmark-cpu2-v2.log) · [Raw timing pairs and hashes](evidence/layout-benchmark-cpu2-v2.json)

## Files and reproduction

- [Patch](continued-coalesce-layout-ranges-v2-b4b7756.patch), SHA-256 `558f519c15385a2cdc5e37f7fa8ba69d587c63ff04244837d4b338d63f2ff162`
- [CPU correctness oracle](layout_range_oracle.cpp)
- [CPU timing fixture](layout_range_bench.cpp)
- [Native Vulkan readback fixture](vulkan_layout_readback.cpp)

Use two clean Continued checkouts at the pinned revision and apply the patch to one. The following PowerShell commands run from this directory. Set `$baseline` and `$candidate` to the checkout roots. Set `$clang` to LLVM-MinGW `clang++.exe` and `$headers` to the Vulkan-Headers `include` directory. The recorded builds used LLVM-MinGW Clang 23.1.6 and Vulkan-Headers `6802bb4733b63ed5efd3adb308a6c885ef180ea1`.

```powershell
git -C $candidate apply (Join-Path (Get-Location).Path 'continued-coalesce-layout-ranges-v2-b4b7756.patch')
if ($LASTEXITCODE -ne 0) { throw 'Patch did not apply' }
$arms = [ordered]@{ baseline = $baseline; candidate = $candidate }
foreach ($arm in $arms.Keys) {
    $src = Join-Path $arms[$arm] 'runtime/src'
    $test = Join-Path $arms[$arm] 'runtime/test'
    $flags = @('-std=c++20', '-O2', '-static', '-pthread', '-DWIN32_LEAN_AND_MEAN', '-DNOMINMAX',
        '-isystem', $headers, '-I', $src, '-I', $test)
    foreach ($fixture in 'layout_range_oracle', 'layout_range_bench', 'vulkan_layout_readback') {
        & $clang @flags "$fixture.cpp" -o "$arm-$fixture.exe"
        if ($LASTEXITCODE -ne 0) { throw "Build failed for $arm $fixture" }
    }
    & "./$arm-layout_range_oracle.exe" $arm
    if ($LASTEXITCODE -ne 0) { throw "Oracle failed for $arm" }
}
```

The timing executable takes `baseline|candidate`, a logical processor index and a round index. Use identical logical processor and round arguments within each pair. Alternate which executable runs first. Each prints record count, iteration count and elapsed nanoseconds as CSV. The oracle and GPU figures above were also verified in `-O0` builds.

For the GPU fixture, use an installed Khronos validation layer and a native Vulkan 1.3 device. Set `LEONIDA_VK_VALIDATION=1` and `LEONIDA_VK_DEVICE` to the desired adapter name for the test process. Continued's helper enables synchronization validation. If the loader cannot locate the installed layer, `VK_LAYER_PATH` can point to its manifest directory for that process. Run each executable with its corresponding `baseline` or `candidate` argument, sequentially with a timeout. Stop on any validation message, readback mismatch or device error. The fixture omits the helper's optional shader FMA extension, which the recorded validator predates. It still forwards the enhanced barriers to core `vkCmdPipelineBarrier2`. [Khronos validation overview](https://docs.vulkan.org/guide/latest/validation_overview.html)

The patch and fixture sources are GPL-3.0-or-later.
