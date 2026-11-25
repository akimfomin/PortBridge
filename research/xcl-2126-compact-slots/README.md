# XCL #2126 scratch packing implementation

This is a one-file implementation on public XCL commit `3283da481077c1962f13f1b4078841662f7a4ccb`. It puts values that start in the same piece in longest-ending order, then reuses their slots strictly after the last destination in the emitted chain. Two-word values require adjacent slots. The original fixed layout stays when packing saves no space. The original shader scheduling, barriers and instruction sequence are unchanged. [XCL #2126](https://github.com/xcl-dev/xcl/pull/2126) · [Prior analysis](https://github.com/xcl-dev/xcl/pull/2126#issuecomment-7155931180)

| Synthetic plan | Baseline DWORDs per group | Candidate |
| --- | ---: | ---: |
| Upstream skip-middle | 128 | 128 |
| Upstream overlap | 160 | 160 |
| Upstream Wave32 loops | 288 | 256 |
| Disjoint control | 128 | 96 |
| Four-piece fragmentation | 192 | 160 |

Across five fixtures the actual implementation's emitter output matched the reference layout, 1,056 scratch words per access order agreed, and DXV validated all 58 output variants. Both unchanged layouts kept the original bytes. The allocator also matched an independent first-fit reference on 128 seeded random interval sets with 6,585 lifetimes. GPU execution and compile and run time on the three upstream programs remain unmeasured.

Get the [pinned census package](https://github.com/akimfomin/PortBridge/tree/2012934dd41bf805ac936d2901eca6b31c58acd0/research/xcl-2126-lifetime-census), run its fetch.py, and pass that directory to the verifier. Use its documented Rust, LLVM-MinGW and Microsoft DXV versions.

```powershell
python -I -B run.py --census $Census --rustc $Rustc --linker $Clang --dxv $Dxv
```

For an upstream checkout at the pinned commit use `git apply --check xcl-2126-compact-slots.patch`. Synthetic fixture, verifier and change follow the upstream GPL-2.0-only license. Original code and test design are credited to the XCL contributors and Kalmarv. [License](LICENSE) · [Results](results.json)
