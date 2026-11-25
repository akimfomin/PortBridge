# D3D12 placement and creation-time check

This independent fixture asks whether 16 minimum-alignment scratch buffers can share one default heap while retaining distinct identities, aligned GPU addresses, and identical data. It isolates the resource allocation change considered for [XCL #2080](https://github.com/xcl-dev/xcl/pull/2080). XCL's reference path creates a committed default-heap buffer with UAV support and initial UAV state for each chained dispatch. [Exact reference](https://github.com/Kalmarv/xcl/blob/af2bd61e39344b0db2f37f14d950c78e0022e7df/crates/xcl/src/hle/d3d12x/real/dispatch_chain.rs#L109-L146)

## Inputs and checks

- Both arms allocate 16 separate 64 KiB UAV-capable resources. The reference creates a committed allocation per buffer. The placed arm makes a buffers-only 1 MiB heap and uses offsets `0, 65536, …, 983040`. The fixture checks the reported allocation alignment and size before issuing any test allocation. Every GPU address must be nonzero, satisfy the raw UAV alignment and describe a distinct range. [D3D12 buffer requirements](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ns-d3d12-d3d12_resource_desc#buffers) · [Heap description](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ns-d3d12-d3d12_heap_desc)
- Placed resources are activated together with null-before/resource-after aliasing barriers under the documented simple model. Both arms transition from UAV to `COPY_DEST`, upload every range, transition to `COPY_SOURCE`, then read back every range. All writes precede all reads. Each buffer region has unique data, and the data changes every round. Each arm has its own readback buffer. The CPU compares all 1,048,576 bytes per arm. [Placed resource activation](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device-createplacedresource#remarks) · [CopyBufferRegion](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12graphicscommandlist-copybufferregion)
- The guard admits only the local RTX 4070 Ti SUPER benchmark, caps the worker and Job Object at 512 MiB and enforces a 3 s worker limit. Admission requires 4 GiB available commit and 6 GiB available physical RAM. The guard monitors host memory while the worker runs. Resources stay alive through a confirmed fence. The worker records the error and terminates its own process if completion cannot be established. Queued GPU copy waits have a 700 ms bound. [Fence event semantics](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12fence-seteventoncompletion)
- Verification reports whether the installed debug layer was available and fails on any warning or error when it is available. Each timing sample has its own full readback check. The reported host elapsed time covers one `CreateHeap` where applicable and all 16 resource creation calls. Timings exclude setup, address checks, recording, validation, copies, waits, release and allocator reset.

## Reproduce on the specified RTX adapter

From this directory with an x64 LLVM-MinGW `clang++.exe` available:

```powershell
.\build.ps1 -Compiler 'path\to\clang++.exe'
New-Item -ItemType Directory -Path .\evidence
.\run.ps1 -Stage Verify -LogDirectory .\evidence
.\run.ps1 -Stage Measure -LogDirectory .\evidence
python -I -B .\summarize.py .\evidence
```

`Measure` requires a clean verification log. It starts two sequential guarded workers with opposite first-arm order and four A/B pairs each. Order alternates within each worker. The raw logs include QPC frequency, allocation alignment and size, durations in ticks, bytes checked, first mismatched word if present, guard status, and the failing step and HRESULT if any. The summary validates order and data parity for all eight pairs before computing the median creation times. Any failure stops the run and keeps the previous logs.

## Current run

The source built successfully with x64 LLVM-MinGW and warnings treated as errors. The first hardware attempt was refused by the memory guard before it started a D3D12 worker. The next attempt completed on the RTX 4070 Ti SUPER. Each arm verified 1,048,576 bytes without a mismatch, and the device reported `S_OK`. The D3D12 debug layer was unavailable, with `DXGI_ERROR_SDK_COMPONENT_MISSING` (`887a002d`). [Build provenance](build.log) · [Refused hardware attempt](evidence/verify.log) · [RTX verification](evidence-0732/verify.log)

Both timing workers completed and independently rechecked every byte in every arm. Across eight pairs the placed allocation was faster in all eight, with 16 MiB verified without mismatches. The median paired difference was 2,482.5 µs and the median paired reduction was 87.603%. The placed result includes heap creation, which took a median 294.2 µs. [AB timing and readback](evidence-0732-timing/measure-ab.log) · [BA timing and readback](evidence-0732-timing/measure-ba.log) · [Paired summary](evidence-0732-timing/summary.log)

| Samples | Pairs | Committed median, µs | Placed median, µs | Median paired reduction |
| --- | ---: | ---: | ---: | ---: |
| All | 8 | 2,810.9 | 356.2 | 87.603% |
| First pair per ready worker | 2 | 2,912.4 | 383.65 | 86.826% |
| Later pairs | 6 | 2,794.4 | 329.0 | 88.295% |

The first pair ran after device, staging and command-queue initialization. It measures the first scratch allocation in a ready worker. The measurement sample is specific to one size, one GPU and the installed driver.

This copy-only fixture covers creation, placed activation, disjoint addresses, and data parity on one direct queue. XCL's runtime has its own UAV dispatch, multi-queue retention, and allocation/fallback behavior. The results can inform whether it is worth investigating allocation pressure in XCL. The fixture does not execute XCL or estimate dispatch speed.
