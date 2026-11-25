# AnyXboxX RDNA 2 FMA with a cheaper rounding check

This candidate builds on [the first exact-rounding patch](https://github.com/akimfomin/PortBridge/tree/95de2b9a7b89e11176866beb18cd332c11dd093c/research/anyxboxx-133-fma). It keeps ordinary multiply-add aliases and HLSL lowering intact. For fused opcodes it recovers the binary64 addition error first. A binary64 sum with zero error needs just the existing final binary32 conversion. For an inexact sum it tests whether the rounded value is a binary32 midpoint, and moves by one binary64 step toward the exact result only there. FastTwoSum uses the larger-magnitude operand first. [Python math functions](https://docs.python.org/3.12/library/math.html)

The exact public #133 revision is `c4e76abac687e55c00cb005ad3de9132a7cbacf3`. The [source-and-test patch](fma-fast-source.patch) adds normal/subnormal and overflow midpoint controls to the previous tests. The [full contributor patch](fma-fast-upstream.patch) includes synchronized README counters for the six new test rows. The candidate tree was tested as commit `e7ca3a716c949ae519f61bfa96c0446c7bc99c87`. The patch is distributed under AnyXboxX’s GPL-3.0-or-later. [Licence text](LICENSE.AnyXboxX) · [Upstream PR](https://github.com/LooperSalty/AnyXboxX/pull/133)

## Correctness

- All 3,072 directed FMA programs agreed with the exact rational oracle across eight opcodes. Original #133 disagreed on 1,024 of them. The 1,072,512 carry-mask comparisons stayed exact. [RDNA2 output](fma-fast-rdna2.json)
- The Windows UCRT `fmaf` matched all 14,976 directed and all 100,000 seeded random finite triples. [Independent cross-check](fma-fast-ucrt.json)
- The AnyXboxX suite reported 492 passed and 207 skipped. The unavailable backends included native runtime, GPU, and other optional builds. No native GPU output is claimed. The synthetic gfx1036 Wave32 fixture remains available with the first patch.

## Timing

CPython 3.12.14 on Windows x64 and Intel Core i5-13600KF. Nine trials each with rotating/reversed order and a warm-up. The reported medians include conversion back to binary32. The interpreter row runs encoded Wave32 programs through the standard Python `rdna2_exec.run` path and takes a checksum of their outputs. Its speed is specific to this dense synthetic workload.

| Workload | Original #133 | Published correction | Cheaper correction |
| --- | ---: | ---: | ---: |
| 152,700 similar-exponent helper calls | 30.60 ms | 73.78 ms | 46.40 ms |
| 152,700 separated-exponent helper calls | 29.67 ms | 73.15 ms | 48.40 ms |
| 126,000 midpoint-oriented helper calls | 24.31 ms | 58.91 ms | 46.29 ms |
| 153,600 Wave32 interpreter lane operations | 166.12 ms | 213.00 ms | 177.78 ms |

The two corrections have equal checksums in all workloads. The new correction reduces the measured interpreter time by 16.5% compared with the first patch and is 7.0% slower than original #133 on this workload. Game workload and GPU timing remain open. [Raw timing samples](time-fma.json) · [Bench harness](time_fma.py)

Reproduce on a clean checkout of the pinned #133 revision. Apply the full patch in one copy and the first published patch in another. Install AnyXboxX’s normal Python test dependencies. Run `python -m pytest -q` in the candidate and run `python time_fma.py --candidate <candidate-path> --previous <first-patch-path> --output timings.json` from this package for the timing comparison. Reuse the two oracle scripts and optional native assembly from the first research package.
