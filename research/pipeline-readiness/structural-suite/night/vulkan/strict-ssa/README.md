# Same-block projection of a single guest mask bit

An additional experiment used a newer XCL main and three pending upstream changes. It delivered a 19.2–19.6% reduction in raymarching draw time with exact output. Of 202 validated open shader entries, the projection produced smaller DXIL in 38. [Matched draft stack and results](draft-overlap/README.md)

On an RTX 4070 Ti SUPER, projecting one observed bit from the original four ballots cut the raylib fullscreen draw from 5.177 to 4.210 ms and from 5.446 to 4.404 ms in two 800 × 450 views. The driver-reported fragment executable of the timed pipeline fell from 221,568 to 197,888 bytes. Both translated RGBA32F images matched the independent D3D12 reference bit for bit. The original source Vulkan shader ran in 0.662/0.627 ms in the separate control series. [Raw draws](draws) · [Joined results](summary.json) · [Source control](../README.md#independent-process-and-same-pipeline-controls)

Both translations use XCL main `e1d84b7d9153f86a97d2ec5d209d196046fc0bea`, four generic guest memory windows and the regular upstream optimizer. The opt-in translation is XCL commit `ed8baf5de7bfe73208974d08a570acc95f978437`. It retains all four original ballots. A same-block reader of its exact mask pair can project its own bit directly from the ballot words. Other consumers, including reads of complete mask words, retain the original result. The earlier lane-local experiment has a different implementation, baseline and admission rule. [Upstream base](https://github.com/xcl-dev/xcl/tree/e1d84b7d9153f86a97d2ec5d209d196046fc0bea) · [Earlier experiment and its Wave32 limitation](../README.md)

| Shader | SPIR-V blocks / ballots, both variants | DXIL bytes, whole → projected | SPIR-V bytes, whole → projected | Vulkan FS executable bytes, whole → projected |
| --- | ---: | ---: | ---: | ---: |
| raylib raymarching | 65 / 538 | 177,584 → 151,968 | 634,124 → 532,976 | 221,568 → 197,888 |
| Mobile NeRF 71 | 1,000 / 1,737 | 283,496 → 229,864 | 1,119,532 → 931,488 | 457,984 → 411,264 |
| Mobile NeRF 73 | 1,000 / 1,737 | 283,988 → 230,608 | 1,120,132 → 932,984 | 457,216 → 412,160 |

On the raymarcher, static SPIR-V ORs fell from 3,400 to 914 and logical right shifts from 2,746 to 938. The 528 quad broadcasts, 30 subgroup shuffles, 538 ballots, 16 selection merges and four loop merges stayed constant. This isolates a reduction in the operations reconstructing complete masks. Dynamic instruction counts and the driver's instruction schedule were unavailable. [Original operation counts](draws/primary-whole.json) · [Projected operation counts](draws/primary-project.json)

The driver attributed 168 registers to each raylib fragment stage and 128 to each NeRF stage. The NeRF entries are two shaders from one source family. Only raylib was executed in this comparison. The executable byte count comes from the NVIDIA Vulkan statistic `Binary Size` for an individual stage. The capture exposed neither disassembly nor a driver memory budget. [Conversion identities](inputs.json) · [NeRF stage captures](physical)

An independent symbolic check traces each output bit back to a set of the 256 bits in the four original ballot results' two selected words. All data operations for a fixed lane are shifts, constant masks and OR. The two expressions have identical source sets for all 504 receiver and width combinations checked, establishing equality for any values of those ballot words. This includes arbitrary helper-returned words when the consumer has a defined observation. The width-128 check reproduces the existing XCL selection of the first two words, including its aliasing above lane 63. It establishes equivalence to that baseline, while hardware conformance of wider mappings remains open. [Executable bit-origin check](verify_bit_origins.py)

| Camera | Whole median, ms | Projected median, ms | Reduction | Ranges of eight-draw averages, ms |
| --- | ---: | ---: | ---: | --- |
| Primary | 5.177 | 4.210 | 18.67% | 5.124–5.202 → 4.201–4.227 |
| Secondary | 5.446 | 4.404 | 19.14% | 5.385–5.506 → 4.386–4.411 |

Each camera/variant used a fresh process on one physical RTX 4070 Ti SUPER, driver 617.14, host subgroup 32 and guest Wave64. A process issued an untimed warmup draw and five fence-separated groups of eight identical fullscreen draws. GPU timestamp pairs bracketed the draws inside each render pass. The median is per draw across the five group averages. Each raw file also records the identity and statistics of the bound pipeline. Primary ran projected then whole, secondary ran whole then projected. This experiment supplies no single-frame maximum, presentation latency, end-to-end application frame time or cross-vendor estimate. The original OpenGL raymarcher differs in edge pixels from the translated D3D12/Vulkan path. Mean RGB errors were 0.000194/0.000188 for both variants against original OpenGL. [Image metrics and individual GPU timestamp intervals](draws)

## Reproduction

The camera generator and reference data are in the companion PortBridge commit `caacde46b05b178611a462b28039bf359f64f00a`, under `night/open-scenes`. The experiment did not log concurrent GPU engine utilization. Later timings from the same desktop found background GPU activity. Within this comparison the camera orders were reversed and the five interval ranges remained separated. An idle-machine run on a second physical adapter would establish portability and help quantify background effects.

Use the parent directory's converter flags, worker build and shader tools, along with the licensed raylib camera generator and the two XCL translator entry points. The offline comparison uses `translate_pixel` and `translate_pixel_projected_masks` with identical pixel inputs and options. The six modules in `inputs.json` have expected DXIL and SPIR-V hashes. The raylib D3D12 reference images and OpenGL controls come from the independent open-scenes study. [Vulkan worker, converter and camera instructions](../README.md#reproduce-from-source) · [Module manifest](inputs.json)

For each converted NeRF module, use the parent instructions with `--profile xcl-nerf-roots` to produce a capture via `run_probe.py`. For each raylib module and camera use `run_ray.py --capture-executable` to capture and draw the same PSO. The resulting summary can be regenerated without a GPU with the following command run from the parent `vulkan` directory. The reference corpus path contains `ray800-primary/scene.json` and `ray800-secondary/scene.json`.

```powershell
python -B summarize_projection.py strict-ssa $referenceCorpus strict-ssa/summary.json
```

### Independent check on another GPU

Generate both translated fragments from the same licensed shader and use the same camera, host driver, worker and vertex shader for both runs. Supply the physical adapter name to `run_ray.py`. Omit `--capture-executable` when the device has no executable statistics support. Compare the two local `output_sha256` values first. The saved NVIDIA/D3D12 digest is an additional cross-backend comparison on the original machine. When the images agree, compare per-draw GPU times from each report's five `gpu_ticks` values, scaled by `timestamp_period_ns / (draws_per_interval × 1,000,000)` to milliseconds. Different vendor statistic names and stage sizes are expected.

The two JSON reports for a camera are sufficient for an aggregate comparison. They identify the guest shader, physical adapter, driver, subgroup width and root guards without sending the images or shader binaries. Include the tested XCL revision and whether whole or projected translation was selected. The existing Test Lab issue tracks the broader mask experiment, so label an SSA submission explicitly. [PortBridge Test Lab discussion](https://github.com/akimfomin/PortBridge/issues/87)
