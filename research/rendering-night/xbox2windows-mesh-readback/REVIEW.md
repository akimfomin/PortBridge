# Independent verification for Xbox2Windows #2127

Reviewed Leyukaka’s head `2dc58a8bdf7e6ed8f4ff2ca4a2f5463c2f34c4d0`. The fixture is synthetic. It extends the repository’s three-vertex mesh test and does not change the pull request’s source. avt0m4t48 previously reported CPU and DXIL checks for a separate implementation and released the claim. R0Y00 requested a fenced pixel check that depends on a recovered high EXEC word.

| Variant | Recovered EXEC words (low, high) | CPU vertex depth | 32 × 32 readback | Pixel mismatches |
| --- | --- | --- | --- | --- |
| Both inactive slots restored | `0x00000001`, `0x00000100` | +0.5 | 1,024 green pixels | 0/1,024 |
| Write zero to low slot | `0x00000000`, `0x00000100` | −0.5 | 1,024 clear pixels | 0/1,024 |
| Write zero to high slot | `0x00000001`, `0x00000000` | −0.5 | 1,024 clear pixels | 0/1,024 |
| Compare the first draw to stale clear pixels | Same as first case | +0.5 | 1,024 green pixels, same export trace | 1,024/1,024, expected exit 1 |

LLVM MC 23.1.6 assembled the three original programs as gfx1013 Wave64 and verified each decoded byte. The exact pull request’s lowerer emitted the expected HLSL. DXC 1.9.2609 compiled traced and untraced mesh shaders for each case. [Compiler evidence](COMPILER-PROOF.txt)

All four native draws ran on a GeForce RTX 4070 Ti SUPER (PCI `10de:2705`), driver `32.0.16.1714`, Windows 11 build `28000`. The D3D12 debug layer was unavailable. The byte-identical traced DXIL from the reviewed head ran through the `offscreen_check` runner built at `84ce29421ab6`. The mesh draw, command dispatch and shared GPU runner sources in that executable match the reviewed head. The harness fenced each draw before comparing the exports and pixels. [Readback log and renderer provenance](GPU-PROOF.txt)

The lowerer resolves the guest Wave64 instructions on the CPU. The readback verifies the resulting D3D12 mesh shader on a host with Mesh Shader Tier 1. Native execution of the original gfx1013 instructions on AMD hardware remains a separate check.

The pull request’s documented scope rejects SGPR-selected lanes. A separately assembled case defines `s44=8` and `s45=40` before the two writes. The exact pull-request lowerer refuses it at the first write. That is a coverage boundary that can help triage the next slice.

## Reproduce

Run from a clean checkout of the specified head with [the companion script](mesh_spill_readback.py) available.

```powershell
python -B path/to/mesh_spill_readback.py --repo .
python -B path/to/mesh_spill_readback.py --repo . --prepare dxc out/mesh-spill
.\tools\dev.ps1
cmake --preset dev
cmake --build --preset dev --target offscreen_check
$env:XBOX2WINDOWS_ADAPTER = "NVIDIA GeForce RTX 4070 Ti SUPER"
python -B path/to/mesh_spill_readback.py --repo . --draw dxc out/build/dev/offscreen_check.exe hardware
```

The `--prepare` command writes DXIL and references without opening a GPU device. Use `warp` in place of `hardware` for WARP. Report exit 77 as a capability skip with the adapter, driver and Windows build. For the full assembly-to-HLSL check on Linux CI, use the repository’s LLVM 15 tools.

```sh
python -B path/to/mesh_spill_readback.py --repo . --binary llvm-mc-15 llvm-objcopy-15 libLLVM-15.so.1
```

[Pull request](https://github.com/R0Y00/Xbox2Windows/pull/2127) · [Previous contributor’s report](https://github.com/R0Y00/Xbox2Windows/issues/1998#issuecomment-7147147674) · [Maintainer’s remaining check](https://github.com/R0Y00/Xbox2Windows/issues/1998#issuecomment-7147403030) · [AMD RDNA 2 ISA](https://www.amd.com/content/dam/amd/en/documents/radeon-tech-docs/instruction-set-architectures/rdna2-shader-instruction-set-architecture.pdf)

## Optional known-register selector follow-up

An isolated add-on on this exact PR head accepts a selector only when the existing scalar model proves its value. The scalar-encoded source reproduced all eight shader/reference hashes from the RTX-verified inline controls. A dynamic selector still refuses. [Optional patch, encoding and proof](known-sgpr/REVIEW.md)
