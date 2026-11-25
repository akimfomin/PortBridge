# GPU-resident point geometry

[Blender add-on and integrated edit-to-frame measurements](viewport/README.md).

## Research decision

Investigate whether existing procedural geometry graphs can keep changing point data on the device through selection, concatenation, field updates and drawing. The proposed contract preserves the ordered geometry visible at CPU checkpoints. A GPU node can consume the device view. A known CPU node can request the canonical attributes and rows it uses. An opaque node requires the complete canonical view. The first scope is point clouds. Mesh topology, cross-domain reductions and renderer integration require separate correctness evidence.

Current point deletion evaluates the selection on the CPU and gathers attributes into a new point cloud. Blender's GPU field WIP can retain attributes for other captures and materialize values for CPU consumers. This leaves a boundary between GPU captures and CPU topology or position updates. The latest source has improved input-buffer reuse. The measured official WIP package below is an earlier artifact. [Blender design workshop](https://code.blender.org/2026/10/geometry-nodes-workshop-september-2026/) · [GPU field WIP](https://projects.blender.org/blender/blender/pulls/165697) · [Later input reuse](https://projects.blender.org/blender/blender/commit/fcf919ae8f45a23e0db1b6012ff26897c7add97b) · [Point separation implementation](https://github.com/blender/blender/blob/02f0899d78e374b63e7181d9061e1f7ab03419cc/source/blender/geometry/intern/separate_geometry.cc) · [Procedural point drawing](https://projects.blender.org/blender/blender/commit/9f63eee7107ff07a50123be80f92c32d05a8b813)

In a published urban-planning study, manipulating about 6.4 million Tokyo LiDAR points limited interaction in Blender 4.4. The authors distinguish approximate node timings from viewport rates. Their results motivate a large-cloud holdout with selection, joins and attribute updates. Our separate stock Blender experiment below exercises four edits on the same published tile at its current revision. [Procedural Point Cloud and Mesh Editing for Urban Planning Using Blender, sections 4.1–4.2](https://www.mdpi.com/2073-445X/14/4/815)

## Alternatives investigated

| Candidate | System evidence | Current decision |
| --- | --- | --- |
| Persistent point geometry | The official particle scene reproduces a measurable CPU/GPU boundary across full scene evaluation. The independent LiDAR study establishes a large-cloud interaction case. | Selected. Compare with recent Blender GPU fields and CPU gathers as well as stable compact device IDs. |
| Reuse typed shader graph partitions across materials | Blender reports scene-level cold shader compilation and repeated compilation after topology edits. A severe 5.3 case involved two specific issues with upstream fixes. | Deferred until the remaining duplicated work is measured with both fixes. Slang modules, driver caches and Godot's universal shaders with later specialization are strong existing approaches. [Blender compilation report](https://developer.blender.org/docs/release_notes/5.1/eevee/#material-compilation) · [Inlining fix](https://projects.blender.org/blender/blender/pulls/166581) · [Compilation memory fix](https://projects.blender.org/blender/blender/commit/2e8d044d74c4f60964c41c6ba427305d95b1bfb9) · [Slang specialization](https://docs.shader-slang.org/en/stable/external/slang/docs/user-guide/10-link-time-specialization.html) · [Godot pipeline compilation](https://docs.godotengine.org/en/stable/tutorials/performance/pipeline_compilations.html) |
| Cross-module tile residency for RAW images | In a warm snapshot test, darktable 5.6.2 on the same RTX took 1.87 vs 6.71 s for the pixel pipeline and 29.75 vs 39.65 s for TIFF export on a 103 MP CC0 RAW under normal vs approximately 1 GiB app quota. Single untraced JPEG pairs took 6.19 vs 12.10 s for 103 MP and 4.28 vs 5.72 s for 46 MP. | Deferred. The software quota changes application planning on a 16 GiB card. The normal and quota paths also change math, so equivalent images require further proof. Graph tiling with overlapping regions, existing kernels and reductions has close prior art. [darktable memory controls](https://docs.darktable.org/usermanual/5.6/en/special-topics/mem-performance/) · [Tiling source](https://github.com/darktable-org/darktable/blob/20891f6c6fa7be995e5bf9dff9d1ee5062051773/src/develop/tiling.c#L1517-L1603) · [ADRENALINE](https://cris.unibo.it/bitstream/11585/545761/5/ADRENALINE-MCSOC.pdf) · [OpenVX graph optimizations](https://research.nvidia.com/sites/default/files/pubs/2014-06_Addressing-System-Level-Optimization/openvx_optimization_2014.pdf) |

Houdini separates physical offsets from dense indices and keeps compatible OpenCL nodes on the device. Futhark compiles irregular nested array operations. RXMesh supports dynamic GPU mesh edits. AMD Work Graphs demonstrate GPU-driven procedural topology and drawing. OpenUSD PointInstancer supports stable IDs and masking. Warbler runs simulation on the GPU and reads Blender output attributes back each update. The remaining question is whether the proposed representation preserves existing graph semantics and host observations while outperforming a compact device index stream. [Houdini geometry](https://www.sidefx.com/docs/hdk/_h_d_k__geometry__intro.html) · [Houdini compiled blocks](https://www.sidefx.com/docs/houdini/model/compile.html) · [Futhark flattening](https://futhark-lang.org/blog/2026-07-31-full-flattening.html) · [Dynamic RXMesh](https://doi.org/10.1145/3731162) · [AMD Work Graphs](https://gpuopen.com/learn/work_graphs_mesh_nodes/work_graphs_mesh_nodes-procedural_generation/) · [OpenUSD PointInstancer](https://openusd.org/25.11/api/class_usd_geom_point_instancer.html) · [Warbler source](https://github.com/BradyAJohnston/warbler/blob/ef30fb7032fccc1ab9cddab16f524de198c94c48/warbler/simulation.py#L1877-L1902)

## Physical baseline

Simon Thommes's official CC0 Particle Simulation ran on a physical RTX 4070 Ti SUPER, driver 617.14. The Blender patch build is 5.4 Alpha at `8657240ced44`, dated October 26, 2026. Its Windows ZIP has SHA-256 `0da86f691dd5ffbe22668d7be8e5ad13b975d253530f154f0b0290a3a8e5f09f`. The input hash is `6c8c381c234030d86a25fb34579e60963973fb20482c9e602196db0380f5ac67`. The attachment in the WIP discussion is a separate scene with far more particle births and heavier noise. The measurements use the official demo with its original density and noise detail. [Blender CC0 demo index](https://www.blender.org/download/demo-files/) · [Particle Simulation input](https://download.blender.org/demo/geometry-nodes/simulation/basic_particle_simulation.blend) · [Official WIP build](https://cdn.builder.blender.org/download/patch/blender-5.4.0-alpha%2Bmain-PR165697.8657240ced44-windows.amd64-release.zip)

- Twelve processes replayed all 150 sequential frames. Each pair used the same binary, input and device. In three pairs CPU ran first. In the other three GPU ran first. The timed loop includes scene and dependency graph evaluation through evaluated object access. Startup, viewport drawing, output writing and the diagnostic observer were outside timing. Background GPU activity between blocks varied from 37% to 80%.
- With both Capture Attribute nodes in Auto, median scene time was **2.306 s**. With both nodes allowed to use the GPU, median scene time was **2.857 s**. The paired median slowdown was **23.27%** and each of the six GPU-enabled runs took longer. The eligible computation in the diagnostic run was the integer age capture.
- Logged 120-frame controls observed 119 age dispatches. Blender reported 2,448,860 values uploaded and the same count read back. The CPU run recorded zero. This represents 9,795,440 logical field bytes in each direction. The logs do not give hardware PCIe traffic or isolated transfer wall time.
- Ordered positions matched exactly at frames 2, 20, 70 and 120, for 63,058 total points. A separate observer converted the resulting point cloud into mesh vertices and checked every position component. IDs, lifetime, velocity and shading need further checks for any replacement.
- This measures selective GPU field execution on the actual scene. PortBridge's reference implementation was outside the comparison. [Raw timings](evidence/scene_timing.csv) · [Paired summary and hashes](evidence/summary.json)

## Full point edit in stock Blender

We downloaded the government Tokyo LiDAR tile 09LD1638 from the Tokyo Metropolitan Government Bureau of Digital Services and used all 6,385,097 points. The archive uses the same tile ID as the paper and has a recorded archive update after the paper. The fixture uses its own graph inspired by the paper. It separates by local X and classification, flattens and reclassifies the selected points, then joins the two partitions. All four edits use the same input cloud, centered once in local coordinates. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) · [Tokyo Metropolitan Government data catalog](https://catalog.data.metro.tokyo.lg.jp/api/3/action/package_show?id=t000029d0000000024) · [Official tile](https://japan-pointcloud.s3.ap-northeast-1.amazonaws.com/Tokyo/2024/01/LP/Original/LAS/09/LD/16/09LD1638.zip)

Stock Blender 5.3.0 at `02f0899d78e3` evaluated twelve recomputes on an i5-13600KF. The four per-edit medians ranged from **51.33 to 59.11 ms** for 865,884 to 3,921,967 selected points. This spans the full dependency-graph update after editing the threshold, before drawing or export. In separate checks, all 25,540,388 resulting rows matched an independent oracle for ordered source ID, XYZ, class and untouched intensity. A full snapshot exposes about 146.14 MiB across these columns. That figure is the size of the checked output. Actual transfers and peak allocations require separate measurement. [Stock fixture](tokyo_stock_point_edit.py) · [Input hash, raw timings and output hashes](evidence/tokyo-stock-point-edit.json)

A stronger CPU comparison fuses the same point edit into a two-pass count and stable scatter with reused workers and preallocated arrays. Across 84 timed calls, medians by threshold were **15.87–16.23 ms** with one worker, **9.22–9.54 ms** with four, and **7.73–8.22 ms** with twenty. Twelve full snapshots matched Blender's SHA-256 for all thread counts and thresholds. Timing includes the CPU operation and publication to the output arrays. Setup, Blender integration, drawing and file I/O are outside this standalone scope. These results establish a competitive comparison for the research and help bound how much of the Blender graph latency may come from evaluating and materializing separate nodes. [CPU implementation](tokyo_fused_cpu.cpp) · [Timings and hashes](evidence/tokyo-pooled-cpu-summary.json)

## Reference implementation

[PointView](point_view.py) composes immutable attribute pages with live masks. Selection changes masks and concatenation shares pages. An indexed field uses the dense order of its current view. User IDs, physical slots and logical ranks remain distinct. An observer requests named columns and a logical range from one exact version. Multiple versions can persist until their consumers complete. Explicit rebalancing recovers dead row slots.

The CPU tests exercise 160 steps of births, deletion and indexed writes, verify retained snapshots and cover duplicate occurrences, requested attribute ranges and rebalancing. The caller owns page lifetimes, allocation limits and in-flight versions. The model has no renderer, Vulkan allocator or Blender integration.

Compare against stable compaction of **IDs only**, with attribute columns resident on the device. Both GPU routes must use the same renderer and fallback gathers. Charge logical rank, sparse traversal, rebalancing, CPU synchronization and live allocations to the candidate. Use the unchanged Particle Simulation plus an open large-point editing workflow. Measure input-to-result time including draw or export when that is the actual consumer. Stop pursuing performance if the observed boundaries cannot plausibly change the complete workflow or if the compact-ID route matches the candidate at equivalent correctness and memory.

## Physical correctness check

The Vulkan prototype keeps two point columns in device memory. It applies two successive filters. The second uses the ordered index after the first filter. Each stage projects a requested window into a distinct output range. The CPU oracle compacts physical IDs in stable order and verifies both masks and all returned words. It also checks untouched source and sentinel values outside the requested output.

On a physical RTX 4070 Ti SUPER, five cases covered 5,412 physical slots. Both frontiers agreed for 2,014 observed point rows and 346 mask words across the two stages. The intentional substitution of physical slot for logical rank was rejected at the second mask. The GPU prefix is serial and the limit is 4,096 slots. This check covers the semantics of filters and projections. Algorithm timing, insertion on GPU, rebalancing, CPU interoperability and Blender drawing remain open. [Shaders and harness](physical) · [Device output](evidence/rank-validation.txt)

## Reproduce

Download the input and patch build separately. The runner keeps derived files in a new folder and disables automatic execution from the input. `BLENDER_USER_RESOURCES` isolates Blender user resources. No existing driver caches need clearing. The results carry no cold-cache label.

```sh
python -B -m unittest discover -s research/geometry-residency -v
python -B research/geometry-residency/run_blender_matrix.py /path/to/blender /path/to/basic_particle_simulation.blend /path/to/new-scratch
```

Use stock Blender 5.3.0 for the point-edit experiment. The script creates its own in-memory graph and stores only the measurements and hashes. Blender supplies NumPy. Download the archive separately and preserve dataset attribution when sharing any derived geometry.

```sh
blender --background --factory-startup --disable-autoexec --python-exit-code 5 --python research/geometry-residency/tokyo_stock_point_edit.py -- /path/to/09LD1638.zip /path/to/new-edit-result.json
```

See the [Vulkan instructions](physical/README.md) for the physical correctness check.

For the stronger CPU comparison, build the C++20 program with threading support and a little-endian target. Export the same read-only input, choose a fresh snapshot directory, and run the selected worker count. Compare the four file SHA-256 digests to `validation` in the stock Blender JSON. Each run writes about 613 MB of snapshots after timing. Build and keep derived files in scratch.

```sh
blender --background --factory-startup --disable-autoexec --python-exit-code 5 --python research/geometry-residency/export_tokyo_cpu_input.py -- /path/to/09LD1638.zip /path/to/new-cpu-input.bin
c++ -std=c++20 -O3 -pthread research/geometry-residency/tokyo_fused_cpu.cpp -o /path/to/tokyo_fused_cpu
/path/to/tokyo_fused_cpu /path/to/new-cpu-input.bin /path/to/new-snapshots 20 7
```
