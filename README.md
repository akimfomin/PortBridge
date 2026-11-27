# PortBridge

**Find and reuse verified compatibility work across independent Xbox Series projects.**

[See team progress](https://akimfomin.github.io/PortBridge/) · [Find a test for your PC](https://akimfomin.github.io/PortBridge/#/lab) · [Request a test](https://github.com/akimfomin/PortBridge/issues/new?template=test-request.yml) · [Start with an agent](docs/AGENT-PROMPT.md) · [Join the Test Lab](https://github.com/akimfomin/PortBridge/issues/112) · [Русский](README.ru.md)

PortBridge connects public issues, pull requests, and test results across projects bringing Xbox Series software to PC. Look up an error or shader instruction, see what another team already tested, and share a reproducible result in the repository where it can help. Each team keeps its own tools, priorities, and review process.

## Try PortBridge on one pull request

[Share a public PR URL and receiving commit](https://github.com/akimfomin/PortBridge/issues/98), or give the same link to your agent to run the check yourself. Volunteers can [take one current Test Lab task](https://github.com/akimfomin/PortBridge/issues/98#issuecomment-7206391931) and reply with an aggregate result.

A repository maintainer can enable the [read-only GitHub check](docs/GITHUB-ACTION.md) to see earlier work or the reason for an empty result directly in a PR. The M5–M6 pilot welcomes one concrete technical decision at a time. [Agent setup](docs/MCP.md) · [Partner feed](API.en.md) · [Measured outcomes and open limits](https://github.com/akimfomin/PortBridge/blob/audit/review/audit/LATEST.md)

In the Continued pilot, two contributors used the team’s own diagnostics to check whether a fresh process reused a recorded pipeline cache. They reported cache hits on a GTX 1050 Ti and an RTX 5070. [PortBridge’s suggestion](https://github.com/ubiquitarianism/leonida/pull/2392#issuecomment-7202363138) · [Empty and populated journal controls](https://github.com/ubiquitarianism/leonida/pull/2392#pullrequestreview-6080300502)

[Letter from the founder](https://akimfomin.github.io/PortBridge/letter.html) · [Reply or volunteer to maintain a component](https://github.com/akimfomin/PortBridge/issues/91) · [Engineering history and evidence](docs/FINAL-AUDIT.md) · [Run or maintain PortBridge](docs/PASSIVE-MAINTENANCE.md)

## Discovery

Search for earlier implementations from other projects using an error, GPU instruction, API symbol or a known issue or PR link. Results include the source revision, compatibility limits, license and a proposed check. [Try it locally](docs/QUICKSTART.md#try-discovery-locally)

## People and Impact

The public projections link technical work to its sources and distinguish contributions, independent tests and receiving decisions. [M4 evidence](docs/PORTBRIDGE-M4.md) · [Engineering record](docs/FINAL-AUDIT.md)

## For project contributors

| What you want to do | Where to go |
| --- | --- |
| See what changed or find a shared check | Open the home dashboard for the last seven days of activity, progress by team, and tests that can help an open PR or issue. |
| Compare what teams have tested | Open the [technical capability map](https://akimfomin.github.io/PortBridge/#/projects) for scoped evidence and repository leads from public trackers and GitHub. |
| Check existing work before investigating an issue | Search by an exact error, instruction, PR number, or GitHub URL. Open the original sources before using a suggested match. [Issue catalog](https://akimfomin.github.io/PortBridge/#/problems) |
| Share a test, a fix, or a result that ruled something out | Include the original source, exact commit, platform, and observed result. [Evidence form](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml) |
| Continue public work when its repository becomes unavailable | Keep author and source links and reproduce one useful result in an active project. [Continuity pilot](docs/CONTINUITY.md) |
| Take a shared check or see where a result was delivered | Start with a [current team need](docs/WORK-PRIORITIES.md), then find a matching check in [Test Lab](https://akimfomin.github.io/PortBridge/#/lab). See prior runs in the [work log](docs/PORTING-WORK.en.md). |
| Get a test run on hardware you lack | Open a request in the Test Lab. Volunteers can reply there. A maintainer can manually send a reviewed invitation. [Test requests](docs/TEST-REQUESTS.md) |
| Try PortBridge in your repository | Check one open PR for prior work, then see if a collaborator can reuse a result. [Pilot for maintainers](docs/AGENT-PROMPT.md#try-portbridge-in-your-repository) |
| Suggest a project, a missing link, or a search improvement | Open the [feedback form](https://github.com/akimfomin/PortBridge/issues/new?template=idea.yml). |

## Start from a pull request

From this checkout, give Discovery the public GitHub PR URL. It reads the PR metadata and makes at most one external search lookup. The result shows the selected technical subject, up to five source links and an explanation when the search is empty or unavailable.

```sh
python -m portbridge.discovery_scan --online --url https://github.com/LooperSalty/AnyXboxX/pull/429
```

Inspect the linked evidence before applying a result. [Measured examples](audit/evidence/m52/assessment.md) · [Audit report](audit/LATEST.md)

## Look up one real case

Paste a GitHub URL into the [public source index](https://akimfomin.github.io/PortBridge/#/sources), then open related work. The site shows how many entries match and labels automatically found candidates. Open the [reviewed catalog](https://akimfomin.github.io/PortBridge/#/problems) for recorded results and the [Research Radar](https://akimfomin.github.io/PortBridge/#/partial) for work that has a next step.

```sh
python -m portbridge.preflight --url https://github.com/LooperSalty/AnyXboxX/pull/133 --q "v_fmac_f32 rounding" --global
```

The exact AnyXboxX search links the earlier RDNA2 evidence and the new CPU correction. Connect the same tools from [Codex or Claude Code](docs/MCP.md), or start with the [Test Lab](https://akimfomin.github.io/PortBridge/#/lab) to try one check.

## PortBridge research

- **Wave32 carry fix.** DarkPanda69 reproduced the XCL error and verified PortBridge’s correction on an RX 9070 XT and an RTX 3060. The patch is awaiting upstream review. [Independent comparison](https://github.com/xcl-dev/xcl/issues/2584#issuecomment-7178879816) · [Fork patch](https://github.com/akimfomin/xcl/commit/d3e7725f9f48c39c18e7b6e011ec76423edb0004)
- **Experimental pixel mask projection.** On one RTX 4070 Ti SUPER, a verified raylib image arrived 99–120 ms sooner. Vulkan draw time fell by 19% in two views. Microsoft’s display filter had mixed timings. This separate opt-in preserves the original ballots. The earlier Lane-local Masks experiment was withdrawn after a Wave32 failure. [Measurements and code](https://github.com/akimfomin/PortBridge/blob/9c2616998e176806565ee1a0076dc4efb7ae4dc1/research/pipeline-readiness/structural-suite/night/ssa-mask-projection/README.md)
- [Observation-scoped GPU readbacks](research/readback-epochs) reuses already observed bytes and tests packed selective readback against bounded exact-range staging. [Ecosystem evidence](docs/READBACK-2026-11-25.md)
- [Portable Vulkan mipmaps](research/mipmap-contract) demonstrates a lane-numbering assumption in NVIDIA's fast shader, a guarded correction, and matched physical output.
- [Adaptive shader dispatch](research/adaptive-switch-dispatch) partitions large sparse switches. The study compares a flat switch, a fixed-size range tree, and a table where the case bodies allow one.
- [Shader tail factoring](research/shader-tail-factoring) shares repeated arithmetic before shader compilation. The [open-corpus audit](research/shader-tail-factoring/CORPUS.md) records where the exact pass found no eligible region.
- [Shader lane-exchange optimizer](research/subgroup-validator) can omit subgroup ballots when full participation is proven. The replay records a physical RTX check with a guarded control.
- [Cross-queue transient slot cover](research/transient-slot-cover) computes reusable memory slots without adding dependencies to its input graph.
- [Buffer Transfer Planner on RTX 4070 Ti SUPER](research/transfer-planner/physical) records the D3D12 and Vulkan measurements and why we kept the planner as a reference.

[Current evidence-first report](docs/EVIDENCE-FIRST-2026-11-25.md) · [Previous research and adoption report](docs/RD-2026-11-25.md) · [Ecosystem audit](docs/ECOSYSTEM-AUDIT-2026-11-25.md)

## Recent cross-project work

- **Wave64 in XCL.** Published RDNA2 measurements pointed to a missing byte-carry test. The XCL author requested a follow-up, and PortBridge submitted a one-file test PR. The reported run on an RTX 4070 Ti SUPER covered Wave32 and split Wave64. [Author response](https://github.com/ivall/xcl/pull/925#issuecomment-7128723618) · [Pinned test](https://github.com/akimfomin/xcl/commit/3858abc46e4c9c3b9db5e4ae648d6636c37bfb51)
- **Shader memory reads in VIctory.** Related work from XCL and Continued guided two synthetic tests. Both passed on an RTX 4070 Ti SUPER and WARP. The earlier translator failed the controls. The patch and the proposed comparison are available in the original discussions. [VIctory test patch](https://github.com/Marvisak/VIctory/pull/571#issuecomment-7128201680) · [XCL comparison](https://github.com/ivall/xcl/pull/544#issuecomment-7128210080)
- **Wave64 in Reforge and Continued.** PortBridge submitted a Reforge D16 fix in Continued. A contributor independently passed 15 CPU checks on macOS and another approved the same revision. [Independent run](https://github.com/ubiquitarianism/leonida/pull/701#issuecomment-7131731339) · [Contributor approval](https://github.com/ubiquitarianism/leonida/pull/701#pullrequestreview-6039203797)

The [merged audit update](https://github.com/akimfomin/PortBridge/pull/1) improved recommendation safety, exact identifier lookup, revision tracking, and review of shared results.

## Run locally

Use Python 3.10 or later. PortBridge uses the Python standard library. Use `python3` if that is the Python executable on your system.

```sh
git clone https://github.com/akimfomin/PortBridge.git
cd PortBridge
python -m portbridge serve
```

Open the [local catalog](http://127.0.0.1:8765/). Run `python -m portbridge.exchange_demo` from the same folder to see two test clients exchange a reviewed result over the local API. The demo uses temporary data.

The [public catalog](https://akimfomin.github.io/PortBridge/) works without an account. Teams that want a shared queue can opt into the [local exchange (Russian)](docs/EXCHANGE-API.md). The [quick start](docs/QUICKSTART.md) covers the public route for people and agents.

[Contribute](CONTRIBUTING.md) · [Tracked projects](https://akimfomin.github.io/PortBridge/#/projects) · [API reference](API.en.md) · [MIT license](LICENSE)

Try PortBridge's GitHub Action on one existing public PR. [Setup guide](docs/GITHUB-ACTION.md) · [Successful XCL pilot](https://github.com/akimfomin/PortBridge/actions/runs/45420038315) · [GitHub Marketplace](https://github.com/marketplace/actions/portbridge-prior-work-summary)

## Try one task with an agent

Open the dashboard, choose **Start here**, and follow one public issue or PR through Search and Lab. The local M5 candidate includes an optional MCP connection, a read-only PR Action and a partner widget. [Pilot quick start](docs/PORTBRIDGE-M5-START.md)

If you find PortBridge useful, a GitHub star would be greatly appreciated. It helps other teams discover the project. [PortBridge on GitHub](https://github.com/akimfomin/PortBridge)
