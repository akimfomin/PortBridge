# Start with PortBridge

Give your agent the GitHub link and the prompt below. Any session that can read public links can use this route without installing PortBridge, connecting MCP, or creating a GitHub token. Running a local test or making a change requires a session with a workspace and the tools for that check. [PortBridge on GitHub](https://github.com/akimfomin/PortBridge) · [Project instructions](../AGENTS.md)

## Copy this prompt

```text
Open https://github.com/akimfomin/PortBridge and read AGENTS.md.
Start with the issue or PR I give you. Otherwise, use docs/WORK-PRIORITIES.md to find a current need in VIctory, XCL, Continued or AnyXboxX.
Check the receiving team's discussion for earlier work, then use Test Lab if it helps make one reproducible contribution.
Record the source, revision, observed result and next step. Credit the original work and link PortBridge in any handoff. Prepare public messages or PRs as drafts for approval.
```

Add a link if you already know the task. If your GPU is unavailable, the agent can use a CPU or source-only check. Agents without a browser that renders the site can read the same public queues as JSON. [Test Lab](https://akimfomin.github.io/PortBridge/#/lab) · [Lab JSON](https://akimfomin.github.io/PortBridge/data/lab.json) · [Activity JSON](https://akimfomin.github.io/PortBridge/data/activity.json)

## Copyable prompt in Russian

```text
Открой https://github.com/akimfomin/PortBridge и прочитай AGENTS.md.
Начни с моего issue или PR. Если я дал только ссылку на PortBridge, используй docs/WORK-PRIORITIES.md, чтобы найти актуальный запрос VIctory, XCL, Continued или AnyXboxX.
Проверь в обсуждении, кто уже работает над задачей. Сделай один воспроизводимый вклад и используй Test Lab, если он поможет. Запиши источник, ревизию, результат и следующий шаг. Сохрани авторство, а при передаче добавь ссылку на PortBridge. Публичное сообщение или PR подготовь для согласования.
```

## Use it regularly

When you start Codex in a local checkout, it reads the root `AGENTS.md`. Claude Code 2.1.277 and later can also load it from the project. The default Claude Code setting prefers `CLAUDE.md` or `CLAUDE.local.md` in the project when present. If automatic loading is unavailable, use the explicit prompt above or import `@AGENTS.md` from a `CLAUDE.md` next to it. [Codex project instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md) · [Claude Code project instructions](https://code.claude.com/docs/en/memory#agents-md)

For a reusable command in a local session, copy the [portable `portbridge` skill folder](../skills/portbridge/) to one of the supported locations.

| Tool | Copy the folder to | Invoke |
| --- | --- | --- |
| Codex CLI or IDE | `~/.agents/skills/portbridge/` or `<project>/.agents/skills/portbridge/` | `$portbridge` |
| Claude Code | `~/.claude/skills/portbridge/` or `<project>/.claude/skills/portbridge/` | `/portbridge` |

The destination should contain `SKILL.md`. If the command does not appear, start a new local session. [Codex skills](https://learn.chatgpt.com/docs/build-skills) · [Claude Code skills](https://code.claude.com/docs/en/skills)

If you want the agent to call search and catalog tools directly, use the optional MCP connection. [MCP setup](MCP.md) · [Public API](../API.en.md)

## Try PortBridge in your repository

Paste a full GitHub PR link into the public Issue catalog, or give your agent the PR link and ask it to open the catalog's sources. For example, XCL #1100 finds the original Scarlett Layer FMA test and the independent XCL reports. This works without a PortBridge account or installation. [Try XCL #1100 in the catalog](https://akimfomin.github.io/PortBridge/#/problems?q=https%3A%2F%2Fgithub.com%2Fivall%2Fxcl%2Fpull%2F1100) · [FMA case](https://akimfomin.github.io/PortBridge/cases/pb-0006.html)

If the trial helps, maintainers can add this optional paragraph to their existing `AGENTS.md` or `CLAUDE.md`. Keep your normal contribution and review rules. Remove the paragraph to stop using the integration.

```markdown
For public compatibility work, look for related tests and fixes in [PortBridge](https://akimfomin.github.io/PortBridge/) before repeating an investigation. Check the original source and exact revision. If a result helps, say in the current issue or pull request what you used and credit the source author and [PortBridge](https://github.com/akimfomin/PortBridge).
```

If a result is useful, record what the receiving team actually did in that same issue or PR, with a link to its test, adopted change, or maintainer decision. For example, a reviewer may report that they ran the shared test at a pinned revision and got the expected result. Count an adopted result only when the receiving team's public evidence confirms it. [Pilot record](PILOT.md#что-записать-после-проверки)

Maintainers can also run the read-only Action for one existing PR. If it helps, they can run it for incoming PRs. [Action setup](GITHUB-ACTION.md) · [Successful XCL pilot](https://github.com/akimfomin/PortBridge/actions/runs/45420038315)
