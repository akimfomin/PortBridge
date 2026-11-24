# Native RDNA2 Wave64 gather probe

AnyXboxX #147 compares translated HLSL with its interpreter. A reviewer reported that the native behavior of `ds_bpermute_b32` in Wave64 remained to be measured. AMD documents a separate 32-lane gather in each half of that wave. This synthetic probe reads the same five-bit lane index twice while changing address bit 7. [AnyXboxX report](https://github.com/LooperSalty/AnyXboxX/pull/147#issuecomment-7140576454) · [AMD RDNA2 ISA, §10.4.4](https://docs.amd.com/api/khub/documents/Et~wpu9g~Ffl7d9q0QZ~Og/content)

## Assemble and inspect

```text
llvm-mc -triple=amdgcn-amd-amdhsa -mcpu=gfx1036 -mattr=+wavefrontsize64 -filetype=obj bpermute_probe.s -o bpermute_probe.o
ld.lld -shared bpermute_probe.o -o bpermute_probe.hsaco
llvm-readobj --notes bpermute_probe.hsaco
```

LLVM 23.1.6 assembled and linked this source for `gfx1036`. The code object records a 64-lane wave and a maximum workgroup size of 64. A run still needs a physical RDNA2 device and a HIP setup that can launch this target in Wave64.

## Run and report

With HIP already configured, build and run the optional launcher. On Windows, use `launch.exe`.

```sh
hipcc -std=c++17 launch.cpp -o launch
./launch bpermute_probe.hsaco
```

The launcher records all 64 rows and checks the sentinel, lane IDs, EXEC and both address controls. Its C++ syntax was checked offline with local API stubs. The launcher and kernel still need a native HIP run.

You can use an existing HIP module harness instead. Launch `bpermute_probe` with grid `1,1,1`, group `64,1,1`, no dynamic LDS and one argument, an 8-byte device pointer. Allocate 1,024 bytes for the result and initialize it to a sentinel. The kernel writes four little-endian 32-bit words at byte offset `16 * lane`.

| Word | Recorded value | Expected under the half-wave rule |
| --- | --- | --- |
| 0 | Physical wave lane number | `lane` for all 64 records |
| 1 | Gather at byte address `4 * ((lane & 31) ^ 1)` | `0xa5000000 + (lane ^ 1)` |
| 2 | Gather at the same byte address plus 128 | Same result as word 1 |
| 3 | Bitwise AND of the two initial EXEC words | `ffffffff` in all 64 records |

A full-wave gather would put lower-half tags in word 1 for both halves and upper-half tags in word 2 for both halves. Two Wave32 waves cannot pass the lane and EXEC controls.

Report the GPU target, platform, driver and assembler, and either all 64 records or the four words for lanes 0, 31, 32 and 63 with the overall control result. If the toolchain cannot load or launch Wave64, report the error and record a skip. [Receiving thread](https://github.com/LooperSalty/AnyXboxX/pull/147)
