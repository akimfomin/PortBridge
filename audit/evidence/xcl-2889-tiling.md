# XCL #2889 · D3D12 tiling on NVIDIA

Tested the input descriptors and assertion logic from the public XCL test at `ca3eb1532c22cbfe1d51117c5032c159cdc0250f`. The probe independently uses the native Direct3D 12 driver as the reference. It creates empty reserved resources and reads their tiling metadata. It does not run the XCL runtime or execute a game. [Current cases](https://github.com/Luislariosss/xcl/blob/ca3eb1532c22cbfe1d51117c5032c159cdc0250f/crates/xcl/tests/tiling_parity.rs#L53-L94) · [Assertion 278](https://github.com/Luislariosss/xcl/blob/ca3eb1532c22cbfe1d51117c5032c159cdc0250f/crates/xcl/tests/tiling_parity.rs#L270-L283)

## Cross-project lead and result

Wine's vkd3d tiled-resource test cases distinguish BC1/BC4 from BC5. Repeating those three 512×512 single-mip cases reproduced the split on an NVIDIA GeForce RTX 4070 Ti SUPER (driver 617.14, Windows build 28000). BC1 and BC4 returned 512×256 with two tiles and BC5 returned 256×256 with four tiles. XCL's comment groups BC5 with BC1/BC4. Its current format cases cover BC1 and leave BC5 for a future extension. [Wine tiled-resource test cases](https://list.winehq.org/hyperkitty/list/wine-gitlab%40list.winehq.org/thread/AVEIV3WAH6DH4QYAO4OAIKSCFAPZCSSV/) · [XCL format comment](https://github.com/Luislariosss/xcl/blob/ca3eb1532c22cbfe1d51117c5032c159cdc0250f/crates/xcl/tests/tiling_parity.rs#L48-L50)

| XCL input | Native grid | Total tiles | Standard / packed mips | Subresource start | Packed start |
| --- | --- | --- | --- | --- | --- |
| RGBA8 8×8 | 0×0×0 | 1 | 0 / 1 | 0xffffffff | 0 |
| RGBA8 256×256 | 2×2×1 | 4 | 1 / 0 | 0 | 0 |
| BC1 256×256 | 0×0×0 | 1 | 0 / 1 | 0xffffffff | 0 |
| D32 8×8 | 0×0×0 | 1 | 0 / 1 | 0xffffffff | 0 |

For the three packed descriptors the driver returns the documented sentinel in `D3D12_SUBRESOURCE_TILING` and the packed range in `D3D12_PACKED_MIP_INFO`. Applying the PR's line 278 check fails for all three because it compares the sentinel with the tile count. The separate bounds check on the packed start plus packed tile count passed. The probe also observed nonzero nominal shapes for all three packed resources. The API describes the shape as undefined in meaning when the entire resource is packed, so comparing the driver and XCL results can stay in place while any fixed shape assertion applies only to standard tiles. [GetResourceTiling contract](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device-getresourcetiling#parameters) · [Packed mip range](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ns-d3d12-d3d12_packed_mip_info)

The released PortBridge preflight returned no indexed entry or external finding for the #2889 URL and no Discovery matches for `GetResourceTiling BC5_UNORM`. The Wine source came from manual public research. The local probe distinguishes the native API answer from a failing assertion in an independently observed configuration. There is no hardware result from the receiving team on this new handoff yet.

## Reproduce

On Windows with LLVM-MinGW on PATH and a physical NVIDIA D3D12 adapter, run from the repository root.

```powershell
clang++ -std=c++20 -O2 -static -Wall -Wextra -Werror audit/evidence/bc-tiling-probe.cpp -ld3d12 -ldxgi -o bc-tiling-probe.exe
.\bc-tiling-probe.exe
```

The probe passed seven native checks. Its `xcl_line_278=FAIL` diagnostic means the PR assertion rejected the native output. It reports `n/a` for standard mips. No GPU work is submitted and no texture backing is allocated. [Probe source](bc-tiling-probe.cpp) · [Raw output](bc-tiling-probe.txt)
