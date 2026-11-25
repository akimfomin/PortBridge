# Continued · Vulkan update of two changed texture tiles

PortBridge transferred a test idea from VIctory #1135 to CPU-sourced texture refresh in Continued. This standalone fixture uses the open XG address mapping and full detile at Continued `0bc810504aa44ba7e30f3c3352ebad697b9814d6`. It creates its pixels procedurally. No shaders, game files or game runtime are needed. [VIctory #1135](https://github.com/Marvisak/VIctory/pull/1135) · [Continued #984](https://github.com/ubiquitarianism/leonida/pull/984) · [PortBridge](https://github.com/akimfomin/PortBridge)

## Observed results

On Windows with an RTX 4070 Ti SUPER and NVIDIA driver 617.14, a single 512 × 512 RGBA8 destination was initialized before each update. Both arms read back and matched all 1,048,576 bytes. The unchanged bytes outside the update regions matched too.

| Update | Regions in one Vulkan call | Requested bytes | Mismatched readback bytes |
| --- | ---: | ---: | ---: |
| Whole image | 1 | 1,048,576 | 0 |
| Two disjoint 128 × 128 regions | 2 | 131,072 | 0 |

The readback hash in each arm was `528d7210085cff25`. Both workers completed with zero counted Khronos synchronization-validation errors. These figures describe the submitted updates and observed output. Runtime performance and the frequency of eligible textures were outside the test. [Raw results](native-readback.log)

## Reproduce

Use Windows x64, Python 3.11+, LLVM-MinGW and the Vulkan SDK with the Khronos validation layer. The device run uses the same RTX adapter as the recorded result. The included public headers remove the need to clone another repository to build the fixture.

```powershell
.\build.ps1 -VulkanInclude "$env:VULKAN_SDK\Include"
.\build\texture-readback.exe --cpu
python -I -B .\run.py --layer-directory "$env:VULKAN_SDK\Bin"
```

Pass `-Compiler` with the full path to LLVM-MinGW `clang++.exe` if it is outside PATH. If the SDK puts `VkLayer_khronos_validation.json` and its library elsewhere, pass that folder to `--layer-directory`. For a second build and run, give new paths with `-OutputDirectory`, `--worker` and `--output`. The runner uses process-local Vulkan settings and enables standard and synchronization validation. One Windows job limits each worker to 512 MiB and three seconds. Each launch needs at least 4 GiB of available system commit and 6 GiB of physical memory. [LLVM-MinGW](https://github.com/mstorsjo/llvm-mingw) · [Vulkan SDK](https://vulkan.lunarg.com/sdk/home)

The 14 bundled public dependency and license files have individual SHA-256 and Git blob hashes in `upstream-headers.json`. `SHA256SUMS` covers the archive contents. The reproduction uses the same fixture source and guard as the recorded native run. The GPLv3 license, MIT guard license and AMD tiling attribution are included. [Pinned Continued source](https://github.com/ubiquitarianism/leonida/tree/0bc810504aa44ba7e30f3c3352ebad697b9814d6) · [Continued license](upstream/LICENSE) · [Guard license](LICENSE.guard) · [Tiling attribution](upstream/runtime/shims/xg_xs_THIRD_PARTY.md)

## Scope of the transfer

Current Continued refresh takes a guarded source snapshot and uploads whole subresources. Its staging path can discard the previous image layout because it replaces every texel. A regional copy needs the actual tracked old layout and a valid previous upload of the same backing. Continue to use a whole update for a new, replaced or uninitialized image, or when write coverage is uncertain. The source can change through a persistent writable map outside the XG/DirectStorage notifier, so this fixture derives its regions from an exact comparison against the prior uploaded snapshot. The strongest candidate for measurement is a warm, private sampled image created by the slot-70 view path. [Continued staging helper](https://github.com/ubiquitarianism/leonida/blob/0bc810504aa44ba7e30f3c3352ebad697b9814d6/runtime/shims/d3d12_title_image_upload.h#L26-L93) · [Refresh and notification handling](https://github.com/ubiquitarianism/leonida/blob/0bc810504aa44ba7e30f3c3352ebad697b9814d6/runtime/shims/d3d12_vulkan_device.cpp#L10636-L10677) · [Vulkan copy rules](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdCopyBufferToImage.html)
