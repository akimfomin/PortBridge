# Continued #1101 · Vulkan readback for a finite loop limit

PortBridge took the loop-boundary question from the merged XCL #2034 and checked it against the Continued translator at `10ad8809b3ddf9f33c97ff0a52555bffbbb15aa7`. This archive has six synthetic SPIR-V assemblies, the guarded readback source and the recorded outcomes. Each disabled-limit shader still exits naturally in five visits. [Continued PR](https://github.com/ubiquitarianism/leonida/pull/1101) · [PortBridge's CPU discussion](https://github.com/ubiquitarianism/leonida/pull/1101#issuecomment-7150851967) · [PortBridge](https://github.com/akimfomin/PortBridge)

## Observed on the RTX 4070 Ti SUPER

Windows, Vulkan 1.3, NVIDIA driver 617.14. The pipelines explicitly required full host subgroups of size 32. Every result below applies to all 32 or 64 invocations in that run.

| Loop limit / natural visits | Native Wave32, count and marker | Emulated Wave64, count and marker |
| --- | --- | --- |
| 4 / 3 | `3 / 42` | `3 / 42` |
| 4 / 5 | `4 / untouched` | `4 / 42` |
| Disabled / 5 | `5 / 42` | Guard refused before launch |

All five hardware runs completed with zero Khronos validation warnings or errors. The sixth passed the CPU interpreter and SPIR-V validation. Hardware Wave64 is outside the scope of the RTX runs. The test verifies the observable difference when the limit forces an exit. The intended post-loop behavior remains a question for Continued. [Raw native log](evidence/native-readback.log) · [Recorded binary hashes](evidence/build-manifest.json)

## Reproduce

Use Windows x64, Python 3.11+, LLVM-MinGW with `clang++`, and the Vulkan SDK with Khronos validation and SPIRV-Tools. The readback is pinned to the reported NVIDIA adapter. Its startup checks require Vulkan 1.3, 32-wide full compute subgroups, shader Int64, buffer device address and the float-control properties declared by the modules. The build and run use local tools and the installed graphics driver. No checkout is required for these two steps. [LLVM-MinGW](https://github.com/mstorsjo/llvm-mingw) · [Vulkan SDK](https://vulkan.lunarg.com/sdk/home) · [Khronos SPIRV-Tools](https://github.com/KhronosGroup/SPIRV-Tools)

From this folder in PowerShell, with the SDK installed and LLVM-MinGW tools on PATH:

```powershell
python -I -B .\prepare.py
.\build.ps1 -VulkanInclude "$env:VULKAN_SDK\Include" -SpirvAs "$env:VULKAN_SDK\Bin\spirv-as.exe" -SpirvVal "$env:VULKAN_SDK\Bin\spirv-val.exe"
python -I -B .\run.py --layer-directory "$env:VULKAN_SDK\Bin"
```

Pass `-Compiler` with the full path to LLVM-MinGW `clang++.exe` if needed. If the SDK places `VkLayer_khronos_validation.json` and its library in a different folder, use that folder for `--layer-directory`. Pass new paths via `-OutputDirectory`, and `--worker` plus `--output` for a separate run. The scripts refuse to overwrite a previous output directory or native log.

The worker executes one workgroup, checks both words per invocation and verifies an untouched 64-byte padding region. The Windows job limits worker and job memory to 512 MiB and gives each worker three seconds. Each launch needs at least 4 GiB available system commit and 6 GiB available physical RAM. The guard stops the sequence at the first refusal, timeout, validation diagnostic or mismatch. Vulkan validation is enabled for the worker process. [Required subgroup size](https://docs.vulkan.org/refpages/latest/refpages/source/VkPipelineShaderStageRequiredSubgroupSizeCreateInfo.html) · [Vulkan synchronization](https://docs.vulkan.org/spec/latest/chapters/synchronization.html) · [Windows job limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information)

### Verify translated sources independently

Supply a clean Continued checkout at exact revision `10ad8809b3ddf9f33c97ff0a52555bffbbb15aa7`. The optional check runs the original CPU probe and compares all six generated assembly files to the archive byte for byte:

```powershell
$checkout = Read-Host 'Path to the pinned Continued checkout'
python -I -B .\prepare.py --checkout $checkout
```

The recorded build used LLVM-MinGW `20261117-ucrt-x86_64` and Vulkan-Headers `6802bb4733b63ed5efd3adb308a6c885ef180ea1`. `SHA256SUMS` covers the shipped files. The recorded build manifest adds SHA-256 for each assembled module. A newly assembled binary's hash may vary by SPIRV-Tools version. The included guard and PortBridge source use the included MIT license. Continued's source is available under its upstream license. [Pinned Continued source](https://github.com/ubiquitarianism/leonida/tree/10ad8809b3ddf9f33c97ff0a52555bffbbb15aa7) · [License](LICENSE)
