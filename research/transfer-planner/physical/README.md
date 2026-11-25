# Buffer Transfer Planner on a physical GPU

We preserve the planner as a reusable exact reference and deprioritize it as a general upload optimization. On the uncapped workloads, the strong greedy baseline already selected the same plan. The exact optimum could improve the modeled cost under imposed caps. Those controls did not show a repeatable end-to-end gain on both APIs. [Original algorithm and software-only results](https://github.com/akimfomin/PortBridge/tree/d490a4e498bdbd956a3d0a8fd8a057c6bfe11d7a/research/transfer-planner)

## Where an advantage occurred

An observation is a buffer update opportunity. A frame may contribute both vertices and indices. The open-scale group uses actual Dear ImGui draw lists from the built-in demo plus a deterministic scrolling asset list and local transforms sampled from the Khronos Fox glTF clips Survey, Walk and Run. The idle list is unchanged. The separate scaled control replicates the Fox Walk animation at 64 evenly spaced phases. Each scenario has 180 transitions, and the census scans all of them.

| Corpus subset | Observations | With changes | Strict model wins at setup scores 2 / 8 / 14 / 32 |
| --- | ---: | ---: | ---: |
| Uncapped open scale | 1,260 | 596 | 0 / 0 / 0 / 0 |
| Uncapped 64-instance control | 180 | 180 | 0 / 0 / 0 / 0 |
| ImGui with imposed 4 KiB cap | 720 | 56 | 0 / 0 / 0 / 12 |
| Replicated Fox with imposed 64 KiB or 4 KiB cap | 360 | 360 | 0 / 360 / 360 / 360 |

Setup scores are model hypotheses in units of 64 bytes. They do not estimate device time. At setup 8, the greedy model scores for capped replicated Fox improve by 0.30% and 2.60% under the 64 KiB and 4 KiB caps respectively. The study estimates incidence in these observed footprints. It supplies no production-wide frequency estimate. [Full census](evidence/trace-census.csv)

## Physical chain

We timed planning, staging, recording, one queue submission, the transfer, compute consumption and a CPU-observed fence on a physical RTX 4070 Ti SUPER with the NVIDIA 617.14 driver. Each API used three fresh processes at setup score 8 and one at setup score 14. Each process used the same 24 uniformly spaced midpoint epochs per case, seven measured repeats per strategy, and three strategies. All 56,448 timed chains passed complete destination and compute-output checks. The comparison verifies equal epoch IDs, region counts, copied bytes, and model scores per strategy across APIs.

The table shows percentage differences in chain time versus greedy, using the sum of per-epoch medians per process. Negative values are faster. The open-scale column includes only uncapped cases with at least one active selected epoch, excluding the replicated control.

| API / setup | Open scale | Replicated Fox with 64 KiB cap | Replicated Fox with 4 KiB cap |
| --- | --- | --- | --- |
| D3D12 / 8 | −1.9, +2.1, +0.5 | +20.0, +12.0, +6.8 | +12.1, +5.6, +1.5 |
| Vulkan / 8 | −9.7, +8.0, +11.7 | +22.8, +41.6, −0.4 | −11.8, +35.1, +26.0 |
| D3D12 / 14 | −0.3 | +3.6 | +14.3 |
| Vulkan / 14 | −1.1 | −16.5 | +6.8 |

The active desktop shared the GPU. Boundary snapshots ranged from 43 to 78% utilization. Identical-plan controls also fluctuated. This limits timing interpretation, especially for small differences. The result supports ordinary coalescing over exact dirty spans in the uncapped replicated primary runs. Greedy obtains the same copy plan, so that gain cannot be attributed to exact optimization. In the artificially constrained D3D12 cases, the additional planning work did not pay for itself.

The workload supplies update footprints. The runner supplies deterministic contents and a compute consumer that reads the entire buffer. Dear ImGui normally writes mapped upload buffers on D3D12, and this replay does not time the native application pipeline. Geometry is padded to the largest captured extent. Fox uses a 64-byte local-transform record per node. The raw packages, description of the timers and matched summaries are available for review. [ImGui D3D12 backend](https://github.com/ocornut/imgui/blob/f5befd2d29e66809cd1110a152e375a7f1981f06/backends/imgui_impl_dx12.cpp) · [Paired study method](PAIRED-STUDY.md) · [Raw measurements and telemetry](evidence/raw) · [Primary](evidence/paired-setup8-summary.json) · [Sensitivity](evidence/paired-setup14-summary.json)

## Reproduce

Run from this directory in a Windows PowerShell session with Python and a C++20 compiler. The validated compiler was llvm-mingw 20261117 UCRT x86_64, Clang 23.1.6. Set `$imgui`, `$fox` and `$vulkanHeaders` to the local source directories below.

- [Dear ImGui v1.91.9b, f5befd2d](https://github.com/ocornut/imgui/tree/f5befd2d29e66809cd1110a152e375a7f1981f06), MIT, Omar Cornut.
- [Khronos Fox, e124e8d8](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/e124e8d8d7330a5372bc2b4d00d39a4a9d7997ea/Models/Fox), use the `glTF` subdirectory with `Fox.gltf` and `Fox.bin`. Credit for the original CC BY 4.0 Fox asset goes to PixelMannen, tomkranis, Asobo Studio and scurest. The experiment derives changed ranges from animation data and redistributes no Fox files. [License](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/e124e8d8d7330a5372bc2b4d00d39a4a9d7997ea/Models/Fox/LICENSE.md)
- [Vulkan-Headers, 6802bb47](https://github.com/KhronosGroup/Vulkan-Headers/tree/6802bb4733b63ed5efd3adb308a6c885ef180ea1). Use [DXC](https://github.com/microsoft/DirectXShaderCompiler) with SPIR-V support. The measured shader was compiled with dxcompiler 1.9.2609.5.

```powershell
clang++ -std=c++20 -O2 -static -I $imgui capture_imgui.cpp "$imgui/imgui.cpp" "$imgui/imgui_draw.cpp" "$imgui/imgui_tables.cpp" "$imgui/imgui_widgets.cpp" "$imgui/imgui_demo.cpp" -o capture-imgui.exe
.\capture-imgui.exe | Set-Content -Encoding ascii imgui.pbtrace
python capture_fox.py $fox | Set-Content -Encoding ascii fox.pbtrace
python prepare_traces.py imgui.pbtrace fox.pbtrace .
Get-FileHash -Algorithm SHA256 open-all.pbtrace
clang++ -std=c++20 -O2 -static -Wall -Wextra -Werror -I .. ../planner.cpp trace_census.cpp -o trace-census.exe
.\trace-census.exe open-all.pbtrace
clang++ -std=c++20 -O3 -static -Wall -Wextra -Werror -I .. ../planner.cpp d3d12_physical_benchmark.cpp -ld3d12 -ldxgi -ld3dcompiler_47 -o d3d12_transfer.exe
clang++ -std=c++20 -O2 -static -Wall -Wextra -Werror -Wconversion -Wsign-conversion -I .. -I "$vulkanHeaders/include" ../planner.cpp vulkan_physical_benchmark.cpp -o vulkan_benchmark_reset.exe
dxc -spirv '-fspv-target-env=vulkan1.0' -T cs_6_0 -E main -Fo consumer_vulkan.spv consumer_vulkan.hlsl
```

The combined trace SHA-256 is `8be3a039ef5957eb571b1fdd749ab112dd8befb540811da2e64b0269e0488502`. Use the full trace with the midpoint selectors and exact hardware flags in [the replay commands](PAIRED-STUDY.md#replay-commands). Vulkan uses the system loader and rejects fallback to a software or mismatched device. D3D12 also checks the named hardware adapter.
