# Full XCL workspace tests on RTX 4070 Ti SUPER

The complete authored XCL workspace built and ran on Windows for both public fork heads. The target covered the normal XCL guest executable, DLL, GPU shader tests, integration tests and Rust doctests. The two changes are separate branches over XCL main `08db8020d323bf478964fcc586152cce54959cfc`, verified as their merge base on 26 November 2026. [Revisions and changed files](baseline.json)

| Public XCL head | Rust passed | Failed | Ignored | Filtered | Explicit skip records |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Wave32 adjacent carry](https://github.com/akimfomin/xcl/commit/d3e7725f9f48c39c18e7b6e011ec76423edb0004) | 1,431 | 0 | 47 | 0 | 28 |
| [SSA pixel mask projection](https://github.com/akimfomin/xcl/commit/be7722969c6604da56fe553cd8ecb5e3b7ed0f37) | 1,433 | 0 | 47 | 0 | 28 |

Each run produced 37 Rust target summaries. The 28 skip records cover subcases within tests that the harness can count as passed. They include 21 cases requiring native wave64, three unsupported per-lane Wave32 lowering cases, three unavailable D3D12 debug-layer passes and one heap-window path. The JSON receipts list the messages and tests that explicitly logged availability of optional samples. The nine sample-file environment variables from XCL's test script were unset. Some conditional tests return early, so the passed total includes more than the physical coverage. [Carry summary](carry/workspace.json) · [Projection summary](projection/workspace.json)

Both complete suites launched the project's authored guest executable through XCL, rendered its D3D12.X triangle on the named GPU and read it back. The guest reported zero failed checks. The full suites used the normal backend configuration. For the projection branch, the same guest also passed in two supplemental runs with the direct backend requested and the projection setting explicitly zero and one. No direct-stage DXIL file was emitted for this guest in either diagnostic run, so these two runs only establish the guest regression result. Independent per-shader receipts for actual use of the optimized route are available in the [runtime and open-scene measurements](../ssa-mask-projection/README.md). [Two supplemental guest receipts](guest-opt-in.json)

A later upstream merge added the offline compute pipeline changes from #2371. Both published heads still merge into `b49be1836844fe0b0cdb3211dce3cb7fb4e21ac7` with no conflict under `git merge-tree --write-tree`. The receipts above apply to the pinned public heads. The merged trees have only been checked for source compatibility. [Change in upstream main](https://github.com/xcl-dev/xcl/pull/2371)

## Reproduction

Use Windows, a working Rust toolchain, the standard DXC runtime and an adapter with shader model support. The original run used the stable x86_64-pc-windows-gnullvm toolchain, Windows D3D12 and RTX 4070 Ti SUPER. Start from a clean checkout of either linked head. Set `XCL_DXC_DIR` to the directory containing `dxcompiler.dll` and `dxil.dll`, and set `XCL_ADAPTER` to the adapter's name. Leave optional retail sample variables unset to reproduce the reported coverage. The following are the two build and test steps in XCL's standard Windows script, with the dependency lock enforced and passing-test output retained. One Cargo build job was used, followed by four concurrent Rust tests. [Upstream test script](https://github.com/xcl-dev/xcl/blob/08db8020d323bf478964fcc586152cce54959cfc/scripts/test.ps1)

```powershell
$env:CARGO_BUILD_JOBS = '1'
cargo build --workspace --locked
cargo test --workspace --locked -- --test-threads=4 --show-output
```

The logs retain all target summaries, failure/skip checks and guest stdout. Personal home and workspace prefixes are redacted. Run `python verify.py` to recompute the counters and check the positive guest markers directly from both compressed logs. [Carry log](carry/workspace.log.gz) · [Projection log](projection/workspace.log.gz) · [Verifier](verify.py)

### Real-title smoke

The authored XCL test executable is a synthetic console program. Its entry point explicitly checks for the guest `--hello` argument; the standalone smoke script launches a title normally. XCL requires a participant to run the same lawfully obtained real title on main and the proposed revision for the same duration and return the two script-produced aggregate blocks. No eligible public Xbox Series executable was verified for this comparison. Microsoft's public samples require GDKX and an authorized DevKit for the console configuration. A user who already owns an eligible title can retain all game data locally. The real-title requirement remains open for both contributions. [XCL contribution rules](https://github.com/xcl-dev/xcl/blob/08db8020d323bf478964fcc586152cce54959cfc/CONTRIBUTING.md) · [XCL authored test](https://github.com/xcl-dev/xcl/blob/08db8020d323bf478964fcc586152cce54959cfc/tests/testtitle/src/main.rs) · [Official Xbox sample guidance](https://github.com/microsoft/Xbox-GDK-Samples/issues/39)
