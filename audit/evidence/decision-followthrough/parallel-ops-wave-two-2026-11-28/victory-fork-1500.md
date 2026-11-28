# victory-fork #1500 independent source-only verification

Source head [`4351fb43edd626bd8fd450853a17f02ca0c1b6f7`](https://github.com/fxceless/victory-fork/commit/4351fb43edd626bd8fd450853a17f02ca0c1b6f7). It was fetched by exact commit from public GitHub. Only reviewed launcher scripts and the dependency-free budget module were executed. The provided runner stub only returns arguments and environment. The source README is an inert existing file used for path validation. Neither the launcher nor the extra fixture starts a game in this setup.

## Results

- PowerShell 7.6.9 · the upstream launcher check passed. It exercised four upscaler modes, explicit overrides, observed forwarding to the stub, settings restoration on success and failure, and rejection of a missing runner.
- PortBridge's second PowerShell check passed. A synthetic successful warm-up invoked the run route once. A warm-up with exit 29 refused to continue. Both restored the parent's settings and directory.
- Rust 1.100.1 on Windows GNU · six CPU unit tests passed. Four are the unmodified budget module tests. Two PortBridge cases cover 16 GiB inclusive selection and the exact 85% retained-block threshold.
- Full crate build, graphics driver behavior, and frame timing remain open. These are source-level policy and launcher results.

## Reproduce

Create a disposable directory with the six public files below, retaining relative paths. Run `pwsh -NoProfile -NonInteractive -File tests/low-memory-launcher.ps1`. Place [portbridge-warm-check.ps1](portbridge-warm-check.ps1) and [portbridge-warm-runner.ps1](portbridge-warm-runner.ps1) in `tests/` and run the former in the same way. Copy the pinned budget module into the same directory as [portbridge-budget.rs](portbridge-budget.rs) as `budget.rs`. Run `rustc --edition=2021 --test portbridge-budget.rs -o portbridge-budget.exe` followed by `./portbridge-budget.exe --test-threads=1`.

| Public source file | SHA-256 |
| --- | --- |
| [`tests/low-memory-launcher.ps1`](https://github.com/fxceless/victory-fork/blob/4351fb43edd626bd8fd450853a17f02ca0c1b6f7/tests/low-memory-launcher.ps1) | `966f85b7c4a71b8ad9e41f1d137601dc93e370b77b58b9a119a16d6c9e9ef29c` |
| [`scripts/play-low-memory.ps1`](https://github.com/fxceless/victory-fork/blob/4351fb43edd626bd8fd450853a17f02ca0c1b6f7/scripts/play-low-memory.ps1) | `979702a61ddc94b2713df3928f52c642797f1ca575f6f66b5fb40aaea5ac29ab` |
| [`scripts/play.ps1`](https://github.com/fxceless/victory-fork/blob/4351fb43edd626bd8fd450853a17f02ca0c1b6f7/scripts/play.ps1) | `e5dfc63323922504c02e0b9773d0b9162a00d5934296b9c45d13e9bf0062baec` |
| [`tests/launcher-probe.ps1`](https://github.com/fxceless/victory-fork/blob/4351fb43edd626bd8fd450853a17f02ca0c1b6f7/tests/launcher-probe.ps1) | `0c213656a60b129941722d4a92f62a823e2b80160bb3f89f6dbb90b3f48885f7` |
| [`README.md`](https://github.com/fxceless/victory-fork/blob/4351fb43edd626bd8fd450853a17f02ca0c1b6f7/README.md) | `55e4f888490076a31d50b0e250fb6de3894ab07de785124786da4a1e09deeb7a` |
| [`crates/victory-gpu/src/budget.rs`](https://github.com/fxceless/victory-fork/blob/4351fb43edd626bd8fd450853a17f02ca0c1b6f7/crates/victory-gpu/src/budget.rs) | `c9e641c2de58a4a6ca655a9de310729f2def85e8290547b772ebac6b13702b24` |

[Exact validation output](victory-fork-1500-results.txt).
