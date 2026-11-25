# XCL #2126 private replay

Measure scratch size and full dispatch-chain GPU time for the three programs Kalmarv identified. This kit works with the same local shaders and seeded inputs already used by XCL. The report contains the public case labels, dispatch dimensions, scratch size, GPU timing summaries and output comparison counts. [Request](https://github.com/xcl-dev/xcl/pull/2126#issuecomment-7157104814) · [Measurement protocol](https://github.com/xcl-dev/xcl/pull/2126)

## Prepare the two builds

Use private local worktrees from [XCL commit `3283da481077c1962f13f1b4078841662f7a4ccb`](https://github.com/xcl-dev/xcl/commit/3283da481077c1962f13f1b4078841662f7a4ccb). Apply the [pinned compact-slots patch](https://github.com/akimfomin/PortBridge/blob/2e46a3635ee7725860ceec08ca246a2ab14615b9/research/xcl-2126-compact-slots/xcl-2126-compact-slots.patch) in the candidate worktree. Keep the XCL harness build options and shader inputs identical. Build the baseline and candidate chains before entering the timed loop and keep cached artifacts for each build distinct.

```powershell
$base = '3283da481077c1962f13f1b4078841662f7a4ccb'
git worktree add --detach ../xcl-2126-baseline $base
git worktree add --detach ../xcl-2126-candidate $base
git -C ../xcl-2126-candidate apply --check $CompactPatch
git -C ../xcl-2126-candidate apply $CompactPatch
```

The temporary probe in [scratch-aggregate.patch](scratch-aggregate.patch) can be applied to both builds if the harness does not already read `DispatchChain.dwords_per_group`. Apply it after the candidate patch. Set `XCL_SCRATCH_AGGREGATE=1` during chain compilation and associate each emitted `pieces` and `scratch_dwords_per_group` pair with the program the harness is compiling. Compile one case at a time when using the probe. The probe is silent by default. Its line has only the piece count and DWORDs per threadgroup. Turn it off for the measured loop and validate that the split chain actually runs.

## Measure on the same GPU

Measure `ef008c0f` on its existing early-exit and late-shading seeds. Measure `c3ae6819` and `fb1c6d2d` on a representative reproducible input per program. Use identical inputs, dispatch grids and reference outputs in both builds. On the same adapter, driver and D3D12 queue configuration, run a three-second warm-up and take four rounds of twenty GPU timings per build and input. Alternate which build goes first between rounds. Use GPU timestamps around the whole dispatch chain, including the internal barriers, and convert to microseconds with the queue timing frequency. Compare the output words from both builds with the same expected result or whole-program reference.

The baseline stride should match the published counts.

| Program | Pieces | Baseline DWORDs per group |
| --- | ---: | ---: |
| `ef008c0f` | 10 | 45,632 |
| `c3ae6819` | 14 | 54,240 |
| `fb1c6d2d` | 14 | 54,432 |

## Produce a shareable report

Write one JSON Lines row per program, input and build using the fields below. Include eight rows. Use the input labels `early-exit` and `late-shading` for `ef008c0f`, and `representative` for the other programs. Use `baseline` and `candidate` for the two builds. The grid holds the three dispatch dimensions. `gpu_us_rounds` holds four arrays of twenty measurements, in round order. `words_checked` and `different_words` describe the output comparison against the common reference.

```text
case input build grid pieces scratch_dwords_per_group words_checked different_words gpu_us_rounds
```

```powershell
python -I -B compare.py measurements.jsonl > summary.json
```

Review `summary.json` locally before sharing it, then add the GPU model, driver and relevant clock state in prose. Keep the per-run timings, source shaders, input and output buffers and raw logs local. Exit code 1 marks an output mismatch or scratch growth, and exit code 2 reports a malformed or incomplete comparison. Time deltas above zero indicate slower execution. The report shows both aggregate medians and the range of relative changes in the four paired rounds.

## Local verification

The probe is tested against the published Wave32 fixture and the public four-piece fragmentation fixture. The comparator verification injects timing numbers to test the protocol. The native GPU timing and actual scratch on the three title programs require authorized access to those inputs.

```powershell
python -I -B verify.py --census $Census --compact $CompactPacket --rustc $Rustc --linker $Clang
```

The verification command uses Python 3.10 or later, the [pinned XCL fixture census](https://github.com/akimfomin/PortBridge/tree/2012934dd41bf805ac936d2901eca6b31c58acd0/research/xcl-2126-lifetime-census) with its verified sources, and the [compact-slots packet](https://github.com/akimfomin/PortBridge/tree/2e46a3635ee7725860ceec08ca246a2ab14615b9/research/xcl-2126-compact-slots). The Python scripts use the [PortBridge MIT license](LICENSE-MIT). The diagnostic patch modifies [XCL’s dispatch-chain source](https://github.com/xcl-dev/xcl/blob/3283da481077c1962f13f1b4078841662f7a4ccb/crates/xcl/src/gpu/dxil/module/split.rs) and retains its [GPL-2.0-only license](LICENSE-GPL-2.0-only). PortBridge contributors added the opt-in diagnostic on 2026-11-25. XCL contributors, including Kalmarv, authored the original dispatch-chain code and Wave32 fixture.
