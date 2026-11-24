# PortBridge quick start

[Русские инструкции по MCP](MCP.md) · [Русский план пилота](PILOT.md)

## See what changed

The home dashboard shows the last seven days by team. Open an event to read its original PR or test report. To help, choose a shared check and record the revision, platform, and outcome in the linked discussion. [Open the dashboard](https://akimfomin.github.io/PortBridge/)

## Check one issue

1. Search for the exact error, instruction, PR number, or PortBridge ID. [Issue catalog](https://akimfomin.github.io/PortBridge/#/problems)
2. Open the linked issue, PR, or test. Compare its commit, platform, and tested condition with yours. Use automated matches as leads to check.
3. Share one reproducible result through the [evidence form](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml). Keep the original discussion linked.

## Connect Codex or Claude Code

Use Python 3.10 or later and clone PortBridge. The default server reads the public catalog. It runs locally and needs no database or GitHub token.

```sh
git clone https://github.com/akimfomin/PortBridge.git
```

Put your full PortBridge path in the examples. Use `python3` or a full path to the Python executable if your system requires it.

### Codex

Add this entry to your Codex `config.toml`.

```toml
[mcp_servers.portbridge]
command = "python"
args = ["-m", "portbridge.mcp"]
cwd = "/absolute/path/to/PortBridge"
```

Run `codex mcp list` and open a new session. Check the connection with `/mcp`. [Codex MCP documentation](https://developers.openai.com/codex/mcp)

### Claude Code

From the project you want to work on in Claude Code, run these commands.

```sh
claude mcp add --env "PYTHONPATH=/absolute/path/to/PortBridge" --transport stdio portbridge -- python -m portbridge.mcp
claude mcp list
```

Open Claude Code in the same folder and check `/mcp`. Update Claude Code if the server connects but the search tool is missing. [Local stdio setup](https://code.claude.com/docs/en/mcp#option-3-add-a-local-stdio-server) · [Tool schema compatibility](https://code.claude.com/docs/en/mcp#tool-input-schemas-with-a-root-level-combinator)

### Try the tools

Ask the agent to call `portbridge_activity` without arguments for progress and shared checks. For a single case, call `portbridge_problem` for `PB-0001` and `portbridge_preflight` for `https://github.com/ubiquitarianism/leonida/pull/207`. Check the linked sources before acting.

## Run a two-team pilot

One participant from each team can start in the GitHub threads they already use.

1. Agree on one input and expected result. An example is the LDS halfword read that crosses a word boundary at byte 3. The VIctory test has exact input values and an expected result. Check the target revision and whether XCL can run an equivalent case. [VIctory test](https://github.com/Marvisak/VIctory/pull/571#issuecomment-7128201680) · [XCL comparison](https://github.com/ivall/xcl/pull/544#issuecomment-7128210080)
2. Link the source test in the receiving issue or PR. Record the commit, platform, expected value, actual value, and any difference in test scope.
3. Keep both results linked in one evidence report. If the receiving team adopts the test, changes what it checks next, or saves a repeat investigation, link the reply, run, or commit that shows it.

Run `python -m portbridge.exchange_demo` from the PortBridge folder to try the exchange offline with test clients. For an opt-in private queue with team-specific access, see [exchange setup (Russian)](EXCHANGE-API.md).
