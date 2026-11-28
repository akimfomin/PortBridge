# Parallel compatibility work · follow-through

The [first wave](../parallel-ops-2026-11-28/README.md) checked 53 PRs and 38 pairs. This wave repeated or added 38 PR-to-branch checks and 33 distinct pair checks. Across both inventories there are **77 distinct public PRs** and **71 pinned pair outcomes**. Of the new 33, 28 are textually clean and 5 conflict. Across the 71, 58 are textually clean and 13 conflict. The additional KLBF/Vice-Tay cross-repository attempt had no common ancestor and is kept separate.

## Useful tests transferred

The first wave recorded 13 grounded test or review leads. This wave delivered the following 12. A proposed shared test does not establish implementation compatibility, a performance improvement, or a maintainer's decision. Branch-level evidence is in [git-results.json](git-results.json).

| Receiving discussion | Source | Useful next control |
| --- | --- | --- |
| [TaynanGT/Vice-Tay #390](https://github.com/TaynanGT/Vice-Tay/pull/390) | [LooperSalty/AnyXboxX #517](https://github.com/LooperSalty/AnyXboxX/pull/517) | An advisory bake may race a write. Require the final bake to bind the latest descriptor across shards. |
| [R0Y00/Xbox2Windows #3139](https://github.com/R0Y00/Xbox2Windows/pull/3139) | [xcl-dev/xcl #2940](https://github.com/xcl-dev/xcl/pull/2940) | Keep success with a stale native blob distinct from forced native failure and recovery of a valid disk pair. The receiver already tests the latter. |
| [ProjectLeonida/mandy #2437](https://github.com/ProjectLeonida/mandy/pull/2437) | [LooperSalty/AnyXboxX #541](https://github.com/LooperSalty/AnyXboxX/pull/541) | Keep stable diagnostic ID across processes independent of adapter/driver eligibility for a compiled artifact. |
| [boykopovar/AnyPS5 #27984](https://github.com/boykopovar/AnyPS5/pull/27984) | [xcl-dev/xcl #3035](https://github.com/xcl-dev/xcl/pull/3035) | Use a mixed two-word read to distinguish an eligible known value from an ordinary queued write that must complete. |
| [boykopovar/AnyPS5 #23955](https://github.com/boykopovar/AnyPS5/pull/23955) | [LooperSalty/AnyXboxX #550](https://github.com/LooperSalty/AnyXboxX/pull/550) | Check exact native bytes released, cache evictions, and a zero-release control. A nonempty reusable pool is essential to the claim. |
| [LooperSalty/AnyXboxX #541](https://github.com/LooperSalty/AnyXboxX/pull/541) | [ProjectLeonida/mandy #2511](https://github.com/ProjectLeonida/mandy/pull/2511) | Repeat across processes under unchanged and changed compiler identity. An unavailable fingerprint cannot suppress or store a result. |
| [Marvisak/VIctory #3069](https://github.com/Marvisak/VIctory/pull/3069) | [ProjectLeonida/mandy #2517](https://github.com/ProjectLeonida/mandy/pull/2517) | Carry range-preservation control into the paired scratch/copy-back fixture. Keep uncovered bytes and the two writers separate. |
| [KytyPS5/KytyPS5 #2278](https://github.com/KytyPS5/KytyPS5/pull/2278) | [ProjectLeonida/mandy #2501](https://github.com/ProjectLeonida/mandy/pull/2501) | Preserve selected-lane bounds at a loop merge. A masked-off lane with a sentinel must not enter the resource range. |
| [fxceless/victory-fork #1500](https://github.com/fxceless/victory-fork/pull/1500) | [LooperSalty/AnyXboxX #550](https://github.com/LooperSalty/AnyXboxX/pull/550) | Validate host policy without any device, then run a separate budget-synchronized GPU test if there is a native target. |
| [xcl-dev/xcl #3056](https://github.com/xcl-dev/xcl/pull/3056) | [ProjectLeonida/mandy #2523](https://github.com/ProjectLeonida/mandy/pull/2523) | Drop an invalid dispatch between two live records. Neither GPU pass nor the next live budget entry may be affected. |
| [edsuuu/VI-BR-PORT #8](https://github.com/edsuuu/VI-BR-PORT/pull/8) | [xcl-dev/xcl #2956](https://github.com/xcl-dev/xcl/pull/2956) | Keep the source texture identity through a bake under pressure. Have an available but different texture as a negative control. |
| [PastiiJay/klbf-lab #16](https://github.com/PastiiJay/klbf-lab/pull/16) | [TaynanGT/Vice-Tay #390](https://github.com/TaynanGT/Vice-Tay/pull/390) | Transfer the cross-shard final-bake control. The Git histories did not share an ancestor at the two public heads. |

The standard public preflight was run on 12 receiving URLs. Four were temporarily unavailable in parallel and responded on serial retry. No trusted first check was returned on any of the 12. Ordinary matching surfaced the KLBF descriptor branch during the Vice-Tay lookup. Its source, named tests and Git history were verified independently. See [preflight outcomes](preflight.json).

## Five technical outcomes delivered or confirmed

| Outcome | Verified scope |
| --- | --- |
| [AnyXboxX #550](https://github.com/LooperSalty/AnyXboxX/pull/550#issuecomment-7230999315) | The author applied both review points and measured 6,220 → 5,708 MB on RTX 4060 Laptop. The 12 GB test is still open. |
| [Continued #2517](https://github.com/ProjectLeonida/mandy/pull/2517#issuecomment-7231040752) | The author adopted and ran the suggested soft-cap regression. PortBridge checked the published test and its receiving tree. |
| [VIctory #3609](https://github.com/Marvisak/VIctory/pull/3609#issuecomment-7231002918) | Andrew added both inputs suggested by PortBridge to a generated compute test. WARP 1.0.22 and DXIL validation gave the expected binary16 results. [Test-only commit](https://github.com/andrewpozdnakov7-jpg/VIctory/commit/742119fa0411cdddff68effe31ea4782b3b84ff3). [Native Intel request updated](https://github.com/akimfomin/PortBridge/issues/134). |
| [VIctory #3630](https://github.com/Marvisak/VIctory/pull/3630#issuecomment-7231030168) | Andrew ran the suggested boundaries for 7, 8 and 9 entries. All 24 WARP readbacks per revision agreed. PortBridge added the result to the [AnyXboxX discussion](https://github.com/LooperSalty/AnyXboxX/pull/571#issuecomment-7230907652). This proves translation fallback preservation for those two VIctory revisions. |
| [victory-fork #1500](https://github.com/fxceless/victory-fork/pull/1500#issuecomment-7231272315) | In response to the author's testing request, PortBridge independently ran pinned public launcher/policy code. Two PowerShell suites and six Rust tests passed. The results and reproduction are in the original thread. [Fixture and exact sources](victory-fork-1500.md). The author's reaction and full-crate or GPU results are still open. |

The first four outcomes have external results or decisions. The fifth is a requester-to-tester handoff completed by PortBridge and delivered back with evidence. XCL #3079 and the other receiving decisions remain open. None of the ten hardware and CPU invitations counts as a submitted test result. One of the six new invitations is explicitly CPU-only.

## Delivered messages and invitations

Cumulative first-wave and second-wave developer count: **24 distinct public contributors**, including the later-superseded #3228 discussion. **23** remained after excluding that record. Voluntary, no-install workflow offers reached **11 distinct teams**. No external installation or recurring use was verified. Ten named testing invitations have direct public receipts.

- PetrSeifert · [TaynanGT/Vice-Tay #390](https://github.com/TaynanGT/Vice-Tay/pull/390#issuecomment-7231272072) · delivered; decision open.
- lambirou · [R0Y00/Xbox2Windows #3139](https://github.com/R0Y00/Xbox2Windows/pull/3139#issuecomment-7231272986) · independent rebase already published, checked fresh head.
- RonLogic · [R0Y00/Xbox2Windows #3228](https://github.com/R0Y00/Xbox2Windows/pull/3228#issuecomment-7231272519) · superseded by upstream before outreach.
- mauroalvare · [LooperSalty/AnyXboxX #541](https://github.com/LooperSalty/AnyXboxX/pull/541#issuecomment-7231273291) · delivered; decision open.
- Nawid3333 · [KytyPS5/KytyPS5 #2278](https://github.com/KytyPS5/KytyPS5/pull/2278#issuecomment-7231272716) · delivered; decision open.
- cebondlovu · [fxceless/victory-fork #1500](https://github.com/fxceless/victory-fork/pull/1500#issuecomment-7231272315) · executed requested source checks and returned results.
- MoonEyes · [ProjectLeonida/mandy #2437](https://github.com/ProjectLeonida/mandy/pull/2437#issuecomment-7231300536) · delivered; decision open.
- 17bryen · [boykopovar/AnyPS5 #27984](https://github.com/boykopovar/AnyPS5/pull/27984#issuecomment-7231300755) · delivered; decision open.
- JJenkx · [boykopovar/AnyPS5 #23955](https://github.com/boykopovar/AnyPS5/pull/23955#issuecomment-7231301059) · delivered; decision open.
- moe-miau · [Marvisak/VIctory #3069](https://github.com/Marvisak/VIctory/pull/3069#issuecomment-7231301348) · delivered; decision open.
- Kalmarv · [xcl-dev/xcl #3056](https://github.com/xcl-dev/xcl/pull/3056#issuecomment-7231301610) · delivered; decision open.
- edsuuu · [edsuuu/VI-BR-PORT #8](https://github.com/edsuuu/VI-BR-PORT/pull/8#issuecomment-7231301917) · delivered; decision open.
- Vladimir-Human · [PastiiJay/klbf-lab #16](https://github.com/PastiiJay/klbf-lab/pull/16#issuecomment-7231418221) · delivered; decision open.

- Decodere · [Invitation #138](https://github.com/akimfomin/PortBridge/issues/138#issuecomment-7231281221) · [Receiving PR](https://github.com/Marvisak/VIctory/pull/3608)
- mrfelek · [Invitation #140](https://github.com/akimfomin/PortBridge/issues/140#issuecomment-7231280761) · [Receiving PR](https://github.com/boykopovar/AnyPS5/pull/27984)
- Helldiverr · [Invitation #143](https://github.com/akimfomin/PortBridge/issues/143#issuecomment-7231281718) · [Receiving PR](https://github.com/boykopovar/AnyPS5/pull/27972)
- neonbyte1 · [Invitation #142](https://github.com/akimfomin/PortBridge/issues/142#issuecomment-7231281901) · [Receiving PR](https://github.com/Marvisak/VIctory/pull/3246)
- adriaespii · [Invitation #141](https://github.com/akimfomin/PortBridge/issues/141#issuecomment-7231281479) · [Receiving PR](https://github.com/fxceless/victory-fork/pull/1500)
- upipibi · [Invitation #139](https://github.com/akimfomin/PortBridge/issues/139#issuecomment-7231281020) · [Receiving PR](https://github.com/boykopovar/AnyPS5/pull/23955)
- [The four earlier invitations](../parallel-ops-2026-11-28/followthrough.md#volunteer-requests).

The initial comments about Xbox2Windows #3139 and #3228 used earlier Git snapshots. Both comments were edited after checking the maintainer replies. #3139's updated branch no longer had the conflict, and #3228 was already superseded by merged #3231. Those independent changes are attributed to their authors. A new Git check of #3139 at `b409dc839def7036e40e439aa68ba87028c36fbe` against `97cde4d53d13bdc4b77250f6e1a1718b12924870` was clean. No duplicate test was requested.

## Reproduction

Use `python controls.py` for the eight independent CPU controls, including 25,000 integer inputs for the DispatchMesh bounds. See [their log](cpu-results.txt). For individual live Git checks use `python -m portbridge.merge_check <PR_URL> <TARGET_SHA>`. For a recorded pair, use an isolated bare repository, fetch the two pinned commits and run `git merge-tree --write-tree --name-only --no-messages <FIRST_HEAD> <SECOND_HEAD>`. Match the commit IDs first. For #1500 re-run the published launcher/policy checks in a disposable directory with the exact source hashes. No shipping game executables, content or user traces are needed.
