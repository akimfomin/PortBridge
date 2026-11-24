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
| Take a shared check or see where a result was delivered | Choose a task by hardware in the [Test Lab](https://akimfomin.github.io/PortBridge/#/lab). See prior runs in the [cross-project work log](docs/PORTING-WORK.en.md). |
| Get a test run on hardware you lack | Open a request from the Test Lab or submit your own check. PortBridge uses public hardware reports to find someone to invite. [Test requests](docs/TEST-REQUESTS.md) |
| Try PortBridge in your repository | Check one open PR for prior work, then see if a collaborator can reuse a result. [Pilot for maintainers](docs/AGENT-PROMPT.md#try-portbridge-in-your-repository) |
| Suggest a project, a missing link, or a search improvement | Open the [feedback form](https://github.com/akimfomin/PortBridge/issues/new?template=idea.yml). |

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
