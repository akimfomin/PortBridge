# Vulkan application cache replay

This Windows fixture compares six small source-generated compute pipelines in fresh processes with the normal installed Vulkan driver. It records pipeline creation with no application cache, one combined application cache and six per-pipeline application caches. Each shader stores an integer XOR of its invocation ID and its unique salt. The fixture creates pipelines without dispatching them.

The seed creates one pipeline in each of six empty caches and merges those caches into a seventh. Separate and combined files come from that one set of pipeline creations. A disjoint, matched shader bundle without an application cache is measured before the seed to give a first-seen reference. No application cache is passed in the absent arm. Implicit driver caches can contribute to every arm. A copied executable name is an observable test condition. Driver cache keys and first production startup latency remain unknown. [Vulkan pipeline cache data](https://docs.vulkan.org/refpages/latest/refpages/source/vkGetPipelineCacheData.html) · [D3D12 driver-cache discussion](https://github.com/xcl-dev/xcl/pull/1849)

## Build and check on the CPU

From this directory in PowerShell, use the existing x64 LLVM-MinGW compiler and pinned Khronos headers. The compiler and shader checks use the files already present in the workspace.

```powershell
$clang = (Resolve-Path ../Leonida-portable-vulkan/tools/llvm-mingw-20261117-ucrt-x86_64/bin/clang++.exe).Path
$headers = (Resolve-Path ../Leonida-portable-vulkan/tools/Vulkan-Headers-6802bb4733b63ed5efd3adb308a6c885ef180ea1/include).Path
& $clang -std=c++20 -O2 -Wall -Wextra -Werror -Wformat=2 -D_WIN32_WINNT=0x0A00 -static -municode "-I$headers" probe.cpp -o portbridge-vulkan-cache.exe -lbcrypt -lpsapi
./portbridge-vulkan-cache.exe self-test
python -I -B replay.py prepare cpu-validated --campaign 218 --groups 1
```

The self-test checks the job memory cap and process cleanup at the deadline. The preparation command uses DXC and independently validates each SPIR-V module for Vulkan 1.1 with SPIRV-Tools. The resulting manifest records the source, tools, per-module SHA-256, bundle digest and unique salts. For another run choose a new directory and an unused campaign number. One group is adequate to check operation. Six groups counterbalance all three arm orderings for same and fresh executable names.

Outside the PortBridge workspace, set `$clang` to your x64 LLVM-MinGW `clang++.exe` and `$headers` to the Vulkan header `include` directory in the build command above. Then pass `--dxc <path-to-dxc.exe>` and `--spirv-val <path-to-spirv-val.exe>` to `replay.py prepare`. Python 3.10 or later is required. [LLVM-MinGW](https://github.com/mstorsjo/llvm-mingw) · [Vulkan-Headers at the checked revision](https://github.com/KhronosGroup/Vulkan-Headers/tree/6802bb4733b63ed5efd3adb308a6c885ef180ea1) · [DXC](https://github.com/microsoft/DirectXShaderCompiler) · [SPIRV-Tools](https://github.com/KhronosGroup/SPIRV-Tools)

## Run one campaign on the selected adapter

Use the exact reported adapter name. The native parent starts one suspended child, assigns it to a Windows job and resumes it only after the memory limit is active. It needs at least 4 GiB free system commit and 6 GiB physical RAM beforehand. It stops the child below 3 GiB commit or 4 GiB physical RAM, or after three seconds. Run during an exclusive GPU slot. The first error stops the campaign and the attempt log retains the completed observations.

```powershell
python -I -B replay.py run cpu-validated --adapter 'NVIDIA GeForce RTX 4070 Ti SUPER'
```

The loader comes from Windows System32. The source uses the driver and layers selected by the ordinary Vulkan configuration. The worker verifies adapter, driver and Vulkan cache UUIDs and the inputs used by each arm. It rejects a mismatched archive header before passing bytes back to Vulkan. [Vulkan cache header](https://docs.vulkan.org/refpages/latest/refpages/source/VkPipelineCacheHeaderVersionOne.html) · [Device IDs](https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceIDProperties.html)

`attempts.jsonl` includes timing for initial setup, shader module creation, each cache creation call and each pipeline creation call. Disk reads are outside the API timing. `groups.json` records current complete groups, archive sizes, header-only indicators, measurements and the amount of valid pipeline feedback. Vulkan 1.3 or the pipeline-feedback extension can report an application-cache hit. Invalid or unsupported feedback yields null. Valid feedback without a hit records that the implementation didn't report an application-cache hit. It leaves driver-managed cache behavior open. [Vulkan feedback flags](https://docs.vulkan.org/refpages/latest/refpages/source/VkPipelineCreationFeedbackFlagBits.html)

The guard is adapted from PortBridge's D3D12 paired pipeline measurement probe. The shader and Vulkan worker were written for this fixture. The standalone source set is `fixture.hlsl`, `guard.h`, `probe.cpp`, `replay.py`, this README, and [LICENSE](LICENSE). Compiler executables and headers are supplied by the user.

## One completed Windows run

Campaign 218 completed eight guarded workers on an NVIDIA GeForce RTX 4070 Ti SUPER. Physical Vulkan 1.4.351 supplied core pipeline feedback through the requested 1.3 API. The six 604-byte shaders in each case were compiled for Vulkan 1.1 and validated independently on the CPU. Every pipeline reported valid feedback. The highest worker job commit was about 67.9 MiB. [Prepared inputs](cpu-validated/prepared.json) · [Matched results](cpu-validated/groups.json)

| Executable name | Absent | Six cache files | Combined cache |
| --- | ---: | ---: | ---: |
| Same as seed | 0.2597 ms | 0.8047 ms | 0.2207 ms |
| Fresh names | 21.6943 ms | 1.7323 ms | 1.7058 ms |

These totals cover six pipeline creation calls and applicable cache opens. Both application-cache layouts reported six hits under both filename conditions. The absent arms reported zero. The separate files totaled 41,006 bytes and the combined file totaled 40,826 bytes. The disjoint pre-seed reference took 26.3151 ms. This one group exercises the feature and records behavior for one driver and input shape. The fresh-name order was separate, combined, absent. Repetition with independent bundles and counterbalanced order is needed to estimate a general timing effect.

The two follow-up groups use new source salts. With the completed group, they place each mode in every position once in each filename condition. The preparation can run without a Vulkan device.

```powershell
python -I -B replay.py prepare continuation-219 --campaign 219 --start-slot 1 --groups 2
```

The follow-up completed both groups on the same adapter and driver. Together the campaigns cover 24 workers and 144 pipeline creations with valid feedback. All 72 calls using a saved application cache reported a hit. Calls made without one reported zero hits. The largest worker job reached 68.1 MiB. [Follow-up inputs](continuation-219/prepared.json) · [Follow-up results](continuation-219/groups.json)

| Median of three groups | Absent | Six cache files | Combined cache |
| --- | ---: | ---: | ---: |
| Same name as seed | 0.2597 ms | 0.2319 ms | 0.2281 ms |
| Fresh names | 21.6791 ms | 1.6584 ms | 1.6673 ms |

Merging saved 180 bytes per group, approximately 0.44%. The comparable D3D12 fixture on the same adapter observed a larger space reduction for its own cache representation. Vulkan additionally reported whether the application-provided cache was used. These separate synthetic workloads establish replay on the tested driver and scope the storage difference to their fixtures.
