# VIctory #1135 BC7 dirty-tile copy control

The control extends PortBridge's RGBA8 upload proof to the format used in the original VIctory #1135 detiling work. It reuses the previous Rust planner and the exact pinned texture layout source without changes. [Receiving PR](https://github.com/Marvisak/VIctory/pull/1135) · [Prior RGBA8 fixture](../portbridge-victory-dirty-tile-upload/README.md) · [Pinned layout source](https://github.com/fxceless/victory-fork/blob/c96b4f2b8365bf43d54ab074940923ef8267f4c6/crates/victory-formats/src/texture.rs)

The texture has two array slices of 1024×1024, each with two mips. The planner produces one 16-texel-aligned box for a dirty 64 KiB tile in mip 0 of slice 1. The CPU emitter checks which physical blocks belong to that box and checks that all three other subresources yield unchanged plans. The native fixture checks the device's BC7 support and obtains D3D12 footprints for all four subresources. Coordinates use texels. Each 4×4 compressed block occupies 16 bytes, and row counts and row sizes are verified in blocks. [Microsoft CopyTextureRegion](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12graphicscommandlist-copytextureregion) · [D3D12 buffer footprints](https://learn.microsoft.com/en-us/windows/win32/direct3d12/upload-and-readback-of-texture-data) · [BC7 blocks](https://learn.microsoft.com/en-us/windows/win32/direct3d11/bc7-format)

Both arms start with the same generated BC7 mode-6 blocks. After a fence, the full-reference arm posts the complete updated subresource and the regional arm posts only the planner's box. The regional staging buffer contains different valid blocks outside the box too, so an unintended copy would appear in readback. A final fence precedes a word-by-word check of both textures against the generated reference. The checks cover 2,621,440 bytes total, 4,096 changed blocks and 159,744 blocks that must remain unchanged, including all three other subresources. The compared update requests are 1,048,576 and 65,536 bytes. The proof covers requested copy size and byte correctness. [BC7 mode 6](https://learn.microsoft.com/en-us/windows/win32/direct3d11/bc7-format-mode-reference#mode-6)

## Reproduce

```powershell
.\build.ps1 -Rustc rustc -Compiler clang++ -OutputDirectory .\replay-a
.\replay-a\native-bc7.exe --hardware
```

Use a recent Rust toolchain with edition 2024 and LLVM-MinGW. For gnullvm, add `-RustLinker` with the compiler path. The build checks the exact source identities and runs the CPU controls without opening a D3D12 device. The optional native command checks the original RTX adapter and uses the 4 GiB free-commit and 6 GiB free-RAM admission guard, a 512 MiB job cap and a three-second deadline. The test submits only Direct3D 12 copies and readback. It needs no shaders or game files.

The exact Rust and C++ build passed. The physical-address oracle checked all 163,840 blocks and the BC7 mode-6 source control passed. The planner mapped `[0x1d0000, 0x1e0000)` to `[256,512) × [256,512)` in subresource 2. [Generated copy box](proof-a/copy-case.inc) · [CPU evidence](proof-a/cpu-evidence.json)

The first scheduled native slot stopped before starting a worker. Its immediate sample had 3,584,720,896 bytes of free system commit, below the 4 GiB requirement. A later slot admitted the same executable with 4,695,928,832 bytes of free system commit and 11,155,546,112 bytes of free physical memory. [First admission record](proof-a/native-preflight.json) · [Completed run receipt](proof-a/native-receipt.json)

On an NVIDIA GeForce RTX 4070 Ti SUPER running Windows 11 Pro build 28000, both copies matched the independently generated reference across all **2,621,440 bytes per arm**. The requested update changed from **1,048,576 to 65,536 bytes**, with 4,096 expected blocks updated, 159,744 blocks preserved and no mismatched 32-bit words. All three other subresources were preserved. The D3D12 device returned `S_OK`; the debug layer was unavailable. The guarded worker exited and was reaped at a peak of 122,314,752 bytes. This is a separate BC7 correctness result with no timestamp collection. [Native readback log](proof-a/native.log)
