# Application cache reuse across D3D12 and Vulkan

RTX 4070 Ti SUPER. Both experiments use own generated compute shaders and ordinary driver settings. No driver cache clearing or profile change. A seed process creates equivalent pipelines before measurement. A separate process creates or reloads the same six pipelines in each arm. Times exclude reading the application cache files and creating the device. Results describe these inputs and this driver.

| API and process filename | No application cache | Individual cached records | Aggregated cache |
| --- | ---: | ---: | ---: |
| D3D12, fresh filenames | 15.44195 ms | 5.845 ms | 5.39045 ms |
| D3D12, same filename as seed | 2.08530 ms | 2.15375 ms | 2.41580 ms |
| Vulkan, fresh filenames | 21.6791 ms | 1.6584 ms | 1.6673 ms |
| Vulkan, same filename as seed | 0.2597 ms | 0.2319 ms | 0.2281 ms |

The D3D12 summary covers six independent groups with every replay order present in both filename cohorts. In every group the library occupies 4,496 fewer bytes, around 41%, than individual PSO blobs. It measures successful replay through D3D12 methods. [Paired output and cache sizes](d3d12/library-archive-balanced.json)

Vulkan covers three groups with each replay method in each order position. Pipeline feedback was valid for all 144 pipeline creations. Across the replay arms Vulkan reported 72/72 application cache hits, 36 for each representation. Across the no-application-cache arms (including pre-seed controls) it reported 0/54. The combined cache occupies 180 fewer bytes per group, roughly 0.44%. [First group](vulkan/cpu-validated/groups.json) · [Further two groups](vulkan/continuation-219/groups.json)

Filename and representation effects differ with ordinary caches. The test seeds both APIs before the replay arms. Fresh filenames identify separate process names; vendor cache state is uncontrolled. The usefully conservative comparison is the same source program and one backend with its exact controls. Existing XCL work examines an explicitly cache-off profile as a different measurement condition. [XCL #1849](https://github.com/xcl-dev/xcl/pull/1849) · [Vulkan pipeline feedback](https://docs.vulkan.org/refpages/latest/refpages/source/VkPipelineCreationFeedbackFlagBits.html)

See [Vulkan reproduction](vulkan/README.md) and the [D3D12 worker](d3d12/worker.cpp), [fixture generator](d3d12/liveness_pairs.py), [guarded runner](d3d12/run_library_smoke.py) and [summary script](d3d12/summarize_archive.py). Each cache stays on its generating adapter for the experiment.
