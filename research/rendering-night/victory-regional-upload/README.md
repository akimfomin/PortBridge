# Partial D3D12 texture uploads from dirty tile ranges

The work in [VIctory #1135](https://github.com/Marvisak/VIctory/pull/1135) avoids detiling everything when only a few pages change. Talakasse and wwwwwwww3333333 showed both whole-subresource and selective-row versions. The latter still records a full host upload for each changed subresource. Once the destination texture and the untouched staging bytes already contain the previous version, a tracked dirty range can also reduce the GPU copy. [Selective-row prototype and attribution](https://github.com/Marvisak/VIctory/pull/1135#issuecomment-7149160095)

`copy_plan.rs` maps sorted dirty-byte intervals into the physical tiles of an eligible mip, then makes region boxes in texel coordinates. It merges adjacent runs, clamps to the actual mip size, skips untouched slices and keeps the full-copy behavior for dense or heavily fragmented updates. The prototype narrows regions to addressable single-sampled 2D color layouts outside the mip tail. The D3D12 caller must confirm a compatible single-plane format and existing destination contents. A first upload, resource replacement or uncertain authority needs the full copy. The 8-box and 75%-area fallbacks bound submission work. They are prototype choices without a production crossover measurement.

`texture.rs` is the exact existing [victory-fork layout oracle](https://github.com/fxceless/victory-fork/blob/c96b4f2b8365bf43d54ab074940923ef8267f4c6/crates/victory-formats/src/texture.rs). Its MIT addrlib attribution and notice are retained. The six layout families in the test include 256 B, 4 KiB and 64 KiB tile modes and linear layout. The CPU oracle updates only the named bytes, fully detiles the new memory, and compares that result with the previous linear buffer plus the planned boxes. The 1,592 checked plans gave 314 unchanged, 1,174 whole and 104 regional results. All eleven Rust tests passed, including nine existing tests.

## Physical RTX comparison

The exact planner generated box `[256,384) × [128,256)` from a single 64 KiB dirty macro tile in a 512×512 RGBA8 texture. The D3D12 fixture first uploaded the same original image to two textures. It then uploaded the entire new staging image to one and just that box to the other, followed by full readback of both textures. Both matched the independent expected image across **1,048,576 bytes**, including 65,536 bytes that had to change and all unchanged surrounding data.

| Update submitted to D3D12 | Full | Regional |
| --- | ---: | ---: |
| Bytes in the requested box | 1,048,576 | 65,536 |
| Unexpected final bytes | 0 | 0 |

The RTX 4070 Ti SUPER process was reaped under the existing 512 MiB and three-second Windows guard. Peak job commit was 108,240,896 B. The D3D12 debug layer was unavailable, and the device returned `S_OK` after the readback. There is no measured GPU transfer latency, frame-time or runtime integration effect. For 4096×4096 RGBA8 the CPU plan calculates 67,108,864 versus 65,536 copy bytes for one corresponding dirty tile. That larger case was evaluated as a plan only.

[CPU logs](proof-results.log) · [Native readback](native-upload-rtx-a.log) · [Microsoft CopyTextureRegion rules](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12graphicscommandlist-copytextureregion)

## Reproduce

Use Git, Rust with edition 2024 enabled, and LLVM-MinGW Clang on Windows. The build reproduces the extent oracle and embeds only the one fixed generated box. Run the optional hardware control separately. It accepts only the specified RTX model. Every worker requires 4 GiB of free commit and 6 GiB of free physical RAM at admission.

```powershell
.\build.ps1 -Rustc rustc -Compiler clang++ -OutputDirectory .\new-proof
.\new-proof\native-upload.exe --hardware
```

For gnullvm, add `-RustLinker` with the full LLVM-MinGW linker path. The program creates no window and uses no title data or shaders. The source and reused guard carry the indicated licenses. [Guard license](LICENSE.guard)
