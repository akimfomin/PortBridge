# Lane-local pixel mask lowering

Two open Mobile NeRF pixel shaders spend about 1.7 seconds in a D3D12 pipeline creation call after the address optimizations in the combined study. XCL restores wave-wide masks even when later instructions need only the caller's own carry or comparison bit. This experiment reuses XCL's existing HLSL-backed mask liveness analysis in the direct DXIL path. A certified write produces the EXEC-gated bit for the current lane, in the appropriate half for Wave64. Reads of full masks, writes to EXEC and unanalyzed writes retain whole-wave reconstruction. [Heavy structure census](heavy-structure.json) · [Experimental source](lane-local-masks.patch)

## Physical comparison

The whole-mask control is byte-identical to the combined study's `ags` output. The local-mask arm differs only in mask lowering. Both arms retain the pinned XCL scalar reload CSE. All four DXIL outputs passed independent Microsoft DXV validation. Five paired, alternating, fresh-process measurements used the same synthetic D3D12 PSO carrier and cache controls as the combined study, on RTX 4070 Ti SUPER driver 617.14. The two inputs are variants of one open workload. [Paired timings](lane-mask-native.json) · [Exact DXIL hashes and structure](lane-mask-shape.json) · [DXV receipts](lane-mask-dxv.json)

| Entry | Whole-mask median | Lane-local median | Speedup | Peak process commit median |
| --- | ---: | ---: | ---: | ---: |
| 071 | 1,653.4 ms | 625.0 ms | 2.65× | 234.3 → 158.3 MiB |
| 073 | 1,747.7 ms | 629.0 ms | 2.78× | 233.5 → 158.1 MiB |

The new arm was faster in all ten pairs. Both entries drop from 1,737 to 133 static ballot calls and from approximately 44,100 to 17,400 static statements. DXIL bytes fall from about 283 kB to 118 kB and the opaque D3D12 cache blob from about 370 kB to 179 kB. Peak process commit covers the fixture as well as pipeline creation. The native machine code size, heavy shader execution time and end-to-end scene latency were outside this experiment.

## Correctness and review boundary

Four targeted compiler tests and 19 existing mask-liveness tests passed. The tests verify both mask halves, require an actual local-mask rewrite, retain whole reconstruction with a full VCC reader, and cover an unchanged entry EXEC ballot. A physical synthetic draw on the same NVIDIA GPU compared horizontal and vertical derivatives and coverage at all 2,048 pixels across guest Wave32 and Wave64, including triangle edges. Waterfall iteration counts were checked within the valid range because hardware wave grouping can differ.

A fully inactive quad can be invisible to a wave-wide ballot inside divergent control flow. If a helper in that quad subsequently reaches a derivative, whole-wave reconstruction and lane-local materialization can differ. The existing HLSL local-mask semantics inform the lane-local representation. Current evidence covers the synthetic edge and waterfall cases. It does not establish general equivalence under reconvergence. The research patch uses a separate explicit offline entry point. AMD and Intel, full scene output, GPU time and safe runtime enablement remain open.

The follow-up checks this patch together with XCL's proposed live-lane and bridged EXEC fixes. [Pinned upstream comparison](UPSTREAM-OVERLAP.md)

## Reproduce without game data

Apply [the matrix patch](xcl-matrix.patch) to XCL `e1d84b7d9153f86a97d2ec5d209d196046fc0bea`. Apply [the lane-mask patch](lane-local-masks.patch) on that tree. The resulting Git tree is `233a165c94a98838b7e741ee063339e65471f9fa`. This is an independent branch from the [ordinary runtime experiment](xcl-runtime.patch). Copy [the observer](observe_lane_masks.rs) to `crates/xcl/examples`. Build the observer and XCL test executable with the same DXC and GPU driver. The source inputs are entries `071` and `073` from the pinned [Khronos extraction](PROVENANCE.md).

```powershell
cargo build --release -p xcl --example observe_lane_masks
cargo test -p xcl --lib gpu::dxil::lanes::ps_ballot_tests -- --nocapture --test-threads=1
cargo test -p xcl --lib gpu::recomp::x64_masks::tests -- --nocapture

$env:XCL_DXIL_SWITCH_READ_FUSION = '1'
Remove-Item Env:XCL_DXIL_NO_OPT -ErrorAction SilentlyContinue
& $observer $rdna whole.dxil 64 769 0 1 -1 root-4 4 whole
& $observer $rdna local.dxil 64 769 0 1 -1 root-4 4 local
$env:XCL_APERTURE_SAMPLE_VARYINGS = '0'
# Use a fresh guarded process for each sample shader.
$env:XCL_APERTURE_SAMPLE_PS = (Resolve-Path whole.dxil).Path
& $xclTests --exact gpu::dxil::aperture_tests::aperture_open_pixel_pso --test-threads=1 --nocapture
```

Set `$observer` and `$xclTests` to the built executables and `$rdna` to the extracted entry's `shader.rdna2`. Repeat for `local.dxil`, alternating the order. Keep logs even on failure. Record GPU, driver, commit, skipped checks and pairs. Use the [Windows job guard](../guarded-test.cpp) for the cold test when a driver may consume excessive memory.
