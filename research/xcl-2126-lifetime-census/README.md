# XCL scratch lifetime replay

PortBridge ran the original XCL split planner and DXIL emitter at revision `3283da481077c1962f13f1b4078841662f7a4ccb`. Strict reuse after the last consuming piece reduced the published native Wave32 loop fixture from 288 to 256 DWORDs per group, an 11.1% decrease. The candidate reaches the lower bound from the peak count of simultaneously live words. The two published payload controls produce byte-identical DXIL between layouts. [XCL #2126](https://github.com/xcl-dev/xcl/pull/2126) · [Pinned fixtures](https://github.com/xcl-dev/xcl/blob/3283da481077c1962f13f1b4078841662f7a4ccb/crates/xcl/src/gpu/dxil/module/split.rs#L638-L801)

| Fixture | Pieces | Fixed DWORDs/group | Reused DWORDs/group | Static payload reads / writes |
| --- | ---: | ---: | ---: | ---: |
| XCL skip-middle payload | 3 | 128 | 128 | 4 / 3 |
| XCL overlapping payload | 3 | 160 | 160 | 5 / 4 |
| XCL native Wave32 loops | 4 | 288 | 256 | 12 / 8 |
| Added disjoint-lifetime control | 4 | 128 | 96 | 5 / 3 |

The CPU scratch replay checked 832 words per layout and access order with zero mismatches. The deliberate overlapping-slot control produced 32 mismatches. Microsoft DXV validated all 28 emitted pieces. Two runs returned identical JSON and DXIL hashes. [Full results](results.json)

## Replay

Use Python 3.10 or later on Windows, a Rust compiler with edition 2024 support, an LLVM-MinGW linker, and Microsoft DXV. The measured setup used Rust 1.100.0 for `x86_64-pc-windows-gnullvm`, LLVM-MinGW clang, and DXV from DirectXShaderCompiler 1.9.2602.17. Provide the executable paths from your own installations. [Rust target](https://doc.rust-lang.org/rustc/platform-support/windows-gnullvm.html) · [LLVM-MinGW](https://github.com/mstorsjo/llvm-mingw) · [DXC release](https://github.com/microsoft/DirectXShaderCompiler/releases/tag/v1.9.2602)

```powershell
python -I -B fetch.py
python -I -B run.py --rustc $Rustc --linker $Clang --dxv $Dxv
```

`fetch.py` retrieves the exact public inputs in `SOURCE.json` and checks their SHA-256 hashes. `run.py` rechecks those files, stages the original optimizer and emitter with a CPU probe, builds one standalone executable, and validates every output with the actual DXV binary. The probe keeps the published fixture computations and control flow and uses a small adapter for native Wave32 and the raw input buffer. It specializes the loop fixture to 32 threads. The baseline explicitly checks that `split_compute` emits the same bytes. Temporary files are removed after the run. [Input checksums](SOURCE.json) · [Runner](run.py) · [Allocation and replay](census.rs)

The new layout uses the defining piece and latest destination among `Plan.edges` for each value. A slot can be reused only in a later piece. Word zero remains the continuation tag. CPU replay concerns scratch events on these fixtures. GPU execution, driver allocation, frame timing and memory savings on the three programs in #2126 remain open. The same experiment on those programs can report the fixed stride, peak live-word bound and strict stride as aggregate counts.

## Attribution

XCL's fixtures and emitter come from the pinned upstream revision. Kalmarv authored #2126 and credited PortBridge's earlier fixed-slot and last-consumer work. The probe and adaptation use GPL-2.0-only. See the upstream license and third-party notice listed in the source manifest. The replay was developed and run with Codex using GPT‑6. [XCL license](https://github.com/xcl-dev/xcl/blob/3283da481077c1962f13f1b4078841662f7a4ccb/LICENSE) · [Third-party notices](https://github.com/xcl-dev/xcl/blob/3283da481077c1962f13f1b4078841662f7a4ccb/THIRD_PARTY.md) · [Earlier author reply](https://github.com/xcl-dev/xcl/pull/2080#issuecomment-7153774055)
