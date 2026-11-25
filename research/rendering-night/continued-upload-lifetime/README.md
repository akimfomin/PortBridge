# Continued title staging · Submission and buffer lifetime

PortBridge extracted the exact `TitleImageUpload` staging allocation, reuse and submission methods from Continued #1495 head `f1b27f7d73a35382093f95d5370daac2cf011a2d`. The source SHA-256 matches the inspected main revision `5129be10d47e16ecf5d8c41cfec12a59a2f25512`. The fixture runs these methods only against fake Vulkan callbacks. It creates no device and uses no game data. [Continued #1495](https://github.com/ubiquitarianism/leonida/pull/1495) · [Pinned upload source](https://github.com/ubiquitarianism/leonida/blob/f1b27f7d73a35382093f95d5370daac2cf011a2d/runtime/shims/d3d12_title_image_upload.h) · [PortBridge](https://github.com/akimfomin/PortBridge)

## Results

The fake primary submit accepts a copy and leaves it pending. The fake host wait then returns a Vulkan error. Exact stock `prepare` admits a further mapped-buffer write at the same size. With a larger request the exact stock code first calls buffer destruction and allocation free while that submission is still pending.

| Fake-driver check | Stock | Reference gate |
| --- | ---: | ---: |
| Writes admitted while pending, same size | 1 | 0 |
| Destruction/free calls while pending, growth | 2 | 0 |
| Writes admitted while pending, growth | 1 | 0 |
| Strict no-reuse policy exit code | 1 | 0 |

The candidate tracks the latest accepted primary value, proven completion and publication of every consumer-queue wait separately. It refuses reuse on an unsuccessful or insufficient timeline query, and permits reuse once the exact prior value is complete. Successful uploads and primary rejection add no counter query. If a consumer wait submission fails after primary completion, the staging allocation can be reused but publication remains incomplete. [Stock output](evidence/stock.log) · [Reference output](evidence/candidate.log) · [Scoped candidate](generated/staging-reuse-reference.patch)

The injected wait failure is deliberately a fake result. A real host wait can fail with device loss or another Vulkan error. The test establishes the caller's reaction when completion is unconfirmed. It does not establish that an RTX or any other driver has produced that failure. [Vulkan host timeline waits](https://docs.vulkan.org/refpages/latest/refpages/source/vkWaitSemaphores.html) · [Vulkan submission result guarantees](https://docs.vulkan.org/refpages/latest/refpages/source/vkQueueSubmit.html)

## Runtime applicability

The reference change covers reuse of shared mapped staging and its command buffer. The existing full upload API still reports failure to the refresh caller. Destination image lifetime, descriptor availability after incomplete publication, device-loss handling and safe teardown remain production prerequisites.

The ordinary queue calls `record_submit_locked` after acceptance, so the deferred deletion tracker can wait for recorded timeline values. The private title upload bypasses that record. Recording every title upload through the same entry would also mark image work pending, adding a device-idle wait to later refreshes. An unresolved accepted upload needs its own completion record and stable semaphore lifetime before freeing its destination or tearing down staging. The current void pre-execute callback also continues toward rendering after a failed texture refresh. A fallback must preserve both the staging and destination lifetime until safe, and avoid publishing incomplete content. [Current submission and retirement tracker](https://github.com/ubiquitarianism/leonida/blob/5129be10d47e16ecf5d8c41cfec12a59a2f25512/runtime/src/vulkan_backend.h#L1689-L1776) · [Pre-execute callback type](https://github.com/ubiquitarianism/leonida/blob/f1b27f7d73a35382093f95d5370daac2cf011a2d/runtime/src/vulkan_backend.h#L1535-L1540)

## Reproduce

Use Windows x64, Python 3.10+, LLVM-MinGW Clang and Vulkan headers. A Vulkan loader, device or driver is not needed. Extraction verifies the exact shipped header and only exposes the transport members to the fake callback harness. This starts a new output directory:

```powershell
$clang = (Get-Command clang++ -CommandType Application).Source
.\build_and_check.ps1 -Compiler $clang -VulkanInclude "$env:VULKAN_SDK\Include" -OutputDirectory .\new-check
```

Both recorded arms used LLVM-MinGW Clang C++20 at `-O2` with Vulkan-Headers `6802bb4733b63ed5efd3adb308a6c885ef180ea1`. Each compiler starts only with at least 3 GiB available system commit and 6 GiB available physical RAM. The reproduction treats the strict stock exit 1 and candidate exit 0 as the expected pair. Sources derived from Continued and the test harness use GPLv3-or-later. [License](upstream/LICENSE)
