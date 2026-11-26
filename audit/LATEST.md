# PortBridge · Адресная кампания 27 ноября 2026

Срез ответов и публикаций — 02:49 МСК. В GitHub проверены все **27** сообщений с инженерным результатом для **27** разных получателей. Волны — **10, 15 и 2**. Для 22 это первое найденное опубликованное предложение PortBridge, для 5 — продолжение прежнего контакта. Разбор отчёта BrokeAsh по прежнему запросу и публикации для сообществ учтены отдельно.

## Отбор и охват

Просмотрены 233 недавно обновлённые открытые темы в AnyXboxX, VIctory, VIctory-7900XTX, XCL, Continued и KLBF Lab. Это 120 PR и 113 Issues. В AnyXboxX было 13 открытых Issues, в остальных выборка составила по 20 PR и 20 Issues. В списке 152 разных автора и 176 разных аккаунтов с учётом участников 62 прочитанных технических обсуждений. Повторные PR и ответы одного человека учитывались по одному логину. Группу получения определяли по доступному публичному журналу взаимодействий.

До ориентира 50 не дошли. Для 27 адресатов был готов отдельный проверяемый результат или точный контроль для открытого вопроса. В остальных рассмотренных случаях для публикации мешали уже готовый ответ, смена базы, отсутствие сопоставимого стенда либо недостаток доказательств. Выборка открытых тем сама по себе не доказывает, что полезных адресатов больше нет.

| Что измерили | Подтверждение |
| --- | --- |
| Ответ на результат кампании | **3 участника.** mauroalvare сослался на найденный конфликт. UwUCammie добавил тот же контроль в AMD-ветку. CwWwWwW подтвердил, что сбой проверки пришёл из main. [AnyXboxX](https://github.com/LooperSalty/AnyXboxX/pull/454#issuecomment-7205307619) · [AMD-ветка](https://github.com/jtrudeau1530/VIctory-7900XTX/pull/27#issuecomment-7205708084) · [VIctory](https://github.com/fxceless/victory-fork/pull/1333#issuecomment-7205834214) |
| Ответы на прежние предложения | **2 участника.** Lewandox добавил проверку двух перекрывающихся чтений. BrokeAsh сам прогнал оба контроля и передал отчёты в Test Lab. [Lewandox](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7205033607) · [Холодный контроль BrokeAsh](https://github.com/akimfomin/PortBridge/issues/95#issuecomment-7205367219) · [Прогретый контроль](https://github.com/akimfomin/PortBridge/issues/95#issuecomment-7205488418) |
| Самостоятельные заявки и запуски | **0 новых заявок**, **1 участник с двумя аппаратными отчётами в существующей заявке Test Lab**. UwUCammie независимо добавил и прогнал регрессию под Wine, mauroalvare самостоятельно сверил 41 ветку. Отдельный запуск CLI или Action PortBridge этими двумя участниками не подтверждён. [Разбор Test Lab](https://github.com/akimfomin/PortBridge/issues/95#issuecomment-7205850459) · [Wine](https://github.com/jtrudeau1530/VIctory-7900XTX/pull/27#issuecomment-7205708084) · [Перепроверка веток](https://github.com/LooperSalty/AnyXboxX/pull/454#issuecomment-7205307619) |
| Повторная самостоятельная задача и рекомендация коллеге | **0 и 0**. Прогретый замер BrokeAsh завершал тот же вопрос. |
| Передача между командами | **2 документированных передачи.** Проверка конкурентного кэша VIctory дошла до AMD/Linux-форка и добавлена в его регрессию. Проверка однокадрового ввода из KLBF направлена в Continued с тестом его кода. Ответ Continued по этому переносу пока не подтверждён. [VIctory](https://github.com/fxceless/victory-fork/pull/1393#issuecomment-7205145118) · [AMD/Linux](https://github.com/jtrudeau1530/VIctory-7900XTX/pull/27#issuecomment-7205708084) · [KLBF](https://github.com/PastiiJay/klbf-lab/pull/78#issuecomment-7205556873) · [Continued](https://github.com/ubiquitarianism/leonida/issues/1900#issuecomment-7205804917) |
| Решения в командах | У UwUCammie новая регрессия в голове PR. mauroalvare предложил проверять переносы до следующей замены базы. AnyXboxX закрыл #436 после замены базы и без замера производительности на ней. Слияний, вызванных этой кампанией, не подтверждено. [Регрессия](https://github.com/jtrudeau1530/VIctory-7900XTX/commit/4455a70d6065b2dacdd8aafdb05121360fcd2756) · [Переносы AnyXboxX](https://github.com/LooperSalty/AnyXboxX/pull/454#issuecomment-7205307619) · [Закрытие #436](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7205296487) |
| Публичные площадки и звёзды | Пример опубликован в GitHub Issues PortBridge и в действующем обсуждении Toolkit у PortWatch VI. Число читателей неизвестно. Звёзды **2 → 2**, изменение **0**. [Вход для нового PR](https://github.com/akimfomin/PortBridge/issues/98#issuecomment-7205337398) · [PortWatch VI](https://github.com/4lwayz/portwatch-vi/issues/55#issuecomment-7205762419) |

## Два случая

**Помогло · VIctory.** В исходном коде #1393 создание объекта могло вернуть пустой результат после того, как другой поток уже опубликовал объект. В управляемом тесте исходник упал, перестановка одной проверки исправила результат. UwUCammie привязал ту же проверку к своему переносу на AMD/Linux и подтвердил её под Wine 11.22. Так следующий перенос может проверять конкретный порядок двух потоков. Это результат теста корректности. Игровая производительность отдельно не измерялась. [Исходный тест и правка](https://github.com/fxceless/victory-fork/pull/1393#issuecomment-7205145118) · [Независимое применение](https://github.com/jtrudeau1530/VIctory-7900XTX/pull/27#issuecomment-7205708084)

**Не дошло до переноса · AnyXboxX.** Lewandox добавил недостающую проверку перекрывающихся чтений, и PortBridge получил 4/4 на физической RTX 4070 Ti SUPER. После #454 файл был переписан, а результатов производительности для новой базы не было. LooperSalty закрыл #436. Повторять тест на прежней ветке смысла нет. Для возобновления нужны актуальная реализация и замер на выбранной базе. [Аппаратная проверка](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7205213561) · [Решение сопровождающего](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7205296487)

## Дополнительные вопросы

- BrokeAsh сам провёл два 300-секундных контроля BM-v1 на Ryzen 5 9600X и RX 9070 XT. Для KLBF 8,84 → 9,03 среднего FPS после прогрева, для его форка 16,08 FPS. Прогрев почти вдвое сократил худший кадр KLBF, но оставил основную разницу в средней частоте кадров. Политики пропуска конвейеров различались, вклад отдельной оптимизации открыт. Проверка обоих JSON восстановила один повреждённый символ по исходнику, после чего совпали контрольные номера и прошла проверка KLBF. [Исходные JSON, условия и команда](evidence/klbf-bm-v1-pilot.md#independent-same-host-controls)
- KLBF #73 и #86 по воде. Пара с одним маршрутом и ревизией остаётся открыта. Доступные прогоны различались режимом Series S/X, масштабированием и кодом. Новая ветка beta-amd требует отдельного прогона RDNA2. [Контроль #73](https://github.com/PastiiJay/klbf-lab/issues/73#issuecomment-7202491449) · [Сверка #86](https://github.com/PastiiJay/klbf-lab/issues/86#issuecomment-7205205908) · [Новая ветка](https://github.com/PastiiJay/klbf-lab/issues/86#issuecomment-7205221785)
- NVIDIA 8 ГБ. Два отчёта для RTX 3070 различались сценой, ревизией и настройкой BAR. Для VIctory #1083 указан доступный переключатель для проверки. Перенос #1316 в ветку #389 конфликтует в четырёх файлах. Парного игрового результата нет. [VIctory #1083](https://github.com/fxceless/victory-fork/issues/1083#issuecomment-7205249537) · [VIctory-7900XTX #389](https://github.com/avatarmanz/VIctory-7900XTX/issues/389#issuecomment-7205556631)

## Фактические доставки

| Волна | Адресат | Контакт | Сообщение | Переданный результат |
| --- | --- | --- | --- | --- |
| 1 | LooperSalty | Прежний | [AnyXboxX #454](https://github.com/LooperSalty/AnyXboxX/pull/454#issuecomment-7205087487) | На предложенной базе Vice-Tay найдены конфликты #433 и #436. |
| 1 | n-romanovich | Первый | [victory-fork #1393](https://github.com/fxceless/victory-fork/pull/1393#issuecomment-7205145118) | Воспроизведение ошибки двух потоков и проверка исправления. |
| 1 | FunWithFlagsDev | Первый | [AnyXboxX #449](https://github.com/LooperSalty/AnyXboxX/issues/449#issuecomment-7205184273) | Проверка разрыва 85%/88% на новой базе и пороговый тест. |
| 1 | real-alponzo | Первый | [xcl #2910](https://github.com/xcl-dev/xcl/pull/2910#issuecomment-7205205815) | Лишнее чтение драйверного кэша при отключённом диске. |
| 1 | narimantos | Первый | [klbf-lab #86](https://github.com/PastiiJay/klbf-lab/issues/86#issuecomment-7205205908) | Два замера воды на разных сборках и способ сравнить в одной. |
| 1 | Lewandox | Прежний | [AnyXboxX #436](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7205213561) | Четыре теста RTX, включая предложенную проверку двух чтений. |
| 1 | CuteBooty | Первый | [victory-fork #1083](https://github.com/fxceless/victory-fork/issues/1083#issuecomment-7205249537) | Отдельный уже имеющийся переключатель для 8 ГБ и проверка без переноса. |
| 1 | fiestorra | Первый | [leonida #1937](https://github.com/ubiquitarianism/leonida/pull/1937#issuecomment-7205310358) | При совместном слиянии #1737 блокирует вызов до новой логики. |
| 1 | CryingLaughing | Первый | [xcl #2908](https://github.com/xcl-dev/xcl/issues/2908#issuecomment-7205310457) | Нативный CopyTiles прошёл на четырёх смещениях, включая 69 632 байта. |
| 1 | SalmanBarkat | Первый | [victory-fork #1385](https://github.com/fxceless/victory-fork/pull/1385#issuecomment-7205337164) | Три проверки WARP с контролем против тихого пропуска. |
| 2 | Alpacher | Первый | [victory-fork #1396](https://github.com/fxceless/victory-fork/pull/1396#issuecomment-7205389775) | Семь конфликтов со свежим main и первый тест холодной компиляции. |
| 2 | mauroalvare | Прежний | [AnyXboxX #438](https://github.com/LooperSalty/AnyXboxX/pull/438#issuecomment-7205406430) | #434 и #438 чисто сочетаются с новой базой и друг с другом. |
| 2 | Luke-Ervin | Первый | [AnyXboxX #402](https://github.com/LooperSalty/AnyXboxX/pull/402#issuecomment-7205467131) | Три теста в обеих сборках и красный контроль старой арифметики. |
| 2 | MKmajster | Первый | [VIctory-7900XTX #389](https://github.com/avatarmanz/VIctory-7900XTX/issues/389#issuecomment-7205556631) | Сверка замеров RTX 3070 и четырёх конфликтов переноса #1316. |
| 2 | Jesper-Andersson | Первый | [VIctory-7900XTX #392](https://github.com/avatarmanz/VIctory-7900XTX/issues/392#issuecomment-7205556763) | Подобран перенос защиты динамических слотов с проверкой двух куч. |
| 2 | Vladimir-Human | Первый | [klbf-lab #78](https://github.com/PastiiJay/klbf-lab/pull/78#issuecomment-7205556873) | Воспроизведена потеря однокадрового ввода при пропущенном опросе. |
| 2 | UwUCammie | Первый | [VIctory-7900XTX #27](https://github.com/jtrudeau1530/VIctory-7900XTX/pull/27#issuecomment-7205556913) | Тот же тест двух потоков прошёл в AMD-переносе. |
| 2 | ending3729 | Первый | [VIctory-7900XTX #347](https://github.com/avatarmanz/VIctory-7900XTX/pull/347#issuecomment-7205598633) | 100 свежих процессов без сбоя на 31 тесте. |
| 2 | HenriqueSBueno | Первый | [VIctory-7900XTX #237](https://github.com/avatarmanz/VIctory-7900XTX/pull/237#issuecomment-7205598787) | Два конфликта и отсутствие защиты от смены владельца слотов. |
| 2 | LofisMusk | Первый | [VIctory-7900XTX #386](https://github.com/avatarmanz/VIctory-7900XTX/pull/386#issuecomment-7205598843) | #166 чисто применяется. Предложен отдельный контроль ожидания compute. |
| 2 | ecox982745 | Прежний | [leonida #2352](https://github.com/ubiquitarianism/leonida/pull/2352#issuecomment-7205599124) | Чистый перенос на main с уже включённым #2404. Сборка упёрлась в SDK. |
| 2 | ErRusso | Первый | [victory-fork #20](https://github.com/fxceless/victory-fork/pull/20#issuecomment-7205662848) | Оба варианта шейдера компилируются. Нужно сохранить выбор при разрешении конфликта. |
| 2 | CwWwWwW | Первый | [victory-fork #1333](https://github.com/fxceless/victory-fork/pull/1333#issuecomment-7205727397) | Пять тестов переноса памяти прошли на объединённой ревизии. |
| 2 | Ahmet-Dedeler | Прежний | [VIctory-7900XTX #390](https://github.com/avatarmanz/VIctory-7900XTX/pull/390#issuecomment-7205762082) | Синтетика показала, что до включения режима контроль пропускает изменения между полосами. |
| 2 | kalijerry | Первый | [VIctory-7900XTX #97](https://github.com/avatarmanz/VIctory-7900XTX/pull/97#issuecomment-7205775800) | Скрытая ошибка сборки после слияния исправлена локально. Четыре теста прошли. |
| 3 | jean-melikian | Первый | [AnyXboxX #413](https://github.com/LooperSalty/AnyXboxX/issues/413#issuecomment-7205791034) | На новой базе прежний переключатель больше не действует. Прошла проверка срока жизни чтения. |
| 3 | BubsMcgee | Первый | [leonida #1900](https://github.com/ubiquitarianism/leonida/issues/1900#issuecomment-7205804917) | Тест точного кода показал 0 попаданий для 0,3 с и 1 для 2,5 с. Передан контроль из KLBF. |

Полный набор PortBridge на Windows — **291 PASS, 0 FAIL, 0 SKIP**. Результаты по внешним проектам относятся к указанным ревизиям и средам. Тесты и исходник аппаратной пробы сохранены рядом. Отслеживание публикаций по расписанию продолжается по прежнему плану, до контрольной недели 4 декабря.

```sh
python -B -m unittest discover -s tests -v
python -B -m portbridge.merge_check https://github.com/LooperSalty/AnyXboxX/pull/433 5ac6926e59043c06317edbe012aee7e51e738cf7
```

[Доказательства и воспроизведение](evidence/campaign-probes.md) · [Журнал взаимодействий](../docs/COMMUNITY-COORDINATION.md) · [Расписание публикаций](https://github.com/akimfomin/PortBridge/actions/workflows/pages.yml?query=branch%3Amain+event%3Aschedule)

## Предыдущая итерация · Самостоятельная проверка совместимости PR

## Итог 27 ноября 2026

**AnyXboxX.** В main PortBridge добавлена проверка публичного PR против указанного коммита. Для #433 она нашла один конфликт в `draw.rs` и дала точную ссылку на изменённый тест. На той же базе #436 слился чисто, а #429 не изменил дерево. Для #433 смысл теста после слияния определён вручную: новый список должен видеть текущие константы, а прежние дескрипторы должны оставаться доступны до завершения работы. [Код #96](https://github.com/akimfomin/PortBridge/pull/96) · [Публичный прогон GitHub](https://github.com/akimfomin/PortBridge/actions/runs/45906366457#summary-140203952342) · [Вход для автора](https://github.com/akimfomin/PortBridge/issues/98)

Первый облачный запуск не получил метаданные через GitHub API. В #97 сравнение переведено на публичный Git. Проверка повторного чтения PR защищает от смены головы между запросами. После исправления облачный результат совпал с локальным. На Windows полный набор для main дал 288 проходов, а для ветки аудита с контролями захватов и автономности — 291. Сохранены [первый запуск](https://github.com/akimfomin/PortBridge/actions/runs/45905990241), [исправление](https://github.com/akimfomin/PortBridge/pull/97) и [точный main](https://github.com/akimfomin/PortBridge/commit/84311ecee759ae3031a4616df9d736699929701d).

**Физическая проверка #436.** На RTX 4070 Ti SUPER три теста проходят на точном PR. В синтетическом тесте 128 чтений используют два выделения буферов. Очередной тест должен проверить два чтения до завершения первого GPU-задания с различимыми данными. Для него есть подходящий контроль свежести данных из VIctory #1376. Измерения отданы Lewandox. [Команда, ревизия и границы замера](evidence/anyxboxx-409-after-revert.md#independent-gpu-check-for-436) · [Ответ в PR](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7204915059)

**VIctory.** Собрана и физически проверена ревизия #1316 `c5b08986a571f4befb6806ca94b8ab7ce8c58dba` с обоими положениями флага. На ранее проверенной `nvidia-wip` флаг отсутствует. Синтетический стенд показал 10,977 → 0,172 мс подготовки в сценарии с высоким повтором и почти нулевой выигрыш подготовки при уникальных источниках. Контроль шести 90-секундных захватов проходит. Анализатор отклоняет короткую запись, разные процессы и цепочки кадров, разрыв времён и отсутствие ON-счётчиков. Игровой замер и проверка картинки остаются открыты. Инструкции обновлены в двух существующих сообщениях. [Воспроизведение](evidence/victory-cbv-ab.md) · [LeonardoS11 и Zignixx](https://github.com/fxceless/victory-fork/issues/1379#issuecomment-7204512623) · [ByFxbian](https://github.com/fxceless/victory-fork/pull/1316#issuecomment-7204512012)

**Воронка.** Два новых предметных предложения опубликованы для двух уникальных участников AnyXboxX. Каждому оставлен готовый результат в его рабочем обсуждении. Чтение и применение не подтверждены. Новых ответов, самостоятельных запусков внешним участником, повторных задач и рекомендаций коллегам к моменту проверки нет. В VIctory обновлены два прежних сообщения, без нового приглашения. BrokeAsh ответил на прежнее приглашение «Yeah sec». Данных для разбора пока нет. Публичная площадка одна, GitHub Issues PortBridge. Статистика читателей не предоставлена. [mauroalvare](https://github.com/LooperSalty/AnyXboxX/pull/409#issuecomment-7204915315) · [Lewandox](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7204915059) · [BrokeAsh](https://github.com/akimfomin/PortBridge/issues/95#issuecomment-7204524358) · [Публичный пример](https://github.com/akimfomin/PortBridge/issues/98)

**Отбор адресатов.** В XCL #2898 автор itsSio уже приложил сопоставимые OFF и ON на RTX 5080 и тест сжатия размещения по пулам. В Continued #2405 проверка относится к конкретным требованиям типов памяти Vulkan на Intel Arc. Наш нативный D3D12 стенд её не воспроизводит. В VIctory #1384 n-romanovich уже сделал упрощение проверки списков из запроса #1379 и приложил тесты. Общий случай жизненного цикла чтений из VIctory #1376 использован в отчёте для AnyXboxX #436. [XCL](https://github.com/xcl-dev/xcl/pull/2898) · [Continued](https://github.com/ubiquitarianism/leonida/pull/2405) · [VIctory](https://github.com/fxceless/victory-fork/pull/1384)

**Автономность.** GitHub Pages собрал, опубликовал и проверил main после #96 и #97. На живом сайте согласованы 14 разделов, партнёрская лента и MCP. Повторный опрос партнёрской ленты вернул ноль изменений. В поколении `2026-11-26T22:44:44Z` опубликованы 28 274 наблюдения, статус охвата источников `partial`. Контрольная сумма `data/site.json` — `67a55b4c8fa98756451de518bcce5bea9381f327f8618e679c00cf66089abace`. По публичной истории GitHub после начала наблюдения в 00:07 МСК ещё не было запуска по расписанию. Публикации после push в недельный счёт не входят. [Выкладка после #97](https://github.com/akimfomin/PortBridge/actions/runs/45906329658) · [Плановые запуски](https://github.com/akimfomin/PortBridge/actions/workflows/pages.yml?query=branch%3Amain+event%3Aschedule)

```sh
python -B -m unittest discover -s tests -p 'test_cbv_ab.py' -v
python -B -m unittest discover -s tests -p 'test_merge_check.py' -v
python -B -m portbridge.merge_check https://github.com/LooperSalty/AnyXboxX/pull/433 15024d54e690743604a67287f0e3f3f30adbaba8
```

## Предыдущая итерация · VIctory NVIDIA и база AnyXboxX

**VIctory.** Самая близкая к игре среди проверенных здесь веток — `nvidia-wip` Zignixx. В его серии замеров на RTX 5080 пролог Series S ускорился с 77,7 до примерно 39 мс на кадр. Это измерение команды на конкретной сцене. Независимый сравнительный прогон LeonardoS11 на RTX 3080 Ti дал 64–73 мс на ветке против 99–116 мс на его сборке. В текущей ревизии `90fe3144a4c5fe8ca4e6ce1b5f0e42f4fb28696b` Zignixx добавил ранний отказ для завышенного масштаба Series S. Отдельный прогон с повышенным внутренним разрешением нельзя выводить из строки с unset scale. [RTX 5080](https://github.com/fxceless/victory-fork/issues/1379) · [Независимый прогон](https://github.com/fxceless/victory-fork/issues/1379#issuecomment-7203857811) · [Изменение масштабирования](https://github.com/fxceless/victory-fork/issues/1379#issuecomment-7204175309)

PortBridge подтвердил, что в этой ревизии нет `VICTORY_CBV_SNAPSHOT_REUSE`. При пробном применении изменения #1316 конфликтуют четыре файла. У ByFxbian есть синтетические измерения, а парных измерений в нужной игровой сцене пока нет. На проверенном локальном стенде выполнена проверка программы для сведения шести чередующихся прогонов и отказа при отсутствии счётчиков. Игровой стенд для такой сцены не подтверждён. Один добровольный запрос получил LeonardoS11 в #1379. На собственном коммите #1316 можно проверить гипотезу без переноса, а вывод о `nvidia-wip` потребует сборки с этой функцией. Результат сверки передан Zignixx и ByFxbian в их обсуждениях. [Предложение в #1379](https://github.com/fxceless/victory-fork/issues/1379#issuecomment-7204512623) · [Сообщение в #1316](https://github.com/fxceless/victory-fork/pull/1316#issuecomment-7204512012) · [Условия и команды](evidence/victory-cbv-ab.md)

**AnyXboxX.** После #452 `main` на `15024d54e690743604a67287f0e3f3f30adbaba8` восстановил то же дерево Neptune, что было до #409. Следующую базу с точной публичной ревизией сопровождающие ещё не указали. Для текущего дерева #416 и #429 уже присутствуют. #433, #447 и #448 имеют конфликты. Для #433 удалось показать, что обычный сброс очищает таблицы, а путь разрезания командного списка сохраняет их. #436 чисто применяется и требует проверки повторного чтения с GPU. Первая сверка опубликована в ответ на вопрос mauroalvare. Все 284 теста PortBridge прошли. [Сообщение в #409](https://github.com/LooperSalty/AnyXboxX/pull/409#issuecomment-7204512277) · [Ревизии и проверки поведения](evidence/anyxboxx-409-after-revert.md)

При контрольном чтении в 01:16 МСК новых ответов в XCL #2889 и PortBridge #95 не было. Недельная сверка остаётся назначенной на 4 декабря, 00:15 МСК. На текущем этапе GitHub ещё не зарегистрировал плановый запуск новой версии. [XCL](https://github.com/xcl-dev/xcl/pull/2889#issuecomment-7204227097) · [KLBF](https://github.com/akimfomin/PortBridge/issues/95) · [Расписание](https://github.com/akimfomin/PortBridge/actions/workflows/pages.yml?query=branch%3Amain+event%3Aschedule)

## PortBridge · проверка для XCL #2889

27 ноября на RTX 4070 Ti SUPER проверили тест Wine для форматов сжатых текстур и все четыре входа PR XCL #2889 через стандартный Direct3D 12. В трёх случаях драйвер помечает запись как упакованную, а проверка XCL принимает эту отметку за номер тайла. Для всех трёх измерен действительный диапазон упакованных тайлов. Отдельный контроль подтвердил, что BC5 отличается от BC1/BC4. Все семь проверок нативного API прошли. [Тест, вывод и версии](evidence/xcl-2889-tiling.md)

Один отчёт опубликован в PR в 00:57:48 МСК. За 26 секунд до него DarkPanda69 отдельно сообщил, что полный тест XCL падает на первом случае на RTX 3060 и проходит на RX 9070 XT. Наш отчёт добавил два остальных упакованных случая, действительный диапазон и различие BC5. Автору доступны готовые входы и показания для решения, как проверять упакованные текстуры. Ответ и применение автором ещё не подтверждены. [Независимый прогон](https://github.com/xcl-dev/xcl/pull/2889#issuecomment-7204220148) · [Наш отчёт в XCL](https://github.com/xcl-dev/xcl/pull/2889#issuecomment-7204227097)

Публичный поиск PortBridge пока не содержал свежего PR. Источник Wine найден вручную. Сверка того, подходит ли контроль, аппаратный прогон и передачу в PR также выполнили вручную. Пилот BrokeAsh открыт, при последнем чтении в нём только исходное приглашение. Плановых поставок после релиза при проверке в 00:58 МСК было 0. Сверка недели назначена на 4 декабря в 00:15 МСК. [Пилот KLBF](https://github.com/akimfomin/PortBridge/issues/95) · [Плановые запуски](https://github.com/akimfomin/PortBridge/actions/workflows/pages.yml?query=branch%3Amain+event%3Aschedule)

## Пилот KLBF Lab после v0.2.0

Кандидат пилота использует релиз [v0.2.0, `49bf084250ec55c70d6732000ea40e62c3d36b4c`](https://github.com/akimfomin/PortBridge/releases/tag/v0.2.0). Аудит доставки и документация проверены полным набором из 284 тестов, без ошибок и пропусков.

## Запрос по BM-v1

27 ноября в 00:33 МСК отправили BrokeAsh одно предложение в PortBridge Test Lab. Вопрос — есть ли для уже опубликованного результата сопоставимый контроль на том же компьютере. Опубликованная таблица содержит референс на том же GPU и с теми же номинальными настройками Series S, FSR и лимитом текстур. У него другой процессор, другая статистика пропущенных конвейеров, а версия FSR и драйвер в JSON не указаны. По этим данным нельзя объяснить разницу между замерами. [Запрос и приглашение](https://github.com/akimfomin/PortBridge/issues/95#issuecomment-7203842475) · [Исходные JSON и точные версии](evidence/klbf-bm-v1-pilot.md)

PortBridge опубликовал проверяемую заявку с точной ревизией и условиями. Выбор участника и условий сравнения выполнялся вручную. Участник может найти подходящий опубликованный JSON или назвать поле, без которого сравнение невозможно. В зачёт входит только его самостоятельный результат. При контрольном чтении в 00:43 МСК в заявке было только наше приглашение. [Очередь заявок Test Lab](https://github.com/akimfomin/PortBridge/issues?q=is%3Aissue+%22Test+request%3A%22+in%3Atitle) · [Обсуждение методики](https://github.com/PastiiJay/klbf-lab/issues/79)

## Публикации по расписанию

Последний видимый запуск по расписанию стартовал 26 ноября в 18:45 МСК, до выхода версии с квитанциями. Состояние опубликованных данных подтверждено отдельной выгрузкой. Предшествующий сбой произошёл на этапе сверки публичного снимка после успешной выкладки. Следующий запуск прошёл. Первого планового запуска новой версии к 00:43 МСК в GitHub ещё не было. Историю расписания проверили через публичную страницу GitHub, а состав артефактов — через авторизованный GitHub API. У старого планового прогона есть только архив Pages. У контрольной выкладки после слияния есть архив Pages и копия каталога. Квитанций расписания в этих двух прогонах нет. [История расписания](https://github.com/akimfomin/PortBridge/actions/workflows/pages.yml?query=branch%3Amain+event%3Aschedule) · [Сбой старой версии](https://github.com/akimfomin/PortBridge/actions/runs/45761703311/job/139714248009) · [Следующий успешный запуск](https://github.com/akimfomin/PortBridge/actions/runs/45852310279) · [Контрольная выкладка после слияния](https://github.com/akimfomin/PortBridge/actions/runs/45896956002#artifacts) · [Публичное состояние](https://akimfomin.github.io/PortBridge/data/health.json)

Недельная проверка привязана к этому чату на 4 декабря в 00:15 МСК. Учитываются только поставки по расписанию с подтверждённой квитанцией той же ревизии, по времени её создания. Повторные попытки требуют отдельной сверки и автоматически не засчитываются. Тест проверяет переход через границу суток, несовпадающую ревизию ручной запуск и повторную попытку. [Команда проверки](m6_autonomy.py) · [Тест](../tests/test_audit_autonomy.py) · [Схема квитанции GitHub](https://docs.github.com/en/rest/actions/artifacts#list-artifacts-for-a-repository)

```sh
python -B audit/m6_autonomy.py --since 2026-11-26T21:07:13Z
python -B -m unittest discover -s tests -p test_audit_autonomy.py -v
```

# PortBridge M5–M6 · пилот и приёмка выпуска

Исходная ревизия — [M5.3, 0cb1fe46d14f0930e7e347e3c9980a53c9d94be9](https://github.com/akimfomin/PortBridge/blob/0cb1fe46d14f0930e7e347e3c9980a53c9d94be9/audit/LATEST.md). Результаты выпуска и послерелизные проверки доступны в [постоянном отчёте для аудитора](https://github.com/akimfomin/PortBridge/blob/audit/review/audit/LATEST.md). [Релизный PR #93](https://github.com/akimfomin/PortBridge/pull/93) · [Реестр 122 требований](../docs/PORTBRIDGE-CHECKLIST.md)

## Итог выпуска v0.2.0

[Публичный GitHub Release v0.2.0](https://github.com/akimfomin/PortBridge/releases/tag/v0.2.0) опубликован 26 ноября в 21:23:55 UTC. Указатель Git-тега и GitHub API независимо указывают на приведённый ниже SHA. В браузере проверены карточка Continued, оба тестера и ссылки на их измерения.

Итоговый код в `main` — [49bf084250ec55c70d6732000ea40e62c3d36b4c](https://github.com/akimfomin/PortBridge/commit/49bf084250ec55c70d6732000ea40e62c3d36b4c). Дополнение с ответами двух участников прошло 283/283 теста на Windows за 47,512 с и 283/283 на GitHub за 35,474 с, без пропусков и ошибок. В репетиции отката сравнили 26 908 наблюдений. [PR #94](https://github.com/akimfomin/PortBridge/pull/94) · [Проверка и репетиция](https://github.com/akimfomin/PortBridge/actions/runs/45896345148) · [Публикация и проверка работающего сайта](https://github.com/akimfomin/PortBridge/actions/runs/45896956002)

На итоговом сайте **27 262 наблюдения**, 14 сверенных разделов. Лента партнёров отдаёт 6 задач и 15 результатов. Два независимых отчёта Continued доступны и на витрине, и в ленте. Полный SHA-256 опубликованного `data/site.json` — `348ddc192d65970ad81fab9c6e15f28580e6e6a3cde453bcf8c615ecb02bd5d4`. Состояние источников — `partial`. Недельное наблюдение стартовало после первой проверенной поставки, 26 ноября в 21:07:13 UTC. Семь суток истекут 3 декабря в 21:07:13 UTC. На момент проверки после второго деплоя плановых публикаций в этом интервале было 0. [Данные конечной проверки](evidence/m6/public-release.json) · [Исходная точка наблюдения](evidence/m6/autonomy-at-release.json) · [Карточка команды](https://akimfomin.github.io/PortBridge/#/impact?target=https%3A%2F%2Fgithub.com%2Fubiquitarianism%2Fleonida%2Fpull%2F2392)

В реестре спецификации 3.0 совпали все **122 уникальных ID**. Подтверждены **80**, выполнено частично **41**, заблокировано **1**. Последнее — подтверждённое повторное применение новой версии тремя независимыми командами. Для пилота отдельно учитываются одна реально использованная рекомендация, два аппаратных отчёта и ноль подтверждённых внешних установок. Фактическое число установок остаётся неизвестным. [Реестр требований](../docs/PORTBRIDGE-CHECKLIST.md) · [Методика и источники пилота](evidence/m6-pilot.md)

## Первая поставка и приёмка

Первая поставка в `main` — [98d1a39be0c2ea161fb3f30fdfb8bb572d55e5cf](https://github.com/akimfomin/PortBridge/commit/98d1a39be0c2ea161fb3f30fdfb8bb572d55e5cf). Дерево совпадает с проверенной ревизией [dc5272213997bca3ffa4fe781e448bd60b382d03](https://github.com/akimfomin/PortBridge/commit/dc5272213997bca3ffa4fe781e448bd60b382d03). До слияния на Windows прошли 282 теста за 46,763 с и проверка полного экспорта. В GitHub прошли те же 282 теста за 37,983 с. Ошибок и пропусков 0. В контрольном восстановлении прежний код заново собрал сайт и Lab для всех 26 106 наблюдений. [Проверка точного кандидата](https://github.com/akimfomin/PortBridge/actions/runs/45894117888) · [Сборка main](https://github.com/akimfomin/PortBridge/actions/runs/45895096163)

При первой выкладке с `main` **14 публичных разделов** совпали со сборкой. На сайте 26 766 записей, в прежнем снимке было 25 426. Состояние источников `partial`. Проверены 10 маршрутов в обычном Chrome и при эмуляции телефона 390×844. Первый опрос партнёрской ленты вернул 6 задач, повторный — 0 изменений. На примере XCL #2322 обычная строка поиска, настоящий MCP-клиент, чтение опубликованного API и GitHub-сводка показали один и тот же пример LLVM. Проверяющий клиент учитывает канонический адрес репозитория после переименования и служебные инструкции формата MCP. [Исходный публичный снимок](evidence/m6/public-before.json) · [Проверка после выкладки](evidence/m6/public-after.json) · [Проверка браузера и опубликованных ссылок](evidence/m6/production-ux.json) · [GitHub Action на выпущенном main](https://github.com/akimfomin/PortBridge/actions/runs/45895897766#summary-140169576949)

## Что проходит у разработчика

Сопровождающий копирует один закреплённый workflow в выбранный публичный репозиторий. При открытии и обновлении PR результаты видны в GitHub Checks. Можно также вставить обычную ссылку в форме запуска. В сводке видны исходный PR, его ревизия, рабочие ссылки, ограничения снимка и причина пустого результата. Ключей от команды и отдельного сервера для этого пути не требуется. Для агента доступны MCP и партнёрский API. [Инструкция](../docs/GITHUB-ACTION.md) · [Пример](../examples/portbridge-pr.yml) · [MCP](../docs/MCP.md) · [API](../API.md)

| Где проверено | Факт |
| --- | --- |
| Отдельный репозиторий владельца, настоящий GitHub | Первый запуск выявил длинную неинформативную сводку. Исправлены вывод, проверка существования PR и привязка к ревизии. Два запуска для одного события дали одинаковые результаты. Недоступность каталога, восстановление и отсутствующий PR показаны раздельно. После отключения workflow следующий коммит не запустил проверку. [Все прогоны и контроль отключения](evidence/m6/receiver.md) |
| Положительный пример GitHub | Для XCL #2322 в форме запуска разработчик получил ссылку на LLVM StackColoring с закреплённой строкой исходника. Это известный источник для сравнения распределения временных слотов. Обе ссылки, полученные для нового PR тестового репозитория, оказались слабыми. [Сводка GitHub](https://github.com/akimfomin/PortBridge-integration-test/actions/runs/45890209530) |
| Пилот с внешней командой | В Continued #2392 предложена проверка попадания в кэш из нового процесса. Автор qhukz13 выбрал уже существующую диагностику Continued #2198 и сообщил о попадании на GTX 1050 Ti. На RTX 5070 lixonik отдельно проверил пустой журнал, положительный контроль и журнал, записанный этой веткой. Последние два дали `verified=1`. Одна команда решила, какой проверкой подтвердить один PR. Установка PortBridge у команды не установлена. [Наше предложение](https://github.com/ubiquitarianism/leonida/pull/2392#issuecomment-7202363138) · [Ответ автора](https://github.com/ubiquitarianism/leonida/pull/2392#issuecomment-7202911853) · [Ревью с контролями](https://github.com/ubiquitarianism/leonida/pull/2392#pullrequestreview-6080300502) |
| Подписка партнёра | Клиент может забирать проверенные задачи и результаты, фильтровать и постранично читать их, хранить курсор у себя и прекратить опрос. Неполная страница, потеря сети и устаревший снимок сохраняют последнее состояние. Повторный опрос полного снимка не порождает новых событий. [Контракт API](../API.en.md) · [Регрессии](../tests/test_m6_partner.py) |

Два исторических аппаратных отчёта FrameLab теперь проходят из Lab в поиск, Radar, People, Impact и партнёрскую ленту. Ссылки на измерение и на его одобрение сохранены отдельно. Повторная проверка выявила две ошибки. В одном случае партнёрам уходили одновременно PASS и FAIL на одинаковом стенде. В другом после отзыва продолжала учитываться старая карточка. Исправления проверены отдельным исполнителем. При отзыве число подтверждений меняется с 9 до 8, при восстановлении одобрения — с 8 до 9. [Источники и воспроизведение](evidence/m6/five-views.md) · [Проверка пути от PR до Lab](evidence/m6/e2e-intake.md)

На релизном PR исправлены ещё два воспроизводимых случая. Отзыв отчёта больше не открывает снятую задачу. Повторная успешная проверка неизменившейся ревизии GitHub обновляет её срок актуальности без перезаписи времени получения исходных данных. Статический сайт при первом открытии сразу читает данные Pages. [Ревью обработки отзыва](https://github.com/akimfomin/PortBridge/pull/93#discussion_r4713207814) · [Ревью подтверждения ревизии](https://github.com/akimfomin/PortBridge/pull/93#discussion_r4713207824) · [Браузерные испытания](evidence/m6/browser-bootstrap.md)

## Подготовка к выкладке и восстановление

До изменения main работающий сайт выдавал 25 426 записей и частичный статус источников. Публичный адрес партнёрской ленты возвращал HTTP 404. Сохранены прежний SHA, поколение, обе контрольные суммы и ссылка на прежнюю сборку. [Проверка до выпуска](evidence/m6/public-before.json) · [Артефакт предыдущего сайта](https://github.com/akimfomin/PortBridge/actions/runs/45852310279/artifacts/15135120357)

Первый запуск на GitHub отклонил резервную копию с новыми таблицами. После исправления на том же типе runner восстановлен каталог из production-кэша и проверена копия с **26 013 наблюдениями**. Экспорт занял 47 с. Предыдущая версия main за 44 с пересобрала сайт с тем же числом наблюдений и сохранила исключение снятых карточек. Проверка ветки оставляла рабочий сайт доступным. В отдельном локальном прогоне сверено полное множество идентификаторов 25 426 ранее опубликованных наблюдений для обеих версий. [Отказ](https://github.com/akimfomin/PortBridge/actions/runs/45889135569) · [Облачное восстановление](https://github.com/akimfomin/PortBridge/actions/runs/45889755929) · [Локальное испытание](evidence/m6/checkpoint-replay.md) · [Порядок отката](../docs/PASSIVE-MAINTENANCE.md#public-checkpoint-and-rollback)

После каждой успешно проверенной плановой публикации GitHub хранит 30 дней квитанцию с ревизией, временем и контрольными суммами. Для проверки недели используются реальные запуски по расписанию с подтверждённой доставкой на Pages. До M6 между двумя последовательными запусками по расписанию проходило 10 ч 18 мин. Успешная выкладка и свежесть данных по каждому источнику проверяются отдельно. [Как наблюдать](../docs/PASSIVE-MAINTENANCE.md#observe-the-first-week)

## Выполнение первоначального плана

**План выполнен частично.** В §XXIX первой мастер-директивы отдельно требуются результат собственных исследований и его принятие, коллективные проверки, измеримое качество поиска и автономная работа. В последующей спецификации 3.0 уже 122 проверяемых требования. На старте этой итерации подтверждались 66 из них. Измеримая работа за пределами PortBridge уже есть: исправление AnyXboxX #133 принято, исправление Wave32 независимо проверили на физическом оборудовании, FrameLab исторически повторно использовал результаты. XCL Scratch #2322 и Continued #1713 на момент сверки остаются открытыми. Эти достижения относятся к разным этапам. [AnyXboxX #133](https://github.com/LooperSalty/AnyXboxX/pull/133) · [Проверка Wave32](https://github.com/xcl-dev/xcl/issues/2584#issuecomment-7179418085) · [Историческое использование](evidence/network.md) · [XCL Scratch](https://github.com/xcl-dev/xcl/pull/2322) · [Continued](https://github.com/ubiquitarianism/leonida/pull/1713)

Поиск дальнейшей настройки не получал. На пяти свежих PR у M5.2 и M5.3 было **0 из 5** источников, отвечающих на заранее поставленные вопросы. SEARCH-08 остаётся открытым. Повторных пользователей новой версии подтверждено **0 команд из 3**. Самостоятельное применение рекомендации подтверждено одной командой по одному PR. Открыты независимая приёмка качества Radar и недельное наблюдение после выхода новой версии. Измерения по другой задаче Continued #2399 команда уже провела самостоятельно. [Аудит поиска](evidence/m53/assessment.md) · [Независимое измерение команды](https://github.com/ubiquitarianism/leonida/pull/2399#issuecomment-7201979513)

## Команды для аудитора

```sh
git clone --branch audit/review https://github.com/akimfomin/PortBridge.git
cd PortBridge
python -B -m unittest discover -s tests -v
python -B -m portbridge --db .portbridge/check.sqlite3 export --out .portbridge/review-site --repository akimfomin/PortBridge
python -B -m portbridge.release_gate .portbridge/review-site
python -B -m portbridge.network --outcomes-only
python -B audit/m6_public_smoke.py --continued-pilot
python -B audit/m6_autonomy.py --since 2026-11-26T21:07:13Z
```

Для повторного запуска на GitHub откройте **Actions → PortBridge one-PR pilot → Run workflow** и вставьте публичную ссылку на PR. Для отдельной копии стенда и проверки отключения используйте [инструкцию приёмки](evidence/m6/receiver.md). Полный перечень оставшихся условий закреплён за ID в [реестре](../docs/PORTBRIDGE-CHECKLIST.md).
