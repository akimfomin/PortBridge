# VIctory #1971 metadata readback

The probe uses the actual registry, mirror, packing and upload allocation from VIctory revision `1ae8ad326ef6b4fe6e5ac1c5555079fafb78575a`. A small independent HLSL shader reads the allocation through a D3D12 root SRV at `t1, space2`. The fixture selects the heap and slot directly, then checks the result on both sides of a fenced descriptor update. [Receiving PR](https://github.com/Marvisak/VIctory/pull/1971) · [Production root binding](https://github.com/thatirishguyyy/VIctory/blob/1ae8ad326ef6b4fe6e5ac1c5555079fafb78575a/crates/victory-gpu/src/draw.rs#L720) · [Production shader lowering](https://github.com/thatirishguyyy/VIctory/blob/1ae8ad326ef6b4fe6e5ac1c5555079fafb78575a/crates/victory-shader/src/emit/lower.rs#L4492)

The four-submit sequence covers the first deferred entry in heap A, a rewrite from 36×22 to 18×11 on the same allocation, a distinct table for heap B with two populated rows, and a return to heap A after clearing its view. Each submit checks the table header, two descriptor slots and zero rows for two out-of-range indices. The probe isolates the production metadata path. It uses fixture-owned heap selection and an independent shader, with no title or runtime shader package.

## Recorded result

The CPU packing and deferred-registry checks passed. Microsoft DXV accepted the 3,292-byte shader. The first hardware slot stopped before creating a device because Windows had 3,435,077,632 bytes of free system commit against a threshold of 4,294,967,296. The same prepared binary and shader passed at a later slot with enough headroom. All 80 output words matched on an RTX 4070 Ti SUPER under Windows 11 Pro build 28000. The Windows job exited successfully and was reaped with a peak of 102,395,904 bytes. [CPU log](evidence/mock.log) · [DXV log](evidence/dxv.log) · [Input identities](evidence/ready.json) · [First admission result](evidence/native-preflight.json) · [Later admission samples](evidence/native-admission.json) · [Raw native words](evidence/native.log) · [Guard result](evidence/native-attempt.json)

| Readback | Slot 1 | Slot 2 |
| --- | --- | --- |
| A, initially deferred | 36×22, 2D array, 2 mip levels | Zero row |
| A, after rewrite on the same GPU address | 18×11, 2D array, 1 mip level | Zero row |
| B, separate table | 12×8, 2D, 1 mip level | 16×4, 2D, 2 mip levels |
| A, after clear | Zero row | Zero row |

All four headers contained four slots. Both out-of-range indices gave a zero row on every dispatch. DXGI reported raw driver value `00200000001006b2`. The fixture used a D3D12 device without requesting the debug layer. The result checks metadata production and hardware readback in the isolated fixture.

## Verify the source and build

Fetch the 13 public source texts listed in the pinned manifest with `fetch_sources.py`. Each download is hash-verified before use. `reconstruct.py` verifies `source-manifest.json` and reconstructs the 16,353-byte source slice. It can run offline with Python 3.11 or later. Building the probe uses Windows x64, Rust 1.98.1 or later with the `x86_64-pc-windows-msvc` target, the x64 MSVC development tools, and Microsoft DXC with `dxc.exe` and `dxv.exe` in the same folder. The portable build resolves dependencies from the included lockfile. The recorded local result used a gnullvm build with previously compiled Windows bindings. The packaged MSVC build recipe was checked as source and has no separate build result in this archive. [Pinned source manifest](source-manifest.json)

```powershell
python -I -B fetch_sources.py
python -I -B reconstruct.py
python -I -B portable.py build local-cpu --dxc "C:\path\to\dxc\bin\x64"
```

## Optional hardware readback

From an x64 MSVC developer shell, prepare a fresh run folder with `--native-ready`. For an AMD or Intel GPU, give its exact DXGI adapter name and use vendor `1002` or `8086`. The build records those two selector changes. The metadata producer and shader stay byte-identical as source. The launcher admits one Windows job with at least 4 GiB of free system commit and 6 GiB of free RAM, a 512 MiB cap and a three-second deadline. Each dispatch fences before the next CPU update. [D3D12 resource lifetimes](https://learn.microsoft.com/en-us/windows/win32/direct3d12/fence-based-resource-management)

```powershell
python -I -B portable.py build local-rtx --native-ready --dxc "C:\path\to\dxc\bin\x64"
python -I -B portable.py native local-rtx
```

The build and run write `ready.json`, `native-attempt.json` and, once a device opens, the decoded adapter/driver identity and output words in `native.log`. Add the Windows version and whether a debug layer was enabled when reporting a result.

## Two views of one texture

The recorded fixture already tests fenced CPU updates while retaining the same metadata allocation. A separate, focused follow-up can compare two valid SRVs of the same small `R8G8B8A8_UNORM` array texture with different base mips. The object-backed producer can use the actual texture description to generate the two rows. This needs no placed-resource aliasing, format reinterpretation, UAV texture support or shader writes to the metadata buffer. The production metadata is in a D3D12 upload heap that stays in `GENERIC_READ`. A UAV-writing test would require a different allocation and test a different path. [2D array SRV](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ns-d3d12-d3d12_tex2d_array_srv) · [Upload heap rules](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ne-d3d12-d3d12_heap_type)

The probe and upstream source are GPL-3.0-or-later. The standalone Windows job guard carries its MIT license. [Upstream license](upstream/LICENSE) · [Guard license](guard/LICENSE.txt)
