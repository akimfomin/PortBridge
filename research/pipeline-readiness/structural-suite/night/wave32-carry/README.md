# Wave32 carry writes to adjacent scalar registers

On XCL `e1d84b7d9153f86a97d2ec5d209d196046fc0bea`, the HLSL pixel path returns the wrong population count on a triangle edge in whole-quad mode. The ordinary direct DXIL path passes the same case. The earlier PortBridge lane-local experiment also fails with whole-quad mode disabled. The witness uses two short, independently assembled gfx1030 programs and no external assets.

The first carry writes `s21`. The second writes `s20`. A full scalar read of `s21` must still observe its first value. The effective Wave32 destination is one register. A backward analysis that treats the second write as covering both registers can classify the first mask as lane-local. The pixel shader exports two independently computed counts. Red reads `s21` after both writes. Green counts the bits in `EXEC & 0xaaaaaaaa` before either write. This comparison accounts for the wave occupancy of the actual draw. Blue and alpha are sentinels.

## What the RTX returned

Each column covers 2,953 pixels across four triangle geometries. The adapter was an RTX 4070 Ti SUPER, driver 617.14. Wave32 is the guest program configuration. The generated HLSL used Microsoft DXC 1.9.2609.5.

| Translation | Differing red/green pixels without WQM | With WQM |
| --- | ---: | ---: |
| XCL HLSL | 0 | 668 |
| Same HLSL with whole-mask reconstruction | 0 | 0 |
| XCL ordinary direct DXIL | 0 | 0 |
| PortBridge original lane-local DXIL | 2,951 | 2,953 |
| PortBridge whole-mask control | 0 | 0 |

For stock HLSL with WQM, the full-screen triangle passed all 1,024 pixels. The two-triangle diagonal differed at 204/1,024, the single edge at 176/496 and the cropped triangle at 288/409. All five translations produced the same coverage for each geometry. This is a correctness measurement on NVIDIA running XCL. Physical RDNA2 guest-hardware comparison and AMD/Intel host results remain open. [Original experiment](../../LANE-MASKS.md) · [Pixel counts and readback digests](pixels.json) · [Raw RGBA32F images](readbacks.zip)

## Reproduce the HLSL comparison

Use a Windows XCL checkout of the revision above and its documented Rust and DXC setup. Set `$fixture` to this directory. From the XCL checkout, run:

```powershell
New-Item -ItemType Directory -Force crates/xcl/examples | Out-Null
Copy-Item "$fixture/night_mask_witness.rs" crates/xcl/examples/
$out = (New-Item -ItemType Directory wave32-carry-run).FullName
Copy-Item "$fixture/*.rdna2" $out
cargo build --release -p xcl --example night_mask_witness
$witness = (Resolve-Path target/release/examples/night_mask_witness.exe).Path
foreach ($shape in 'wave32-s21-read','wave32-s21-read-wqm') {
    & $witness emit $out $shape
    if ($LASTEXITCODE) { throw 'Translation failed' }
    foreach ($arm in 'hlsl-stock','hlsl-whole') {
        & $witness draw $out $shape $arm
        if ($LASTEXITCODE) { throw 'Draw failed' }
    }
}
python "$fixture/check_pixels.py" $out hlsl-stock hlsl-whole
```

The two `.s` sources correspond to the included 72-byte and 76-byte streams. LLVM MC's AMDGPU assembler accepts both for `gfx1030` with `+wavefrontsize32,-wavefrontsize64`. The whole control changes the generated calls from `ballot_px_local` to `ballot_px` before compiling with the same DXC. Record the XCL revision, graphics adapter, driver, DXC version and the covered/mismatched counts for each geometry. [Independent test request](https://github.com/akimfomin/PortBridge/issues/87)
