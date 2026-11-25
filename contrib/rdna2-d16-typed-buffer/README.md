# Native RDNA2 D16 typed-buffer load probe

This source-only probe runs the 17 cases from [PortBridge #85](https://github.com/akimfomin/PortBridge/issues/85), filed by KainanP. Each case reads one four-byte HIP allocation slot with the exact same instruction. The buffer resource format selects the conversion. A full Wave32 begins with EXEC set for all 32 lanes. One lane runs the cases and records the 32-bit destination word from each. Each row has a tag written by the same store as its value. The launcher requires all tags, full initial EXEC and the A5 control's lower 16 bits of 3c00. It prints the full destination word, including both halves, so the report retains unexpected results.

## What remains open

The input words are synthetic examples from KainanP's public test request. AMD documents the D16 load and resource formats in the RDNA2 ISA. The case-specific conversion results still need a native run for this probe. [AMD RDNA2 ISA](https://www.amd.com/content/dam/amd/en/documents/radeon-tech-docs/instruction-set-architectures/rdna2-shader-instruction-set-architecture.pdf) · [Receiving AnyXboxX PR](https://github.com/LooperSalty/AnyXboxX/pull/230)

- A1–A4 distinguish exact quotient rounding from rounding through float32 for 16_UNORM and 16_SNORM. A5 is the 1.0 sanity control.
- B1–B8 cover 32_FLOAT rounding, overflow, subnormals and NaNs.
- C1 checks 16_FLOAT signaling NaN handling. C2–C3 cover 16_USCALED rounding and overflow. C4 checks how 32_UINT narrows to a D16 result.

## Build and run on physical RDNA2

Use a working HIP environment where the physical gfx103x device is available. Set the exact architecture in the assembly and compile settings. The launcher requires gfx103x, Wave32 and an input range that fits the V# descriptor's 48-bit byte address.

```sh
target=gfx1030
sed "s/gfx1030/$target/g" d16_probe.s > d16_probe-local.s
amdclang++ -target amdgcn-amd-amdhsa -mcpu="$target" -mcode-object-version=5 -x assembler -c d16_probe-local.s -o d16_probe.o
ld.lld -shared d16_probe.o -o d16_probe.hsaco
hipcc -std=c++17 launch.cpp -o launch
./launch d16_probe.hsaco
```

On Windows substitute the architecture in a copy of the assembly before building, use the configured HIP SDK's Clang and run the resulting launch.exe. If using standalone LLVM tools, use an AMDGPU-enabled llvm-mc and a code object ABI supported by the installed HIP runtime. [LLVM AMDGPU ABI](https://llvm.org/docs/AMDGPUUsage.html) · [HIP modules](https://rocm.docs.amd.com/projects/HIP/en/latest/doxygen/html/group___module.html)

Report the complete aggregate line with initial EXEC and all 17 case values, plus the GPU model and target, OS, driver, assembly tool version and code-object SHA-256. [Report thread](https://github.com/akimfomin/PortBridge/issues/85)

## Offline verification

LLVM 23.1.6 assembled the probe and LLD linked it for gfx1030 and gfx1036. Disassembly of each ELF found 17 instances of the exact `00 00 00 e2 00 00 01 80` instruction and 18 tagged stores. The host launcher passed 23 mock scenarios. It accepted a complete result with a changed A5 upper half and rejected each of the 18 missing rows, bad A5, wrong EXEC, a non-RDNA2 target and a pointer outside the address range. The mock validates reporting and setup. Physical results and SDK runtime compatibility remain open.
