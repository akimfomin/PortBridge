# Continued Vulkan image layout coalescing

This two-file follow-up applies to Continued main `3f81d46ac01021bd7517f0cce153f4283bc8dd17`. DadaCap requested independent review of range coalescing while #1284 handles the undo journal. The production change stays in `LayoutTracker::pieces()` and its range visitor. Each initialized rectangle covers the same image aspect, array layers, mip levels and old layout. Each emitted Vulkan call keeps its original scope and command order. Mixed first-use undefined cells keep the existing initialization granularity. The undo and release paths remain those of the checked revision. [DadaCap's reply](https://github.com/ubiquitarianism/leonida/pull/1284#issuecomment-7151040310) · [Vulkan subresource ranges](https://docs.vulkan.org/refpages/latest/refpages/source/VkImageSubresourceRange.html) · [Vulkan memory barriers](https://docs.vulkan.org/refpages/latest/refpages/source/VkImageMemoryBarrier2.html)

[Patch](0001-Coalesce-equal-Vulkan-image-layout-ranges.patch) · [Upstream main](https://github.com/ubiquitarianism/leonida/commit/3f81d46ac01021bd7517f0cce153f4283bc8dd17)

## Measured results

Clang 23.1.6 built both arms. State-map and texture-barrier tests and a synthetic per-cell geometry oracle passed on main and on a clean local merge with #1284 head `2c178819ff68e82ba27ce0677f84b812576ad8bb`. The oracle checked 96 seeded partial ranges, color and depth/stencil aspects, the end-of-range Vulkan sentinels, and ordered enhanced barriers. The combined local merge trees were `944a90a6c07d2fb79a659c7f7ebea03045c188c6` as the baseline and `ddd6b97d01955f63fb15bef6e2ca45e7f5c22a07` with the follow-up. The two combined trees differ only in the files changed by this patch.

| Synthetic case | Baseline | Coalescing |
| --- | ---: | ---: |
| Release barrier records on #1284 and the local main+#1284 merge | 12 | 3 |
| Barrier records across release, discard and transfer transitions in the same ordered calls | 14 | 5 |
| Release allocations in the same fixture | 5 | 4 |
| Same-layout ordering allocations | 0 | 0 |
| Cancellation restores original image layouts, and a later rollback preserves committed changes | Pass | Pass |
| CPU mip or layer stripes, 10×64 | 640 records | 2 records |
| CPU range with one different cell, 10×64 | 640 records | 5 records |

The current-main CPU benchmark measured 18 layouts in eight alternating pairs on each of two logical CPUs. Large stripes reduced partition time by 41.7–47.1%. A single different cell reduced it by 35.4–36.1%. Mostly undefined ranges measured +0.55% and +4.66%. The 8×32 checkerboard measured +1.77% and +16.41%, with noisy pair-to-pair results. These figures cover the CPU partition routine and its output allocation. [CPU 2](evidence/current-main-layout-bench.json) · [CPU 10](evidence/current-main-layout-bench-cpu10.json)

Earlier native Vulkan verification at `b4b7756e` on RTX 4070 Ti SUPER matched 699,040 texels on each arm with Khronos synchronization validation enabled. It reduced 97 records to 13 in the same two Vulkan calls. The current combined revision has CPU verification and a compiled native fixture. The new native run remains open. A rendering or GPU timing comparison remains open.

## Reproduce

Use a public Continued checkout that contains the exact main revision, Clang with MinGW/UCRT for this Windows command line, and Vulkan headers. Run the commands from this bundle folder. Set `$Upstream` to the Continued checkout and `$IncludeDir` to the Vulkan headers include directory.

```powershell
$Candidate = Join-Path $PWD 'coalescing-local'
$Patch = (Resolve-Path -LiteralPath '0001-Coalesce-equal-Vulkan-image-layout-ranges.patch').Path
git -C "$Upstream" worktree add --detach "$Candidate" 3f81d46ac01021bd7517f0cce153f4283bc8dd17
git -C "$Candidate" apply --check "$Patch"
git -C "$Candidate" apply "$Patch"
clang++ -std=c++20 -O0 -static -pthread -DWIN32_LEAN_AND_MEAN -DNOMINMAX -isystem "$IncludeDir" -I "$Candidate/runtime/src" "$Candidate/runtime/test/replay_texture_barrier_test.cpp" -o replay_texture_barrier_test.exe
./replay_texture_barrier_test.exe
```

Under the same flags, compile and run `runtime/test/d3d12_state_map_test.cpp` and `layout_range_oracle.cpp candidate`. For a baseline, build the same cases from an unchanged worktree and pass `baseline` to the oracle. The rollback fixture uses the separately merged #1284 and takes the same argument. The CPU benchmark fixture builds with `-O2`. The benchmark executable takes `baseline` or `candidate`, the logical CPU ID, and the round index (0–7). Alternate which arm runs first.

The patch and synthetic fixtures are distributed under the upstream GPL-3.0-or-later license. The patch SHA-256 is `7663d87ea4b0b5e6a29148db726ed0faff5135d7abe2571442e7db6a0b0374eb`. See the included [license](LICENSE). This evidence was produced with PortBridge and Codex.
