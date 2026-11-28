# PortBridge ecosystem transfer wave

Public GitHub revisions sampled on 28 November 2026. PortBridge product baseline `4b3378af870d8b3fac78bb50ffd019c886a056ba`.

## What was checked

- [Fresh sample](fresh-sample.json) contains 150 PR metadata records across 13 repositories, drawn from 365 pull records returned by GitHub for 14 repositories, including a fork with no PRs. Prior identical heads from the previous published three-wave PR list were excluded from the fresh sample. This is platform triage. The changed files of the narrower Git sample were inspected separately.
- [98 PRs against their current base](same-repository-results.json): 87 clean and 11 conflicting. Of [72 pair trials](same-repository-results.json), 50 built a changed tree, 20 conflicted and two added no changes. [49 cross-repository trials](cross-repository-results.json): 16 source patches applied directly, 24 three-way trials conflicted, five vendored-source contexts differed, one exact patch was already present, and three were skipped after revision drift. Thus 118 completed pair/transfer trials, plus 98 current-base trials. No trial executed fetched code.
- Direct source trials used only `crates/` and `scripts/` and the existing vendored prefix for AnyXboxX. A clean application is permission to build and investigate. The evidence makes no claim about compile, performance, graphics equivalence or a compatible release.

## Ready checks and transfer decisions

| Case | Finding | Next evidence |
| --- | --- | --- |
| AnyXboxX #577 and Vice-Tay #395 | Both replay static-sampler order. The AnyXboxX NVIDIA path still omits the library name if only the new feature is enabled. Vice-Tay admits a named pipeline when all samplers were primed. | Check cold learning, fresh-process hit, one new sampler, and a replay refusal with the override unset. [AnyXboxX delivery](https://github.com/LooperSalty/AnyXboxX/pull/577#issuecomment-7238679662) · [source comparison and seven CPU policy vectors](sampler-source-receipt.json). |
| Vice-Tay #395 | A sampler whose root creation returns an error still enters the primed-key set. A refused earlier key may change the numbering of later keys. | [GPL patch for the pinned Vice-Tay head](vice-sampler-fail-closed.patch) enters the existing fallback when opening/reading the list or recreating any listed root fails. It applies and reverses at the exact head; a Windows diagnostics `cargo check --locked -p victory-gpu --lib --features diagnostics` passed at the pinned head plus this patch. The driver fallback still needs a runtime test. Existing driver-override behavior is outside the change. [Receiving thread](https://github.com/TaynanGT/Vice-Tay/pull/395#issuecomment-7238679395). |
| victory-altracing + VIctory-NVIDIA #1017 and #1018 | The depth probe needs the copied plane's actual footprint, while same-list lighting needs a freshly written depth plane. Both fixes together produce the same tree in both orders on the fork's main. | Run `depth_probe_reads_the_copied_plane_layout` and `a_depth_planes_twin_is_drawn_into_the_plane` separately on the aggregate. The former needs `diagnostics`. [Original probe](https://github.com/trustno1-coder/VIctory-NVIDIA/pull/1017) · [Original writer fix](https://github.com/trustno1-coder/VIctory-NVIDIA/pull/1018) · [pinned stack](altracing-stack-receipt.json). |
| victory-altracing + VIctory-NVIDIA #1015 | Adapter separation in the pipeline library also stacks with both depth fixes in either tested order. It addresses separate adapter paths, alongside the fork's existing cold-sampler limitation. | Compare generated adapter-specific library directories first; retain same-list depth outputs. [Original adapter PR](https://github.com/trustno1-coder/VIctory-NVIDIA/pull/1015) · [fork's cold-cache caveat](https://github.com/whoalin1/victory-altracing/blob/95e1ca80b56865b3bf2654f27c7550b05a8d54a9/README.md#L59-L64). |
| victory-altracing + VIctory-NVIDIA #1006 / #1008 | The #1006 source patch reverses cleanly from the target, so there is no second port to make. #1008 conflicts in `memory.rs` despite superficially similar BVH fault handling. | Check ownership and fault accounting before considering adaptation. [#1006](https://github.com/trustno1-coder/VIctory-NVIDIA/pull/1006) · [#1008](https://github.com/trustno1-coder/VIctory-NVIDIA/pull/1008). |
| Copperframe + Vice-Tay #388 and Copperframe #4 | The same author has separate adaptations of the refresh-ahead approach. The direct transfer into Copperframe conflicts in `host.rs`. | Prefer the native patch as the comparison base. Existing CPU evidence shows why the byte-range invalidation still needs a separate negative control even when sharing KLBF page-copy tracking. [Existing Copperframe delivery](https://github.com/XaviFortes/VIctory-RDNA/pull/4#issuecomment-7231768185) · [Vice-Tay #388](https://github.com/TaynanGT/Vice-Tay/pull/388). |
| Copperframe and KLBF + VIctory-NVIDIA #1019 | The synthetic Wave32 gather correction applies to both main pins. It is separate from their same-list depth port, which conflicts. | For each target independently, capture 64- and 128-thread results for wrap and inactive source lanes before considering a merge. [Original Wave32 regression](https://github.com/trustno1-coder/VIctory-NVIDIA/pull/1019). |
| KLBF #89 and #152 | KLBF already has owners for both. #89 remains stacked on open #41. #152 closed unmerged, but the maintainer requested base / serialization-only / full-source runs in the receiving thread. | Use the existing threads for results, preserve actual Proton/driver versions and group-shape evidence, and preserve tested/read-only status. [#89 maintainer decision](https://github.com/PastiiJay/klbf-lab/pull/89#issuecomment-7197873409) · [#152 maintainer decision](https://github.com/PastiiJay/klbf-lab/pull/152#issuecomment-7237920674). |

## Test Lab result intake

[PortBridge #163](https://github.com/akimfomin/PortBridge/issues/163) is open for physical NVIDIA. The fork owner received [one optional invitation](https://github.com/akimfomin/PortBridge/issues/163#issuecomment-7238826359) in the PortBridge issue. The original same-list fixture returns success early when no host GPU or depth-plane twin is selected. The reproducer also emits a test-only guard that rejects both early returns and identifies the selected adapter by the live DXGI device. This produces a separate strict tree in the receipt. PortBridge verified both positive checks locally. An independent repeat remains open. The request to post in VIctory-NVIDIA #1018 was denied by the GitHub integration.

## Physical correctness checks on victory-altracing

The strict tree `74a66f97afcff228896e18a8d1511edeb71d484f` built and ran on PortBridge's physical RTX 4070 Ti SUPER, driver 617.14, native D3D12 and Windows 11 build 28000. We ran two source-provided synthetic checks with the strict guard. No title data was involved. The normal path passed two tests with no skips. Then we reintroduced packed texel width and separately postponed the depth publication until close. Both selected checks failed in their own assertions. Restoring the verified tree passed both again.

| Check | With the changes | With its negative control |
| --- | --- | --- |
| Addressing the copied depth plane | PASS | FAIL, offset 3,715,488 instead of 3,711,184 |
| Lighting later in the same command list | PASS | FAIL, class 65 at texel 1 was dark when it should light up |

[Positive receipt](altracing-hardware-receipt.json) · [Negative receipt](altracing-negative-receipt.json) · [Negative-control runner](check_altracing_negative.py) · [Independent repeat #163](https://github.com/akimfomin/PortBridge/issues/163).

Use the checkout and Cargo filters in the request. On the Windows GNU toolchain the local build used Rust 1.98.1, the bundled LLD via `-C linker-flavor=ld.lld`, and the checksum-pinned [GNU Binutils bundle](../decision-followthrough/anyxboxx-dsp/native-bindings/toolchain.json) on the process path. Run the negative-control script from an isolated checkout with the strict tree staged and no unstaged edits. Set `PB_CARGO_PATH` to Cargo and `PB_CONTROL_RECEIPT` to a new local JSON path. The script uses the same environment as the positive checks and restores the two changed files in a finally block. This round tested correctness on our stand. It measured no frame rates and does not establish a maintainer decision.

## Search replay on the same public work

[Actual results](discovery-live-replay.json) list four hand-selected source relationships, the input URLs, terms and external lookup counts. The clean-database online URL path found none, with two zero-lookup no-subject responses. The live preflight path found the Copperframe to Vice-Tay pair at rank 1 (technical terms, suggested, score 0.77). The same author opened both proposals before this check. This is a small operational replay, with three failures on the published path and no independent new discovery claim.

The new [published catalog](https://akimfomin.github.io/PortBridge/data/projects.json) and [capability API](https://akimfomin.github.io/PortBridge/data/ecosystem.json) contain all three additions. GitHub Pages deployment and its follow-up smoke check succeeded. The live health receipt exposes 41,690 observations and eight unavailable sources. [GitHub delivery](https://github.com/akimfomin/PortBridge/actions/runs/46141025231) · [Live health](https://akimfomin.github.io/PortBridge/data/health.json).

## Follow-through

- Vice-Tay #392's author isolated the old test flake after the same-base control, with 5/30 failures before and 0/40 after the separate test fix. External contributor maximecmb then measured a second system, RTX 5080, with the original and queued card-copy implementations. At 2,000+ draws, mean delta was approximately 1.4 ms, with ±0.7 ms in the source report; the outdoor-only difference was inside run noise. The PR author integrated the diagnostic A/B toggle in `fb40506`. These are two distinct results from the prior track, with separate attribution. [Flake](https://github.com/TaynanGT/Vice-Tay/pull/392#issuecomment-7232904064) · [External measurement](https://github.com/TaynanGT/Vice-Tay/pull/392#issuecomment-7237442462) · [Author response](https://github.com/TaynanGT/Vice-Tay/pull/392#issuecomment-7237465822).
- Xbox2Windows #3299 was merged. RonLogic narrowed the AMD control to a vertical-only ramp and added two derivative paths, after the earlier test fixture did not isolate both. Earlier RX 9060 XT results remain valid as observations of the original fixture. The revised fixture has RTX/WARP evidence. Its AMD replay stays open, because the recent 7-pass/1-skip RX 9060 XT receipt covers different runtime tests. [Prior PortBridge handoff](https://github.com/R0Y00/Xbox2Windows/pull/3255#issuecomment-7233284599) · [Author replay](https://github.com/R0Y00/Xbox2Windows/pull/3255#issuecomment-7235184338) · [Merged #3299](https://github.com/R0Y00/Xbox2Windows/pull/3299) · [Unrelated updated AMD receipt](https://github.com/R0Y00/Xbox2Windows/pull/3241#issuecomment-7238366904).
- Local RTX 4070 Ti SUPER was at 56–58% utilization during spot checks, so no local timing run was used.
- PortBridge catalog gained three source-backed entries through [PR #162](https://github.com/akimfomin/PortBridge/pull/162). All 336 tests and the publication gate passed locally. Scheduled GitHub runs checked from Nov 24 21:30 UTC to Nov 28 10:17 UTC: 10 successes and one failure. Among the latest eight successful runs, the start gap ranged from 7 h 01 min to 16 h 10 min. These are run receipts, not a seven-day cadence. [Run history](https://github.com/akimfomin/PortBridge/actions/workflows/pages.yml).
- Requirements remain 83 verified, including 39 open or blocked. No new independent team installations or repeat requests were confirmed in this wave.

## Existing hardware tasks

- Continued #2405: an RTX 4070 SUPER report from Tyrannys exposed that the old Intel-compatible regression compared two distinct 64 KiB pages on NVIDIA. The author corrected the fixture in `cf30c0a1f8e89d4eaecfe92b6039714c7a488f61`. PortBridge checked its composition with `d48a957bb9988afce424552a3c0c8d01ef12320f`, resulting in `0c699d8ade1d89d5bb8b6c891a1b8097c6ce7437`, and updated the existing Arc A770 request. No new post-fix result was received. [Independent report](https://github.com/ProjectLeonida/mandy/pull/2405#issuecomment-7232694541) · [Author decision](https://github.com/ProjectLeonida/mandy/pull/2405#issuecomment-7232899362) · [Test Lab #117](https://github.com/akimfomin/PortBridge/issues/117).
- Xbox2Windows: [Test Lab #159](https://github.com/akimfomin/PortBridge/issues/159) now offers the adopted vertical-ramp fixture at `19358dae7f7da44c646beb2f5ba76314fe1cf1c8` for new AMD repeats and preserves the earlier pins and report history.

## Reproduce

From this directory with Python 3.11+ and a recent Git with `merge-tree --merge-base`. The first two commands validate current public refs against pinned receipts and may skip a moved ref. The last two use immutable SHAs. Downloaded source is used as data.

```powershell
$env:PB_OPS_REPORT_FILE = "$env:TEMP/pb-git-recheck.json"
python same-repository.py
python cross-repository.py git-targets.json "$env:TEMP/pb-cross-recheck.json"
python check_altracing_stack.py
python verify_sampler_gate.py
```

The upstream projects retain authorship of all source changes and existing regressions. The Vice-Tay delta is an adaptation on its GPL source. Primary GitHub links and testable controls identify what PortBridge compared or produced.


For the URL client replay, use one fresh temporary database per row and the exact `pr` in the receipt. The preflight command reads the published catalog by default.

```text
python -m portbridge.discovery_scan --db <fresh-db> --online --url <pr>
python -m portbridge.preflight --url <pr> --limit 5
```
