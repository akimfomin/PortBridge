# Interaction with current XCL mask fixes

The direct pixel path has two related upstream correctness changes. XCL #2501 makes first-lane selection and scalar condition checks prefer live lanes. The lane-local experiment leaves EXEC and masks with whole-value readers in the existing whole-mask path, where that correction applies. XCL #2503 masks bridged compares with EXEC in the separate per-lane compute translator. The pixel experiment already gates its write with EXEC and does not enter that bridge. [XCL #2501](https://github.com/xcl-dev/xcl/pull/2501) · [XCL #2503](https://github.com/xcl-dev/xcl/pull/2503)

Both PR commits apply to the exact [matrix tree](README.md). The experimental [mask patch](lane-local-masks.patch) then applies unchanged. The tested Git tree is `07622a771150d9f14278426f6402080b30f067ca`. #2446 scalar reload CSE remains enabled in both timing arms.

| Stacked upstream patch | Exact revision |
| --- | --- |
| #2501 | `de915b5adb519c9aa342107fb05fbe56540541ff` |
| #2503 | `10514822001f2302cd102b9431a9d8613e45cf3a` |

Six targeted CPU and compiler validation tests passed. The exact stack also passed the lane-local derivative edge test, the #2501 live-lane selection and scalar condition GPU test and the #2503 bridged EXEC GPU test on RTX 4070 Ti SUPER, with zero skips. The pixel tests use the Wave32 and Wave64 guest configurations. [GPU test receipts](upstream-overlap-gpu.json)

The two Mobile NeRF baseline and treatment shader outputs all pass standalone DXV validation. Compared with the preceding study the #2501 live-lane logic adds two emitted ballot calls in each arm. The lane-local path still reduces 1,739 calls to 135 in each heavy entry. Release and debug builds produced byte-identical DXIL for all four outputs. [DXV and shape receipts](upstream-overlap-shape.json) · [Release identities](upstream-overlap-release.json)

| Entry | Whole-mask median | Lane-local median | Speedup |
| --- | ---: | ---: | ---: |
| 071 | 1,787.9 ms | 645.6 ms | 2.77× |
| 073 | 1,677.8 ms | 618.1 ms | 2.71× |

The local variant was faster in all ten pairs. The procedure uses five alternating fresh-process pairs per entry with the same [D3D12 timing carrier](README.md#physical-cold-pipeline-creation). Some arms overlapped a separate Rust compiler build. The system-memory guard delayed starts when commit headroom was too low, then completed every planned arm. Comparisons across the two campaigns therefore use the ratios from their own matched pairs. [All timing samples and binary hashes](upstream-overlap-native.json)

These tests establish coexistence for the pinned code and fixtures. General equivalence under helper-lane reconvergence, AMD and Intel results, original-scene execution and XCL title smoke remain open.
