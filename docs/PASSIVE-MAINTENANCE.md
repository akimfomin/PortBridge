# Maintaining PortBridge in passive mode

You can use the catalog, run a published experiment or volunteer for one open test. For questions about taking responsibility for a component, leave a comment in [the public handover](https://github.com/akimfomin/PortBridge/issues/91). The repository accepts issues and pull requests. Responses and reviews depend on a volunteer being available.

## Run it yourself

Use Python 3.10 or newer. The catalog and public MCP reader use the Python standard library.

```sh
git clone https://github.com/akimfomin/PortBridge.git
cd PortBridge
python -m portbridge serve --offline
```

Open the [local dashboard](http://127.0.0.1:8765). A new offline checkout starts with the reviewed seed. Run `python -m portbridge sync` for public metadata or start `python -m portbridge serve` for periodic local refreshes. To search the published index directly, run `python -m portbridge.preflight --url https://github.com/LooperSalty/AnyXboxX/pull/133`. The MCP client starts `python -m portbridge.mcp` on the reader’s machine and reads the same public snapshots. The optional private exchange needs its own local server and credentials. [MCP setup](MCP.md) · [API](../API.en.md) · [Private exchange](EXCHANGE-API.md)

## What runs unattended

| Operation | Trigger and dependencies |
| --- | --- |
| Catalog, search index, public JSON, Atom feed and dashboard | GitHub Actions reads public metadata, refreshes Test Lab reports, advances the cached SQLite index, runs the tests and builds static files on a hosted runner. GitHub Pages publishes from `main` with `PORTBRIDGE_ENABLE_GITHUB_PAGES=true`. Readers can use the last published files while the next refresh is pending. [Workflow](../.github/workflows/pages.yml) |
| Test Lab intake | Eligible comments in designated PortBridge issues are validated and may produce a seven-day Actions receipt. Scheduled scans read supported report threads. A reviewed decision can trigger a fresh site build. Intake cannot post a reply or make a maintainer decision. [Intake workflow](../.github/workflows/lab-intake.yml) · [Report format and review](TEST-LAB.md) |
| Public feedback and coordination | A GitHub account can open an issue or PR. Anyone can read the catalog and evidence. Opening or labeling a test request does not invite a tester. A maintainer may manually dispatch one invitation on an approved request. The one-PR pilot also requires a manual run. [Forms](https://github.com/akimfomin/PortBridge/issues/new/choose) · [Test requests](TEST-REQUESTS.md) |

The owner’s PC can be off. The publication uses a GitHub-hosted runner, a job-scoped token and GitHub Pages. The optional Cloudflare job was skipped in the checked deployment. No additional host is required. The Actions cache retains previously fetched metadata when available. Cache evictions, source outages and API quotas can reduce coverage. Read the age and state of each source in [public health](https://akimfomin.github.io/PortBridge/data/health.json) and compare the last build with the [site manifest](https://akimfomin.github.io/PortBridge/data/site.json).

## If the site is stale

1. Inspect the latest [static snapshots runs](https://github.com/akimfomin/PortBridge/actions/workflows/pages.yml). The clock requests builds at minutes 13 and 43 UTC. During the handover, the schedule starts on 25 November 2026 at 04:34, 14:56 and 23:36 UTC all succeeded. The gaps show that actual delivery can take hours. The last of these completed its public verification. [Scheduled run](https://github.com/akimfomin/PortBridge/actions/runs/45722640647)
2. Check `build`, `github-pages` and `verify-github-pages` in the same run. A green deployment can contain partially refreshed source data. Check [activity](https://akimfomin.github.io/PortBridge/data/activity.json), [Test Lab](https://akimfomin.github.io/PortBridge/data/lab.json) and the [source index](https://akimfomin.github.io/PortBridge/data/browse-index.json). If only one source failed, look up its original URL and last successful check.
3. GitHub disables scheduled workflows after 60 days without repository activity in a public repository. A maintainer with write access can open Actions, enable **PortBridge static snapshots** if necessary and select **Run workflow** on `main`. If Pages was reconfigured, check that its source is GitHub Actions and the repository variable above is enabled. [GitHub schedule policy](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows) · [Manual dispatch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
4. For a fork or ownership transfer, review the explicit repository, owner and allowed issue checks in Pages, report intake and test invitations before enabling publication. An owner review in a designated result thread and a volunteer report have distinct authority. Test the mapping with the new repository before granting any write permissions.
5. For a bad release, revert the responsible change in a PR, run the same tests and merge the verified revert into `main`. The next build regenerates the site. Preserve research branches and contributor revisions for reproducibility.

## Add a source, share a result or resume an experiment

- To suggest a repository or correct a card, use the [feedback form](https://github.com/akimfomin/PortBridge/issues/new?template=idea.yml) or propose a change in [seed.json](../portbridge/data/seed.json). Keep existing project slugs and problem IDs. Include the source URL and explain why the repositories or results are related. A search suggestion can guide review.
- To submit reviewed evidence, use the [evidence form](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml), or add the exact revision, author, platform, outcome and primary link to the existing card. For a published PortBridge experiment, add or update its [public research entry](../portbridge/data/research.json). Credit independent verification and upstream adoption separately.
- For a hardware check, take a [Test Lab task](https://akimfomin.github.io/PortBridge/#/lab), verify that the receiving source and revision still apply, and post the measured result in its linked thread. For a new reviewed task, update [task definitions](../portbridge/lab.py). For a new structured report format, also check the [format policies](../portbridge/lab_report_formats.py) and the local issue lists in both workflows above.
- To resume research, start from the [published experiments](../research), find the pinned source, license, workload and expected measurements, and use a separate checkout. Keep original inputs and revisions intact. Report the hardware, output checks, limits and the upstream decision separately. Any team can resume an open experiment under the licenses of the components it uses.
- Before merging, run `python -m unittest discover -s tests -v` and `python -m portbridge export --out dist --repository akimfomin/PortBridge`. To preview the static output, run `python -m http.server --directory dist --bind 127.0.0.1 8766` and open [the preview](http://127.0.0.1:8766). After deployment open the public route you changed.

## Коротко по-русски

Сайт, каталог, поиск, Test Lab и JSON обслуживаются на GitHub. Компьютер основателя для них не нужен. Чтобы предложить исправление или взять направление, напишите в [общее обсуждение](https://github.com/akimfomin/PortBridge/issues/91). Для запуска своей копии достаточно Python и трёх команд в начале этой страницы. По поводу оборудования или результатов теста обращайтесь в ветку конкретной задачи. Решения о публикации, проверке результата и приглашении добровольца принимает человек, когда у него есть время.

Если данные перестали обновляться, откройте [историю публикаций](https://github.com/akimfomin/PortBridge/actions/workflows/pages.yml) и [состояние источников](https://akimfomin.github.io/PortBridge/data/health.json). Паузы между запусками могут занимать несколько часов. После 60 дней без активности GitHub отключает расписание. Сопровождающий может снова включить его на вкладке Actions и вручную запустить **PortBridge static snapshots** из `main`. Ссылки на изменяемые файлы, команды проверки и порядок отката приведены выше.
