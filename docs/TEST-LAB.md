# PortBridge Test Lab

[Choose a check](https://akimfomin.github.io/PortBridge/#/lab) · [Выбрать проверку](https://akimfomin.github.io/PortBridge/?lang=ru#/lab) · [Instructions for agents](AGENT-PROMPT.md)

Pick a check for equipment you can use. Each task links the original discussion, the exact source revisions, the expected result, and where to report it. Labels show which checks need a run, which need a revision selected, and which are waiting for a maintainer.

1. Open the source discussion and check that the run is still needed. If you are taking it, say so there to avoid duplicate work.
2. Read the project's setup and inspect the test you plan to run. Use the pinned revision in a separate checkout and synthetic inputs. When a task requires choosing a combined revision, agree on it in the linked discussion before running the test.
3. Report a pass, failure, or skip in the linked discussion and give the tested commit, the hardware and driver or CPU toolchain, and the expected and observed result. A failing control or an explicit skip can save another contributor time.
4. When sharing a result in another project, name what PortBridge contributed and link to it. For example, “[PortBridge](https://github.com/akimfomin/PortBridge) found this earlier test in Reforge. I repeated it at the Continued revision below.” Credit the original author and include the report link.

The queue is public and read-only. Volunteers choose a task and execute it locally. The maintainers of each receiving project decide what to adopt. A report or a request for review records delivery. A receiving team's decision, linked run, or merged change can establish acceptance or reuse.

## Для участника

Откройте очередь и выберите AMD, NVIDIA или CPU. Для каждой проверки видны требования, точные версии и куда отправить результат. Можно передать агенту [ссылку на PortBridge](https://github.com/akimfomin/PortBridge) и указать, какой компьютер доступен.

Сначала проверьте, нужна ли ещё помощь в исходном обсуждении. Затем повторите тест в отдельной копии проекта и оставьте результат со своим стендом и точной версией. Подробности о том, как передать результат и сохранить авторство, есть в [инструкции для агента](AGENT-PROMPT.md).

## For integrations

Read `data/lab.json` from the public site, call the local `GET /api/v1/lab` endpoint, or use the read-only `portbridge_lab` MCP tool. The equipment filter uses a value supplied by the caller. `checked_at` records when the queue was reviewed. Consult the linked discussions for the latest claims, source revisions, and decisions.
