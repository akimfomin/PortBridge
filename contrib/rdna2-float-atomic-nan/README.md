# AnyXboxX #136 native RDNA2 `global_atomic_fmin`/`fmax` with NaN

This synthetic probe measures what `global_atomic_fmin` and `global_atomic_fmax` store on RDNA2 when exactly one operand is a quiet NaN. [AnyXboxX #136](https://github.com/LooperSalty/AnyXboxX/pull/136) keeps the non-NaN value for every float min/max atomic and marks this as an assumption to confirm on hardware. [Source at d546df6b](https://github.com/KainanP/AnyXboxX/blob/d546df6b3ad26649af1280640569e2613de70172/PrototypeScarlett/emu/rdna2_exec_atomic.py#L49-L56) · [Assumption note](https://github.com/KainanP/AnyXboxX/blob/d546df6b3ad26649af1280640569e2613de70172/PrototypeScarlett/emu/rdna2_exec_atomic.py#L14-L15)

## Already measured: LDS and buffer atomics

- `ds_min_f32` and `ds_max_f32`: Lyrnc ran all 289 pairs of 17 values on a gfx1036 iGPU (AMD driver 32.0.21042.62), with IEEE mode on and off and f32 denormals flushed and kept. "A NaN loses to a number, whichever side it is on"; an sNaN is written back quieted; with two quiet NaNs the data is kept. [Report](https://github.com/Marvisak/VIctory/pull/628#issuecomment-7123597917)
- `buffer_atomic_fmin` and `buffer_atomic_fmax`: Leonida's hardware oracle on gfx1036 (same driver, Wave32 and Wave64) found that a quiet NaN "returns the non-NaN operand" and that the L2 atomic unit quiets sNaN regardless of MODE. [Leonida design notes](https://github.com/ubiquitarianism/leonida/blob/3aa975421d470b76da1aa986a91282c59e20d642/docs/design.md#L516)

Both agree with AnyXboxX #136. No native measurement of the global forms was found: Leonida's global row says "Not GPU-verified", and the GPU runs in leonida #1039 and VIctory #1342 executed a translated compare-and-swap loop, not the instruction. [Leonida global row](https://github.com/ubiquitarianism/leonida/blob/3aa975421d470b76da1aa986a91282c59e20d642/docs/design.md#L290)

This probe repeats the LDS cases as controls on the same device and asks the open global question.

## Question and hypotheses

| Hypothesis | One quiet NaN operand | Source |
| --- | --- | --- |
| **Number wins** | The number is stored, whichever side holds the NaN | IEEE 754-2008 `minNum`/`maxNum`, used by AnyXboxX #136 and by LLVM for `atomicrmw fmin`, which selects these instructions directly on gfx10 ([LLVM `SIISelLowering.cpp`](https://github.com/llvm/llvm-project/blob/c03a45eace81951e326026d55694e3ab7bf88fe3/llvm/lib/Target/AMDGPU/SIISelLowering.cpp#L21416-L21451)). The measured LDS and buffer forms behave this way. |
| **Compare as written** | `(src < tmp) ? src : tmp`: NaN data is ignored, a NaN already in memory stays | AMD RDNA2 ISA guide pseudo-code for `GLOBAL_ATOMIC_FMIN`/`FMAX`, printed p.232 ([PDF p.240](http://web.archive.org/web/20230214072857id_/https://developer.amd.com/wp-content/resources/RDNA2_Shader_ISA_November2020.pdf#page=240)); the same form in the RDNA3 pseudo-code ([tinygrad `str_pcode.py`](https://github.com/tinygrad/tinygrad/blob/e3bdfb1d59c42c05b295aae1636f75a95fd38ae5/tinygrad/runtime/autogen/amd/rdna3/str_pcode.py#L234-L235)). The LDS measurement already contradicts this form for `ds_min_f32`. |
| **NaN wins** | NaN is stored | IEEE 754-2019 `minimum`/`maximum`. No AMD source; listed to recognise it. |

## Inputs

One Wave32 lane (EXEC = 1). Each memory word is first written with its initial value, then receives one atomic without return. The LDS words are read back with `ds_read_b128`. NaN is the quiet NaN `7fc00000`, 1.0 is `3f800000`, 3.0 is `40400000`, 5.0 is `40a00000` and 7.0 is `40e00000`.

| Field | Operation | Memory, data | Number wins | Compare as written | NaN wins |
| --- | --- | --- | --- | --- | --- |
| `global_fmin[0]` | `global_atomic_fmin` | 1.0, NaN | `3f800000` | NaN < 1 is false: `3f800000` | `7fc00000` |
| `global_fmin[1]` | `global_atomic_fmin` | NaN, 1.0 | `3f800000` | 1 < NaN is false: `7fc00000` | `7fc00000` |
| `global_fmin[2]` | `global_atomic_fmin` | 5.0, 3.0 | `40400000` | `40400000` | `40400000` |
| `global_fmax[0]` | `global_atomic_fmax` | 1.0, NaN | `3f800000` | NaN > 1 is false: `3f800000` | `7fc00000` |
| `global_fmax[1]` | `global_atomic_fmax` | NaN, 1.0 | `3f800000` | 1 > NaN is false: `7fc00000` | `7fc00000` |
| `global_fmax[2]` | `global_atomic_fmax` | 3.0, 5.0 | `40a00000` | `40a00000` | `40a00000` |
| `ds_min[0..3]` | `ds_min_f32` | (1, NaN), (NaN, 1), (5, 3), (5, 7) | `3f800000,3f800000,40400000,40a00000` | measured control | measured control |
| `ds_max[0..3]` | `ds_max_f32` | (1, NaN), (NaN, 1), (3, 5), (5, 3) | `3f800000,3f800000,40a00000,40a00000` | measured control | measured control |

## Expected output line

Under **Number wins** (AnyXboxX #136, same as the measured LDS and buffer forms):

```text
initial_exec=ffffffff global_fmin=3f800000,3f800000,40400000 global_fmax=3f800000,3f800000,40a00000 ds_min=3f800000,3f800000,40400000,40a00000 ds_max=3f800000,3f800000,40a00000,40a00000
```

Under **Compare as written**:

```text
initial_exec=ffffffff global_fmin=3f800000,7fc00000,40400000 global_fmax=3f800000,7fc00000,40a00000 ds_min=3f800000,3f800000,40400000,40a00000 ds_max=3f800000,3f800000,40a00000,40a00000
```

Under **NaN wins**:

```text
initial_exec=ffffffff global_fmin=7fc00000,7fc00000,40400000 global_fmax=7fc00000,7fc00000,40a00000 ds_min=3f800000,3f800000,40400000,40a00000 ds_max=3f800000,3f800000,40a00000,40a00000
```

Any NaN encoding counts as NaN. The launcher fails if EXEC was not `ffffffff`, a number-only global case differs, or an LDS word differs from the gfx1036 measurement. The probe does not cover signalling NaNs, −0 against +0, denormals or the `_x2` forms.

## Offline assembler check

```sh
llvm-mc -triple=amdgcn-amd-amdhsa -mcpu=gfx1030 -mattr=+wavefrontsize32 -filetype=asm -show-encoding fminmax_probe.s
```

LLVM 20.1.8 assembled the probe without errors or warnings. It has not run on AMD hardware yet. The kernel descriptor requests IEEE mode and DX10 clamp, the LLVM defaults for compute.

## Native run

Use a physical RDNA2 Wave32 device and a HIP setup that can launch code objects on it. The assembly and build target `gfx1030`. For another RDNA2 model, change both target strings in `fminmax_probe.s` and the `-mcpu` setting, for example `sed -i 's/gfx1030/gfx1036/g' fminmax_probe.s`. Set `HIP_VISIBLE_DEVICES` if the system has multiple supported AMD GPUs. On Windows use the HIP SDK's `clang++` in place of `amdclang++` from a configured x64 developer shell, then run `launch.exe`.

```sh
amdclang++ -target amdgcn-amd-amdhsa -mcpu=gfx1030 -mcode-object-version=5 -x assembler -c fminmax_probe.s -o fminmax_probe.o
ld.lld -shared fminmax_probe.o -o fminmax_probe.hsaco
hipcc -std=c++17 launch.cpp -o launch
./launch fminmax_probe.hsaco
```

Report the full output line, driver version, OS and the exact target. A port into another harness is fine if it keeps the instructions, operands, initial values and their order, as in [PortBridge #19](https://github.com/akimfomin/PortBridge/issues/19#issuecomment-7136020663).

[LLVM AMDGPU ABI](https://llvm.org/docs/AMDGPUUsage.html) · [AMD HIP module API](https://rocm.docs.amd.com/projects/HIP/en/latest/doxygen/html/group___module.html)
