# Physical rank validation

Use a Vulkan 1.1 compute device with a coherent cached host-visible staging memory type, a C++20 compiler, Vulkan headers and loader, glslang, SPIRV-Tools and Python. The small validator reuses the device, buffer and synchronization helpers from the earlier readback experiment. Its device prefix implementation is intended for correctness work at up to 4,096 points. [Vulkan synchronization](https://docs.vulkan.org/guide/latest/synchronization_examples.html) · [Readback test setup](../../readback-epochs/README.md#reproduction)

From this directory, create a scratch area outside the source checkout. The commands below assume a compiler that links the Vulkan loader with `-lvulkan`. On Windows, link the Vulkan SDK's `vulkan-1.lib` or the equivalent import library.

```sh
glslangValidator -V --target-env vulkan1.1 rank_filter.comp -o /path/to/scratch/rank_filter.spv
glslangValidator -V --target-env vulkan1.1 rank_observe.comp -o /path/to/scratch/rank_observe.spv
spirv-val --target-env vulkan1.1 /path/to/scratch/rank_filter.spv
spirv-val --target-env vulkan1.1 /path/to/scratch/rank_observe.spv
c++ -std=c++20 -O2 -Wall -Wextra -Werror validate_rank.cpp -lvulkan -o /path/to/scratch/validate-rank
python -B generate_fixtures.py /path/to/scratch
/path/to/scratch/validate-rank /path/to/scratch/rank_filter.spv /path/to/scratch/rank_observe.spv /path/to/scratch/sparse.txt "device name"
```

Repeat with dense, empty, boundary and single inputs. The `--physical-index` mutation on the sparse case must fail on the second mask. With `validate-rank.exe` in the Windows output folder, `.\run.ps1 -Output <path-to-scratch> -Adapter "device name"` runs all cases including the deliberately wrong path.
