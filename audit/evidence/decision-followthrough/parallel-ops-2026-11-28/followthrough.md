# Delivery, decisions and Discovery follow-up

This is the second part of the [parallel Git and test wave](README.md). There were 13 delivered technical comments to 12 distinct receiving PR authors in 8 repositories. There were four personal invitations in reviewed Lab issues. A public comment, capability skip, author report, published upstream patch, eventual merge, and recurring use all have different evidence requirements.

## Decisions with code on public branches

- **AnyXboxX #550** · KainanP applied both PortBridge review points to the rebased [`b45603a0106c87fcbaaac893076d664144f30c44`](https://github.com/LooperSalty/AnyXboxX/commit/b45603a0106c87fcbaaac893076d664144f30c44), against [main `132da615`](https://github.com/LooperSalty/AnyXboxX/commit/132da61504cc2c2d086796c468a8ace1759aba22). The author reported an RTX 4060 Laptop 8 GB synthetic test at 6,220 MB before and 5,708 MB after. One unrelated watch test was intermittent in their broader runs, without a confirmed cause. PortBridge independently confirmed clean Git integration and repinned [Lab #132](https://github.com/akimfomin/PortBridge/issues/132). The current 12 GB result is simulated and the physical comparison stays open. [Author decision and measurements](https://github.com/LooperSalty/AnyXboxX/pull/550#issuecomment-7230999315)
- **Continued #2517** · Tyrannys confirmed an intentional soft cap and added the scenario from PortBridge. The first crossing to 67 is accepted in full. A later addition is refused with no mutation, and already-covered bytes still fit. The author reports the fixture passing. PortBridge confirmed the test on [`7ec666eeffe524d2a33c0d67ea2c77a5a51c097e`](https://github.com/ProjectLeonida/mandy/blob/7ec666eeffe524d2a33c0d67ea2c77a5a51c097e/runtime/test/title_write_ranges_test.cpp) and its clean merge against [`d4428519`](https://github.com/ProjectLeonida/mandy/commit/d44285197237cfe331684aa150fb9dec4b1d08b5). [Author decision](https://github.com/ProjectLeonida/mandy/pull/2517#issuecomment-7231040752)
- **XCL #3079** · the two-recorder reproduction reached RodrigoTorreao with the source-built [Xbox2Windows fixture](https://github.com/R0Y00/Xbox2Windows/pull/2332). Waiting for a choice between enforcing a single-recorder scope and testing queue-owned retirement. The independent XCL hardware test and any PR change are open. [Delivered proof](https://github.com/xcl-dev/xcl/pull/3079#issuecomment-7230924161)

## Delivered technical work

- KainanP · [LooperSalty/AnyXboxX 568](https://github.com/LooperSalty/AnyXboxX/pull/568#issuecomment-7230854923)
- Vladimir-Human · [fxceless/victory-fork 1280](https://github.com/fxceless/victory-fork/pull/1280#issuecomment-7230855411)
- gmankab · [KytyPS5/KytyPS5 2591](https://github.com/KytyPS5/KytyPS5/pull/2591#issuecomment-7230855760)
- SmartIngenieriayDesarrollo · [TaynanGT/Vice-Tay 389](https://github.com/TaynanGT/Vice-Tay/pull/389#issuecomment-7230907471)
- KainanP · [LooperSalty/AnyXboxX 571](https://github.com/LooperSalty/AnyXboxX/pull/571#issuecomment-7230907652)
- RodrigoTorreao · [xcl-dev/xcl 3079](https://github.com/xcl-dev/xcl/pull/3079#issuecomment-7230924161)
- Tyrannys · [ProjectLeonida/mandy 2517](https://github.com/ProjectLeonida/mandy/pull/2517#issuecomment-7230937914)
- Moon0755 · [Marvisak/VIctory 3609](https://github.com/Marvisak/VIctory/pull/3609#issuecomment-7230938186)
- chitters2004 · [boykopovar/AnyPS5 27979](https://github.com/boykopovar/AnyPS5/pull/27979#issuecomment-7230938535)
- andrewpozdnakov7-jpg · [Marvisak/VIctory 3630](https://github.com/Marvisak/VIctory/pull/3630#issuecomment-7230938853)
- LooperSalty · [LooperSalty/AnyXboxX 519](https://github.com/LooperSalty/AnyXboxX/pull/519#issuecomment-7231006372)
- marquezinii · [fxceless/victory-fork 92](https://github.com/fxceless/victory-fork/pull/92#issuecomment-7231058971)
- hamdanpor-ctrl · [TaynanGT/Vice-Tay 382](https://github.com/TaynanGT/Vice-Tay/pull/382#issuecomment-7231073087)

The AnyXboxX #519 comment initially cited the head of #521 by mistake. It was corrected in place to the exact #519 head already used in the pair table. The recorded pair and its conflicts did not change.

## Volunteer requests

- ZrDaniel07 · [Task and delivered invitation #136](https://github.com/akimfomin/PortBridge/issues/136#issuecomment-7230998488)
- Cai-piroska · [Task and delivered invitation #134](https://github.com/akimfomin/PortBridge/issues/134#issuecomment-7230998945)
- Doorriiaann · [Task and delivered invitation #135](https://github.com/akimfomin/PortBridge/issues/135#issuecomment-7230998696)
- KDenKC · [Task and delivered invitation #133](https://github.com/akimfomin/PortBridge/issues/133#issuecomment-7231000862)

The four Lab tasks are public GitHub requests. They can be claimed directly by people or agents. They are not yet reviewed task cards in the static Lab index. No reply or submitted result was recorded for these four requests before this check. Existing #132 was repinned without sending a duplicate invitation.

GitHub adoption proposals without setup were offered in the AnyXboxX and victory-fork threads. [Public entry for an agent or contributor](https://github.com/akimfomin/PortBridge/issues/98#issuecomment-7231109215). There is no new confirmed external installation. The Vice-Tay #273 opt-in request remains open, Continued #2379 still awaits an answer, and XCL Scratch #2322 retains its existing exact-head checks. No repeated pings were sent to those threads.

## Discovery and service verification

The first parallel on-demand replay shared one SQLite lease. Three of four runs returned busy without making a search request. A serial replay removed the collision. It confirmed that AnyXboxX #568 alone had no technical subject. The old lookup returned zero results with no external search. The shipped cue made one lookup, returned five candidates and surfaced [AnyPS5 #24219's synthetic negative control](https://github.com/boykopovar/AnyPS5/pull/24219). This control was verified in the merged source and sent to [AnyXboxX #519](https://github.com/LooperSalty/AnyXboxX/pull/519#issuecomment-7231006372). The result **helps choose a test**. The separate and better-matched [VIctory #3623](https://github.com/Marvisak/VIctory/pull/3623) came from manual review. One of the five new links was unrelated. See [exact before/after results](discovery-timing.json).

The narrow cue changed the title-only subject on two of the 53 selected PRs: AnyXboxX #568 and VIctory #3623. The tests also exercised the prefixed body spelling, one-request budget and an unrelated negative control. Local `python -m unittest discover -s tests` passed 322 tests. A fresh seeded `python -m portbridge --db <temp-db> export --out <temp-dir> --repository akimfomin/PortBridge` and `python -m portbridge.release_gate <temp-dir>` passed. The usual GitHub PR snapshot run was skipped by its event filter. The merged revision is [`e2847c438af3377ab04fd20ee3ed4250b1a537c1`](https://github.com/akimfomin/PortBridge/commit/e2847c438af3377ab04fd20ee3ed4250b1a537c1). [GitHub push run](https://github.com/akimfomin/PortBridge/actions/runs/46088844439).

To check the public lookup from either revision, run `python -m portbridge.discovery_scan --db <isolated-db> --online --url https://github.com/LooperSalty/AnyXboxX/pull/568` one call at a time per database. The external response is live and can change. This series has two author-confirmed adoptions of a specific review result. Neither is evidence of regular self-service use.
