# Cold graphics pipelines on an open scene

This replay renders the complete geometry of *A Beautiful Game* in Vulkan and verifies three offscreen images. It measures how the order of creating six graphics pipelines affects the first complete image and the rest of the batch. Two pipelines render the first image. The other four produce the normal and material diagnostic views. Render work and image verification are identical in every policy.

The scene has 49 indexed draws, 1,500,224 instantiated triangles per frame, 15 materials and 33 source textures remapped to a 512-pixel array. Resolution is 1024×768. The renderer uses a small common lit shader with approximation of the glass by alpha blending, along with the two diagnostic shaders. The result characterizes this full open-scene replay and its pipeline workload. It provides neither reference glTF shading fidelity nor a timing estimate for other engines.

## Source and attribution

*A Beautiful Game* original model by MaterialX Project, © 2020 ASWF. glTF conversion by Ed Mackey, © 2022 Ed Mackey. The model and conversion are CC BY 4.0. The prepared input transforms the texture dimensions and uses the simplified shading above. The repository preserves the input manifest and retrieves the files at the pinned open commit during preparation. [Asset and credits](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/e124e8d8d7330a5372bc2b4d00d39a4a9d7997ea/Models/ABeautifulGame/README.md) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) · [Pinned asset manifest](evidence/scene-manifest.json)

## Initial slot-reservation comparison

Each fresh process creates six pipelines using matched shader recipes. Each arm uses its own shader identity. Cold preflight exercises Vulkan's compile-required result and the measured feedback flags qualify the application-cache state. Driver-managed partial reuse is still possible. The warm control primes its in-process application cache before the demand timer.

The first campaign's four blocks showed readback latency gains from reserving a worker in every pair. Its startup and peak host-memory signs were mixed. The failure path in the renderer was subsequently corrected for thread lifetime, and a distinct eight-block campaign used fresh shader identities. These are the medians from that confirming campaign on an RTX 4070 Ti SUPER.

| Policy | Request to verified image | Process start to first image | Lifetime peak private commit |
| --- | ---: | ---: | ---: |
| Three shared demand-priority workers | 60.10 ms | 343.72 ms | 204.33 MiB |
| Reserve one of the three workers | 58.73 ms | 334.35 ms | 202.73 MiB |
| Required pipelines first, after upload | 48.96 ms | 340.68 ms | 206.79 MiB |
| Warmed application cache, primed in process | 20.36 ms | 392.06 ms | 177.94 MiB |

The reserve won four of eight paired request-latency comparisons, with a 0.10 ms median paired advantage. Startup won five of eight with a 9.22 ms paired median advantage, while individual paired differences ranged from an 85.52 ms loss to an 84.76 ms win. Peak commit was lower in seven of eight by a paired median of 1.91 MiB. Those magnitudes and the mixed pilot limit the inference about reserve policy. All 96 output images in the confirming campaign matched their three reference hashes exactly. [Initial raw runs](evidence/reservation-pilot.jsonl) · [Confirming raw runs](evidence/reservation-confirmation.jsonl) · [Confirming summary](evidence/reservation-confirmation.json)

The process memory counters include memory for the benchmark and scene, and measure Windows private commit and working set. Explicit Vulkan allocation bytes are a separate cumulative counter, including temporary allocations. [Windows process memory counters](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex)

## Start the required pipelines during upload

The next paired experiment uses the same complete workload and three workers. Both arms know which two pipelines the first frame needs. The reference starts them after real scene upload. The candidate starts those same two at layout readiness, while the main thread transfers the geometry and textures. Both arms wait for upload and compilation before drawing. The other four pipelines start at or after the common post-upload request. The native timelines show both required calls intersecting upload in every candidate pair and zero overlaps in the reference. [Vulkan pipeline creation](https://docs.vulkan.org/refpages/latest/refpages/source/vkCreateGraphicsPipelines.html) · [Vulkan image-upload synchronization](https://docs.vulkan.org/guide/latest/synchronization_examples.html#image-upload-from-a-cpu-to-a-gpu)

| Observed endpoint | Compile after upload | Compile during upload |
| --- | ---: | ---: |
| Layout ready to verified first image | 65.84 ms | 57.15 ms |
| Layout ready to all three verified images | 102.88 ms | 91.81 ms |
| Full process start to verified first image | 355.12 ms | 323.39 ms |
| Lifetime peak host private commit | 205.76 MiB | 205.79 MiB |
| Lifetime peak host working set | 149.92 MiB | 161.58 MiB |

Layout-ready time covers the real texture and geometry upload, required compilation, the render, and the synchronized image readback. It improved in all eight pairs, with a median paired gain of **8.32 ms** for the first image and **11.00 ms** for all three. All 48 frames matched their corresponding reference images byte for byte, totaling 150,994,944 compared RGBA bytes. Each process created six qualified cold pipelines. Total explicit Vulkan allocations were 93,016,128 bytes in every run.

The full-start measurement includes unrelated setup that finished before the policy took effect. It varied materially between paired processes. The layout-ready endpoint estimates the benefit of overlapping the phases. Peak private commit stayed similar, and peak resident working set rose in all eight pairs. The measured benefit is scoped to this scene on one physical RTX. Use the exact first-frame requirements and maintain both timing and memory comparisons when transferring the approach to another workload. [Raw overlap runs](evidence/overlap-runs.jsonl) · [Overlap summary](evidence/overlap-summary.json) · [Audit](evidence/paired-audit.json)

## Reproduce on Windows

The active sources build the upload comparison and the default four-way reservation experiment. The earlier commit in this branch preserves the exact reservation-only source used for the confirming campaign. The final check used Python with Pillow 13.0.0, LLVM-MinGW, DXC 1.9.2602 and SPIRV-Tools. Set the local tool paths below and a fresh campaign number. The script downloads the pinned scene and independently verifies all three frame hashes per run.

```powershell
$toolPath = 'C:/tools'
python -B prepare.py scene prepared
python -B run.py build build-559 --clang "$toolPath/llvm-mingw/bin/clang++.exe" --headers "$toolPath/Vulkan-Headers/include" --dlltool "$toolPath/llvm-mingw/bin/llvm-dlltool.exe"
python -B run.py run results-559 --executable build-559/scene.exe --scene-dir prepared --dxc "$toolPath/dxc/bin/x64/dxc.exe" --validator "$toolPath/spirv-tools/bin/spirv-val.exe" --adapter 'NVIDIA GeForce RTX 4070 Ti SUPER' --campaign 559 --groups 8 --phase
```
