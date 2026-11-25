# XCL scratch fragmentation in a four-piece Wave32 fixture

The pinned XCL planner and DXIL emitter produced four pieces from a purpose-built synthetic input. Fixed slots and the first-fit order from the earlier census each used 192 DWORDs per group. When values defined in the same piece were placed in descending order of their last destination, the same strict reuse rule used 160 DWORDs per group, a 16.7% reduction. The result reaches the lower bound from simultaneously live words on this fixture. [XCL #2126](https://github.com/xcl-dev/xcl/pull/2126) · [Earlier replay](https://github.com/akimfomin/PortBridge/tree/2012934dd41bf805ac936d2901eca6b31c58acd0/research/xcl-2126-lifetime-census)

| Live pieces | Width in DWORDs per lane | Fixed and first fit | Longer-ending first |
| --- | ---: | --- | --- |
| 0–3, byte offset | 1 | 1 | 1 |
| 0–1, early result | 1 | 2 | 3 |
| 0–3, later result | 1 | 3 | 2 |
| 2–3, 64-bit pair | 2 | 4–5 | 3–4 |

Word zero remains the continuation tag. When piece 2 starts, first fit leaves one free word at slot 2 while slot 3 is still live, so the pair needs two new adjacent words. Placing the two longer-lived values first frees adjacent words at the end of the occupied range. Pieces 2 and 3 each need four payload words plus the tag, so five DWORDs per lane and 160 per group are optimal for this fixture. The candidate keeps the earlier rule that reuse starts in a piece strictly after the previous value's last destination. XCL's planner keeps cycles in a single piece, and its crossing edges progress in dispatch order. [Transport widths and dispatch planner](https://github.com/xcl-dev/xcl/blob/3283da481077c1962f13f1b4078841662f7a4ccb/crates/xcl/src/gpu/dxil/module/split.rs#L430-L627)

The emitted pieces have the same static payload counts across all layouts, seven DWORD reads and five writes. CPU replay checked 224 scratch words in each read/write order with zero mismatches. Microsoft DXV validated all 12 emitted pieces, and two complete runs returned identical JSON and DXIL hashes. GPU execution, Intel Arc coverage, and savings on the three programs from #2126 remain open. [Full results](results.json) · [Intel Arc test request](https://github.com/akimfomin/PortBridge/issues/54)

## Repeat on Windows

Use Python 3.10+, an edition 2024 Rust compiler, an LLVM-MinGW linker, and Microsoft DXV. The measurements used Rust 1.100.0 targeting x86_64-pc-windows-gnullvm, LLVM-MinGW clang 23.1.6 (5b10d2d7), and DXV from DirectXShaderCompiler 1.9.2602.17. The validator SHA-256 is in the results. [Rust target](https://doc.rust-lang.org/rustc/platform-support/windows-gnullvm.html) · [DXC release](https://github.com/microsoft/DirectXShaderCompiler/releases/tag/v1.9.2602)

Get the files of the earlier replay at PortBridge commit 2012934dd41bf805ac936d2901eca6b31c58acd0. Run its fetch.py once to retrieve the XCL sources and verify their hashes. Then run this extension with the path to that earlier replay and your local executables.

```powershell
$Census = 'C:\path\to\research\xcl-2126-lifetime-census'
Push-Location $Census
python -I -B fetch.py
Pop-Location
python -I -B run.py --census-dir $Census --rustc $Rustc --linker $Clang --dxv $Dxv
```

The runner verifies the prior harness and the pinned upstream source hashes. It compiles one small CPU probe, stages the original XCL optimizer and emitter in a temporary folder, and counts and validates the resulting pieces. The harness and fixture use GPL-2.0-only, with Kalmarv credited for the XCL implementation and original tests. This synthetic extension was developed and run in PortBridge with Codex using GPT‑6. [License](LICENSE) · [Upstream third-party notices](https://github.com/xcl-dev/xcl/blob/3283da481077c1962f13f1b4078841662f7a4ccb/THIRD_PARTY.md)
