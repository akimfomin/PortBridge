# XCL direct DXIL compiler experiment

The current optimizer rescans all reachable PHI instructions after a replacement, even when only a few instructions could change. On a loop-carried chain presented in reverse order, each scan collapses one more node. The implementation in this experiment records two distinct inputs for each PHI that still conflicts. When either representative changes, the optimizer rechecks that PHI in the same logical order as the original sweeps. It reuses two indexed watch slots per pending PHI. Two ordinary sweeps handle short cascades and the first dependency sweep avoids filling the heap up front.

This experiment runs the post-lowering optimizer. Itsmetibo's earlier work batched use replacements during per-lane SSA construction. PR #1818 folds constant control-flow edges before calling PHI simplification. I compared the original optimizer and this version, then separately repeated the comparison over the #1818 head. PortBridge surfaced the related work and helped scope the experiment to the downstream optimizer. [XCL request for shader optimizations](https://github.com/xcl-dev/xcl/issues/1269) · [Earlier lowering experiment](https://github.com/xcl-dev/xcl/issues/1269#issuecomment-7142669751) · [PR #1818](https://github.com/xcl-dev/xcl/pull/1818) · [PortBridge](https://github.com/akimfomin/PortBridge)

## Measurements

Windows, Core i5-13600KF, RTX 4070 Ti SUPER, NVIDIA 617.14, Rust 1.100.0 (gnullvm) and DXC 1.9.2602.17. The base is `1d027e5c76c9a86a7ee2ca1cc677edf0be95d331`. The optimizer, module and bitstream sources are byte-identical in that base and in the checked later main commit `689f2db477c3c062cf162649781640ef8a977c18`. All inputs were generated from source. [Base optimizer](https://github.com/xcl-dev/xcl/blob/1d027e5c76c9a86a7ee2ca1cc677edf0be95d331/crates/xcl/src/gpu/dxil/module/opt.rs) · [Later main optimizer](https://github.com/xcl-dev/xcl/blob/689f2db477c3c062cf162649781640ef8a977c18/crates/xcl/src/gpu/dxil/module/opt.rs)

| Measured path | Synthetic input | Baseline → candidate |
| --- | --- | ---: |
| Whole production optimizer | 8,192 PHIs, reverse dependency chain | 86.562 → 0.402 ms |
| Whole production optimizer | 16,384 PHIs, reverse dependency chain | 349.655 → 0.958 ms |
| Whole production optimizer | 16,384 PHIs, chain after common-subexpression elimination | 338.633 → 0.994 ms |
| Whole production optimizer | 16,384 PHIs, forward chain control | 0.318 → 0.432 ms |
| Whole production optimizer | 16,384 PHIs, all retained control | 0.674 → 0.678 ms |
| Source shader → DXIL | 128 loops, 96 scalar-register copies per loop, switch windows | 19.899 → 18.667 ms |
| Source shader → DXIL | Same shader, heap windows and wave splitting | 25.386 → 23.567 ms |
| D3D12 create to pipeline ready | Wave64 compute readback with 8 stress loops | 7.531 → 7.897 ms |
| D3D12 create to pipeline ready | Same GPU fixture with 32 loops | 14.880 → 14.360 ms |
| D3D12 create to pipeline ready | Same GPU fixture with 128 loops | 42.500 → 41.817 ms |

The first five rows are medians of nine samples in three alternating process pairs with the real production module and bitstream writer. The independent #1818 adaptation produced 345.59 → 0.97 ms on the 16,384 reverse chain in seven measurements per build. The corpus times use the median from seven fresh alternating processes, each with five timed translations per case. In the longest scalar-copy cases the candidate was faster in seven of seven pairs in both modes. The early hash-based implementation was 7–9% slower in those long cases. The indexed implementation removed that regression. Several corpus controls varied by a few percent in either direction.

The GPU fixture used nine alternating process pairs at each size, separate XCL caches and no XCL disk pipeline or translation cache. It includes the adapter driver, which can maintain its own cache. Each of 54 processes used the direct DXIL path with zero HLSL fallbacks and checked all 1,536 readback words from the actual GPU. The candidate was faster in eight of nine pairs at 32 and 128 loops. Median paired differences were +0.421, −0.534 and −0.926 ms at 8, 32 and 128 loops. The first baseline process at each size was slower, so the paired differences are reported alongside the raw samples.

## Correctness and scope

- The bitcode compared equal for all 2,048 mixed graphs, including cycles, multiple backedges and results exposed after CSE. The separate #1818 comparison passed for the same 2,048 inputs.
- All 24 source-generated shaders produced byte-identical DXIL between the builds, aggregate SHA-256 `7cba02fa3dbeb4737814fab931cdbe6d59989c57e752f97d66e48664824bb323`.
- The XCL workspace test command reported 960 passed, 43 ignored and zero failures, including 24 explicit runtime skip reports. The forced direct-DXIL GPU subset reported 441 passed, 19 ignored and zero failures, including 21 runtime skip reports. Runtime skips include unavailable debug facilities and hardware paths.
- Longer chains can impose quadratic repeated scans in the original optimizer. The candidate avoids that scaling on the tested chains. Other graph shapes can still revisit a PHI several times. The index is allocated when the first two sweeps still have work and adds storage proportional to the number of instructions and unresolved PHIs.
- These timings cover compiler and synthetic GPU pipeline paths. Retail launch, frame rate, AMD, Wine and the frequency of these graphs in a representative workload remain unmeasured. The ordinary forward-chain and short-GPU controls show the cost of taking a broader performance claim on this data. Keep the candidate experimental pending upstream review and representative traces.

## Reproduce

Use an XCL checkout with the pinned revisions below, Python 3.10 or later, and XCL's supported Windows Rust/D3D12 build environment. Use the project's build prerequisites and a compatible DXC. The three patches contain upstream context and use XCL's GPL-2.0-only license. The Rust fixtures use the same license. [XCL build and contribution rules](https://github.com/xcl-dev/xcl/blob/main/CONTRIBUTING.md)

1. Make separate baseline and candidate worktrees at `1d027e5c76c9a86a7ee2ca1cc677edf0be95d331`. Apply [xcl-phi-worklist.patch](xcl-phi-worklist.patch) only to the candidate. Fetch the exact `365148bcc935ef04aeb9608debe0d72ba7db866f` #1818 commit into the checkout's object store.
2. From this directory, run `python -I prepare_harness.py --checkout PATH_TO_CANDIDATE` and `python -I run_matrix.py`. Supply `--rustc` or `--linker` when the binaries are absent from the default toolchain paths. The harness generates the independent [#1818 adaptation](xcl-1818-phi-adaptation.patch) and verifies exact outputs before timing.
3. Copy [portbridge_synthetic_phi_corpus.rs](portbridge_synthetic_phi_corpus.rs) into `crates/xcl/tests` in each worktree and apply [xcl-stress-gpu-fixture.patch](xcl-stress-gpu-fixture.patch) in both. In each, set `CARGO_PROFILE_RELEASE_DEBUG=0` and run `cargo test --release --locked -p xcl --test portbridge_synthetic_phi_corpus --test gpu_compute_e2e --no-run`.
4. Run `python -I run_native.py --base BASE_CORPUS_EXE --candidate CANDIDATE_CORPUS_EXE --dxc-dir DXC_BIN_DIR`, then `python -I run_pso.py --base BASE_GPU_EXE --candidate CANDIDATE_GPU_EXE --dxc-dir DXC_BIN_DIR --adapter "RTX 4070"`. Replace the adapter match for another device. Both scripts write raw samples, and the GPU script also writes per-process logs. Keep other compilations and GPU tests idle during timings.
5. In the candidate, run `cargo build --locked --workspace` and `cargo test --locked --workspace --no-fail-fast -- --test-threads=1 --show-output`. Repeat the direct path with `XCL_DIRECT_DXIL=all` and `cargo test --locked -p xcl --lib gpu:: -- --test-threads=1 --show-output`.

[Raw optimizer timings](results.json) · [Whole shader translation](native-results.json) · [GPU pipeline timings](pso-results.json)
