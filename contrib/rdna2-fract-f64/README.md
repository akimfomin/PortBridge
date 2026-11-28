# AnyXboxX #209 native RDNA2 `v_fract_f64` bound and special values

This synthetic probe measures `v_fract_f64` on RDNA2 where the result of x − floor(x) rounds to 1.0, and for ±0, ±inf and NaN inputs. [AnyXboxX #209](https://github.com/LooperSalty/AnyXboxX/pull/209) bounds the result below 1.0 at `3fefffffffffffff`, returns a NaN for ±inf and makes a NaN input quiet. It says the bound was "read in LLVM, not measured on hardware". [Merged interpreter](https://github.com/LooperSalty/AnyXboxX/blob/6fdf355abab918b7c6666103c8f7c5f781427879/PrototypeScarlett/emu/rdna2_exec_wide.py#L74-L80)

## Already measured: `v_fract_f32`

Leonida measured the f32 form on an RX 6800 (gfx1030) in all four IEEE/DX10_CLAMP combinations: one rounding, `3f7fffff` "where that gives 1.0, e.g. fract(-1e-10)", fract(−0) = +0, fract(±inf) = NaN, and a NaN passes through. On gfx1036 with IEEE 0, fract(±inf) is exactly `ffc00000` and a signalling NaN comes back unchanged. [leonida design.md](https://github.com/ubiquitarianism/leonida/blob/9f9a7c5f30f8559c52675780cf84004571b8d6e5/docs/design.md#L411)

No measurement of the f64 form was found. This probe asks whether the same rules hold for `v_fract_f64`.

## Question and hypotheses

| Hypothesis | Rule | Source |
| --- | --- | --- |
| **AnyXboxX #209** | min(x − floor(x), `3fefffffffffffff`); ±inf → `7ff8000000000000`; NaN → the same NaN made quiet, in every MODE | #209, following LLVM's constant folding of `amdgcn_fract`: "The min() operator is there to prevent fract(-small) from returning 1.0" ([LLVM `ConstantFolding.cpp`](https://github.com/llvm/llvm-project/blob/87f0227cb60147a26a1eeb4fb06e3b505e9c7261/llvm/lib/Analysis/ConstantFolding.cpp#L2334-L2345)) |
| **f32 rule carried to f64** | The same bound; ±inf → negative default NaN `fff8000000000000`; a NaN passes through, a signalling NaN is made quiet only with IEEE 1 | The `v_fract_f32` measurements above |
| **ISA formula, no bound** | x + −floor(x) rounded to nearest even, so fract(−1e-20) = 1.0; special values as in the row above | The formula AMD gives for `V_FRACT_F64` (`S0 + -floor(S0)`, quoted in #209). Neither the RDNA2 ISA guide nor AMD's machine-readable RDNA2 ISA ("Compute the fractional portion of a double-precision float input") states a bound. |

## Inputs

One Wave32 lane (EXEC = 1), `v_fract_f64_e32`. The same 10 instructions run in two kernels, one with MODE.IEEE = 1 and one with MODE.IEEE = 0; both keep f64 denormals and DX10_CLAMP = 1.

| Field | Input | AnyXboxX #209 | f32 rule carried to f64 | ISA formula, no bound |
| --- | --- | --- | --- | --- |
| d1 | 1.25 `3ff4000000000000` | 0.25 `3fd0000000000000` | same | same |
| d2 | −1.25 `bff4000000000000` | 0.75 `3fe8000000000000` | same | same |
| d3 | −1e-20 `bbc79ca10c924223` | 1 − 1e-20 rounds to 1.0, bounded: `3fefffffffffffff` | `3fefffffffffffff` | 1.0 `3ff0000000000000` |
| d4 | −2^-53 `bca0000000000000` | 1 − 2^-53 exactly: `3fefffffffffffff` | same | same |
| d5 | −0.0 `8000000000000000` | −0 + +0 = +0: `0000000000000000` | `0000000000000000` | `0000000000000000` |
| d6 | +inf `7ff0000000000000` | `7ff8000000000000` | `fff8000000000000` | `fff8000000000000` |
| d7 | −inf `fff0000000000000` | `7ff8000000000000` | `fff8000000000000` | `fff8000000000000` |
| d8 | sNaN `7ff0000000000001` | `7ff8000000000001` | IEEE 1: `7ff8000000000001`, IEEE 0: `7ff0000000000001` | as the f32 rule |
| d9 | NaN `fff8000000000123` | `fff8000000000123` | `fff8000000000123` | `fff8000000000123` |
| d10 | 1e300 `7e37e43c8800759c` | 0 | 0 | 0 |

Arithmetic. In [0.5, 1) doubles are 2^-53 apart, so 1 − 2^-53 is exact (d4, a control) while 1 − 1e-20 lies within half a step of 1.0 and rounds to it (d3, the question). d1, d2, d4 and d10 are controls with the same word under every hypothesis.

## Expected output lines

Under **AnyXboxX #209** (both lines):

```text
ieee1 initial_exec=ffffffff d1-d10=3fd0000000000000,3fe8000000000000,3fefffffffffffff,3fefffffffffffff,0000000000000000,7ff8000000000000,7ff8000000000000,7ff8000000000001,fff8000000000123,0000000000000000
ieee0 initial_exec=ffffffff d1-d10=3fd0000000000000,3fe8000000000000,3fefffffffffffff,3fefffffffffffff,0000000000000000,7ff8000000000000,7ff8000000000000,7ff8000000000001,fff8000000000123,0000000000000000
```

Under **f32 rule carried to f64**:

```text
ieee1 initial_exec=ffffffff d1-d10=3fd0000000000000,3fe8000000000000,3fefffffffffffff,3fefffffffffffff,0000000000000000,fff8000000000000,fff8000000000000,7ff8000000000001,fff8000000000123,0000000000000000
ieee0 initial_exec=ffffffff d1-d10=3fd0000000000000,3fe8000000000000,3fefffffffffffff,3fefffffffffffff,0000000000000000,fff8000000000000,fff8000000000000,7ff0000000000001,fff8000000000123,0000000000000000
```

Under **ISA formula, no bound**:

```text
ieee1 initial_exec=ffffffff d1-d10=3fd0000000000000,3fe8000000000000,3ff0000000000000,3fefffffffffffff,0000000000000000,fff8000000000000,fff8000000000000,7ff8000000000001,fff8000000000123,0000000000000000
ieee0 initial_exec=ffffffff d1-d10=3fd0000000000000,3fe8000000000000,3ff0000000000000,3fefffffffffffff,0000000000000000,fff8000000000000,fff8000000000000,7ff0000000000001,fff8000000000123,0000000000000000
```

The fields are independent: for example the bound can hold while the NaN words differ. The launcher fails if EXEC was not `ffffffff` or a control (d1, d2, d4, d10) differs in either kernel.

## Offline assembler check

```sh
llvm-mc -triple=amdgcn-amd-amdhsa -mcpu=gfx1030 -mattr=+wavefrontsize32 -filetype=asm -show-encoding fract_f64_probe.s
```

LLVM 20.1.8 (Linux release build) assembled the probe for `gfx1030` and `gfx1036` without errors or warnings (`v_fract_f64_e32` is VOP1 opcode `0x3e`), and `ld.lld` linked both code objects. The two kernel descriptors differ only in the IEEE bit of COMPUTE_PGM_RSRC1 (`0x60af0007` and `0x602f0007`). The launcher passes an MSVC `/W4` syntax check against a stub HIP header. It has not run on AMD hardware yet.

## Native run

Use a physical RDNA2 Wave32 device and a HIP setup that can launch code objects on it. The assembly and build target `gfx1030`. For another RDNA2 model, change both target strings in `fract_f64_probe.s` and the `-mcpu` setting, for example `sed -i 's/gfx1030/gfx1036/g' fract_f64_probe.s`. Set `HIP_VISIBLE_DEVICES` if the system has multiple supported AMD GPUs. On Windows use the HIP SDK's `clang++` in place of `amdclang++` from a configured x64 developer shell, then run `launch.exe`.

```sh
amdclang++ -target amdgcn-amd-amdhsa -mcpu=gfx1030 -mcode-object-version=5 -x assembler -c fract_f64_probe.s -o fract_f64_probe.o
ld.lld -shared fract_f64_probe.o -o fract_f64_probe.hsaco
hipcc -std=c++17 launch.cpp -o launch
./launch fract_f64_probe.hsaco
```

Report both output lines, driver version, OS and the exact target. A port into another harness is fine if it keeps the instruction, the inputs and the two MODE settings, as in [PortBridge #19](https://github.com/akimfomin/PortBridge/issues/19#issuecomment-7136020663).

[LLVM AMDGPU ABI](https://llvm.org/docs/AMDGPUUsage.html) · [AMD HIP module API](https://rocm.docs.amd.com/projects/HIP/en/latest/doxygen/html/group___module.html)
