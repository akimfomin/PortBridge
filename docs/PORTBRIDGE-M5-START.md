# Start a one-task PortBridge pilot

Open the dashboard and choose **Start here**. For a public compatibility issue, paste its GitHub URL into Issue catalog. Review the source revisions, then try one exact test in Lab. You can use the catalog and send a link with no installation. During review, open the `start.html` from the site artifact. After approval the same entry point will be available on the public site.

## Codex and Claude Code

In either agent paste the Start page and your task link. Ask for prior work, source versions, relevant differences, one small check and a draft report. For project-level guidance, copy [the short fragment](../examples/AGENTS.portbridge.md) into `AGENTS.md` for Codex or `CLAUDE.md` for Claude Code.

Use [the MCP setup](QUICKSTART.md#connect-codex-or-claude-code) for structured results. From a verified checkout, any client can start `python -m portbridge.mcp`. Add `--db /absolute/path/catalog.sqlite3` to use an existing local catalog. The default reads the published site and requires no token. Use `portbridge_preflight` with the exact PR URL, `portbridge_lab` with a task ID, and `portbridge_partner` for reviewed results. Remove the entry with `codex mcp remove portbridge` or `claude mcp remove portbridge` in the scope where it was added.

The optional authenticated Lab route uses `--exchange-port 8765 --enable-lab-writes` and the local credential `PORTBRIDGE_EXCHANGE_TOKEN`. The task and report tools require explicit confirmation per write. A separate principal reviews in Exchange. An agent report only enters review, and reviewed results can be withdrawn. The public snapshot has no write tools or participant credentials. [Exchange setup and review](EXCHANGE-API.md)

## GitHub Action and partner feeds

Copy [the optional PR workflow](../examples/portbridge-pr.yml) to `.github/workflows/portbridge-pr.yml` in a repository you maintain. Open a pull request or choose **Actions → Optional PortBridge prior work → Run workflow** and paste its public URL. Open the run summary for source links or the reason for an empty result. The workflow uses a pinned PortBridge revision, runs without checking out the PR, and requests no repository write permissions. To disconnect, disable the workflow under Actions or remove that file. [Action instructions and measured results](GITHUB-ACTION.md)

Use [the partner contract](../API.en.md#partner-feed) for JSON, the widget or a local digest. Schedule the pull in your own environment only if the updates help your work. Stop the schedule and remove its cursor to unsubscribe.

## Examples with receiving-team evidence

- AnyXboxX used Lyrnc's independent native RDNA2 measurement in its work on the interpreter. [Receiving PR](https://github.com/LooperSalty/AnyXboxX/pull/133#issuecomment-7136721736)
- FrameLab reviewed and accepted JoeY54's two AMD checks in its own issue. This was one task with two hardware reports. [Review](https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7160148587)

If PortBridge helps your work, a GitHub star is welcome. [PortBridge on GitHub](https://github.com/akimfomin/PortBridge)
