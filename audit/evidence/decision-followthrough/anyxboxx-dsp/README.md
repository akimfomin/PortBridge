# AnyXboxX #534 · Windows test for the proposed opt-in import

Run the reproducer on Windows with the official GNU Rust distribution, including its standard library, Rust linker and MinGW component. The run used Rust 1.100.1. The script checks the hashes of three public, pinned source files before compiling them in a temporary directory. Its input is a generated unit-impulse spectrum and a single sample on a 512-frame mono stream. [Rust release manifest](https://static.rust-lang.org/dist/2026-11-27/channel-rust-stable.toml)

```powershell
python -B audit/evidence/decision-followthrough/anyxboxx-dsp/reproduce.py --rustc C:/path/to/rust/bin/rustc.exe
```

| Source | Switch | First output sample | Result |
| --- | --- | ---: | --- |
| AnyXboxX main | `1` | 0 | Confirms silence before the import |
| AnyXboxX main | `1` | 0 | Wet-output assertion fails on purpose |
| Imported source | unset | 0 | Preserves silence with the default setting |
| Imported source | `0` | 0 | Preserves silence when disabled explicitly |
| Imported source | `1` | 0.24975586 | All 10 tests pass, including exact agreement within 1e-6 for the generated block |

The original expected value of 0.25 omitted the missing Nyquist bin. Its absence contributes an alternating amplitude of 0.25 / 1024 across the test block. The final assertion checks every sample against that calculation and verifies the ticket and status returned by the actual submit function. [Measured output](results.json) · [Source format](https://github.com/TaynanGT/Vice-Tay/blob/e45051afa41b76bba1bcd0c439384b3660f93255/crates/victory-hle/src/modules/dsp_convolve.rs#L146)

The harness exercises the pinned connect, activate, submit and release functions, uses the real Windows current-process memory read, and replaces export registration and logging with local stubs. Neither the console-side pre-delay nor the full AnyXboxX workspace, launcher profiles or a game session were tested. The result supports bringing the code into AnyXboxX with the existing opt-in flag after the receiving build and test suite pass. Switching the default needs separate evidence and a maintainer decision. [Exact AnyXboxX main](https://github.com/LooperSalty/AnyXboxX/commit/bebcfb104aebbcb081a2b2f2233d5c3c009a4250) · [Vice-Tay donor and credits](https://github.com/TaynanGT/Vice-Tay/pull/293) · [Previous import check](../../active-operations/anyxboxx-dsp-apply.json)
