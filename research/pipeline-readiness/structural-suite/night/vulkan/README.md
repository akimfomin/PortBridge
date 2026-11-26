# Vulkan fragment executable statistics

The stricter same-block optimization keeps every original wave ballot. It reduced the measured GPU time of the translated raylib draw by 18.7–19.1% on two cameras, with exact translated images and a 10.7% smaller Vulkan fragment executable. This separate comparison uses an ordinary upstream baseline. [SSA projection code revision, raw data and reproduction](strict-ssa/README.md)

On one RTX 4070 Ti SUPER, PortBridge's subsequently withdrawn lane-local lowering for XCL reduced the executable for the translated raylib raymarcher from 221,568 to 108,288 bytes. The same instrumented pipelines drew two 800 × 450 camera views in 1.43–1.45 ms each, down from 5.17–5.41 ms. Every translated image agreed bit for bit with the independently run D3D12 path. The original Vulkan program remained faster at 0.63–0.66 ms. [Per-stage reports](physical) · [Draws and image hashes](draws) · [Joined data](evidence.json)

These timings describe warmed batches of eight fullscreen draws, including GPU execution inside the pass. CPU submission, readback, presentation and pipeline construction are outside the timestamp interval. The raymarcher is a guest Wave64 shader. A separate synthetic guest Wave32 shader exposes an adjacent carry-mask error in the liveness analysis used by the experimental lane-local path. The original lowering has been withdrawn. Its data remain available for comparison with the separately implemented SSA projection. [Wave32 counterexample and physical controls](../wave32-carry/README.md)

This Windows probe compiles one graphics pipeline for a selected physical adapter and preserves each driver-reported executable statistic with its type, value, and description. It queries internal representation names and reported sizes. The measurement uses the public Khronos extension. The only fragment inputs tested here are licensed raylib and Khronos shader workloads, plus their XCL direct-DXIL translations. [Extension specification](https://docs.vulkan.org/refpages/latest/refpages/source/VK_KHR_pipeline_executable_properties.html) · [Statistic formats](https://docs.vulkan.org/refpages/latest/refpages/source/VkPipelineExecutableStatisticKHR.html) · [Internal representations](https://docs.vulkan.org/refpages/latest/refpages/source/VkPipelineExecutableInternalRepresentationKHR.html)

The common vertex shader generates a triangle from the vertex index. Pipeline construction fixes one RGBA32F color attachment, unit sample count and triangle-list geometry. The statistics-only mode compiles a 16 × 16 pipeline with capture of both executable statistics and internal representations, without allocating an image or submitting a draw. Its creation interval includes capture overhead. Driver-internal caching is uncontrolled, so a single interval cannot establish cold compile time. The separate raylib draw mode verifies images and measures GPU execution.

## Binding agreement

The original adapted raylib fragment SPIR-V uses one 64-byte fragment push range and no descriptors. XCL DXIL was converted by dxil-spirv at `b540c8a2484eecc7c2155994c806bbd8a8706f41` with the five UAV descriptors rooted individually. Fragment push offsets 0, 8, 16, 24 and 32 provide five physical storage buffer addresses. The raymarching translation has no descriptor sets. The two Mobile NeRF translations additionally declare a runtime sampled-2D-image array at set 0, binding 0. The three signed, unsigned and floating views select the same descriptor category. For these compile-only comparisons, the pipeline layout advertises 64 sampled-image descriptors. The GPU never reads their contents. This is an executable comparison of these exact translated modules and pipeline state. The default DXIL converter mapping aliases sampled images with a storage texel buffer on the heavy modules and must not be used for this layout. [Descriptor arrays](https://docs.vulkan.org/guide/latest/descriptor_arrays.html) · [dxil-spirv revision](https://github.com/HansKristian-Work/dxil-spirv/tree/b540c8a2484eecc7c2155994c806bbd8a8706f41)

The Python entry point invokes Khronos SPIRV-Tools, checks reflected descriptor types, fragment inputs, and push offsets before launching the executable. It verifies minimum module headers and bounds, records the SHA-256 of the inputs and tools, and limits wall time to 45 s per child. The C++ worker checks host memory headroom and installs a Windows process-commit cap of 512 MiB for the source profile and 2 GiB for the XCL profiles. It checks the active fragment module's subgroup requirements against the adapter. Ordinary rendering can proceed without the executable-properties extension. Each process holds at most one pipeline. Exit after the first unsuccessful run.

## Reproduce from source

On the measurement machine the toolchain was llvm-mingw 20261117, Vulkan-Headers `6802bb4733b63ed5efd3adb308a6c885ef180ea1`, SPIRV-Tools and glslang. These example invocations assume the compiler and shader tools are on PATH and `$headers` points to the Vulkan-Headers checkout. The input fragment path, adapter and output file are explicit.

```powershell
clang++ -std=c++20 -O2 -static -Wall -Wextra -Werror -Wno-missing-field-initializers -I "$headers/include" pipeline_stats.cpp C:/Windows/System32/vulkan-1.dll -lpsapi -o pipeline_stats.exe
glslang -V --target-env vulkan1.1 -S vert fullscreen.vert -o fullscreen.vert.spv
python -B run_probe.py --probe pipeline_stats.exe --vertex fullscreen.vert.spv --fragment ray-whole-roots.spv --dis (Get-Command spirv-dis).Source --val (Get-Command spirv-val).Source --device 'NVIDIA GeForce RTX 4070 Ti SUPER' --profile xcl-ray-roots --out ray-whole.json
```

Choose `source`, `xcl-ray-roots`, or `xcl-nerf-roots` as appropriate. `--validate-only` performs CPU-side validation without loading Vulkan. Each report includes provenance hashes, reflected interface, stage flags, SPIR-V size, all statistics, internal representation descriptors, peak process commitment and working set.

## Interpretation on NVIDIA 617.14

The RTX 4070 Ti SUPER exposed the Vulkan FS metric `Binary Size`, which the driver describes as the executable's byte size for that stage. This is separate from SPIR-V size, serialized pipeline cache size, total driver consumption, VRAM, and the D3D12 shader memory budget. The fragment shader binary changes with the driver and complete pipeline configuration. No binary content was retrieved. The driver returned no internal representations for these PSOs. Its `Local Memory Size` values were at least 68,719,476,736 even for the common vertex shader. Preserve those raw results and leave their interpretation open. [Pipeline executable properties](https://docs.vulkan.org/refpages/latest/refpages/source/vkGetPipelineExecutablePropertiesKHR.html)

## Rendering the raylib translation

The render mode accepts the resource-free raymarching fragment with five rooted buffer addresses. Every pointer producer in its SPIR-V is independently checked before submission. The four input variants only perform 12 static 32-bit reads, all from SGPR indices 0–11 in the first root. The worker places the same 128 incoming SGPRs used by XCL's D3D12 reference in that slot, and supplies four 256-byte zeroed guest-memory windows. It verifies the root data and surrounding guards after execution. The readback buffer has its own prefix and suffix guards.

The two 800 × 450 cameras reuse the public raylib scene parameters and OpenGL reference images from the associated corpus study. The worker submits one untimed draw, then five fence-separated render passes of eight timed draws each. Each interval surrounds the eight draws with Vulkan GPU timestamps. The output image comes from the final pass. The worker reads back RGBA32F after a color-attachment-to-transfer barrier and a transfer-to-host barrier. Drawn shaders use the original SPIR-V inputs from the statistics-only mode. The ordinary render omits capture flags. With `--capture-executable`, statistics and draw timings come from the very same pipeline object.

```powershell
python -B run_ray.py --probe pipeline_stats.exe --vertex fullscreen.vert.spv --fragment ray-local-roots.spv --dis (Get-Command spirv-dis).Source --val (Get-Command spirv-val).Source --device 'NVIDIA GeForce RTX 4070 Ti SUPER' --camera $raylibPrimaryCameraDirectory --out primary-local.json
```

The camera directory provides `scene.json`, `sgprs.bin`, and `gl.rgba32f`. Both input files are checked against the recorded camera hashes. Each successful run writes a fresh JSON report and a raw `.rgba32f` image. A 16 × 16 smoke camera precedes the full workload. The two full-resolution camera orders were whole / packed / local-packed / local, then the reverse. The `summarize.py` report checks exact shader identity and image digest equality against the independent D3D12 reference before joining the measured data.

The matching open-scenes study builds the raymarching source at raylib revision `7aeef5775435ed9f57890bf3c1b53279f6b0866a`. Use its `render_raylib.py` and the primary and secondary camera configurations to regenerate the inputs. `run_ray.py` requires NumPy in addition to the tools above. [Licensed raylib shader](https://github.com/raysan5/raylib/blob/7aeef5775435ed9f57890bf3c1b53279f6b0866a/examples/shaders/resources/shaders/glsl330/raymarching.fs)

The whole and local Vulkan inputs were independently regenerated from the corresponding XCL DXIL images. Both regenerated files matched the input SHA-256 values in the physical test records. The published converter source was built with one missing standard-library include for llvm-mingw. [Exact converter binary hash, flags, DXIL and SPIR-V identities](dxil-conversion.json)

```powershell
dxil-spirv ray-whole.dxil --root-descriptor uav 0 0 --root-descriptor uav 0 2 --root-descriptor uav 0 3 --root-descriptor uav 0 4 --root-descriptor uav 0 5 --output ray-whole-roots.spv
```

## Measured results

| Fragment | Whole mask, Vulkan FS bytes | Lane-local | Packed | Lane-local + packed |
| --- | ---: | ---: | ---: | ---: |
| raylib raymarching | 221,568 | 108,288 | 228,736 | 110,208 |
| Mobile NeRF 71 | 455,424 | 238,336 | 441,984 | 243,072 |
| Mobile NeRF 73 | 454,784 | 239,616 | 441,472 | 241,024 |

The common vertex executable was 768 bytes in all 13 captured pipelines. For reference, the original open raylib shader before the XCL translation had 37,704 bytes of SPIR-V and a 50,048-byte fragment executable on this driver. The direct comparison isolates lowering inside XCL. Its overhead relative to the source remains substantial. On all three translations, packed OR in addition to lane-local increased the FS executable size slightly.

| Camera | Original OpenGL, ms | Vulkan whole, ms | Lane-local | Packed | Lane-local + packed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Primary | 0.578 | 5.245 | 1.371 | 5.478 | 1.342 |
| Secondary | 0.649 | 5.532 | 1.520 | 5.510 | 1.403 |

These are per-draw medians. Each of the eight Vulkan images matched the corresponding translated D3D12 image in all 360,000 RGBA32F pixels. The original GLSL reference differs in low bits and some edge pixels. Primary and secondary mean absolute RGB error was 0.000194 and 0.000188, with maximum absolute error in any channel of 0.05482 and 0.05490 respectively. All four Vulkan variants had identical hashes within each camera.

The measured GPU improvement applies to a complete fullscreen procedural draw on this adapter. It does not measure application startup, a game, another vendor, or a released compatibility runtime. GPU timestamps in the initial pass use one process per camera and variant. The two Mobile NeRF inputs share a shader family and are not two independent source projects.

### Independent process and same-pipeline controls

The second set used fresh processes and reversed the order of the translated whole and local runs within each camera. Every row below came from a pipeline that both drew the verified output and returned its own executable statistics. Source Vulkan used the same render target, viewport, vertex shader and timestamp protocol. The source control takes the pinned raymarching SPIR-V via `--original-source --capture-executable`. Its 40-byte push constants encode the same camera, time and resolution as the translated shader's guest-register input.

| Camera | Source Vulkan, ms | Translated whole, ms | Lane-local, ms | Whole/local |
| --- | ---: | ---: | ---: | ---: |
| Primary | 0.662 | 5.171 | 1.425 | 3.63× |
| Secondary | 0.627 | 5.413 | 1.451 | 3.73× |

The actual timed fragment executables were exactly 50,048, 221,568 and 108,288 bytes respectively in both cameras. Their sizes matched the separate statistics-only workers. All translated captures were bit-identical to D3D12. The source-only Vulkan pictures differed from the original OpenGL at p99 by 0.0000300 and 0.0000284. The native Vulkan baseline remains about twice as fast as the improved translation.

The number of SPIR-V blocks was constant across all four translations: 65 for raymarching, 991 for each NeRF. Whole→local decreased the static ballot count from 546 to 54 for raymarching and from 1,739 to 135 for each NeRF. Packed whole reduced these counts further but needed 268 and 868 subgroup ORs, respectively. Removing ballots alone did not predict either the final executable size or execution time. [Joined measurements](evidence.json) · [SPIR-V operation counts](structure.json)
