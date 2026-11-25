# XCL #2126 compact-slot integration candidate

This patch applies to XCL `3283da481077c1962f13f1b4078841662f7a4ccb`. It adds dated attribution, a standalone allocator unit case and an assertion in XCL's Wave32 fixture that actually exercises compacted slots. The baseline branch and the same-piece, last-consumer rules came from Kalmarv's #2126 and the prior PortBridge work. [XCL #2126](https://github.com/xcl-dev/xcl/pull/2126) · [Original compact patch](https://github.com/akimfomin/PortBridge/tree/2e46a3635ee7725860ceec08ca246a2ab14615b9/research/xcl-2126-compact-slots)

## Verify the candidate

Use a separate XCL checkout at the exact baseline and the normal XCL Windows toolchain. Keep the downloaded patch path in `$Patch`. For the Wave32 fixture, use DXC from the Windows SDK or set `XCL_DXC_DIR` to the directory containing `dxcompiler.dll` and `dxil.dll`.

```powershell
git apply --check $Patch
git apply $Patch
cargo test --locked -p xcl --lib payload_slots_reopen_only_after_the_last_consumer
cargo test --locked -p xcl --lib dispatch_chain_wave32_reuses_scratch_before_gpu_run
```

The allocator test checks that the last-consuming piece keeps its word and that a later piece can reuse a contiguous two-word pair. The other test builds and validates the actual XCL synthetic Wave32 program without a GPU dispatch, checking 256 DWORDs per group. Both passed locally on Windows with Rust 1.100.0 gnullvm and DXC 1.9.2602.17. With the same test and fixed-layout control, it failed at 288 DWORDs per group. [Verification summary](verification.json)

For a voluntary hardware check, select a physical Wave32-capable adapter using XCL's test instructions, then run the existing integration test. It verifies actual reuse at 256 DWORDs per group before comparing all 96 output words from both the split and whole shader with the CPU oracle. Report the GPU, driver, OS, toolchain and exact counts, including any skips.

```powershell
cargo test --locked -p xcl --lib gpu::dxil::module::split::tests::dispatch_chain_wave32_live_loops -- --exact --nocapture --test-threads=1
```

The Windows GPU check and Kalmarv's three real workloads are pending. A report for this synthetic fixture does not supply the GPU timings or scratch sizes requested for those workloads. The aggregate-only kit handles that separate measurement on the author's existing setup. [Maintainer's gate](https://github.com/xcl-dev/xcl/pull/2126#issuecomment-7157104814) · [Aggregate-only kit](https://github.com/akimfomin/PortBridge/tree/be78ccc5a42d7cdb5e23b9ea53af972ea3099652/research/xcl-2126-private-replay)

The [patch](xcl-2126-stacked.patch) modifies XCL source and is available under [GPL-2.0-only](LICENSE). The source header and `THIRD_PARTY.md` preserve attribution. The separate PortBridge aggregate-comparison and verification Python scripts retain MIT. XCL's contribution rules require a person to open an upstream PR. [XCL contribution rules](https://github.com/xcl-dev/xcl/blob/3283da481077c1962f13f1b4078841662f7a4ccb/CONTRIBUTING.md#licence-and-provenance)
