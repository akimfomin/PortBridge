# Continued regional upload · Eligibility and completion proof

This offline model tests a narrow continuation of the PortBridge Vulkan readback. It uses a bounded previous snapshot for one private slot-70 sampled image, fixed 512 × 512 RGBA8, one mip and one layer, non-tail 64 KiB display tiling. The first complete upload seeds the snapshot. Subsequent updates require the same resource, Vulkan image and generation, plus a tracked `GENERAL` layout. An exact byte comparison selects at most four whole tiles. Dense or uncertain updates use the existing full route. GPU-owned textures are excluded. The four-tile cutoff is a model choice without a production crossover measurement. [Prior native readback](https://github.com/akimfomin/PortBridge/blob/c4dc7e8f8ae6b2652714c4d2f45182f524610db4/research/rendering-night/continued-regional-upload/README.md) · [Continued #1495](https://github.com/ubiquitarianism/leonida/pull/1495)

The code review used exact #1495 head `f1b27f7d73a35382093f95d5370daac2cf011a2d`. The staging, layout and dirty-range helper files matched the inspected later main `bfef489cb6307fa4e1dc6ed2c40bfc0ce120d066` byte for byte. The private slot-70 path creates and keeps its own resource reference, creates it without unordered-access flags and retires it under the title-texture registry. The slot-71 UAV path excludes owned entries. Sampled descriptors may have a different title address alias without proving that another resource has the same backing. [Owned resource creation](https://github.com/ubiquitarianism/leonida/blob/f1b27f7d73a35382093f95d5370daac2cf011a2d/runtime/shims/d3d12_vulkan_device.cpp#L9857-L9915) · [Slot-71 route](https://github.com/ubiquitarianism/leonida/blob/f1b27f7d73a35382093f95d5370daac2cf011a2d/runtime/shims/d3d12_vulkan_device.cpp#L9460-L9483)

| Observation | Transition tested |
| --- | --- |
| Source unreadable or backing unavailable | Defer. Retain the dirty revision. |
| Ineligible format, owner or layout | Use the existing CPU full path when applicable. Leave GPU-owned images to the GPU. |
| Partial attempt explicitly refused before recording | Retry the full copy for the same valid target. |
| Transfer never submitted | Leave the source revision dirty. A later attempt uses the full path. |
| Primary transfer finished but a consumer queue wait failed | Keep the affected image unavailable until a fully published replacement or retirement. Keep the source revision dirty. |
| Primary completion unknown | Pin the original image and quarantine shared staging until the primary timeline proves completion. Keep the affected image unavailable until publication or retirement. |
| Transfer completes and queue waits are published | Record the exact uploaded bytes and advance only through the captured revision. A newer write remains dirty. |

## Production prerequisites

The warm old-layout and backing check must run inside the existing title registry, tracker and submit ownership. The full path begins with `UNDEFINED` and replaces every texel. The regional path must preserve the tracked initialized layout. The retained snapshot should cover the complete guarded read, because current range notifications can miss direct mapped writes. A new backing or interpretation starts with a full upload. [Current guarded snapshot/fill](https://github.com/ubiquitarianism/leonida/blob/f1b27f7d73a35382093f95d5370daac2cf011a2d/runtime/shims/d3d12_vulkan_device.cpp#L9963-L10049) · [Current tracker and submit locks](https://github.com/ubiquitarianism/leonida/blob/f1b27f7d73a35382093f95d5370daac2cf011a2d/runtime/src/vulkan_backend.h#L1406-L1424)

The current upload helper returns a single result after a primary submit, a host timeline wait, and wait submissions on other consumer queues. Failure can therefore mean either that nothing ran, that the primary is still pending, or that bytes changed without complete publication. Its current void pre-execute callback cannot communicate the latter cases to queue submission, and the current timed retirement has no proven relationship to this primary timeline. A production port needs phase-aware completion and an image/staging reference through confirmed work. It also needs to keep an incompletely published image from sampling. The model exercises those contracts. [Primary wait and consumer submissions](https://github.com/ubiquitarianism/leonida/blob/f1b27f7d73a35382093f95d5370daac2cf011a2d/runtime/shims/d3d12_title_image_upload.h#L155-L186) · [Void pre-execute callback](https://github.com/ubiquitarianism/leonida/blob/f1b27f7d73a35382093f95d5370daac2cf011a2d/runtime/src/vulkan_backend.h#L1535-L1540) · [Execution resumes after callback](https://github.com/ubiquitarianism/leonida/blob/f1b27f7d73a35382093f95d5370daac2cf011a2d/runtime/src/vulkan_backend.h#L2482-L2499) · [Timed retirement](https://github.com/ubiquitarianism/leonida/blob/f1b27f7d73a35382093f95d5370daac2cf011a2d/runtime/shims/d3d12_vulkan_device.cpp#L9665-L9671)

With every consumer on the same Vulkan queue, the extra consumer wait submissions disappear by construction. This removes the incomplete-consumer-wait case if queue coverage is established. A main-queue submission whose host wait fails still requires the lifetime and publication gate. [Consumer queue selection](https://github.com/ubiquitarianism/leonida/blob/f1b27f7d73a35382093f95d5370daac2cf011a2d/runtime/shims/d3d12_title_image_upload.h#L125-L134) · [Vulkan host timeline wait results](https://docs.vulkan.org/refpages/latest/refpages/source/vkWaitSemaphores.html)

## Reproduce the CPU proof

```powershell
python -I -B .\test_regional_refresh.py
```

The tests compare simulated GPU bytes to independent expected values for all 256 pairs of four-tile patterns, plus the exact 1 MiB case with two 64 KiB updates. They also cover first use, changed backing with reused handles, unsupported shapes, unreadable sources, new source writes while submitting, failures at each stage and safe fallback. It is a CPU reference model. The current Continued runtime and Vulkan error paths were examined statically. [Test results](proof.log) · [MIT license](LICENSE)
