# XCL Direct DXIL replay

PortBridge checked real compute-shader output from XCL #1022 at `7e1b659cfcd95c37d8710c85adb3753847455575`. The CPU-only replay used DXC 1.9.2609.5 with DXIL validator 1.9, explicitly required a supported validator, and validated both original containers. The fixture uses four synthetic instructions with offsets 0, 4, 128 and 0. The last read uses partial guest EXEC. No title material enters the fixture or the analysis. [Pinned source](https://github.com/xcl-dev/xcl/commit/7e1b659cfcd95c37d8710c85adb3753847455575) · [XCL integration and upstream hardware reports](https://github.com/xcl-dev/xcl/pull/1022)

## What the replay checks

All eight emitted reads passed the modeled contract when participating host lanes include guest EXEC. Each refuted the weaker independent-mask case in 3,968 of 32,000 projected classes. The exact file hashes, register numbers, immediate offsets, examples and predicate domains are in [xcl-dxil-results.json](xcl-dxil-results.json). These are model classes, with no workload-frequency or frame-time estimate.

The recognizer binds opcode 117 and the following local values:

- Per-lane byte address and data from the test input UAV at `u0`, addition of the instruction's immediate offset when present, and low five bits of the index after the shift.
- The reader's virtual half in the guest source index. In split mode, the host read takes only the low five bits, while the source EXEC word uses the full virtual lane index.
- The same guest EXEC word pair for the source and destination guards. The first three reads use high and low words at `u0` byte offsets 508 and 504. The fourth uses the known literal pair. An inactive guest source selects zero and an inactive destination selects its input register value.
- The exact destination VGPR byte address and the test output UAV at `u1`. The audited local control-flow exits reach the output block. The fixture requires nonaliasing input and output resources.

The initial lane mapping and participant set are inputs to the proof. The native check assumes the flattened workgroup index agrees with the physical lane layout. The split check assumes two complete 32-lane subgroups, consistent virtual bases 0 and 32, and a shared virtual mapping for register and shuffle inputs. The adapter recognizes the lane producers in the listing. It does not prove the runtime atomic/barrier initialization, lane layout, participation, arbitrary DXIL, or driver machine code. An unsupported shape receives an explicit unmodeled status. [XCL selector and source guard](https://github.com/xcl-dev/xcl/blob/7e1b659cfcd95c37d8710c85adb3753847455575/crates/xcl/src/gpu/dxil/lower_mem.rs#L2024-L2039) · [XCL split and native read paths](https://github.com/xcl-dev/xcl/blob/7e1b659cfcd95c37d8710c85adb3753847455575/crates/xcl/src/gpu/dxil/lanes.rs#L435-L451) · [Microsoft WaveReadLaneAt](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/wavereadlaneat)

The replay mutates the **text disassembly** in memory for two controls. Removing the native half base refutes all four reads. Routing the split EXEC-bank check through the physically trimmed index causes the recognizer to reject the changed read. With mask `0xAAAAAAAA_55555555`, virtual source lane 33 has bit 1 active in the high word. The same physical index 1 would appear inactive if tested in the low word. The text mutations were not rebuilt, accepted by DXC, or dispatched on GPU.

## Reproduce

The model and parser use Python 3.11 or newer. Run them in the directory containing `lane_contract.py` and `dxil_transport.py`.

```text
python -B -m unittest discover -s . -v
```

For the real capture, save the [pinned XCL archive](https://codeload.github.com/xcl-dev/xcl/zip/7e1b659cfcd95c37d8710c85adb3753847455575) as `xcl-public-7e1b659.zip` and unpack it in a disposable folder. The observed archive SHA-256 was `9e4184f43d41338b04c3981f16f7b0242adb8dea84af449ad0eb0b7b6bac6dd0`. Run the commands in PowerShell 7 with the Windows Rust toolchain required by the pinned XCL checkout and DXC's `dxcompiler.dll` and `dxil.dll` version 1.9.2609.5. The measured build used Rust 1.100.0 `x86_64-pc-windows-gnullvm` with the matching LLVM-MinGW linker. The commands append [capture-hook.rs](capture-hook.rs) once at the end of `crates/xcl/src/gpu/recomp/tests.rs` in the disposable tree. The hook calls the direct backend with explicit compute layout options and writes the original DXIL and disassembly to a local output directory without creating a D3D device. [XCL direct backend entry point](https://github.com/xcl-dev/xcl/blob/7e1b659cfcd95c37d8710c85adb3753847455575/crates/xcl/src/gpu/dxil/kernel.rs#L79-L86) · [XCL validator](https://github.com/xcl-dev/xcl/blob/7e1b659cfcd95c37d8710c85adb3753847455575/crates/xcl/src/gpu/dxil/validate.rs#L75-L103)

```powershell
$xclTree = (Resolve-Path './xcl-7e1b659cfcd95c37d8710c85adb3753847455575').Path
$env:XCL_DXC_DIR = (Resolve-Path './dxc/bin/x64').Path
$env:PORTBRIDGE_DXIL_CAPTURE = Join-Path (Get-Location) 'xcl-dxil-capture'
$hook = Get-Content -Raw -LiteralPath 'capture-hook.rs'
Add-Content -LiteralPath (Join-Path $xclTree 'crates/xcl/src/gpu/recomp/tests.rs') -Value ("`n" + $hook) -Encoding utf8
cargo test --manifest-path "$xclTree/Cargo.toml" --locked -p xcl --lib portbridge_capture_direct_bpermute_dxil -- --nocapture 2>&1 | Tee-Object -FilePath capture-test.log
if ($LASTEXITCODE) { exit $LASTEXITCODE }
python -B replay_xcl_dxil.py --capture xcl-dxil-capture --archive xcl-public-7e1b659.zip --validator-log capture-test.log --output xcl-dxil-results.json
```

`capture-hook.rs` is a GPL-2.0-only fixture hook for the XCL crate. [XCL-CAPTURE-COPYING](XCL-CAPTURE-COPYING) applies to that hook. The Python recognizer, tests and replay script are MIT. The project provides the independently written hook and the measurement report. A fresh local replay produces the XCL binaries and disassembly.
