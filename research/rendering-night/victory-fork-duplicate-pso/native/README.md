# victory-fork #470 real pipeline-library control

The fixture uses the exact `pipeline()` and lock helpers extracted for the prior CPU comparison on `c96b4f2b8365bf43d54ab074940923ef8267f4c6`. The extraction matches the two archived bodies. It keeps their Windows string types and replaces the host test doubles with a real device, root signature and empty `ID3D12PipelineLibrary1`. A second invocation mode uses a CPU mock for the same schedule. Initializing the project's file cache and its production logging are outside the fixture. [Pinned compute caller](https://github.com/fxceless/victory-fork/blob/c96b4f2b8365bf43d54ab074940923ef8267f4c6/crates/victory-gpu/src/pipeline/host.rs#L525) · [Receiving issue](https://github.com/fxceless/victory-fork/issues/470)

Both callers use the same name, one source-generated compute program and the identical descriptor. The first caller stops at a CPU gate following its library miss. The original implementation lets the second caller reach the same gate after another miss. The candidate holds the second at the exact-name wait. The first real create and store complete before the baseline's second real create is released. A subsequent request checks the warm library entry in both forms. This schedule avoids simultaneous native calls on the same PSO and counts visible API calls, statuses and valid returned objects. [D3D12 same-PSO loading rules](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device1-createpipelinelibrary#thread-safety) · [Compute load](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12pipelinelibrary-loadcomputepipeline) · [Store](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12pipelinelibrary-storepipeline)

The test uses one independently validated source-generated DXIL program below 4 KiB and the root signature from that program. It creates no command queue or dispatch. Each arm runs under the existing Windows guard with 4 GiB of initial commit and 6 GiB physical headroom, a 512 MiB combined job limit and a three-second deadline. It stops on the first native error. The code uses normal caches throughout; an empty application library can coexist with driver-managed cached work.

```powershell
python -I -B check.py build proof-a
python -I -B check.py native proof-a
```

The build command uses the existing Rust gnullvm and LLVM-MinGW tools and the checked Windows binding artifacts identified in the build log. It compiles the two exact-source arms, executes their CPU mocks under both global-lock settings, and runs Microsoft DXV on the input. The native command is a separate scheduled step and runs default lock settings. The files in the selected directory record input and executable identities, all mock results and each observed native outcome.

This experiment measures whether the actual D3D12 entry points are called more than once under the specified request overlap. It leaves internal driver compilation, production duplicate frequency, queue latency and frame-time impact open.
