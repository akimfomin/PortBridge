# PortBridge

**Общий рабочий штаб для команд совместимости Xbox Series с ПК.**

[Прогресс команд](https://akimfomin.github.io/PortBridge/?lang=ru) · [Найти тест под свой компьютер](https://akimfomin.github.io/PortBridge/?lang=ru#/lab) · [Запросить тест](https://github.com/akimfomin/PortBridge/issues/new?template=test-request.yml) · [Дать задачу агенту](docs/AGENT-PROMPT.md) · [Как помочь проекту](https://github.com/akimfomin/PortBridge/issues/112) · [English](README.md)

После разделения Leonida работа продолжилась в разных репозиториях. Поэтому одна команда может уже исправить ошибку, другая — проверить тот же случай, а третья — начать разбор заново. PortBridge находит эту связь, помогает перенести полезную проверку или правку и сохраняет исходные ссылки, версии и авторство.

> PortBridge is an open coordination tool for independent Xbox Series compatibility projects. Find related work, reuse verified tests, and share results in the repositories where development happens.

## Проверить один pull request

[Передайте ссылку на публичный PR и целевой коммит](https://github.com/akimfomin/PortBridge/issues/98). Эту же ссылку можно дать своему агенту, чтобы запустить проверку самостоятельно. Добровольцы могут [взять одну готовую задачу](https://github.com/akimfomin/PortBridge/issues/98#issuecomment-7206391931) и оставить краткий результат.

Сопровождающий может включить [проверку GitHub](docs/GITHUB-ACTION.md). Результат появится прямо в PR с источниками или причиной пустой выдачи. В пилоте M5–M6 можно предложить один конкретный технический вопрос. [Подключение агента](docs/MCP.md) · [Партнёрская лента](API.md) · [Проверенные результаты и ограничения](https://github.com/akimfomin/PortBridge/blob/audit/review/audit/LATEST.md)

В пилоте Continued проверила, что новый процесс действительно использует записанный кэш. Два участника получили положительный результат на GTX 1050 Ti и RTX 5070 с помощью диагностики самой команды. [Предложение PortBridge](https://github.com/ubiquitarianism/leonida/pull/2392#issuecomment-7202363138) · [Проверка пустого и заполненного журналов](https://github.com/ubiquitarianism/leonida/pull/2392#pullrequestreview-6080300502)

[Письмо основателя](https://akimfomin.github.io/PortBridge/letter.ru.html) · [Ответить или взять часть проекта](https://github.com/akimfomin/PortBridge/issues/91) · [История и инженерные итоги](docs/FINAL-AUDIT.ru.md) · [Как запустить и поддерживать проект](docs/PASSIVE-MAINTENANCE.md)

## Discovery

Ищите работы других проектов по ошибке, инструкции GPU, функции API или ссылке на известный Issue или PR. У находки указаны ревизия, ограничения, лицензия и предлагаемый тест. [Как попробовать](docs/PORTBRIDGE-M2.md)

## Что можно сделать сейчас

| Ваша задача | Куда идти |
| --- | --- |
| Узнать, что изменилось и где можно помочь | На [главной](https://akimfomin.github.io/PortBridge/?lang=ru) видны события за семь дней, прогресс по командам и проверки, которые можно повторить в другой команде. |
| Перед правкой узнать, что уже пробовали | [Поиск по ошибке, термину или PR](https://akimfomin.github.io/PortBridge/?lang=ru#/problems) |
| Передать тест, исправление или отрицательный результат | [Форма результата](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml) |
| Подхватить работу или проверить чужой вывод | [Журнал портирования](docs/PORTING-WORK.md) |
| Найти проекты по направлению | [Отслеживаемые репозитории](docs/PROJECTS.md) |
| Взять совместную проверку | Сверьте [текущие задачи команд](docs/WORK-PRIORITIES.md#по-русски) и выберите подходящий прогон в [Test Lab](https://akimfomin.github.io/PortBridge/?lang=ru#/lab). |
| Продолжить работу после потери доступа к репозиторию | Сохранить авторство и передать воспроизводимый результат в действующий проект. [Пилот PortBridge](docs/CONTINUITY.md#по-русски) |
| Запросить проверку на другом железе | Откройте запрос из Test Lab. Доброволец может откликнуться в самом запросе. При необходимости сопровождающий вручную проверяет и отправляет приглашение. [Как это работает](docs/TEST-REQUESTS.md#по-русски) |
| Попробовать PortBridge в своём проекте | Вставьте полную ссылку на PR в [каталог](https://akimfomin.github.io/PortBridge/?lang=ru#/problems) или запустите [GitHub Action для одного PR](docs/GITHUB-ACTION.md). [Пример сводки](https://github.com/akimfomin/PortBridge/actions/runs/45420038315) |
| Подключить помощника к поиску | [Codex и Claude Code через MCP](docs/MCP.md) |
| Попросить агента взять задачу и довести её до результата | [Готовый запрос и порядок работы](docs/AGENT-PROMPT.md) |
| Попробовать совместную проверку с другой командой | [Один тест на два проекта](docs/PILOT.md) |
| Предложить проект, связь или исправление поиска | [Форма обратной связи](https://github.com/akimfomin/PortBridge/issues/new?template=idea.yml) |

## Попробуйте на одной задаче

Вставьте ссылку на PR в [поиск по источникам GitHub](https://akimfomin.github.io/PortBridge/?lang=ru#/sources) и откройте связанные работы. В списке видны полное число найденных записей и отметки о проверке связи. [Проверенные результаты](https://akimfomin.github.io/PortBridge/?lang=ru#/problems) · [Где можно помочь](https://akimfomin.github.io/PortBridge/?lang=ru#/partial)

```powershell
python -m portbridge.preflight --url https://github.com/LooperSalty/AnyXboxX/pull/133 --q "v_fmac_f32 rounding" --global
```

Этот запрос ведёт к прежним измерениям RDNA2 и к новой правке округления на CPU. Для подключения агента откройте [руководство по MCP](docs/MCP.md). Для участия выберите одну проверку на своём оборудовании в [Test Lab](https://akimfomin.github.io/PortBridge/?lang=ru#/lab).

## Исследования PortBridge

- **Исправление маски переноса Wave32.** DarkPanda69 воспроизвёл ошибку XCL и подтвердил исправление PortBridge на RX 9070 XT и RTX 3060. Правка ожидает рассмотрения в XCL. [Независимая проверка](https://github.com/xcl-dev/xcl/issues/2584#issuecomment-7178879816) · [Исходный код](https://github.com/akimfomin/xcl/commit/d3e7725f9f48c39c18e7b6e011ec76423edb0004)
- **Эксперимент с проекцией пиксельных масок.** На RTX 4070 Ti SUPER первый проверенный кадр raylib появился на 99–120 мс раньше. В двух ракурсах время отрисовки в Vulkan сократилось на 19%. В фильтре Microsoft результаты разошлись. Отдельная опция сохраняет исходные групповые операции и выключена по умолчанию. Прежний вариант Lane-local Masks отозван после ошибки Wave32. [Измерения и код](https://github.com/akimfomin/PortBridge/blob/9c2616998e176806565ee1a0076dc4efb7ae4dc1/research/pipeline-readiness/structural-suite/night/ssa-mask-projection/README.md)
- [Выборочный возврат данных GPU](research/readback-epochs) возвращает только изменившиеся диапазоны и измеряет полный цикл на Vulkan. [Исследование и актуальные отчёты команд](docs/READBACK-2026-11-25.md)
- [Переносимая генерация уровней текстуры в Vulkan](research/mipmap-contract) показывает зависимость от нумерации потоков, исправление с явными условиями и проверку вывода на физической RTX.
- [Разбиение больших ветвлений шейдера](research/adaptive-switch-dispatch) сравнивает плоское ветвление, дерево с фиксированными группами и таблицу для совместимых входов.
- [Устранение повторяющихся вычислений](research/shader-tail-factoring) сокращает код до компиляции. [Проверка открытых шейдеров](research/shader-tail-factoring/CORPUS.md) показывает границы применения.
- [Оптимизация обмена между потоками шейдера](research/subgroup-validator) убирает лишние операции при доказанной полной подгруппе. Есть проверка на физической RTX и контроль неполной группы.
- [Повторное использование временной памяти между очередями](research/transient-slot-cover) подбирает слоты по уже действующим зависимостям.
- [Buffer Transfer Planner на RTX 4070 Ti SUPER](research/transfer-planner/physical) содержит замеры через D3D12 и Vulkan и объясняет, почему планировщик остался эталоном для сравнений.

[Текущий отчёт об измерениях](docs/EVIDENCE-FIRST-2026-11-25.md) · [Предыдущий отчёт](docs/RD-2026-11-25.md) · [Аудит экосистемы](docs/ECOSYSTEM-AUDIT-2026-11-25.md)

## Работа идёт

**VIctory, XCL и Continued.** Сопоставили реализацию чтения памяти шейдеров, тесты XCL и исправление гонки в Continued. По ним добавили два теста в локальную копию VIctory. Оба прошли на RTX 4070 Ti SUPER и WARP, а контроль с прежним переводчиком показал отказ в обоих случаях. [Результат и границы проверки](docs/PORTING-WORK.md#чтение-памяти-шейдеров-в-victory)

**XCL и VIctory.** Сопоставили работу по Wave64 с замерами RDNA2. После исправления XCL проверили, что его эталон совпадает с четырьмя опубликованными измерениями, и передали вход для отдельного теста смещения. [Проверка и предложение в XCL](https://github.com/ivall/xcl/pull/925#issuecomment-7128418828)

**Reforge и Continued.** PortBridge передал правку D16 из Reforge в Continued. Независимый участник подтвердил 15 из 15 тестов на macOS, другой одобрил эту версию. [Независимый прогон](https://github.com/ubiquitarianism/leonida/pull/701#issuecomment-7131731339) · [Одобрение](https://github.com/ubiquitarianism/leonida/pull/701#pullrequestreview-6039203797)

## Как проходит задача

1. **Найти.** Введите точный симптом или номер PR, откройте исходную работу.
2. **Сверить.** Выберите один проверяемый случай. Сохраните версию, стенд и результат.
3. **Передать.** Сошлитесь на одну запись в нужном PR или issue и предложите конкретное действие.
4. **Довести до результата.** Добавьте ответ, ссылку на принятую правку или причину, по которой перенос не подошёл.

Участник продолжает работу в своём репозитории. Сопровождающие выбирают, что применять. В журнале видно, что уже проверено и какой шаг остался.

## Запуск на Windows

Нужен Python 3.10 или новее. Чтобы открыть каталог с локальными данными, из папки проекта выполните `python -m portbridge serve` и перейдите на [локальный адрес](http://127.0.0.1:8765/).

[Настройка и обслуживание](docs/MAINTAINERS.md) · [Как внести вклад](CONTRIBUTING.md) · [API](API.md) · [Лицензия MIT](LICENSE)

В режиме `--office` доступен общий план проверок, обсуждения и поиск новых проектов. [Настройка рабочего штаба](docs/OFFICE.md)

## Одна задача с агентом

На сайте нажмите «Начать», вставьте ссылку на задачу или PR и откройте связанную проверку Lab. Для работы в своём репозитории доступны MCP, GitHub Action для чтения и виджет для партнёров. [Инструкция пилота](docs/PORTBRIDGE-M5-START.md)

Если PortBridge пригодился, можно поставить звезду на GitHub. [Репозиторий](https://github.com/akimfomin/PortBridge)
