# PortBridge

**Find and reuse verified compatibility work across independent Xbox Series projects.**

[See team progress](https://akimfomin.github.io/PortBridge/) · [Find a test for your PC](https://akimfomin.github.io/PortBridge/#/lab) · [Share evidence](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml) · [Connect an agent](docs/QUICKSTART.md#connect-codex-or-claude-code) · [Русский](README.ru.md)

PortBridge connects public issues, pull requests, and test results across projects bringing Xbox Series software to PC. Look up an error or shader instruction, see what another team already tested, and share a reproducible result in the repository where it can help. Each team keeps its own tools, priorities, and review process.

## For project contributors

| What you want to do | Where to go |
| --- | --- |
| See what changed or find a shared check | Open the home dashboard for the last seven days of activity, progress by team, and tests that can help an open PR or issue. |
| Check existing work before investigating an issue | Search by an exact error, instruction, PR number, or GitHub URL. Open the original sources before using a suggested match. [Issue catalog](https://akimfomin.github.io/PortBridge/#/problems) |
| Share a test, a fix, or a result that ruled something out | Use the evidence form. Include the original source, exact commit, platform, and observed result. |
| Take a shared check or see where a result was delivered | Choose a task by hardware in the [Test Lab](https://akimfomin.github.io/PortBridge/#/lab). See prior runs in the [cross-project work log](docs/PORTING-WORK.en.md). |
| Suggest a project, a missing link, or a search improvement | Open the [feedback form](https://github.com/akimfomin/PortBridge/issues/new?template=idea.yml). |

## Recent cross-project work

- **Wave64 in XCL.** Published RDNA2 measurements pointed to a missing byte-carry test. The XCL author requested a follow-up, and PortBridge submitted a one-file test PR. The reported run on an RTX 4070 Ti SUPER covered Wave32 and split Wave64. [Author response](https://github.com/ivall/xcl/pull/925#issuecomment-7128723618) · [Test PR](https://github.com/maximecmb/xcl/pull/1)
- **Shader memory reads in VIctory.** Related work from XCL and Continued guided two synthetic tests. Both passed on an RTX 4070 Ti SUPER and WARP. The earlier translator failed the controls. The patch and the proposed comparison are available in the original discussions. [VIctory test patch](https://github.com/Marvisak/VIctory/pull/571#issuecomment-7128201680) · [XCL comparison](https://github.com/ivall/xcl/pull/544#issuecomment-7128210080)
- **Wave64 in Reforge and Continued.** PortBridge linked the same source commit in both projects. A later D16 correction from Reforge passed 15 CPU tests and the result was shared with Continued. [Continued handoff](https://github.com/ubiquitarianism/leonida/pull/265#issuecomment-7128554846)

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

Add an optional prior-work summary to pull requests in your own repository. [GitHub Action](https://github.com/marketplace/actions/portbridge-prior-work-summary) · [Setup guide](docs/GITHUB-ACTION.md)
