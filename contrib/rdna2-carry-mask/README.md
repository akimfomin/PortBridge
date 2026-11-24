# AnyXboxX #133 native RDNA2 carry probe

This synthetic probe reproduces the Wave32 carry-mask inputs in [AnyXboxX at e2af2d38](https://github.com/LooperSalty/AnyXboxX/blob/e2af2d38e48b5a0019dae5c78aa398cc71c42c8d/tests/test_rdna2_exec_vop12.py#L120-L130). It uses five output integers and a single GPU workgroup.

## Offline assembler check

```sh
llvm-mc -triple=amdgcn-amd-amdhsa -mcpu=gfx1036 -mattr=+wavefrontsize32 -filetype=asm -show-encoding carry_probe.s
```

## Native run

Use a physical RDNA2 Wave32 device and a HIP setup that can launch code objects on it. The assembly and build below target `gfx1036`. To use another RDNA2 model, change both target strings in `carry_probe.s` and the `-mcpu` setting. Set `HIP_VISIBLE_DEVICES` if the system has multiple supported AMD GPUs. On Windows use the HIP SDK's `clang++` in place of `amdclang++` from a configured x64 developer shell, then run `launch.exe`.

```sh
amdclang++ -target amdgcn-amd-amdhsa -mcpu=gfx1036 -mcode-object-version=5 -x assembler -c carry_probe.s -o carry_probe.o
ld.lld -shared carry_probe.o -o carry_probe.hsaco
hipcc -std=c++17 launch.cpp -o launch
./launch carry_probe.hsaco
```

The host checks that all 32 lanes started enabled, lane 0 produced zero in both sums, and bit 0 is set in each carry output. Report the full output line, driver version, OS, and the exact target. The two carry masks distinguish these cases.

| `carry_e32` or `carry_e64` | Interpretation for that instruction |
| --- | --- |
| `00000001` | Inactive carry bits clear |
| `ffffffff` | Inactive carry bits preserve the preload |
| Any other value | Report the exact value for follow-up |

A mixed pair distinguishes the two instruction forms. The assembly was checked offline with LLVM 23.1.6. HIP launch and silicon behavior still need a hardware run.

[LLVM AMDGPU ABI](https://llvm.org/docs/AMDGPUUsage.html) · [AMD HIP module API](https://rocm.docs.amd.com/projects/HIP/en/latest/doxygen/html/group___module.html) · [AMD HIP Windows compiler](https://rocmdocs.amd.com/projects/HIP/en/latest/faq.html)
