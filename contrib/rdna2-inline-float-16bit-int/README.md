# AnyXboxX #221 native RDNA2 inline float constants on 16-bit integer sources

This synthetic probe measures which 16 bits RDNA2 reads when an inline float constant (`0.5`, `-4.0`, `1/(2π)`, codes 240-248) is the source of a 16-bit integer compare or of `s_pack_*_b32_b16`. [AnyXboxX #221](https://github.com/LooperSalty/AnyXboxX/pull/221) reads the half-precision value on `v_cmp[x]_*_{i16,u16}` sources (`0.5` = `3800`) and refuses an inline float on the 16-bit `s_pack` sources because the value is not settled. Both are taken from documents, not measured. [Compare constants at the PR head](https://github.com/LooperSalty/AnyXboxX/blob/6f5854531f77c46db187fa115a8b413e4453564b/PrototypeScarlett/emu/rdna2_exec_cmp16.py#L12-L24) · [s_pack refusal](https://github.com/LooperSalty/AnyXboxX/blob/6f5854531f77c46db187fa115a8b413e4453564b/PrototypeScarlett/emu/rdna2_exec_bits.py#L99-L102)

## Why the sources disagree

- AMD's RDNA2 ISA (§6.2) calls codes 240-248 "single, double, or half-precision inline floats", and the machine-readable XML sizes the `v_cmp_*_u16` sources and the `s_pack_ll` sources at 16 bits. #221 reads that as the f16 value.
- LLVM's disassembler prints them that way (`v_cmp_eq_u16_e32 vcc_lo, 0x3800, v10` for code 240), but LLVM's own note on the hardware says otherwise for integer 16-bit instructions: "for UI16 instructions: corresponding single-precision float value" ([LLVM `AMDGPUBaseInfo.cpp`](https://github.com/llvm/llvm-project/blob/87f0227cb60147a26a1eeb4fb06e3b505e9c7261/llvm/lib/Target/AMDGPU/Utils/AMDGPUBaseInfo.cpp#L2680-L2690)). Its assembler accepts the f32 encodings for i16 operands (`isInlinableLiteralI16` calls `isInlinableLiteral32`, [L2659-L2661](https://github.com/llvm/llvm-project/blob/87f0227cb60147a26a1eeb4fb06e3b505e9c7261/llvm/lib/Target/AMDGPU/Utils/AMDGPUBaseInfo.cpp#L2659-L2661)).
- Leonida measured related cases on gfx1036: the integer source of `v_cvt_f16_u16_sdwa d, 1.0 src0_sel:WORD_1` reads `3f80`, the high half of the f32 bits, and an inline float on the S2 of `v_mad_i32_i16` "is its f32 pattern" ([design.md L331](https://github.com/ubiquitarianism/leonida/blob/9f9a7c5f30f8559c52675780cf84004571b8d6e5/docs/design.md#L331), [L359](https://github.com/ubiquitarianism/leonida/blob/9f9a7c5f30f8559c52675780cf84004571b8d6e5/docs/design.md#L359)). For 16-bit **float** ops it measured the opposite: the f16 value over a zero high half ([L329](https://github.com/ubiquitarianism/leonida/blob/9f9a7c5f30f8559c52675780cf84004571b8d6e5/docs/design.md#L329)). Neither covers the compares or the SALU packs.

## Question and hypotheses

| Hypothesis | 16-bit integer source with an inline float | 32-bit `s_pack` source (`hh`, S1 of `lh`) |
| --- | --- | --- |
| **AnyXboxX #221** | f16 value (`0.5` → `3800`) | f32 bits |
| **f32 bits** | low half of the f32 bits (`0.5` → `0000`, `1/(2π)` → `f983`) | f32 bits |
| **f16 over zero** | f16 value | f16 value in the low half, zero high half (the rule measured for f16 float ops) |

## Inputs

**VALU compares.** Three lanes (EXEC = 7). For each constant, lane 0 holds the f16 value, lane 1 the low half of the f32 bits and lane 2 the high half, all over a junk high half `abcd`. `v_cmp_eq_u16` compares only bits 15-0, so the mask names the half the hardware read: `1` for f16, `2` for the f32 low half, `4` for the f32 high half, `0` for none of them. Each constant runs as VOPC (`_e32`, mask in VCC) and VOP3 (`_e64`, mask in an SGPR); inactive lanes are written as 0.

| Constant (code) | f16 | f32 | Lane 0 | Lane 1 | Lane 2 |
| --- | --- | --- | --- | --- | --- |
| 0.5 (240) | `3800` | `3f000000` | `abcd3800` | `abcd0000` | `abcd3f00` |
| −4.0 (247) | `c400` | `c0800000` | `abcdc400` | `abcd0000` | `abcdc080` |
| 1/(2π) (248) | `3118` | `3e22f983` | `abcd3118` | `abcdf983` | `abcd3e22` |
| control: integer 1 (129) | | | `abcd0001` | `abcd0000` | `abcd0001` |

The control mask is `5` under every hypothesis.

**SALU packs.** s3 = `56781234`. `s_pack_ll` gives {S1[15:0], S0[15:0]}, `s_pack_lh` {S1[31:16], S0[15:0]}, `s_pack_hh` {S1[31:16], S0[31:16]} (high half first). AMD's XML sizes `ll` S0/S1 and `lh` S0 at 16 bits and the others at 32 bits.

| Field | Instruction | AnyXboxX #221 | f32 bits | f16 over zero |
| --- | --- | --- | --- | --- |
| pack[0] | `s_pack_ll_b32_b16 s30, 0.5, s3` | refused; f16: `12343800` | `12340000` | `12343800` |
| pack[1] | `s_pack_ll_b32_b16 s31, s3, 1/(2π)` | refused; f16: `31181234` | `f9831234` | `31181234` |
| pack[2] | `s_pack_lh_b32_b16 s32, 1/(2π), s3` | refused; f16: `56783118` | `5678f983` | `56783118` |
| pack[3] | `s_pack_hh_b32_b16 s33, 1/(2π), s3` | `56783e22` | `56783e22` | `56780000` |
| pack[4] | `s_pack_lh_b32_b16 s34, s3, 1/(2π)` | `3e221234` | `3e221234` | `00001234` |

#221 refuses the first three; the "f16" value there is what its compare rule would give.

## Expected output line

Under **AnyXboxX #221**:

```text
initial_exec=ffffffff vopc=1,1,1 control=5 vop3=1,1,1 pack=12343800,31181234,56783118,56783e22,3e221234
```

Under **f32 bits**:

```text
initial_exec=ffffffff vopc=2,2,2 control=5 vop3=2,2,2 pack=12340000,f9831234,5678f983,56783e22,3e221234
```

Under **f16 over zero**:

```text
initial_exec=ffffffff vopc=1,1,1 control=5 vop3=1,1,1 pack=12343800,31181234,56783118,56780000,00001234
```

VALU and SALU can follow different rules; report the line as observed. The launcher fails if EXEC was not `ffffffff` or the control mask is not 5.

## Offline assembler check

```sh
llvm-mc -triple=amdgcn-amd-amdhsa -mcpu=gfx1030 -mattr=+wavefrontsize32 -filetype=asm -show-encoding inline16_probe.s
```

LLVM 20.1.8 (Linux release build) assembled the probe for `gfx1030` and `gfx1036` without errors or warnings, and `ld.lld` linked both code objects. Every constant is an inline operand, not a literal: `v_cmp_eq_u16_e32 vcc_lo, 0.5, v10` is `[0xf0,0x14,0x54,0x7d]` (src0 = 240), the VOP3 form `[0x18,0x00,0xaa,0xd4,0xf0,0x14,0x02,0x00]`, and `s_pack_ll_b32_b16 s30, 0.5, s3` `[0xf0,0x03,0x1e,0x99]`. The launcher passes an MSVC `/W4` syntax check against a stub HIP header. It has not run on AMD hardware yet.

## Native run

Use a physical RDNA2 Wave32 device and a HIP setup that can launch code objects on it. The assembly and build target `gfx1030`. For another RDNA2 model, change both target strings in `inline16_probe.s` and the `-mcpu` setting, for example `sed -i 's/gfx1030/gfx1036/g' inline16_probe.s`. Set `HIP_VISIBLE_DEVICES` if the system has multiple supported AMD GPUs. On Windows use the HIP SDK's `clang++` in place of `amdclang++` from a configured x64 developer shell, then run `launch.exe`.

```sh
amdclang++ -target amdgcn-amd-amdhsa -mcpu=gfx1030 -mcode-object-version=5 -x assembler -c inline16_probe.s -o inline16_probe.o
ld.lld -shared inline16_probe.o -o inline16_probe.hsaco
hipcc -std=c++17 launch.cpp -o launch
./launch inline16_probe.hsaco
```

Report the full output line, driver version, OS and the exact target. A port into another harness is fine if it keeps the encodings above (inline operand codes, not literals), as in [PortBridge #19](https://github.com/akimfomin/PortBridge/issues/19#issuecomment-7136020663).

[LLVM AMDGPU ABI](https://llvm.org/docs/AMDGPUUsage.html) · [AMD HIP module API](https://rocm.docs.amd.com/projects/HIP/en/latest/doxygen/html/group___module.html)
