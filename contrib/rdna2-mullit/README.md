# AnyXboxX #151 native RDNA2 `v_mullit_f32` probe

This synthetic probe measures the special-value rules of `v_mullit_f32` on RDNA2. [AnyXboxX #151](https://github.com/LooperSalty/AnyXboxX/pull/151) leaves the instruction untranslated because AMD's RDNA2 description ("0.0 * x = 0.0") contradicts the RDNA3 pseudo-code for 0 × +inf. A measurement can replace that refusal with a tested rule.

## Question and hypotheses

`v_mullit_f32` is the multiply of the old Direct3D `lit` instruction. It takes three operands: S0 × S1 is the product and S2 acts as a guard. The sources disagree on the guard, on zero times infinity or NaN, and on which S1 values force the guard result.

| Hypothesis | Rule | Source |
| --- | --- | --- |
| **RDNA2 description** | S0 × S1 with "0.0 * x = 0.0". S2 is not mentioned. Other "INF, NaN, overflow rules" are not stated. | AMD RDNA2 ISA guide §12.12, printed p.170 ([PDF p.178](http://web.archive.org/web/20230214072857id_/https://developer.amd.com/wp-content/resources/RDNA2_Shader_ISA_November2020.pdf#page=178)): "Multiply for lighting. Specific rules apply: 0.0 * x = 0.0; Specific INF, NaN, overflow rules. `D.f = S0.f * S1.f`" |
| **GCN (CLRX)** | If S2 is not greater than 0 or is NaN: −MAX_FLOAT. Otherwise, if S0 or S1 is ±0: +0.0. Otherwise IEEE S0 × S1. | CLRX GCN documentation for `V_MULLIT_F32` ([CLRX `GcnInstrsVop3.md`](https://github.com/CLRX/CLRX-mirror/blob/fb8fbf972e19ea1fb1f7a9c8d84fdef1bf7cc3df/doc/GcnInstrsVop3.md#L1897-L1914)) |
| **RDNA3 pseudo-code** | If S1 is −MAX_FLOAT, −inf or NaN, or S2 ≤ 0 or NaN: −MAX_FLOAT. Otherwise IEEE S0 × S1, so 0 × inf is NaN. | AMD RDNA3 pseudo-code as extracted by tinygrad ([tinygrad `str_pcode.py`](https://github.com/tinygrad/tinygrad/blob/e3bdfb1d59c42c05b295aae1636f75a95fd38ae5/tinygrad/runtime/autogen/amd/rdna3/str_pcode.py#L1078)) |

No public native measurement of these cases was found on RDNA2 or RDNA3. tinygrad's RDNA3 tests cover only 2 × 3 with guard 1.0 (6.0) and guard 0.0 (`ff7fffff`), and they are compared with hardware only when run with `USE_HW=1`. [tinygrad tests](https://github.com/tinygrad/tinygrad/blob/e3bdfb1d59c42c05b295aae1636f75a95fd38ae5/test/amd/hw/test_vop3.py#L23-L43) · [USE_HW note](https://github.com/tinygrad/tinygrad/blob/e3bdfb1d59c42c05b295aae1636f75a95fd38ae5/test/amd/hw/helpers.py#L1-L4)

## Inputs

One Wave32 lane (EXEC = 1). MAX_FLOAT is `7f7fffff`, −MAX_FLOAT `ff7fffff`. A NaN result is written as `7fc00000`, the input NaN and the usual default quiet NaN. Any NaN encoding (exponent all ones, nonzero mantissa) counts as a match.

| Field | S0 × S1, S2 | RDNA2 description | GCN (CLRX) | RDNA3 pseudo-code |
| --- | --- | --- | --- | --- |
| c1 | 2 × 3, 1.0 | 6.0 = `40c00000` | `40c00000` | `40c00000` |
| c2 | 2 × 3, +0 | `40c00000` | S2 ≤ 0: `ff7fffff` | S2 ≤ 0: `ff7fffff` |
| c3 | 2 × 3, −1.0 | `40c00000` | `ff7fffff` | `ff7fffff` |
| c4 | 2 × 3, NaN | `40c00000` | `ff7fffff` | `ff7fffff` |
| c5 | 0 × +inf, 1.0 | 0.0 rule: `00000000` | S0 = 0: `00000000` | IEEE invalid: `7fc00000` |
| c6 | +inf × 0, 1.0 | `00000000` | S1 = 0: `00000000` | `7fc00000` |
| c7 | 2 × −inf, 1.0 | −inf = `ff800000` | `ff800000` | S1 = −inf: `ff7fffff` |
| c8 | 2 × NaN, 1.0 | `7fc00000` | `7fc00000` | S1 NaN: `ff7fffff` |
| c9 | 2 × −MAX, 1.0 | overflow: `ff800000` | `ff800000` | S1 = −MAX: `ff7fffff` |
| c10 | −0 × 5, 1.0 | 0.0 rule: `00000000` | S0 = 0: `00000000` | IEEE: −0 = `80000000` |
| c11 | MAX × 2, 1.0 | overflow: `7f800000` | `7f800000` | `7f800000` |
| c12 | NaN × 0, 1.0 | 0.0 rule: `00000000` | S1 = 0: `00000000` | NaN propagates: `7fc00000` |
| c13 | 2 × 3, −0 | `40c00000` | −0 is not > 0: `ff7fffff` | −0 ≤ 0: `ff7fffff` |
| c14 | 0 × NaN, 1.0 | 0.0 rule: `00000000` | S0 = 0: `00000000` | S1 NaN: `ff7fffff` |

Arithmetic. 6.0 = 1.5 × 2^2 has exponent 129 = `0x81` and mantissa `0x400000`, so `0x81 << 23 | 0x400000` = `40c00000`. 2 × (−MAX_FLOAT) and MAX_FLOAT × 2 exceed the f32 range and round to ±inf in round-to-nearest-even. The RDNA2 description does not say whether its 0.0 rule keeps the sign of −0 × 5 (c10). Its unstated overflow rule could also clamp c9 and c11 to ∓MAX_FLOAT. Report such fields as observed.

## Expected output line

Under **RDNA2 description**:

```text
initial_exec=ffffffff c1-c14=40c00000,40c00000,40c00000,40c00000,00000000,00000000,ff800000,7fc00000,ff800000,00000000,7f800000,00000000,40c00000,00000000
```

Under **GCN (CLRX)**:

```text
initial_exec=ffffffff c1-c14=40c00000,ff7fffff,ff7fffff,ff7fffff,00000000,00000000,ff800000,7fc00000,ff800000,00000000,7f800000,00000000,ff7fffff,00000000
```

Under **RDNA3 pseudo-code**:

```text
initial_exec=ffffffff c1-c14=40c00000,ff7fffff,ff7fffff,ff7fffff,7fc00000,7fc00000,ff7fffff,ff7fffff,ff7fffff,80000000,7f800000,7fc00000,ff7fffff,ff7fffff
```

The launcher fails if EXEC was not `ffffffff` or c1 is not 6.0.

## Offline assembler check

```sh
llvm-mc -triple=amdgcn-amd-amdhsa -mcpu=gfx1030 -mattr=+wavefrontsize32 -filetype=asm -show-encoding mullit_probe.s
```

LLVM 20.1.8 assembled the probe without errors or warnings, with three source operands (VOP3 opcode `0x150`). It has not run on AMD hardware yet. The kernel descriptor requests round-to-nearest-even, no denormal flushing, DX10 clamp and IEEE mode.

## Native run

Use a physical RDNA2 Wave32 device and a HIP setup that can launch code objects on it. The assembly and build target `gfx1030`. For another RDNA2 model, change both target strings in `mullit_probe.s` and the `-mcpu` setting, for example `sed -i 's/gfx1030/gfx1036/g' mullit_probe.s`. Set `HIP_VISIBLE_DEVICES` if the system has multiple supported AMD GPUs. On Windows use the HIP SDK's `clang++` in place of `amdclang++` from a configured x64 developer shell, then run `launch.exe`.

```sh
amdclang++ -target amdgcn-amd-amdhsa -mcpu=gfx1030 -mcode-object-version=5 -x assembler -c mullit_probe.s -o mullit_probe.o
ld.lld -shared mullit_probe.o -o mullit_probe.hsaco
hipcc -std=c++17 launch.cpp -o launch
./launch mullit_probe.hsaco
```

Report the full output line, driver version, OS and the exact target. A port into another harness is fine if it keeps the instructions, operands and their order, as in [PortBridge #19](https://github.com/akimfomin/PortBridge/issues/19#issuecomment-7136020663).

[LLVM AMDGPU ABI](https://llvm.org/docs/AMDGPUUsage.html) · [AMD HIP module API](https://rocm.docs.amd.com/projects/HIP/en/latest/doxygen/html/group___module.html)
