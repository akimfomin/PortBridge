# RDNA 2 float32 FMA in AnyXboxX

The Wave32 interpreter at the open AnyXboxX #133 head (`c4e76abac687e55c00cb005ad3de9132a7cbacf3`) drops a small addend when it rounds the sum to binary64. If that rounded sum is exactly between two binary32 numbers, the final conversion can select the wrong neighbour. The earlier `9736508b0d201c641b119d2e4a18fb72f28bdde4` revision produces the same result. [AnyXboxX #133](https://github.com/LooperSalty/AnyXboxX/pull/133) · [Interpreter source](https://github.com/LooperSalty/AnyXboxX/blob/c4e76abac687e55c00cb005ad3de9132a7cbacf3/PrototypeScarlett/emu/rdna2_exec_ops.py#L233-L238)

All three inputs are finite normal binary32 values:

| Input | Bits | Exact value |
| --- | --- | --- |
| A | `3FC00000` | `1.5` |
| B | `3F800001` | `1 + 2^-23` |
| C | `99800000` | `-2^-76` |

The product is `1.5 + 3 * 2^-24`, exactly halfway between `3FC00001` and `3FC00002`. Adding C in binary64 leaves the midpoint and the old interpreter returns `3FC00002`. Single rounding of the exact result returns `3FC00001`. With C zero, exact tie-to-even still returns `3FC00002`.

## Results

| Check | Earlier pin | Current pin | CPU candidate |
| --- | ---: | ---: | ---: |
| Carry/borrow lane comparisons | 1,072,512/1,072,512 | 1,072,512/1,072,512 | 1,072,512/1,072,512 |
| Directed FMA programs matching exact binary32 | 2,048/3,072 | 2,048/3,072 | 3,072/3,072 |
| Finite triples matching UCRT `fmaf` on this Windows host | — | 114,712/114,976 | 114,976/114,976 |
| Full pytest suite, with unavailable backends skipped | — | 486 passed, 207 skipped | 490 passed, 207 skipped |

The carry sweep checks 33,516 encoded Wave32 programs for addition, subtraction and reversed subtraction, with 0, sparse and full EXEC masks. It checks each vector destination, inactive lane preservation, and each scalar carry mask. The test covers VOP2 VCC and VOP3 in-place or separate SGPRs.

The directed FMA corpus has 384 cases for each of eight encodings. Each original pin differs on 128 per encoding. Each exact unperturbed tie passes. The eight forms are `v_fmac_f32` and `v_fmac_legacy_f32` in VOP2 and VOP3, `v_fma_f32` and `v_fma_legacy_f32` in VOP3, and `v_fmamk_f32` and `v_fmaak_f32` in VOP2. The Fraction oracle uses exact binary32 values and compares neighbour distances using exact rational arithmetic. The separate UCRT check includes signed zero, subnormal, overflow and ordinary inputs. The 264 original differences are in its targeted cases. The 100,000 seeded random triples match on both builds. [AMD RDNA 2 ISA, §12.7](https://www.amd.com/content/dam/amd/en/documents/radeon-tech-docs/instruction-set-architectures/rdna2-shader-instruction-set-architecture.pdf#page=136) · [LLVM legacy FMA implementation](https://reviews.llvm.org/D89558) · [UCRT `fmaf`](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/fma-fmaf-fmal?view=msvc-170)

## Candidate

The patch recovers the sign of the binary64 addition error only when the computed sum is a binary32 midpoint. The product of two binary32 operands is exact in binary64. FastTwoSum recovers the addition error. A single step to the adjacent binary64 value then places the sum on the correct side before the existing binary32 conversion. At an exact tie, the existing ties-to-even conversion remains in effect. Legacy FMA retains its zero-multiplier rule. The patch keeps the previous implementation for the non-fused MAC/MAD spellings. In a separate Windows microbenchmark, 190,500 interpreter FMA helper and binary32 conversion calls took 32 ms originally and 86 ms with the candidate, using the best of five attempts for each. This measures the helper in isolation.

The regression adds four pytest rows. Three detect wrong neighbours and one preserves the exact tie. The transfer patch contains the interpreter and regression files. For the complete local test run, we also changed each of the nine README test counters from 693 to 697 as requested by AnyXboxX's test-count check. The translated HLSL uses `mad`. Microsoft documents that its implementation can be fused or separate, so GPU parity needs its own measurement. [HLSL `mad`](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/mad)

## Reproduce

Run from a directory containing this package. Use Python 3.12. The probes use the standard library. The full test suite uses AnyXboxX's requirements.

```powershell
git clone --no-checkout --single-branch --depth=1 https://github.com/LooperSalty/AnyXboxX.git upstream
git -C upstream fetch --no-tags --depth=1 origin refs/pull/133/head
git -C upstream fetch --no-tags --depth=1 origin c4e76abac687e55c00cb005ad3de9132a7cbacf3
git -C upstream checkout --detach c4e76abac687e55c00cb005ad3de9132a7cbacf3
git -C upstream worktree add --detach ../candidate c4e76abac687e55c00cb005ad3de9132a7cbacf3
git -C candidate apply ../anyxboxx-fma-source-tests.patch
python -B probe_rdna2.py upstream
python -B probe_rdna2.py candidate
python -B crosscheck_fmaf.py upstream
python -B crosscheck_fmaf.py candidate
```

The UCRT cross-check runs on Windows. For a small native check, assemble `fma_probe.s` with LLVM MC and follow the fixture comment to read back `v4:v7` from a Wave32 kernel. The exact mathematical values are `3FC00001, 3FC00001, 3FC00002, 3FC00002`. We assembled this source with LLVM 23.1.6 for `gfx1036`. A native run is pending.

```powershell
llvm-mc -triple=amdgcn-amd-amdhsa -mcpu=gfx1036 -mattr=+wavefrontsize32 -show-encoding fma_probe.s
```

From each AnyXboxX checkout, install its pinned Python requirements in an isolated environment. To run the candidate's new checks alone, use `python -m pytest -q tests/test_rdna2_fma_rounding.py`. To repeat the full verification, change each candidate README's row from 693 to 697 and run `python -m pytest -q -rs` in each checkout. The recorded skips include unavailable DXC/runner, C++/Rust builds and optional submodules. The package contains synthetic inputs and public source references.

The test and candidate code build on the public AnyXboxX interpreter by its contributors and are offered under the upstream GPL-3.0-or-later licence. The standalone probes are PortBridge research. Attribution for the earlier, separate native carry result remains with Lyrnc. [AnyXboxX licence](https://github.com/LooperSalty/AnyXboxX/blob/c4e76abac687e55c00cb005ad3de9132a7cbacf3/LICENSE) · [Lyrnc's carry result](https://github.com/akimfomin/PortBridge/issues/19#issuecomment-7136020663)

The [AnyXboxX license text](LICENSE.anyxboxx) applies to the source-and-test patch.
