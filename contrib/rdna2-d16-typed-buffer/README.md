# Native RDNA2 D16 typed-buffer load probe

This source-only probe runs the 17 cases from [PortBridge #85](https://github.com/akimfomin/PortBridge/issues/85), filed by KainanP. Each case reads one four-byte HIP allocation slot with the exact same instruction. The buffer resource format selects the conversion. A full Wave32 begins with EXEC set for all 32 lanes. One lane runs the cases and records the 32-bit destination word from each. Each row has a tag written by the same store as its value. The launcher requires all tags, full initial EXEC and the A5 control's lower 16 bits of 3c00. It prints the upper and lower halves so the report retains unexpected results.

## What remains open

AnyXboxX #230 now incorporates a sweep on an RX 6700, gfx1031. A1–A4 already distinguish exact quotient rounding from an intermediate float32 with native data. The sweep also observed that 16_FLOAT bit patterns pass through unchanged, which covers C1. Use those five cases as cross-device controls. B1–B8 still test assumptions about conversion of 32_FLOAT, including rounding, overflow, subnormals and NaNs. C2–C3 cover 16_USCALED conversion, and C4 covers the 32_UINT conversion that AnyXboxX #230 currently refuses. [Current AnyXboxX change](https://github.com/LooperSalty/AnyXboxX/pull/230) · [Native sweep, cases A1–A4 and C1](https://github.com/ubiquitarianism/leonida/blob/9f9a7c5f30f8559c52675780cf84004571b8d6e5/docs/shader_validation.md#L1612-L1665)

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

Report only the aggregate result line, GPU model and target, OS, driver, assembly tool and code-object SHA-256. [Report thread](https://github.com/akimfomin/PortBridge/issues/85)

## Offline verification

LLVM 23.1.6 assembled the probe and LLD linked it for gfx1030 and gfx1036. Disassembly of each ELF found 17 instances of the exact `00 00 00 e2 00 00 01 80` instruction and 18 tagged stores. The host launcher passed 23 mock scenarios. It accepted a complete result with a changed A5 upper half and rejected each of the 18 missing rows, bad A5, wrong EXEC, a non-RDNA2 target and a pointer outside the address range. The mock validates reporting and setup. Physical results and SDK runtime compatibility remain open. [AMD RDNA2 ISA](https://www.amd.com/content/dam/amd/en/documents/radeon-tech-docs/instruction-set-architectures/rdna2-shader-instruction-set-architecture.pdf)
