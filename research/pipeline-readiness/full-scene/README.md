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
