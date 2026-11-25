# PortBridge Test Lab

[Choose a check](https://akimfomin.github.io/PortBridge/#/lab) · [Выбрать проверку](https://akimfomin.github.io/PortBridge/?lang=ru#/lab) · [Request a test](TEST-REQUESTS.md) · [Instructions for agents](AGENT-PROMPT.md)

Choose your equipment first. The queue starts with tests that need a run. Use **Show all statuses** to see checks waiting for a revision or review, and paused checks. Each task links the original discussion, exact source revisions, expected result, and reporting thread.

Use **Open this test** to share a link to one check. **Copy this task for an agent** includes the pinned revisions, steps and expected result. [Example task](https://akimfomin.github.io/PortBridge/#/lab?task=framelab-12-vulkan-handoff)

After the run, use **Copy result template** to get the link and fields for a report in the source discussion. Fill in what happened before posting. **Find another check** takes you back to the queue and keeps the relevant equipment filter. If your setup has no GPU or build tools, try the Scarlett Commons and Continued check with Git and Python. [CPU check](https://akimfomin.github.io/PortBridge/#/lab?task=scarlett-commons-continued-add-basic)

1. Open the source discussion and check that the run is still needed. If you are taking it, say so there to avoid duplicate work.
2. Read the project's setup and inspect the test you plan to run. Use the pinned revision in a separate checkout and synthetic inputs. When a task requires choosing a combined revision, agree on it in the linked discussion before running the test.
3. Report a pass, failure, or skip in the linked discussion and give the tested commit, the hardware and driver or CPU toolchain, and the expected and observed result. A failing control or an explicit skip can save another contributor time.
4. When sharing a result in another project, name what PortBridge contributed and link to it. For example, “[PortBridge](https://github.com/akimfomin/PortBridge) found this earlier test in Reforge. I repeated it at the Continued revision below.” Credit the original author and include the report link.

Volunteers choose a task and execute it locally. If you need another setup, open a test request from the queue. PortBridge can invite a tester based on public hardware reports. The maintainers of each receiving project decide what to adopt. A report or a request for review records delivery. A receiving team's decision, linked run, or merged change can establish acceptance or reuse.

Selected tasks show reports found in their linked discussion, with the reporter, tested hardware, pinned revision and result. A complete passing report can move a task to **Awaiting team review**. Look under **Show all statuses** to find it. The initial monitored task is FrameLab's AMD Vulkan check. [Reporting discussion](https://github.com/5headsmartbtw/leonida-framelab/issues/15)

Before inviting a tester for a monitored task, PortBridge checks the reporting discussion. An unavailable discussion or a passing result that covers the request puts the invitation on hold.

## Для участника

Откройте очередь и выберите AMD, NVIDIA или CPU. Сначала показаны проверки, которым нужен исполнитель. Включите **Показать все статусы**, чтобы увидеть также результаты на ревью и отложенные проверки.

Нажмите **Открыть эту проверку**, чтобы отправить ссылку на одну задачу. Кнопка **Копировать эту проверку для агента** включает точные версии, шаги и ожидаемый итог. [Пример](https://akimfomin.github.io/PortBridge/?lang=ru#/lab?task=framelab-12-vulkan-handoff)

После прогона кнопка **Копировать шаблон результата** подставит ссылку на карточку и поля отчёта. Заполните их перед публикацией в исходном обсуждении. Кнопка **Выбрать другую проверку** возвращает к очереди с подходящим фильтром. Для прогона без видеокарты и компилятора есть проверка Scarlett Commons и Continued через Git и Python. [Проверка на процессоре](https://akimfomin.github.io/PortBridge/?lang=ru#/lab?task=scarlett-commons-continued-add-basic)

Если нужного оборудования нет, нажмите **Запросить тест** в карточке или создайте свой запрос. [Порядок работы](TEST-REQUESTS.md#по-русски)

Если исходный проект недоступен, карточка сохраняет прежние результаты и ведёт в обсуждение, где можно оставить подтверждённый командой публичный адрес. Приглашения возобновляются после проверки точной версии теста.

Сначала проверьте, нужна ли ещё помощь в исходном обсуждении. Затем повторите тест в отдельной копии проекта и оставьте результат со своим стендом и точной версией. Подробности о том, как передать результат и сохранить авторство, есть в [инструкции для агента](AGENT-PROMPT.md).

В некоторых карточках PortBridge показывает найденные отчёты с автором, оборудованием, точной версией и итогом. Полный успешный прогон может перевести задачу в статус **Ждём ответа команды**. Чтобы найти такую задачу в очереди, включите **Показать все статусы**. Первой отслеживается проверка FrameLab на AMD. [Обсуждение с отчётами](https://github.com/5headsmartbtw/leonida-framelab/issues/15)

Перед приглашением тестировщика PortBridge сверяет обсуждение отслеживаемой задачи. При недоступном обсуждении или уже полученном полном результате приглашение откладывается.

## For integrations

Read `data/lab.json` from the public site, call the local `GET /api/v1/lab` endpoint, or use the read-only `portbridge_lab` MCP tool. Use `task` to filter by a task's exact `id`. To open the same check for a person, link to `#/lab?task=<id>` on the public site. The equipment filter uses a value supplied by the caller. `checked_at` records when the queue was reviewed. Consult the linked discussions for the latest claims, source revisions, and decisions.

Monitored tasks include `report_sync`. Its `state` is `fresh` after a successful check, `stale` when the latest attempt failed and the previous check is still available, `unavailable` when a check fails with no previous check available, or `unchecked` before the first attempt. The object's `checked_at` and `attempted_at` give the last successful and attempted checks in UTC. Either may be null. Each entry in `reports` has the original comment `url`, GitHub `author`, tested `revision`, `hardware`, `outcome` (`pass`, `fail`, or `partial`), and `reported_at`. The `adoption` field still records the receiving team's decision.

Pages checks monitored discussions before exporting the queue. To refresh a local copy, run `python -m portbridge refresh-lab`. To use a specific database, run `python -m portbridge --db path/to/catalog.sqlite3 refresh-lab` and use that same database for the local API, export, or MCP.

### Show open checks on a partner site

Start with a link to [PortBridge Test Lab](https://akimfomin.github.io/PortBridge/#/lab). This optional snippet shows up to three checks marked `needs_run` and the equipment they need. Each link opens the instructions and reporting discussion for that check. It reads the [public JSON](https://akimfomin.github.io/PortBridge/data/lab.json) across origins without credentials. The Test Lab link stays visible if the feed is empty or unavailable.

```html
<section id="portbridge-open-tests" aria-labelledby="portbridge-tests-title">
  <h2 id="portbridge-tests-title">Help run a compatibility check</h2>
  <p><a href="https://akimfomin.github.io/PortBridge/#/lab">Open PortBridge Test Lab</a></p>
  <ul hidden></ul>
  <small hidden></small>
</section>
<script type="module">
  const section = document.getElementById('portbridge-open-tests')
  const list = section.querySelector('ul')
  const reviewed = section.querySelector('small')
  const equipment = new Map([['amd', 'AMD'], ['nvidia', 'NVIDIA'], ['cpu', 'CPU']])

  function discussion(value) {
    try {
      const url = new URL(value)
      return url.origin === 'https://github.com' && !url.username && !url.password &&
        /^\/[^/]+\/[^/]+\/(issues|pull)\/\d+\/?$/.test(url.pathname) ? url.href : null
    } catch {
      return null
    }
  }

  try {
    const reply = await fetch('https://akimfomin.github.io/PortBridge/data/lab.json', {
      credentials: 'omit', referrerPolicy: 'no-referrer'
    })
    if (reply.ok) {
      const lab = await reply.json()
      const tasks = Array.isArray(lab.tasks) ? lab.tasks : []
      for (const task of tasks) {
        if (task?.status !== 'needs_run' || typeof task.title !== 'string' || !task.title.trim()) continue
        if (!/^[a-z0-9-]{1,80}$/.test(task.id) || !discussion(task.source_url)) continue
        const item = document.createElement('li')
        const link = document.createElement('a')
        link.href = 'https://akimfomin.github.io/PortBridge/#/lab?' + new URLSearchParams({task: task.id})
        link.textContent = task.title
        const kinds = (Array.isArray(task.equipment) ? task.equipment : [])
          .map((kind) => equipment.get(kind)).filter(Boolean)
        item.append(link, kinds.length ? ' · ' + kinds.join(', ') : '')
        list.append(item)
        if (list.children.length === 3) break
      }
      list.hidden = list.children.length === 0
      const date = new Date(lab.checked_at)
      if (!list.hidden && typeof lab.checked_at === 'string' && Number.isFinite(date.getTime())) {
        reviewed.textContent = 'Queue reviewed ' + date.toISOString().slice(0, 16).replace('T', ' ') + ' UTC'
        reviewed.hidden = false
      }
    }
  } catch {
    // The Test Lab link remains available.
  }
</script>
```
