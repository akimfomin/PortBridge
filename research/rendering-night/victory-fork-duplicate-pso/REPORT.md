# victory-fork · Duplicate creation on a cold pipeline-library miss

KretliJ reported persistent pipeline backlog and dropped draws and offered to check specific hypotheses. PortBridge's priority and preflight checks led to the original issue, which the indexed public snapshot did not yet cover. The test below examines a distinct source-level mechanism behind repeated pipeline work. It does not connect that mechanism to the reported frame time. [Receiving issue](https://github.com/fxceless/victory-fork/issues/470)

## Source finding

Separate guest handles each get a `Pending`. In `library::pipeline`, the old name lock covered `LoadPipeline` only. A second worker could miss after the first worker released the name lock but before the first worker called `StorePipeline`. Each worker then executed the expensive `create()` for the same host PSO. Both `pipeline()` and the old `same_name()` are text-identical in KretliJ's `2119b0e44c53aa9648307b0c5c73590290305b1f` and the checked `c96b4f2b8365bf43d54ab074940923ef8267f4c6`. [Reported source](https://github.com/fxceless/victory-fork/blob/2119b0e44c53aa9648307b0c5c73590290305b1f/crates/victory-gpu/src/pipeline/library.rs) · [Tested source](https://github.com/fxceless/victory-fork/blob/c96b4f2b8365bf43d54ab074940923ef8267f4c6/crates/victory-gpu/src/pipeline/library.rs)

The patch reserves the exact name through load, conditional create and store. The reservation is removed when the call returns, including errors. Same-name contenders retry the normal load with their own descriptors. A different descriptor can still miss and be created without replacing the entry. No driver call holds the admission map mutex. The optional diagnostic global lock and existing save/store synchronization remain in place. Microsoft requires application synchronization for concurrent loads of the same PSO. [DX12 thread-safety rules](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device1-createpipelinelibrary#thread-safety) · [Descriptor checks on load](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12pipelinelibrary-loadgraphicspipeline) · [Store rules](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12pipelinelibrary-storepipeline)

## Deterministic A/B

The runner extracts production `pipeline()` and both admission implementations directly from the pinned tree and patched file. The fake D3D12 library models descriptor-checked loads, non-overwriting stores and failures. A test-only observer marks the candidate's wait boundary. Channels hold the first create before store and let three additional callers reach their respective admission points. No timing arithmetic or randomized schedules decide the outcome.

| Result | Pinned source | With patch |
| --- | ---: | ---: |
| Create callbacks for four concurrent identical cold requests | 4 | 1 |
| Matching library hits | 0 | 3 |
| Successful stores including unrelated control | 2 | 2 |
| Unrelated name sharing the old mutex bucket completes before release | Yes | Yes |
| Uncontended warm hits tested | 12 | 12 |
| Allocator calls for those warm hits | 12 | 24 |
| Test cases passed with each lock configuration | 6/6 | 6/6 |

Controls cover waking a same-name retry after create failure, warm reuse, descriptor mismatch, rejected store and an unavailable library. Default and `VICTORY_LIBRARY_LOCK=1` both pass. The full native crate and D3D12 driver were outside this CPU verification. On a store refusal, same-name subsequent misses still create serially. After map initialization, the guard adds short map operations and one 32-byte key allocation per uncontended warm hit. Actual duplicate rate, driver benefits and warm-path latency need evidence before associating the change with any frame-time claim. [Call and lock review](LOCK-AND-WARM-REVIEW.md)

[Baseline log](ab/baseline/default-test.log) · [Candidate log](ab/candidate/default-test.log) · [Baseline legacy-lock log](ab/baseline/legacy-lock-test.log) · [Candidate legacy-lock log](ab/candidate/legacy-lock-test.log)

## Overlap and handoff

The related pending changes cover frame-budget resets and wakeups (#398), long-running worker reporting (#458), pipeline-library save serialization (#237), shader-cache atomic publication (#488), and VIctory's two-stage scheduling of shared shader translations (#1898). The published proposals address different boundaries. #470 is the receiving thread for a result about repeated PSO work. [#398](https://github.com/fxceless/victory-fork/pull/398) · [#458](https://github.com/fxceless/victory-fork/pull/458) · [#237](https://github.com/fxceless/victory-fork/pull/237) · [#488](https://github.com/fxceless/victory-fork/pull/488) · [VIctory #1898](https://github.com/Marvisak/VIctory/pull/1898)

To reproduce, check out the pinned commit and place the patch, `run.py` and `harness.rs` in `proof/` beneath it. Apply the patch to that checkout and run `python proof/run.py`. The recorded run used Rust 1.100 gnullvm with LLVM-MinGW. If those tools are outside `PATH`, pass `--rustc` and `--linker` with their executable paths. The patch passes forward apply checking on the pinned index and reverse apply checking in the patched checkout. SHA-256 `c73e5eeeecf119ce078a66796135b5d11b7ab99691fb36173bc9745b88e3f21b`.

[Patch](victory-fork-name-flight-c96b4f2.patch) · [Fixture](harness.rs) · [Runner](run.py)
