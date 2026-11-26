# D3D12 cold pipeline and warm draw measurements

The same strict shader transform was tested on DXIL from XCL main `08db802` with the proposed #2501, #2503 and #2557 changes applied. One RTX 4070 Ti SUPER created one ordinary graphics PSO per fresh process. Runs used the two device-local D3D12 implicit shader caches disabled by the test harness, reversed arm order on alternate blocks, and rotated scene order. The OS capped each worker at 512 MiB and kept a six-GiB system reserve. All 24 workers completed. The workload remained a single shader per process. [Hashes and hardware](native-identity.json) · [24 raw samples](native-samples.jsonl)

| Open fragment program | Native PSO creation, median ms, whole → projected | Opaque cache blob, bytes | Process private allocation during creation, MiB |
| --- | ---: | ---: | ---: |
| Mobile NeRF MLP combo | 1,613.45 → 1,448.07 | 370,786 → 322,674 | 130.8 → 116.2 |
| Mobile NeRF Morpheus combo | 1,602.50 → 1,433.52 | 372,114 → 323,042 | 130.6 → 116.0 |
| raylib raymarching | 854.97 → 757.48 | 207,106 → 186,114 | 90.3 → 78.9 |

DXGI's process-local and nonlocal memory counters each showed a median delta of zero at PSO creation. A subsequent ordinary 16 MiB resource calibration is included per sample. The measurements establish reduced CPU private allocation during creation, reduced serializable blob size and faster native creation for these programs. D3D12 did not expose native instruction bytes here. The accompanying [Vulkan comparison](../../vulkan/strict-ssa/draft-overlap/README.md) measured a reported executable size separately. These results leave driver-wide capacity and other adapters unmeasured.

The ordinary D3D12 render used the open raylib scene, two cameras, 800 × 450 pixels, and two independent batches of eight full-screen draws per view and arm. Time below is the median of those two per-draw batch means. One process from the clean-baseline series stopped when the OS reserve dipped before it produced a usable frame, and the same input was measured again after reserve recovered. All 16 admitted output hashes were checked against the corresponding raw float4 readbacks. The reference, projected and previously published Vulkan images match for each camera. The stronger stack's D3D12 times were 7.306 → 6.068 ms (primary; 16.9% reduction) and 7.697 → 6.346 ms (secondary; 17.6%). Clean XCL yielded 7.226 → 6.162 ms and 7.775 → 6.468 ms. These timings cover a warmed offscreen pass. [Clean draw receipts](warm-draws-clean.json) · [Strong-baseline draw receipts](warm-draws-drafts.json)

## Reproduction

1. Use the stage inputs named by the [strong-baseline build and census](../../vulkan/strict-ssa/draft-overlap/README.md). Copy the six matching DXIL files to the names in [native-manifest.json](native-manifest.json), preserving each SHA-256.
2. Use the existing [XCL matrix harness](../../../README.md). Apply [the process-memory sampler](xcl-meter.patch) on top of the PSO measurement harness at XCL revision `f87aa761e01a3d3ef185c474f5d0d2521736799b`. The harness receives already compiled PS bytes and its own XCL revision is separate from the compiler branches being compared.
3. Apply [the small-job option](small-job-guard.patch) to the [existing resource guard](../../../../guarded-test.cpp) and build the guard using the existing C++ toolchain. Run [measure_pso.py](measure_pso.py) with the manifest, guard, XCL release test executable, DXC directory, adapter name, new output directory, `--small-job --blocks 4`. The driver accepts one ordinary PSO per worker. Exact tool hashes are recorded in the identity file.
4. For timed, rendered output use [the dated raylib scene and resource setup](../../open-scenes/README.md) and [draw_raylib.py](draw_raylib.py) with the same inputs and two rounds. Recompute the report by running `python summarize.py .` in this directory. [Checked summary](summary.json)
