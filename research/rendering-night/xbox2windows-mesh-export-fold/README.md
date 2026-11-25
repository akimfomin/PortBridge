# Share identical runtime mesh exports

This proposed Xbox2Windows change shares identical emitted vertex and primitive export bodies. Each original input predicate and mesh allocation remains in the shader. The patch targets the bounded runtime mesh translator at `4c1b27dd80bf921fb0ca4188d73350e8d6bfb0a1`. The source-built test extends avt0m4t48’s geometry fixture. [Runtime mesh task #1760](https://github.com/R0Y00/Xbox2Windows/issues/1760) · [PortBridge Test Lab](https://akimfomin.github.io/PortBridge/#/lab)

| 32-partition fixture | Baseline | Shared exports |
| --- | ---: | ---: |
| Emitted export blocks | 32 | 2 |
| HLSL bytes | 53,142 | 16,858 |
| Optimized DXIL bytes | 26,556 | 5,736 |
| Static DXIL vertex-output call sites | 1,024 | 64 |
| Static DXIL index-output call sites | 64 | 4 |

Dispatch counts, vertex positions, attributes and primitive indices matched across 65 inputs. On an RTX 4070 Ti SUPER, baseline and candidate each matched all 1,024 reference pixels for a triangle and a quad. A stale-pixel-only reference on the candidate failed with the expected 528 mismatches. D3D12 debug layer unavailable. The shader-size counts are static compiler output. [Compiler proof](COMPILER-PROOF.txt) · [GPU proof](GPU-PROOF.txt)

## Reproduce

Use Python 3.11 or newer, an AMDGPU-capable LLVM assembler and objcopy, and DXC. Local evidence used LLVM MC 23.1.6 and DXC 1.9.2609. Create a clean baseline checkout and a separate copy with [the patch](0001-mesh-share-runtime-export-bodies.patch) applied.

```sh
python -B verify_fold.py baseline --repo ./Xbox2Windows-base --output out/baseline --oracle out/oracle.txt --llvm-mc llvm-mc --llvm-objcopy llvm-objcopy --dxc dxc
python -B verify_fold.py candidate --repo ./Xbox2Windows-candidate --output out/candidate --oracle out/oracle.txt --llvm-mc llvm-mc --llvm-objcopy llvm-objcopy --dxc dxc
python -B ./Xbox2Windows-candidate/tests/mesh_dynamic_aot_check.py
```

The verifier assembles and compares the source-built programs, compiles them, and writes two expected-pixel files and a stale reference for the existing Windows D3D12 fixture. Build that fixture from either Xbox2Windows checkout using `cmake --build --preset release --target offscreen_check`. Run the four matched draws serially. This example runs the candidate triangle.

```powershell
$env:XBOX2WINDOWS_ADAPTER = "NVIDIA GeForce RTX 4070 Ti SUPER"
./Xbox2Windows-candidate/out/build/release/offscreen_check.exe hardware --mesh-indexed out/candidate/candidate.dxil out/candidate/solid-magenta.dxil out/candidate/geometry-1-triangle.bin
```

Repeat with `geometry-2-quad.bin` and with the baseline DXIL. For the stale control, keep candidate DXIL and use `geometry-1-stale-quad-pixels.bin`. Expect exit 1 and exactly 528 mismatches. Report exit 77 as a capability skip.
