# Buffer transfer planner

A standalone C++20 component for copying modified parts of a buffer. It uses a stable source snapshot, a list of changed atoms, boundaries the caller authorizes, and the maximum size of one transfer. There are no library dependencies. The code is MIT-licensed.

## Why study this

VIctory Fork recorded frequent range queries on its Wine/RADV path. Changing the range grid from 4 MiB to 64 KiB reduced queried bytes from 7,336 MB to 1,457 MB while increasing requests from 1,746 to 3,705 and median watch time from 618 ms to 712 ms in its reported windows. Those are write detection costs. They establish a relevant granularity trade-off without establishing upload counts or frame acceleration for this component. A separate same-binary comparison in that thread had large run-to-run variation. PortBridge MCP found the exact discussion, while its global search did not expand the dirty-range terminology. The original thread supplied the measurements. [Range comparison](https://github.com/fxceless/victory-fork/issues/10#issuecomment-7154994278) · [Repeatability correction](https://github.com/fxceless/victory-fork/issues/10#issuecomment-7156790682)

Batching transfers is established practice. DXVK's D3D9 buffer path stages a dirty hull. D3D12 records one region per `CopyBufferRegion` call, while Vulkan can record disjoint regions in one `vkCmdCopyBuffer`. A smaller number of regions therefore need not reduce command or queue-submission counts across APIs. GPU packing also has prior work in scientific middleware. This component studies the constrained partition problem inside a single batched upload. [DXVK implementation](https://github.com/doitsujin/dxvk/blob/654a2410e795883bca660383c95a09a0c00e471e/src/d3d9/d3d9_device.cpp#L5589-L5618) · [D3D12](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12graphicscommandlist-copybufferregion) · [Vulkan](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdCopyBuffer.html) · [GPU packing research](https://www.mcs.anl.gov/papers/P2028-0212.pdf)

## Contract

- One problem covers one source/destination mapping and one stable epoch. Use separate problems for distinct resources, mappings or epochs.
- Each half-open authority island is an interval where copying any byte from the snapshot is valid. Bytes that might contain a newer device write belong outside such islands. Adjacent islands are still separate. An atom is caller-aligned, so its entire contents must be safe to replace.
- Explicit dirty atoms are sorted and unique. Every dirty atom must be in an island. The cap is positive. The result consists of sorted non-overlapping half-open ranges that cover all dirty atoms and fit the cap.
- Alignment, source/destination alias validation, API state transitions, barriers and keeping the source alive through completion are caller responsibilities. The planner does not observe concurrent writes. It returns copy ranges only.

```cpp
#include "planner.hpp"
#include <array>

const std::array<std::uint32_t, 3> dirty{0, 4, 6};
const std::array authority{transfer::Range{0, 7}};
const transfer::Problem p{7, 5, {8, 1}, dirty, authority};
auto copies = transfer::plan(p);  // [0,1), [4,7)
```

## Algorithm and baseline

The objective is lexicographic. It minimizes `sum(setup + unit * length)`, then actual copied units, then region count. `setup` is a marginal per-region cost. Queue submissions and fixed per-epoch work belong outside the objective. The score helps choose a plan, and is expressed in caller-defined integer units. It is a model rather than a timing guarantee.

`exact` copies contiguous dirty runs within the same constraints. `greedy` additionally accepts a gap when its byte cost is smaller than one region's setup cost, filling left to right up to the same cap. Without a binding cap that local decision is optimal. With a cap, accepting an earlier profitable gap can crowd out a better later gap. For dirty atoms 0, 4 and 6 with cap 5, setup 8 and unit cost 1, greedy chooses `[0,5), [6,7)` at score 22 and the planner chooses `[0,1), [4,7)` at score 20. With two dirty singletons and a gap of equal cost to setup, the byte tie break preserves the hole.

For a legal final group beginning at dirty index `j` and ending at `i`, the objective adds its setup and a term proportional to `end[i] - begin[j]`. For fixed `i`, the end terms are constant across all legal predecessors. The planner maintains the minimum transformed prefix in a monotonic deque and drops predecessors that exceed the cap. A later predecessor with a better transformed key remains available for at least as long. Each entry is pushed and popped at most once. An unprofitable gap is a safe decomposition point because splitting a copy there meets the same cap and cannot increase the objective. Dense and uncapped blocks avoid the deque. Runtime is linear in dirty atoms plus islands, with scratch linear in the largest constrained sparse block.

## Selection and reserve

| Direction | Evidence and testability | Decision |
| --- | --- | --- |
| Transfer planning | Open range-granularity measurements and at least two distinct graphics API paths. Can check bytes and cost independently without title inputs or access to a physical adapter. | Main investigation |
| Cross-ISA lane semantics | AMD and Vulkan subgroup behavior can differ for inactive source lanes. Divergence fuzzers already exist. A reusable reserve would validate guest-to-host lowering against an explicit definedness and execution-mask contract, with minimized counterexamples. | Reserve after validation of matching adapters and open workloads |
| Barrier movement | Scope inflation can make an earlier legal barrier more expensive. Existing batching is a strong baseline and validation requires transparent hazard state plus representative GPU timings. | Deferred |

[XCL lane measurements](https://github.com/xcl-dev/xcl/issues/772) · [ShaDiv prior art](https://cse.hkust.edu.hk/~shuaiw/pldi-25.pdf) · [Vulkan synchronization scopes](https://docs.vulkan.org/spec/latest/chapters/synchronization.html)

## Reproduction

Build from this directory with a C++20 compiler.

```sh
c++ -std=c++20 -O3 -Wall -Wextra planner.cpp verify.cpp -o verify
./verify
c++ -std=c++20 -O3 -Wall -Wextra planner.cpp census.cpp -o census
./census
c++ -std=c++20 -O3 -Wall -Wextra planner.cpp benchmark.cpp -o benchmark
./benchmark --samples 61
```

The D3D12 harness is Windows-only. LLVM-MinGW reproducible command:

```powershell
clang++ -std=c++20 -O2 -Wall -Wextra -Werror -static planner.cpp warp_benchmark.cpp -ld3d12 -ldxgi -o warp_benchmark.exe
.\warp_benchmark.exe 60
.\warp_benchmark.exe 60 14
```

The D3D12 harness requires the DXGI software flag and uses committed upload, destination and readback buffers. It measures planning, staging, recording, a single submission and fence completion. Whole-buffer validation and reset are outside the measured wall interval. Every sample is checked, including a separate deliberately invalid copy whose first forbidden change must be detected. Timestamp samples run separately. Microsoft documents that readback mapping needs an explicit fence. [WARP enumeration](https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_4/nf-dxgi1_4-idxgifactory4-enumwarpadapter) · [Readback and fences](https://learn.microsoft.com/en-us/windows/win32/direct3d12/readback-data-using-heaps)

The Vulkan harness uses the Windows loader and Vulkan headers. Point the process to an installed software driver manifest. The harness requires a CPU device type before creating a logical device.

```powershell
clang++ -std=c++20 -O2 -Wall -Wextra -Werror -static -I path/to/Vulkan-Headers/include planner.cpp vulkan_benchmark.cpp -o vulkan_benchmark.exe
$env:VK_DRIVER_FILES = 'C:\path\to\software-driver-icd.json'
.\vulkan_benchmark.exe
```

The measured Vulkan interval includes planning, staging, one batched upload command, a full readback command in the same submit, and fence completion. Checking the mapped output is outside the timed interval. Times across the APIs are not directly comparable, because the backends use different fixtures and measured operations. [Loader driver selection](https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderDriverInterface.md#overriding-the-default-driver-discovery) · [SwiftShader](https://swiftshader.googlesource.com/SwiftShader/)

## Measurements

Measurements use synthetic programmatically generated data on Windows build 28000 and an Intel Core i5-13600KF. The buffer planner was verified against an independent partition enumerator for 132,915 inputs, including boundary geometry, protected intervals and overflow. The verifier also passed with UndefinedBehaviorSanitizer trap checks. The independent model had 387 strict lexicographic wins over greedy across this generated verification corpus.

### D3D12 software path

Five independent processes each ran 60 samples per strategy and case. Times are medians of the per-process medians, in microseconds. One submission per strategy was kept fixed.

| Scenario | Exact dirty ranges | Same-cap greedy | Exact planner |
| --- | ---: | ---: | ---: |
| Clustered edits | 360.8 | 109.3 | 108.2 |
| Protected gaps | 523.5 | 527.4 | 525.9 |
| Binding cap, earlier merge crowds out a better one | 423.9 | 322.8 | 306.7 |
| Sparse edits | 87.2 | 85.2 | 87.1 |
| Dense edits | 491.4 | 487.0 | 489.4 |

The cap case uses the same 128 regions for greedy and the exact planner. The planner moves 249,856 instead of 278,528 bytes and reduces median wall time by 5.0%. The corresponding p95 changes from 390.1 to 364.0 microseconds. All five process medians favored the exact planner. Clustered edits mainly reflect conventional batching, which greedy already captures. Protected, sparse and dense controls give no general speedup.

These trials used fixed synthetic setup and unit weights of 8 and 1. A separate WARP transport sweep, with a single submission held constant, measured roughly 0.590 microseconds per region at fixed 64 KiB and 0.657 microseconds per KiB at fixed 64 regions. These are local slopes for record, submit and fence time in the two sweeps.

An independent sensitivity pass with the rounded local ratio 14:1 used five more processes. In the cap case, greedy versus exact-planner medians were 326.4 versus 312.1 microseconds, while p95 rose from 373.5 to 382.7. In the protected-gap case the plans copied more legal bytes, from 49,152 at setup 8 to 229,376 at setup 14, without a robust wall-time gain. The protected bytes were preserved.

### Vulkan software path

Seven separate SwiftShader processes ran 24 timed samples per strategy and case. That is 1,512 timed chains and 1,764 full output comparisons with warmups. All seven forbidden-copy canaries were detected.

| Scenario | Exact dirty ranges | Same-cap greedy | Exact planner |
| --- | ---: | ---: | ---: |
| Sparse edits | 27.05 | 27.60 | 27.95 |
| Dense edits | 55.60 | 54.85 | 55.20 |
| Binding cap | 57.85 | 57.60 | 58.15 |

Times are in microseconds and are medians of process medians. In the sparse case, fewer regions increased copied atoms from 90 to 198, with paired median wall time roughly 2.84% higher than the exact-ranges baseline. In the cap case the planner copied 640 instead of greedy's 800 atoms, without a demonstrated latency gain. Vulkan's native multiregion command is a strong baseline.

### CPU replay

The CPU harness measures planning, copying into a preallocated staging buffer and applying the complete batch to a destination. It verifies the full destination. Its small-burst fit used independent timings for 4–64 KiB. A broader fit returned a negative marginal region estimate and was discarded. A roughly 53 KiB held-out point matched the small-burst estimate within about 1%, while a roughly 13 KiB point was overestimated by 52–98% across the initial runs. The 256 KiB controls show a different regime. The 80 CPU configurations and 14,640 timed replay samples found no strict modeled advantage over same-cap greedy on their fitted profiles and no repeatable wall-time advantage.

### When the exact planner changes a plan

A deterministic census evaluates 4,096 held-out synthetic epochs across four families, three cost profiles and two caps, for 24,576 paired comparisons. With a 4 KiB cap and cost weights 8:1, modeled gain exceeds 1% in 1,020/1,024 local-burst epochs and 802/1,024 dense patterned epochs. Aggregate modeled gains are 1.81% and 1.60%. Strided has 34/1,024 above 1%, uniform scatter has zero. With the CPU-like 2:1 ratio, no family has an epoch above 1%. With the cap removed, no model has a strict gain over greedy. This is an incidence measurement for the stated synthetic families, not an estimate for production games. [Measurements](measurements.json)

## Integration boundary

D3D12 buffer staging clients and Vulkan copy clients can both call the planner with aligned, nonoverlapping source-valid regions. A wgpu client needs an authoritative shadow for the original contents of any bridged hole. The planner's finite-cap advantage is proven for its cost objective. Initial software measurements justify a trace-driven trial when a cap actually binds and upload planning is measured as a material cost. A physical-device run, production workload coverage and frame-level measurements remain open. [wgpu staging implementation](https://github.com/gfx-rs/wgpu/blob/60cef2be828e03ba54e2e1598001b4625c0c2163/wgpu-core/src/device/queue.rs#L1066-L1093)
