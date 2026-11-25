# Optional contiguous page asks for VIctory Fork

An experiment on [VIctory Fork 9376fd6](https://github.com/fxceless/victory-fork/commit/9376fd60c0ba0e76a74c39b49b1407dbac0a64c7), following the Windows reset control in [issue #10](https://github.com/fxceless/victory-fork/issues/10#issuecomment-7157543744).

The current submission code first forms a single span for each shadow, then allows gaps up to 8 MiB when grouping those spans. With `VICTORY_ASK_CONTIGUOUS=1`, submission prefetch passes the original refresh ranges and joins only touching or overlapping 64 KiB pages. The default keeps the existing grouping. Per-flush requests with `VICTORY_ASK_ONCE=0` keep their existing behavior. Submission lifetime, the one-GiB grouping limit, reservation fallback and journaling of every returned page remain in the existing paths. Later batch refreshes and stale-flight checks can still cover a wider range.

## Verified on Windows

Built the actual `victory-gpu` test binary using Rust 1.100.0 for Windows gnullvm. All 14 tests in `watch::tests` passed, including three new controls. A native `GetWriteWatch` test with a test-local journal confirmed that the two selected ranges enter the same generation and that the dirty gap page remains visible to a later kernel read. The tests also distinguish touching pages from a gap and enforce the existing limit when adding adjacent ranges. The suite passed all 24 repeats using one test thread and all 24 using four test threads. The upstream MSVC toolchain, Proton, title playback and GPU execution were outside this run. [Repeat log](repeat-proof.json)

```sh
git switch --detach 9376fd60c0ba0e76a74c39b49b1407dbac0a64c7
git apply --check /path/to/watch-contiguous-experiment.patch
git apply /path/to/watch-contiguous-experiment.patch
cargo test --locked -p victory-gpu --lib watch::tests -- --test-threads=1
```

For a receiving A/B test, first establish baseline variance with identical repeated runs and matched workload ranges. Then alternate the same build with `VICTORY_ASK_CONTIGUOUS` unset and set to `1`. Record fallback calls, queried bytes, dirty pages, submission and mapping-lock tail latency, stale-flight settles, visible output consistency and any missing ranges. A workload with many disjoint ranges may make extra calls and add quadratic interval membership work under the journal lock. Keep the current default unless a stable benefit survives baseline variance and page/output controls.

The patch modifies VIctory Fork files under GPL-3.0-or-later and is redistributed under those terms. [License](LICENSE-GPL-3.0-or-later) · [Machine record](verification.json)
