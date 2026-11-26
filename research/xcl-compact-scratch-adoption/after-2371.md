# Split payload slots after XCL #2371

XCL #2371 introduced an offline first-fit allocator in the same part of `split.rs` changed by #2322. A merge of the pinned candidate into `b49be18` conflicts. The separate [integration commit](https://github.com/akimfomin/xcl/commit/dfb580beccbc1fe4353544a5068245d502de9bfa) adapts the two-file change to that exact parent. The [original measurement pair](https://github.com/xcl-dev/xcl/pull/2322#issuecomment-7167441435) is still available for Kalmarv's ongoing comparisons.

The candidate retains #2371's original first-fit layout for its test-only environment flag. In production the PortBridge allocator selects compact offsets only when the total stride decreases. A four-stage SSA regression exercises overlapping one- and two-word values. The candidate uses four words per lane, including the continuation tag. The offline comparator uses six. This fixture distinguishes which implementation ran. It measures a synthetic layout, without predicting GPU time for a title.

Both configurations passed all 11 split tests in separate processes on an RTX 4070 Ti SUPER on Windows 11. The three-piece divergent GPU fixture checked 384 words at 32 threads and 768 words at 64 threads, with 16 guard words. Its measured footprint was the same under both algorithms. Separate open fixtures compare whole-shader output, split output and CPU results. [Aggregate results](after-2371.json) · [XCL #2371](https://github.com/xcl-dev/xcl/pull/2371) · [Prior independent AMD and NVIDIA reports](https://github.com/xcl-dev/xcl/pull/2322)

To repeat with Rust 1.100.0, the Windows toolchain and DXC/DXIL 1.9.2609.5, select the intended hardware adapter with `XCL_ADAPTER`, then run the following in PowerShell at the integration commit.

```powershell
Remove-Item Env:XCL_SAMPLE_SLOT_REUSE -ErrorAction SilentlyContinue
cargo test --locked -p xcl --lib gpu::dxil::module::split::tests -- --test-threads=1 --show-output
$env:XCL_SAMPLE_SLOT_REUSE = '1'
cargo test --locked -p xcl --lib gpu::dxil::module::split::tests -- --test-threads=1 --show-output
```
