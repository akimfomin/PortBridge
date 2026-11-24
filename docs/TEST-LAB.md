# PortBridge Test Lab

[Choose a check](https://akimfomin.github.io/PortBridge/#/lab) · [Выбрать проверку](https://akimfomin.github.io/PortBridge/?lang=ru#/lab) · [Request a test](TEST-REQUESTS.md) · [Instructions for agents](AGENT-PROMPT.md)

Pick a check for equipment you can use. Each task links the original discussion, the exact source revisions, the expected result, and where to report it. Labels show which checks need a run, which need a revision selected, and which are waiting for a maintainer.

1. Open the source discussion and check that the run is still needed. If you are taking it, say so there to avoid duplicate work.
2. Read the project's setup and inspect the test you plan to run. Use the pinned revision in a separate checkout and synthetic inputs. When a task requires choosing a combined revision, agree on it in the linked discussion before running the test.
3. Report a pass, failure, or skip in the linked discussion and give the tested commit, the hardware and driver or CPU toolchain, and the expected and observed result. A failing control or an explicit skip can save another contributor time.
4. When sharing a result in another project, name what PortBridge contributed and link to it. For example, “[PortBridge](https://github.com/akimfomin/PortBridge) found this earlier test in Reforge. I repeated it at the Continued revision below.” Credit the original author and include the report link.

Volunteers choose a task and execute it locally. If you need another setup, open a test request from the queue. PortBridge can invite a tester based on public hardware reports. The maintainers of each receiving project decide what to adopt. A report or a request for review records delivery. A receiving team's decision, linked run, or merged change can establish acceptance or reuse.

## Для участника

Откройте очередь и выберите AMD, NVIDIA или CPU. Для каждой проверки видны требования, точные версии и куда отправить результат. Можно передать агенту [ссылку на PortBridge](https://github.com/akimfomin/PortBridge) и указать, какой компьютер доступен.

Если нужного оборудования нет, нажмите **Запросить тест** в карточке или создайте свой запрос. [Порядок работы](TEST-REQUESTS.md#по-русски)

Сначала проверьте, нужна ли ещё помощь в исходном обсуждении. Затем повторите тест в отдельной копии проекта и оставьте результат со своим стендом и точной версией. Подробности о том, как передать результат и сохранить авторство, есть в [инструкции для агента](AGENT-PROMPT.md).

## For integrations

Read `data/lab.json` from the public site, call the local `GET /api/v1/lab` endpoint, or use the read-only `portbridge_lab` MCP tool. The equipment filter uses a value supplied by the caller. `checked_at` records when the queue was reviewed. Consult the linked discussions for the latest claims, source revisions, and decisions.

### Show open checks on a partner site

Start with a link to [PortBridge Test Lab](https://akimfomin.github.io/PortBridge/#/lab). This optional snippet shows up to three checks marked `needs_run`, the equipment they need, and the source discussion for each. It reads the [public JSON](https://akimfomin.github.io/PortBridge/data/lab.json) across origins without credentials. The Test Lab link stays visible if the feed is empty or unavailable. Visitors can check the source discussion before taking a task.

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
        const source = discussion(task.source_url)
        if (!source) continue
        const item = document.createElement('li')
        const link = document.createElement('a')
        link.href = source
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
