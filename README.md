# PortBridge

**Find and reuse verified compatibility work across independent Xbox Series projects.**

[See team progress](https://akimfomin.github.io/PortBridge/) · [Find a test for your PC](https://akimfomin.github.io/PortBridge/#/lab) · [Request a test](https://github.com/akimfomin/PortBridge/issues/new?template=test-request.yml) · [Start with an agent](docs/AGENT-PROMPT.md) · [Русский](README.ru.md)

PortBridge connects public issues, pull requests, and test results across projects bringing Xbox Series software to PC. Look up an error or shader instruction, see what another team already tested, and share a reproducible result in the repository where it can help. Each team keeps its own tools, priorities, and review process.

## For project contributors

| What you want to do | Where to go |
| --- | --- |
| See what changed or find a shared check | Open the home dashboard for the last seven days of activity, progress by team, and tests that can help an open PR or issue. |
| Compare what teams have tested | Open the [technical capability map](https://akimfomin.github.io/PortBridge/#/projects) for scoped evidence and repository leads from public trackers and GitHub. |
| Check existing work before investigating an issue | Search by an exact error, instruction, PR number, or GitHub URL. Open the original sources before using a suggested match. [Issue catalog](https://akimfomin.github.io/PortBridge/#/problems) |
| Share a test, a fix, or a result that ruled something out | Include the original source, exact commit, platform, and observed result. [Evidence form](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml) |
| Continue public work when its repository becomes unavailable | Keep author and source links and reproduce one useful result in an active project. [Continuity pilot](docs/CONTINUITY.md) |
| Take a shared check or see where a result was delivered | Start with a [current team need](docs/WORK-PRIORITIES.md), then find a matching check in [Test Lab](https://akimfomin.github.io/PortBridge/#/lab). See prior runs in the [work log](docs/PORTING-WORK.en.md). |
| Get a test run on hardware you lack | Open a request from the Test Lab or submit your own check. PortBridge uses public hardware reports to find someone to invite. [Test requests](docs/TEST-REQUESTS.md) |
| Try PortBridge in your repository | Check one open PR for prior work, then see if a collaborator can reuse a result. [Pilot for maintainers](docs/AGENT-PROMPT.md#try-portbridge-in-your-repository) |
| Suggest a project, a missing link, or a search improvement | Open the [feedback form](https://github.com/akimfomin/PortBridge/issues/new?template=idea.yml). |

## Look up one real case

Paste a GitHub URL into the [public source index](https://akimfomin.github.io/PortBridge/#/sources), then open related work. The site shows how many entries match and labels automatically found candidates. Open the [reviewed catalog](https://akimfomin.github.io/PortBridge/#/problems) for recorded results and the [Research Radar](https://akimfomin.github.io/PortBridge/#/partial) for work that has a next step.

```sh
python -m portbridge.preflight --url https://github.com/LooperSalty/AnyXboxX/pull/133 --q "v_fmac_f32 rounding" --global
```

The exact AnyXboxX search links the earlier RDNA2 evidence and the new CPU correction. Connect the same tools from [Codex or Claude Code](docs/MCP.md), or start with the [Test Lab](https://akimfomin.github.io/PortBridge/#/lab) to try one check.

## PortBridge research

- **Wave32 carry fix.** DarkPanda69 reproduced the HLSL error and verified the PortBridge fix on RX 9070 XT and RTX 3060. The patch awaits XCL review. The earlier Lane-local Masks experiment was withdrawn. [Independent results](https://github.com/xcl-dev/xcl/issues/2584#issuecomment-7178879816) · [Fork patch](https://github.com/akimfomin/xcl/commit/d3e7725f9f48c39c18e7b6e011ec76423edb0004)
- Pixel mask projection lowered GPU draw time by 19% on two views of an open raylib scene on an RTX 4070 Ti SUPER. Both images matched the baseline bit for bit. A Microsoft display filter showed mixed timings. The opt-in XCL patch, its proof and measurements are available for review. [Code and reproduction](research/pipeline-readiness/structural-suite/night/ssa-mask-projection/README.md)
- [Cold graphics pipeline readiness](research/pipeline-readiness/ORDERED-GRAPHICS.md) cut recording-to-first-image time from 11.98 to 6.31 seconds on an open Vulkan scene with identical output. The report includes the exact eager baseline, memory cost, and the related XCL findings.

- [Cold pipeline readiness](research/pipeline-readiness) is the active study. It measures how compilation delays the first correct output and tests whether preserving memory headroom for required work helps.
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
