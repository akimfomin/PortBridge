# Packed branch targets for a compact shader dispatcher

The open XCL HLSL backend #1448 shares case bodies with different successors. Its minority targets use selects inside a tree with at most 32 selects per leaf. A separate proposal, #1548, shares scalar immediates. This experiment keeps case bodies and parameters as they are. It replaces only selected large target lists with one shared constant-data lookup. [Existing branch-target code](https://github.com/xcl-dev/xcl/blob/06489ea27c0f657263a948f244ca80373bd0f8fa/crates/xcl/src/gpu/recomp/compact.rs#L294-L428) · [Scalar-operand work](https://github.com/xcl-dev/xcl/pull/1548)

One presence word covers 32 blocks. A second word records the number of exceptions in earlier pages. The population count below the current bit gives its position in a packed array of absolute targets. This uses one presence read and up to three additional word reads. Classes with 32 or fewer overrides keep the current tree. The others are considered in descending override count. The original class table plus new target data must stay within 8,192 words. If a class cannot fit, retain its tree.

## Results

The synthetic programs use the same source-level operations and successors before and after. A CPU oracle checked 374,784 original target choices and separately computed the output for each lane from the raw graph. DXC 1.9.2602 validated each generated container. The bounded native pair covered all 96 possible start blocks, with 64 lanes per block. Both variants independently returned all 6,144 words exactly on a GeForce RTX 4070 Ti SUPER. Both child jobs were reaped. The peak was 108,920,832 bytes under a 512 MiB limit and each worker had a three-second deadline. [Structure and digest](readback-matrix/results.json) · [Native fixture](readback-matrix/readback-meta.json)

| Synthetic case | DXIL bytes, inline → packed | DXC process median, inline → packed |
| --- | ---: | ---: |
| 96 blocks, one active class | 2,708 → 2,284 | 21.58 → 18.68 ms |
| 2,048 blocks, no overrides | 2,076 → 2,076 | 18.34 → 18.60 ms |
| 512 blocks, three heavily varying classes | 5,728 → 2,744 | 31.99 → 19.18 ms |
| 2,048 blocks, three heavily varying classes | 10,524 → 3,616 | 47.89 → 19.85 ms |
| 4,096 blocks, 16 heavily varying classes | 49,464 → 8,432 | 241.94 → 20.74 ms |
| Same 4,096 blocks, only two classes fit | 49,464 → 45,372 | 238.40 → 201.50 ms |

There were 12 process pairs for each row, with alternating order and verification against the exact compiled hash after each process. Elapsed time includes DXC process startup and writing its output. The largest example reduced static select instructions from 2,638 to zero. The no-overrides control was byte-identical. The native comparison covers the first row and checks equality only. These are isolated synthetic results. Driver compile time, execution time, and actual workload incidence remain unmeasured. On one large workload discussed by the XCL author, even omitting every override reduced DXIL only 6% and changed the result. The largest known class table is already close to the cap. A production change needs evidence on shapes where the data fits and overrides account for substantial cost. [Raw pairs](dxc-bench-a/dxc-times.json) · [XCL author's ceiling test](https://github.com/xcl-dev/xcl/pull/1448#issuecomment-7138196521)

## Reproduction

The compiler fixture is original synthetic code and can run independently of the XCL repository. The Python code modeling the upstream target-selection behavior is distributed under GPL-2.0-only. The Windows job shim retains MIT.

```powershell
python -I -B compact_targets.py
python -I -B compact_targets.py --output cases --dxc PATH_TO_DXC --dxv PATH_TO_DXV
python -I -B benchmark_dxc.py PATH_TO_DXC cases dxc-bench
python -I -B readback.py cases
```

The optional online hardware run uses the prior verified AnyXboxX runner from its pinned public source and the existing Windows job guard. Build the same runner or adapt the 96-group fixture to a local D3D12 harness with one raw UAV at register 0. The runner reads and writes one 24,576-byte buffer. The checked-in manifest pins the expected result.
