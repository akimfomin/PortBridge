# Discovery · правила графических API · 27 ноября 2026, МСК

[Кандидат `d96f0c0`](https://github.com/akimfomin/PortBridge/commit/d96f0c0d9d0f619e8c1077600a6cc91925fe7d67) продолжает [PR #128](https://github.com/akimfomin/PortBridge/pull/128). Сравнение с [предыдущим кандидатом](https://github.com/akimfomin/PortBridge/commit/0ca21bb60d20c35fcfe3344348b8c2ee1cb449b0) использует одни и те же публичные задачи и строгий критерий точной ревизии, файла и диапазона. Базовая выдача и дополнительный локальный поиск оценены отдельно. Объединённое попадание означает, что точный источник был в первой пятёрке хотя бы одной из двух выдач.

| Выборка | Точные ответы до → с дополнительным поиском | Лишние ссылки на отрицательных задачах до → после |
| --- | ---: | ---: |
| Последняя независимая, после заморозки алгоритма | 2/3 → 3/3 | 0 → 0 |
| Предыдущая проверка, использованная при разборе вложений | 1/3 → 3/3 | 2 → 2 |
| Разбор исходных шаблонов, использованный при разработке | 0/5 → 2/5 | 7 → 7 |
| Прежняя проверка охвата | 1/6 → 2/6 | 3 → 3 |

Разметку и выдачу последней выборки сохранили с хешами. В ней есть три задачи с заранее установленным ответом и один отрицательный контроль. Выборка узкая и не заменяет приёмку общего поиска. На более старой широкой диагностической задаче [wgpu #9880](https://github.com/gfx-rs/wgpu/issues/9880) среди нескольких независимых кодов одно правило вытеснило подходящий тест SPIRV-Tools из первой пятёрки; точный отдельный запрос по этому коду остаётся применимым. [Сводка](summary.json) · [Последняя слепая разметка](nested-holdout.json) · [Выдача](nested-results.json) · [Регрессия широкой выдачи](previous-results.json)

## Что позволяет проверить источник

- В [Godot #118930](https://github.com/godotengine/godot/issues/118930) найдено именно то правило, которое разрешает проверить согласованность привязанных наборов дескрипторов с разметкой конвейера. Система восстановила место включения общей нормы. Это закрытая задача, использованная для контроля поиска. [Норма](https://github.com/KhronosGroup/Vulkan-Docs/blob/81b1d516cbf42f04a3c7f781977c499945b5e5dc/chapters/commonvalidity/draw_dispatch_common.adoc#L7) · [Данные](nested-results.json)
- В [SDL #16315](https://github.com/libsdl-org/SDL/issues/16315) найден исходный шаблон обязанности сверить `oldLayout` с текущим состоянием изображения. В самой задаче уже была ссылка на опубликованную спецификацию. Результат проверяет способность PortBridge восстановить исходную норму из кода ошибки. [Правило](https://github.com/KhronosGroup/Vulkan-Docs/blob/81b1d516cbf42f04a3c7f781977c499945b5e5dc/chapters/commonvalidity/image_memory_barrier_common.adoc#L11) · [Место подключения](https://github.com/KhronosGroup/Vulkan-Docs/blob/81b1d516cbf42f04a3c7f781977c499945b5e5dc/chapters/synchronization.adoc#L7715)
- Для [SDL #16780](https://github.com/libsdl-org/SDL/issues/16780) найдено обозначение возможности DirectX, позволяющей выбрать допустимое выравнивание строки. Два найденных источника для Godot и Slang на предыдущей выборке потребовали пройти вложенный include или прочитать официальный документ, у которого в Git выставлен бит исполняемости. Операция чтения сверяет содержимое с Git и не запускает его. [DirectX](https://github.com/microsoft/DirectX-Specs/blob/db16a3da3e1cd7575a4990053ded0622f8b48d97/d3d/VulkanOn12.md#L223-L232) · [Повтор Godot и Slang](blind-results.json)
- Независимый ревьюер проверил обратный контроль версий. `03675` находится в Vulkan 1.3.275. Текущий закреплённый документ содержит `10126` с дополнительным условием. Резолвер сохраняет точную ревизию правила и не объявляет эти идентификаторы эквивалентными. [Историческая норма](https://github.com/KhronosGroup/Vulkan-Docs/blob/9b94c27d65dc7d11e50a7c00581b89f1983d34ff/chapters/commonvalidity/build_acceleration_structure_nonindirect_common.adoc#L7) · [Текущая норма](https://github.com/KhronosGroup/Vulkan-Docs/blob/81b1d516cbf42f04a3c7f781977c499945b5e5dc/chapters/commonvalidity/build_acceleration_structure_nonindirect_common.adoc#L7)

## Сборка и границы

В расширенном индексе 554 файла из шести проектов, 30 633 871 байт входных данных и около 69 МБ SQLite. Первый сбор 552 файлов занял около 71 секунды загрузки и 17 секунд индексирования. Финальная переиндексация уже собранных источников плюс двух новых файлов заняла около 21 секунды. Медиана дополнительного поиска на четырёх последних задачах около 4 мс, с заранее загруженными метаданными. Сборка проверяет ровно те заранее утверждённые каталоги и версии, которые перечислены в коде. Документация Khronos и Microsoft — CC BY 4.0, условия исходников проверяются по каждому выбранному проекту. [Сводка замеров](summary.json) · [Khronos](https://github.com/KhronosGroup/Vulkan-Docs/blob/81b1d516cbf42f04a3c7f781977c499945b5e5dc/LICENSE.adoc) · [Microsoft](https://github.com/microsoft/DirectX-Specs/blob/db16a3da3e1cd7575a4990053ded0622f8b48d97/LICENSE)

Распознаются конкретный `refpage` и локальный include внутри одобренного дерева. Не интерпретируются произвольные переменные в путях и условия сборки спецификации. Результат показывает правило и контекст ссылки, применимую версию и расширение определяет разработчик. Расширенный индекс доступен как отдельная локальная проверка. 324 теста, сборка обычного 93-файлового индекса и проверка экспорта прошли. Сайт остаётся на принятом PR #125. SEARCH-08 сохраняет частичный статус.

## Внешняя польза

RonLogic воспроизвёл наблюдение jstrdev на Windows 11 / RTX 4070 и взял исправление. Это отдельный результат принимающей команды, слияние правки пока открыто. В KytyPS5 исходное задание уточнено по коду. `--depth-readback-only` выполняет CPU-контроль параметров глубины, `--image-overlap-only` запускает Vulkan на GPU. Участника повторно не приглашали. Аппаратный XCL #3037 от pickles976 дал 10/10 на RTX 4060 Laptop с Linux/Wine для загрузочных буферов, а проверка полного управления резидентностью текстур остаётся отдельной. [Xbox2Windows](https://github.com/R0Y00/Xbox2Windows/issues/3052#issuecomment-7226021506) · [KytyPS5](https://github.com/akimfomin/PortBridge/issues/100) · [Отчёт XCL](https://github.com/xcl-dev/xcl/pull/3037#issuecomment-7225653981)

## Воспроизведение

В рабочей копии кандидата:

```sh
python -B -m portbridge.code_search --db .portbridge/base.sqlite3 --refresh --require-complete
python -B -m portbridge.code_research --db .portbridge/rules.sqlite3 --refresh
python -B -m portbridge.code_research --db .portbridge/rules.sqlite3 --query VUID-VkImageMemoryBarrier-oldLayout-01197
python -B -m unittest discover -s tests -v
```

При ограничении GitHub REST можно собрать те же закреплённые файлы через [локальные Git-зеркала и хеши](build.py). Для каждого репозитория создайте bare-зеркало с коротким именем проекта и получите точный SHA из `code_research.scopes()`, например `git fetch --depth=1 --filter=blob:none URL SHA`. Команда `python -B audit/evidence/discovery-contracts/build.py CHECKOUT DB BLOB_CACHE MIRRORS` использует метаданные только этих деревьев и скачивает только допущенные исходники. Для сравнения по URL из ветки аудита:

```sh
python -B audit/evidence/core-mission-iii/replay.py CHECKOUT BASE_DB audit/evidence/discovery-contracts/nested-holdout.json --research-db RULES_DB
```

Скрипт прекращает проверку при изменении хеша описания. При лимите REST используйте `--inputs` с ранее полученными публичными ответами API. В ветку вошли разметка, ссылки, метрики и программы воспроизведения.
