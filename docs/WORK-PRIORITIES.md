# Work priorities

[Русский](#по-русски) · [Cross-project evidence](PORTING-WORK.en.md) · [Verified interactions](COMMUNITY-COORDINATION.md) · [Test Lab](https://akimfomin.github.io/PortBridge/#/lab)

Use **50%** for technical assistance, **25%** for contributors and partnerships, **15%** for coordination and evidence exchange, and **10%** for PortBridge itself as a starting budget. Adjust it when a receiving team has a higher-value need. Monitor smaller projects for a fixture, tool or contributor that addresses an open problem. Keep earlier findings available for reuse.

## Choose a task

Before starting substantial work, open the receiving issue, PR or maintainer note and record five answers:

1. Who asked for the result or can act on it? Link their request or explain the evidence of demand.
2. What exact failure, missing comparison, or decision is open?
3. Which current technical goal does the result advance?
4. Where could the result be accepted or reused? Name the review, test, fix, or decision it could change.
5. Who has claimed related work? Compare current revisions, open changes and reported coverage before starting.

Start with one bounded check. Use PortBridge search to find shared evidence and Test Lab to fill a named gap. Pause if the receiver's decision is already supported, a parallel effort covers the same case, or the available public evidence cannot support a useful check.

## Receiving teams

Evidence checked on 25 November 2026, Moscow time. Recheck the linked discussions and revisions before starting.

| Team and goal | Demand, overlap and next useful result |
| --- | --- |
| **VIctory · structured buffers used in rendering** | Rezwo asked for a two-descriptor check on #984. The missing case selects descriptors with different strides, 56 and 32 bytes. Single-stride results already exist, and AnyXboxX #164 has evaluated this work. Help the existing review with a mixed-stride control. Marvisak paused new outside PRs to review the queue. [Review request](https://github.com/Marvisak/VIctory/pull/984#discussion_r4685537007) · [Receiver](https://github.com/LooperSalty/AnyXboxX/issues/164) · [Contribution status](https://github.com/Marvisak/VIctory/issues/712#issuecomment-7125173767) |
| **XCL · shader compiler performance and stability** | #1748 merged with independent synthetic output and DXIL size comparisons on AMD and NVIDIA. Those checks establish output and size. On #1100, PastiiJay completed the exact AMD Wave64 check and exposed a requirement gap in the standalone FMA test on NVIDIA. The AMD evidence stays pinned to `1b3fbc4` while review continues. [Maintainer request](https://github.com/xcl-dev/xcl/issues/1269) · [DXIL validation](https://github.com/xcl-dev/xcl/pull/1748#issuecomment-7143311158) · [AMD FMA report](https://github.com/xcl-dev/xcl/pull/1100#issuecomment-7144197194) |
| **Continued · first-frame rendering and shader paths** | #511 and #682 already have independent pixel comparisons. #1060 has native Wave64 results on Radeon. In #1042 madhyn adopted PortBridge's waiter guard and both exception tests. A reviewer identified a timing assumption in a separate fixture. PortBridge supplied a deterministic replacement for review. [First-frame comparison](https://github.com/ubiquitarianism/leonida/pull/682#issuecomment-7136308990) · [Radeon result](https://github.com/ubiquitarianism/leonida/pull/1060#issuecomment-7141131001) · [Adopted in #1042](https://github.com/ubiquitarianism/leonida/pull/1042#issuecomment-7143506847) · [Fixture follow-up](https://github.com/ubiquitarianism/leonida/pull/1042#issuecomment-7144431667) |
| **AnyXboxX · final composition and shader correctness** | LooperSalty reports richer G-buffer output while composition is still uniform. Indexed-rectangle work is already underway. The Continued 32-SGPR change is a lead to check against a specific missing input. Continued #1087 attributes its last case to a separate `buffer_store_short` change. For the immediate NVIDIA request on #169, PortBridge verified that the focused regression fails on the base and that the patched version passes on RTX. [Maintainer update](https://github.com/LooperSalty/AnyXboxX/issues/140#issuecomment-7140464399) · [Continued source](https://github.com/ubiquitarianism/leonida/pull/1087) · [NVIDIA request](https://github.com/LooperSalty/AnyXboxX/pull/169) · [Result](https://github.com/LooperSalty/AnyXboxX/pull/169#issuecomment-7143022441) |

The victory-fork #11 indirect-lighting change merged. The maintainer recorded shader translation and binding on RTX, with a controlled image comparison still open. The independent stability reports in #26 cover particular hardware and revisions. AnyXboxX #171 merged a pinned fork update and cites #26. Check the exact integrated revision before transferring a result from a newer fork build. [Lighting report](https://github.com/fxceless/victory-fork/pull/11#issuecomment-7143771500) · [Stability discussion](https://github.com/fxceless/victory-fork/issues/26) · [Integration](https://github.com/LooperSalty/AnyXboxX/pull/171)

For another cross-project check, victory-fork #55 requests a way to identify GPU adapters in telemetry. Follow the existing work in #44 and use synthetic duplicate adapter names and unknown identifiers. The open Five Star Recomp wave32/FMA work already has owners. Xbox2Windows #369 includes NVIDIA controls. KLBF Lab has supplied the exact AMD FMA result, and a reciprocal synthetic RTX test is available if they post a need. [Adapter request](https://github.com/fxceless/victory-fork/issues/55) · [Existing PR](https://github.com/fxceless/victory-fork/pull/44#issuecomment-7144319892) · [Five Star Recomp claim](https://github.com/ThatRecompDev/five-star-recomp/issues/9#issuecomment-7144210409) · [Xbox2Windows #369](https://github.com/R0Y00/Xbox2Windows/issues/369) · [KLBF exchange](https://github.com/akimfomin/PortBridge/issues/14#issuecomment-7144359164)

## What the audit found

| Evidence | Decision |
| --- | --- |
| **Merged reuse in a leading project.** AnyXboxX #129 used a value from the independent VIctory D16 measurement in an interpreter regression. #144 fixed an ALU test on WARP. | Keep solving precise receiving-project questions. Track WARP test reliability within its scope. [D16 regression](https://github.com/LooperSalty/AnyXboxX/pull/129) · [WARP fix](https://github.com/LooperSalty/AnyXboxX/pull/144) |
| **Requested evidence used before merge.** An AnyXboxX reviewer flagged dependent work in #133. Lyrnc took the Test Lab request, ran the ADD case in his own HIP harness on native AMD Wave32, and KainanP applied the result to #133. The author of XCL #1144 used a boundary comparison and added controls. Continued #1042 incorporated a test cleanup. | Give this kind of work first claim on testing time. Track the pending merge or uncovered case at its receiving PR. [AnyXboxX review](https://github.com/LooperSalty/AnyXboxX/pull/133#pullrequestreview-6041873843) · [Test Lab result](https://github.com/akimfomin/PortBridge/issues/19#issuecomment-7136020663) · [Use in #133](https://github.com/LooperSalty/AnyXboxX/pull/133#issuecomment-7136721736) · [XCL](https://github.com/xcl-dev/xcl/pull/1144#issuecomment-7133518162) · [Continued](https://github.com/ubiquitarianism/leonida/pull/1042#issuecomment-7140737395) |
| **Independent use by a smaller project.** FrameLab documented the NVIDIA comparison, opened its own AMD validation issue and added a direct Test Lab task link to its main-branch documentation. The AMD run is open. | Keep that volunteer route available. Use the fixture for leading-team work when a receiver needs the same queue comparison. [Merged validation doc](https://github.com/5headsmartbtw/leonida-framelab/blob/1b1c3cfc371225cd020bf4bfbba50e8c696a86f1/docs/evidence/independent-vulkan-handoff.md) · [FrameLab's request](https://github.com/5headsmartbtw/leonida-framelab/issues/15) |
| **Standalone evidence without a current receiver.** The TuxBox timing probe and XValkyrie rectangle readback answer local synthetic questions. SceneGate has a reusable pixel control. Reforge's public source is unavailable, and the XCL #925 receiving PR closed. | Keep these as reference material. Reserve further engineering time for a current receiving task with a matching gap. Preserve Reforge attribution and published measurements. [Existing fixtures](PORTING-WORK.en.md) · [Reforge continuity](CONTINUITY.md) · [XCL #925](https://github.com/xcl-dev/xcl/pull/925) |

Record whether a result changed a technical decision, was applied or merged, or was independently adopted by a participant. Include the public link and exact scope. Use those outcomes to adjust the next round of work.

## По-русски

Ориентир на итерацию — 50% усилий на техническую помощь, 25% на участников и партнёрства, 15% на координацию и обмен результатами, 10% на сам PortBridge. Перед работой проверяем, кому нужен результат, какую проблему он решает, к какой цели приближает, где его смогут применить и кто уже занимается тем же.

В [очереди выше](#receiving-teams) указаны запросы команд, известные результаты и конкретный следующий шаг. Подтверждённую пользу отмечаем по решениям, принятым правкам и самостоятельному использованию PortBridge. [Журнал работ](PORTING-WORK.md) · [Журнал взаимодействий](COMMUNITY-COORDINATION.md)
