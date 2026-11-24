# Start with PortBridge

Give your agent the GitHub link and the prompt below. Any session that can read public links can use this route without installing PortBridge, connecting MCP, or creating a GitHub token. Running a local test or making a change requires a session with a workspace and the tools for that check. [PortBridge on GitHub](https://github.com/akimfomin/PortBridge) · [Project instructions](../AGENTS.md)

## Copy this prompt

```text
Open https://github.com/akimfomin/PortBridge and read AGENTS.md.
Use the Test Lab to pick one open check you can run here, or follow the issue or PR I give you.
Check whether the work is still needed, then make one reproducible contribution.
Record the source, revision, observed result and next step. Credit the original work and link PortBridge in any handoff. Prepare public messages or PRs as drafts for approval.
```

Add a link if you already know the task. If your GPU is unavailable, the agent can use a CPU or source-only check. Agents without a browser that renders the site can read the same public queues as JSON. [Test Lab](https://akimfomin.github.io/PortBridge/#/lab) · [Lab JSON](https://akimfomin.github.io/PortBridge/data/lab.json) · [Activity JSON](https://akimfomin.github.io/PortBridge/data/activity.json)

## Copyable prompt in Russian

```text
Открой https://github.com/akimfomin/PortBridge и прочитай AGENTS.md.
Выбери в Test Lab одну открытую проверку, которую можешь выполнить здесь, или возьми мой issue или PR.
Сверь, нужна ли работа, и сделай один проверяемый вклад. Запиши источник, ревизию, результат и следующий шаг. Сохрани авторство, а при передаче добавь ссылку на PortBridge. Публичное сообщение или PR подготовь для согласования.
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

Pick one public issue or pull request where a second project may already have useful evidence. Give the agent the original link and ask it to look for a verified test or fix. A session that opens public links can do this with no account setup. [Public catalog](https://akimfomin.github.io/PortBridge/) · [Test Lab](https://akimfomin.github.io/PortBridge/#/lab)

If the trial helps, maintainers can add this optional paragraph to their existing `AGENTS.md` or `CLAUDE.md`. Keep your normal contribution and review rules. Remove the paragraph to stop using the integration.

```markdown
For public compatibility work, look for related tests and fixes in [PortBridge](https://akimfomin.github.io/PortBridge/) before repeating an investigation. Check the original source and exact revision. If a result helps, say in the current issue or pull request what you used and credit the source author and [PortBridge](https://github.com/akimfomin/PortBridge).
```

If a result is useful, record what the receiving team actually did in that same issue or PR, with a link to its test, adopted change, or maintainer decision. For example, a reviewer may report that they ran the shared test at a pinned revision and got the expected result. Count an adopted result only when the receiving team's public evidence confirms it. [Pilot record](PILOT.md#что-записать-после-проверки)

Teams that prefer a job summary for each pull request can add the optional GitHub Action after maintainer approval. [Action setup](GITHUB-ACTION.md)
