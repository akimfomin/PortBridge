# AnyXboxX #203 native RDNA2 `v_fma_f32` NaN results

This synthetic probe measures which NaN `v_fma_f32` returns on RDNA2. [AnyXboxX #203](https://github.com/LooperSalty/AnyXboxX/pull/203) made the f32 FMAs round once and, for NaN results, chose a rule that it marks as assumed, not measured: the first NaN operand made quiet, otherwise (∞ × 0, ∞ − ∞) the positive quiet NaN `7fc00000`. [Rule in the merged interpreter](https://github.com/LooperSalty/AnyXboxX/blob/6802e44b5201391a300d723ced1613d79b4e82c9/PrototypeScarlett/emu/rdna2_exec_ops.py#L249-L255)

## Question and hypotheses

| Hypothesis | NaN operand | Invalid operation (∞ × 0, ∞ − ∞) | Source |
| --- | --- | --- | --- |
| **AnyXboxX #203** | First NaN in S0, S1, S2 order, made quiet, sign and payload kept | `7fc00000` | Assumption in #203; the ISA does not say which NaN an FMA returns |
| **Measured on RDNA 3.5** | First NaN (lowest source), quiet; with IEEE off a signalling NaN passes unchanged | `ffc00000` | Leonida's f32 hardware fuzzer on gfx1150, not RDNA2: "With several NaN operands the first (lowest source) wins in add/mul/fma/fmaak/fmac", "Invalid operations (inf - inf, 0 * inf, ...) give `0xffc00000` in every mode and op, never `0x7fc00000`" ([leonida shader_validation.md](https://github.com/ubiquitarianism/leonida/blob/9f9a7c5f30f8559c52675780cf84004571b8d6e5/docs/shader_validation.md#L1305-L1331)). Its RDNA2 runs (gfx1036, gfx1031) matched the model but did not judge NaN payloads. |
| **Canonical NaN** | `7fc00000` | `7fc00000` | Listed to recognise a default-NaN unit |

On RDNA2 the negative default NaN is already measured for other ops: `v_fract_f32(±inf)` gives `ffc00000` on gfx1036 and f16 transcendentals give `fe00` ([leonida design.md](https://github.com/ubiquitarianism/leonida/blob/9f9a7c5f30f8559c52675780cf84004571b8d6e5/docs/design.md#L411)). No RDNA2 measurement of the FMA cases below was found.

## Inputs

One Wave32 lane (EXEC = 1), `v_fma_f32` (VOP3, D = S0 × S1 + S2). Each NaN has its own payload so the winner can be read from the result. The same 14 instructions run in two kernels, one with MODE.IEEE = 1 and one with MODE.IEEE = 0; both keep denormals and DX10_CLAMP = 1, as in the other probes.

| Field | S0, S1, S2 | AnyXboxX #203 | Measured on RDNA 3.5 | Canonical NaN |
| --- | --- | --- | --- | --- |
| f1 | 2, 3, 1 | 7.0 = `40e00000` | `40e00000` | `40e00000` |
| f2 | NaN `7fc00001`, 1, 0 | `7fc00001` | `7fc00001` | `7fc00000` |
| f3 | 1, NaN `7fc00002`, 0 | `7fc00002` | `7fc00002` | `7fc00000` |
| f4 | 1, 1, NaN `7fc00003` | `7fc00003` | `7fc00003` | `7fc00000` |
| f5 | sNaN `7f800005`, 1, 0 | quiet: `7fc00005` | IEEE 1: `7fc00005`, IEEE 0: `7f800005` | `7fc00000` |
| f6 | NaN `ffc00006`, 1, 0 | `ffc00006` | `ffc00006` | `7fc00000` |
| f7 | NaN `7fc00007`, 1, NaN `7fc00008` | S0: `7fc00007` | `7fc00007` | `7fc00000` |
| f8 | 1, NaN `7fc00009`, NaN `7fc0000a` | S1: `7fc00009` | `7fc00009` | `7fc00000` |
| f9 | NaN `7fc0000b`, NaN `7fc0000c`, 0 | S0: `7fc0000b` | `7fc0000b` | `7fc00000` |
| f10 | +inf, 0, 1 | `7fc00000` | `ffc00000` | `7fc00000` |
| f11 | +inf, 1, −inf | `7fc00000` | `ffc00000` | `7fc00000` |
| f12 | +inf, 0, NaN `7fc0000d` | the NaN operand: `7fc0000d` | `7fc0000d` (one NaN operand) | `7fc00000` |
| f13 | NaN `7fc0000e`, sNaN `7f80000f`, 0 | S0: `7fc0000e` | `7fc0000e` | `7fc00000` |
| f14 | −inf, 0, 1 | `7fc00000` | `ffc00000` | `7fc00000` |

f13 also shows whether a signalling NaN takes priority over an earlier quiet one, as on some other architectures; that would give `7fc0000f`. Any other word is worth reporting as observed.

## Expected output lines

The launcher prints one line per kernel. AnyXboxX has no MODE, so its rule gives the same line twice.

Under **AnyXboxX #203** (both lines):

```text
ieee1 initial_exec=ffffffff f1-f14=40e00000,7fc00001,7fc00002,7fc00003,7fc00005,ffc00006,7fc00007,7fc00009,7fc0000b,7fc00000,7fc00000,7fc0000d,7fc0000e,7fc00000
ieee0 initial_exec=ffffffff f1-f14=40e00000,7fc00001,7fc00002,7fc00003,7fc00005,ffc00006,7fc00007,7fc00009,7fc0000b,7fc00000,7fc00000,7fc0000d,7fc0000e,7fc00000
```

Under **Measured on RDNA 3.5**:

```text
ieee1 initial_exec=ffffffff f1-f14=40e00000,7fc00001,7fc00002,7fc00003,7fc00005,ffc00006,7fc00007,7fc00009,7fc0000b,ffc00000,ffc00000,7fc0000d,7fc0000e,ffc00000
ieee0 initial_exec=ffffffff f1-f14=40e00000,7fc00001,7fc00002,7fc00003,7f800005,ffc00006,7fc00007,7fc00009,7fc0000b,ffc00000,ffc00000,7fc0000d,7fc0000e,ffc00000
```

Under **Canonical NaN** (both lines):

```text
ieee1 initial_exec=ffffffff f1-f14=40e00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000
ieee0 initial_exec=ffffffff f1-f14=40e00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000,7fc00000
```

The launcher fails if EXEC was not `ffffffff` or f1 is not 7.0 in either kernel.

## Offline assembler check

```sh
llvm-mc -triple=amdgcn-amd-amdhsa -mcpu=gfx1030 -mattr=+wavefrontsize32 -filetype=asm -show-encoding fma_nan_probe.s
```

LLVM 20.1.8 (Linux release build) assembled the probe for `gfx1030` and `gfx1036` without errors or warnings, and `ld.lld` linked both code objects. All operands other than VGPRs are inline constants (VOP3 opcode `0x14b`). The two kernel descriptors differ only in the IEEE bit of COMPUTE_PGM_RSRC1 (`0x60af0004` and `0x602f0004`). The launcher passes an MSVC `/W4` syntax check against a stub HIP header. It has not run on AMD hardware yet.

## Native run

Use a physical RDNA2 Wave32 device and a HIP setup that can launch code objects on it. The assembly and build target `gfx1030`. For another RDNA2 model, change both target strings in `fma_nan_probe.s` and the `-mcpu` setting, for example `sed -i 's/gfx1030/gfx1036/g' fma_nan_probe.s`. Set `HIP_VISIBLE_DEVICES` if the system has multiple supported AMD GPUs. On Windows use the HIP SDK's `clang++` in place of `amdclang++` from a configured x64 developer shell, then run `launch.exe`.

```sh
amdclang++ -target amdgcn-amd-amdhsa -mcpu=gfx1030 -mcode-object-version=5 -x assembler -c fma_nan_probe.s -o fma_nan_probe.o
ld.lld -shared fma_nan_probe.o -o fma_nan_probe.hsaco
hipcc -std=c++17 launch.cpp -o launch
./launch fma_nan_probe.hsaco
```

Report both output lines, driver version, OS and the exact target. A port into another harness is fine if it keeps the instructions, operands, their order and the two MODE settings, as in [PortBridge #19](https://github.com/akimfomin/PortBridge/issues/19#issuecomment-7136020663).

[LLVM AMDGPU ABI](https://llvm.org/docs/AMDGPUUsage.html) · [AMD HIP module API](https://rocm.docs.amd.com/projects/HIP/en/latest/doxygen/html/group___module.html)
