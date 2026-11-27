# AnyXboxX #534 · Windows check with the receiving export registry

PortBridge linked the tested DSP import against the versions of `windows-sys` and `tracing` used by the receiving repository. All 11 downloaded crate versions and checksums match [its lockfile](https://github.com/LooperSalty/AnyXboxX/blob/bebcfb104aebbcb081a2b2f2233d5c3c009a4250/third_party/victory/Cargo.lock). The fixture uses the receiving project's unmodified [registry.rs](https://github.com/LooperSalty/AnyXboxX/blob/bebcfb104aebbcb081a2b2f2233d5c3c009a4250/third_party/victory/crates/victory-hle/src/registry.rs), with the list of modules restricted to DSP. The test resolved all five `CHAD.DLL` export names to their function addresses, rejected an unknown name, and reproduced the expected in-place output. **13 passed, 0 failed.**

For reproduction, use the source URLs and hashes in [the prior fixture](../reproduce.py). Copy `harness.rs`, `Cargo.toml`, and `Cargo.lock` into a disposable directory. Copy the two pinned donor files to `modules/dsp.rs` and `modules/dsp_convolve.rs`. Copy the receiving `registry.rs` to the harness root (SHA-256 `21db26ea9b63720600c14aaf4243cff066e7a07ef89fba102d6895642d35d0ec`). Copy [portbridge_gate.rs](../portbridge_gate.rs) to `modules/dsp/portbridge_gate.rs` and append `#[cfg(test)]` followed by `mod portbridge_gate;` on separate lines to the DSP module. Use Rust 1.100.1 for Windows GNU and MinGW binutils. The following is the test invocation after putting a working GNU assembler and import-library tool on the process PATH.

```powershell
$env:VICTORY_DSP_CONVOLUTION = '1'
$env:PORTBRIDGE_EXPECT_WET = '1'
cargo test -j 2 --locked --lib -- --test-threads=1 --nocapture
```

The actual run selected Rust's LLD and GNU Binutils 2.47.20260726 as the import-library tool. The Rust package's bundled dlltool could not start its assembler on this host. The isolated check does not cover the full workspace, launcher, or a game session. The full workspace includes [a BCPack table excluded from the repository license](https://github.com/LooperSalty/AnyXboxX/blob/bebcfb104aebbcb081a2b2f2233d5c3c009a4250/third_party/victory/docs/asset-policy.md#the-one-exception). The test used no such table or title data. The proposal to merge as opt-in remains with the receiving team. [Runtime tool versions](toolchain.json) · [Results](results.json)
