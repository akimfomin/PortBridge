# Continued #939 · first-use pipeline checkpoint coverage

The pinned first-run profile defaults `LEONIDA_PIPELINE_COMPILE` to `on-demand`. That selects first-use Vulkan compute pipeline creation. The optional startup cache checkpoint runs after slow creation in the eager branch. The first-use materialization callback invokes the same Vulkan API without sending a checkpoint request. [First-run profile](https://github.com/ubiquitarianism/leonida/blob/eb6a08cd359d98b5777e70d54d0ae8a75879495a/runtime/src/main.cpp#L67-L81) · [Mode selection](https://github.com/ubiquitarianism/leonida/blob/eb6a08cd359d98b5777e70d54d0ae8a75879495a/runtime/shims/d3d12_vulkan_device.cpp#L11462-L11467) · [Compute branches](https://github.com/ubiquitarianism/leonida/blob/eb6a08cd359d98b5777e70d54d0ae8a75879495a/runtime/shims/d3d12_vulkan_device.cpp#L5187-L5218)

The probe compiles those exact public branches inside a small C++ fixture. A fake clock advances when a stub Vulkan call returns. The save stub only counts requests. It uses no GPU, no game inputs and no pipeline cache files.

| Compute creation mode | 499 ms | 500 ms | 501 ms |
| --- | ---: | ---: | ---: |
| Eager, opt-in and cache present | 0 | 1 | 1 |
| First use, opt-in and cache present | 0 | 0 | 0 |

All 48 combinations passed the source-level oracle, spanning opt-in, cache, creation result and test delay. First-use success was also materialized twice to check that the cached result makes only one compile call. This is control-flow evidence. It does not measure application startup, Vulkan times, graphics pipelines, or whether device teardown later saved the cache. [Raw transcript](checkpoint-result.log)

If first-use checkpoints are intended, a result from materialization can mark the cache dirty and a later owner can drain it after replay locks release. Full cache serialization inside the materializer would add file I/O to a path that already holds the compute compile mutex. Related persistence and shader warm-up work exists in Continued #218 and #1308. Coordinate the behavior with those changes before modifying the runtime. [Continued #939](https://github.com/ubiquitarianism/leonida/pull/939) · [Persistence](https://github.com/ubiquitarianism/leonida/pull/218) · [Warm-up](https://github.com/ubiquitarianism/leonida/pull/1308)

Fetch the public PR head into a clean Continued checkout, then run:

```powershell
git fetch upstream refs/pull/939/head
python -I -B reproduce.py --repo <continued-checkout> --clang <LLVM-MinGW-clang++.exe>
```

The harness and its extracted GPL-3.0-or-later Continued code use the same license.
