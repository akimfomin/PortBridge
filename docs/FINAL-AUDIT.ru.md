# Что создал PortBridge и что можно продолжить

26 ноября 2026 года · [English](FINAL-AUDIT.md) · [Письмо основателя и открытое обсуждение][future] · [Передача проекта][maint]

У независимых команд, которые работают над совместимостью Xbox Series и ПК, снова и снова возникал один вопрос. Кто уже разбирал похожий графический сбой и у кого есть другая видеокарта, чтобы проверить ответ? С этого начался PortBridge. За проектом стоял один человек, дома, с ИИ-агентом. Остались работающий поиск, проверяемые измерения, несколько принятых изменений и люди, которые потратили своё время на чужую задачу. Отдельные команды пользовались лабораторией. Регулярного самостоятельного использования, которое позволило бы сохранить прежний темп, добиться не удалось. [Первый коммит][start] · [Журнал публичного сотрудничества][log]

## Как развивалась работа

- **24 ноября.** Первый каталог связал публичные отчёты с конкретными версиями кода. Появились проверка предыдущих исследований перед началом работы, локальный MCP, подключаемая проверка для GitHub и лаборатория добровольцев Test Lab. На ранней фиксированной выборке искомая ссылка попала в первую пятёрку по 7 из 10 запросов PortBridge и по 8 из 10 запросов прямого поиска GitHub. Обмен данными проверили двумя программными имитациями агентов. Случаи с реальными участниками перечислены ниже. [Открытие Test Lab][lab] · [Задания, результаты и последующие оценки поиска][search]
- **25 ноября.** Каталог получил индекс поиска по частям, автоматический сбор отчётов и Research Radar. Начались аппаратные эксперименты с передачей буферов и обменом между потоками GPU, затем с возвратом данных на CPU и подготовкой графического конвейера. Несколько собственных алгоритмов уступили уже доступным способам. Исходники и измерения сохранены, чтобы следующий исследователь мог начать с места, где выявилось ограничение. [Обновление каталога][radar] · [Планировщик передач на RTX][ref62] · [Чтение данных и зависимости][ref74]
- **26 ноября.** Проверка пикселей на границах треугольников опровергла раннее упрощение масок. Она также выявила ошибку в обычном переводе пиксельных шейдеров XCL. Правку ошибки отделили от осторожной экспериментальной оптимизации. Обе версии опубликованы, а два вычислительных прохода отработали на GPU в сравнении с исходными шейдерами. [Отозванное преобразование][p77lane] · [Материалы в основной ветке PortBridge][main90]

## Что действительно использовали другие команды

| Получатель | Кто что сделал, где оказалась разработка и как её проверить |
| --- | --- |
| AnyXboxX, WARP и D16 | LooperSalty принял исправление PortBridge для инициализации регистров на WARP в #144, коммит `becaf782`. Сохранились четыре прежних расхождения в текстурных проверках. В #129 Skyfrye использовал ожидаемое значение D16 из проверки PortBridge для VIctory в собственном тесте интерпретатора. Слияние — `b15d8821`. В исходных обсуждениях есть условия проверок. [Правка WARP][warp] · [Принятый тест D16][d16] · [Первоначальный тест][victory] |
| AnyXboxX, округление и FMA | Автор принятых изменений интерпретатора — KainanP. PortBridge воспроизвёл расхождения и подготовил аппаратную пробу. Lyrnc измерил значения переноса у неактивных потоков на физической gfx1036. #133 принят в `71d4c615`, отдельная правка однократного округления FMA в #203 — в `6802e44b`. Аппаратный результат Lyrnc относится к проверенной инструкции и конфигурации. [Слияние #133][c133] · [Аппаратный отчёт][lyrnc] · [#203 с проверками и атрибуцией][fma] |
| AnyXboxX, текстуры | Изменение PortBridge для декодера BC7 принято в #202, коммит `0539d7f8`. Выход совпал с другим CPU-декодером на всех 68 868 пикселях при проверке восьми режимов и обрезанных краёв. Репозиторий применяет GPL-3.0-or-later, сохранены MIT-уведомления исходного переноса Xbox2Windows. В #188 Lewandox реализовал предложенное PortBridge переиспользование координат на `c5ca937c`. После смены текстурного движка команда закрыла #188 без слияния. [Принятый BC7 и команды][bc7] · [Сравнение декодеров][pillow] · [Реализация Lewandox][gfxcode] · [Решение по #188][gfx] |
| FrameLab, VIctory и KLBF Lab | 5headsmartbtw добавил независимую проверку PortBridge на NVIDIA в основную документацию FrameLab. JoeY54 передал два принятых AMD-отчёта для FL-07. PastiiJay из KLBF Lab взял задачу из Test Lab и опубликовал результаты двух наборов входов XCL #1100. Обсуждение VIctory и проверка D16 стали первоисточником результата, который использовал AnyXboxX. [Изменение FrameLab][frame] · [Приёмка FL-07][joe] · [Отчёт участника KLBF][klbf] · [Обсуждение VIctory][victory] |

Ahmet-Dedeler включил Test Lab в общественный каталог. Six on PC добавил PortBridge в группу лабораторий в исходниках своего трекера. [Код трекера][board] PC Race отклонил размещение с учётом тематики своего трекера. Это подтверждённые редакционные решения. По ним нельзя судить о регулярном использовании. [Включение в каталог][added] · [Ответ PC Race][declined]

## Инженерные разработки и незакрытые вопросы

**1. SSA Mask Projection, эксперимент.** Компилятор PortBridge для прямого перевода XCL в DXIL умеет проследить четыре бита, нужные группе пикселей, через выражения с доказанным происхождением. Для скалярных операций сохраняется полная маска. Когда происхождение неизвестно, действует прежний путь. Точная версия форка — `5d04cc10`, выпуск материалов — `2223a0b6`. На опубликованной версии прошли 1 436 тестов, в сочетании с обновлённой основной веткой XCL — 1 450. В каждом прогоне 47 тестов выключены и 28 подпроверок явно пропущены. Из 397 допустимых комбинаций шейдера и ширины группы размер DXIL уменьшился в 34 случаях, вырос в 24 и остался прежним в 339. Для включения в новом процессе прямого пиксельного пути задайте `XCL_DIRECT_PIXEL_MASK_PROJECTION=1`. Команда `python verify.py` в папке исследования сверяет архивные результаты. Там же указаны лицензии шейдеров и GPL-2.0-only для патчей XCL. [Код][ssa] · [Инструкции и лицензии][main90] · [Корпус и журналы][receipt]

| Полный вычислительный проход на RTX 4070 Ti SUPER | Полные маски | Предыдущая строгая проекция | Расширенная проекция | Исходный Vulkan |
| --- | ---: | ---: | ---: | ---: |
| Khronos Mobile NeRF 071 | 297 мкс | 193–195 мкс | 163–170 мкс | около 14 мкс |
| Khronos Mobile NeRF 073 | 265 мкс | 178–184 мкс | 156–157 мкс | около 14 мкс |

Все переведённые варианты дали одинаковые значения каждого из 57 600 пикселей в обоих кадрах. Максимальное расхождение по каналу с исходным шейдером — 2,39 × 10⁻⁷. Два шейдера имеют много общего кода, полное сравнение выполнено на одной физической NVIDIA. Полноразмерный D3D12-прогон остановила защита запаса памяти. Остаются открытыми проверка на AMD или Intel, влияние на полное время кадра приложения и предельная память драйвера. [Исходные замеры GPU и хеши кадров][raw] · [Добровольная независимая проверка][ask87]

**2. Wave32 Carry Fix, независимые аппаратные результаты.** Штатный HLSL-переводчик XCL мог перезаписывать соседнюю маску на границах треугольников. На нашей RTX число неверных пикселей с учётом повторных отрисовок снизилось с 668 из 2 953 до нуля. DarkPanda69 воспроизвёл ошибку на RX 9070 XT и RTX 3060 и подтвердил исправление на обеих картах. luckyteagirl отдельно проверила точный исправленный тест на RX 6800M. Исходная версия и фактическая ширина группы в этой дополнительной проверке не измерены. Полный прогон PortBridge на исправленной версии дал 1 431 успешный тест. Для повтора соберите GPL-2.0-only форк XCL на `d3e7725f` и выполните `gpu_wave32_pixel_carry_preserves_adjacent_mask_at_triangle_edges` по инструкции. Для принятия в XCL ещё нужны запрошенная парная проверка на законно доступной игре и решение сопровождающих. [Исправление][wave] · [Инструкция][wrun] · [Независимое парное сравнение][dark] · [RX 6800M][luck]

**3. Повторное использование временной памяти XCL, черновик #2322.** Kalmarv написал основу для хранения промежуточных значений между этапами, принятую в #2126. PortBridge добавил отдельный распределитель для значений с непересекающимися сроками жизни. На более ранней базе Kalmarv участник ettehn независимо измерил 47 712 → 20 064 DWORD на группу при тех же 12 корректных частях и прошёл восемь аппаратных проверок. Время исполнения GPU в этом отчёте отсутствует. Для парного эксперимента сохранены версия черновика `b3f7ab55` и точная исходная версия `afc5ee86`. После конфликта с новой основной веткой опубликована отдельная совместимая версия `dfb580be`: по 11 проверок прошли в каждом режиме распределителя. Набор включает отчёты nnonno91 и luckyteagirl, программу сравнения, команды сборки и поля для трёх запрошенных нагрузок. Патч XCL — GPL-2.0-only, программа сравнения — MIT. [Измерение ettehn][ett] · [Код, инструкции и лицензии][scratch] · [Ожидаемые измерения][kal] · [Совместимая версия][dfb]

**4. Continued Vulkan #1713, открыт в Continued и использован в форке.** DadaCap предложил отдельно исследовать объединение областей с одинаковым графическим состоянием. PortBridge объединил соседние прямоугольники с одинаковой раскладкой и аспектом. В контрольном примере для тех же переходов каждой ячейки понадобилось пять барьеров вместо четырнадцати. potatoe0100 проверил `ef9ae1fd` в сочетании с `bcaa13dad` на RTX 4060. Прошли три целевых проверки и 409 CTest. Leonida Ultimate перенёс изменение с указанием авторства в `e7124f97`. Его ветка по умолчанию `ultimate` на момент проверки `c9bd989e` содержала этот коммит и ещё 198 последующих. [История ветки][forkline] PR основной команды Continued остаётся открыт. Для продолжения повторите закреплённые тесты состояний и воспроизведения на текущей ветке, включая смешанные и одиночные области. Код Continued распространяется под GPLv3 или новее. Прирост частоты кадров не измерен. [PR и команды][c1713] · [Стенд][cbench] · [Независимая проверка][pot] · [Принимающий форк][fork]

**5. RDNA2, внешний вклад KainanP #78.** KainanP самостоятельно принёс пять открытых аппаратных проб на `81f607fa`. PortBridge перепроверил сборку и линковку и опубликовал `14bacd57`, чтобы незаписанные результаты не считались успехом. Пять полных CPU-контролей прошли, все 117 одиночных пропусков отклонены. Для завершения нужны физические данные с совместимой AMD. Команда запуска есть в README каждой пробы. Используйте правку полноты и сохраните точные модель карты и драйвер. Для #84 есть отдельный стенд четырёх инструкций. В #85 после отзыва прежнего источника требуется полный объявленный вывод, в том числе A5. Материалы находятся в MIT-репозитории PortBridge. Авторская ветка и PR сохранены. [Пять проб и инструкции][k78] · [Проверка полноты][kfix] · [#84][k84] · [#85][k85]

**6. Переносимость генерации mipmap NVIDIA, отчёт передан.** PortBridge показал, что номер потока в рабочей группе может расходиться с его позицией внутри подгруппы. При намеренной перестановке логических номеров на RTX исходный образец изменил 14 194 байта, а исправленный вернул ожидаемый результат. При обычном порядке на трёх открытых текстурах совпали 8 388 604 байта. akeley98, ранее работавший в NVIDIA, в неофициальном ответе сообщил, что ему неизвестно оборудование с такой перестановкой для одномерных групп. Драйвер, самостоятельно выбирающий этот порядок, и принятие изменения NVIDIA не подтверждены. Для повтора используйте полные подгруппы фиксированной ширины, образец NVIDIA под Apache-2.0 на `6c248f55`, модель и текстуры из PortBridge `cb0faec3`. Существенным новым свидетельством стал бы реальный другой порядок. [Исходный образец][nvrepo] · [Точное воспроизведение][mip] · [Ответ автора][nv]

## Сохранённые ветки и отрицательные результаты

В [публичной описи версий](engineering-inventory.json) зафиксировано состояние до выпуска передачи: 68 запросов на слияние PortBridge, 89 ссылок на ветки и метки и 22 инструкции к исследованиям и внешним вкладам. Для запросов сохранены точные версии, инструкции открываются на закреплённых коммитах.

| Работа | Зачем сохранена и при каком условии стоит вернуться |
| --- | --- |
| GPU-resident Geometry · черновик #75 · `88cede55` | Реализация Blender показала предварительный просмотр и сохранила корректный объект из 6,385 млн точек открытых данных Токио. Пересылка данных с CPU оказалась медленнее, но стабильного превосходства над сильным вариантом, уже хранящим маски на GPU, нет. Для нового сценария используйте общий рендерер и хеши геометрии. В отчёте сохранена атрибуция Токио CC BY и указаны зависимости Blender. [Интеграция и команды][bl] |
| Halide WebGPU · черновик #76 · `c0775045` | В двух примерах Halide 22.1.0 ожидание завершения по событию снизило задержку отображения с 33,08 до 5,51 мс и с 43,76 до 9,19 мс. Сопоставимая реализация CPU SIMD заняла 0,885 и 6,334 мс. Результат полезен для старого режима с одним последовательным вызовом. Версия Halide имеет лицензию типа MIT. Для фото астронавта нет известных ограничений авторского права, фото Hubble находится в общественном достоянии. [Происхождение изображений][halinputs] · [Лицензия Halide][hallicense] [Версии, входы и повтор][hal] |
| Cold Pipeline Readiness · черновик #77 · `64280ea4` | В архиве запись графических команд в исходном порядке, Read Guard Fusion, специализации root/UMA и ранние эксперименты с масками. Ускорение Read Guard Fusion в 11,4 раза получено на синтетике. В первом внешнем корпусе условие выполнялось в 1 из 72 случаев при одном окне памяти и в 0 из 72 при четырёх. Ранняя широкая Lane-local Masks ошибалась на краях треугольников. Для новых опытов подходит более поздний пакет SSA. Перед переносом кода прочитайте текущий статус и сравните точные исходные версии. [Сводка статусов][pr77] · [Закреплённое дерево][arch77] · [Контрпример][p77lane] |
| Прежние эталонные компоненты | Точный Buffer Transfer Planner ни разу не превзошёл жадный алгоритм среди 596 изменившихся наблюдений без ограничений размера. Для обменов между потоками, диспетчеризации switch, общего хвоста шейдеров и повторного использования слотов остались эталонные проверки. Наборы для адаптивного чтения GPU и зависимостей вычислений сохраняют опыты с порядком и временем жизни данных. В README каждого есть нагрузки и команды воспроизведения. Поводом вернуться станет задача с измеренным ограничением из соответствующего отчёта. [Планировщик][ref62] · [Исследования компиляторов и памяти][ref67] · [Чтение данных и зависимости][ref74] |

Для собственных инструментов PortBridge действует [лицензия MIT][license]. Патчи сторонних проектов, открытые шейдеры, изображения и тестовые данные сохраняют уведомления на своих закреплённых ревизиях. Публичная ссылка сама по себе не даёт права распространять сторонний материал. При передаче результата сохраняйте лицензию, ревизию, команду, устройство, пропуски и отрицательные контроли.

## Состояние экосистемы на момент передачи

26 ноября в 02:23 UTC проверены публичные головы веток по умолчанию для 45 записей каталога и связанных дополнительных адресов, повторяющиеся адреса учитывались один раз. Из 48 адресов 42 вернули точную версию. Для остальных при этой проверке получить ревизию по публичной ссылке не удалось. Исторические сведения сохранены. Доступность ветки сама по себе ничего не говорит о технической зрелости, скрытой активности или принятии работ PortBridge. Старый отдельный beta-репозиторий KLBF отправляет читателя в KLBF Lab. В форках встречаются отчёты общего происхождения. Происхождение и трекеры описаны в [предыдущем аудите источников][eco], актуальность очередной выгрузки показана в [состоянии источников сайта][coverage].

| Публичный источник | Ветка по умолчанию | Ревизия |
| --- | --- | --- |
| [0x0007b/XBVK](https://github.com/0x0007b/XBVK) | main | [858cd6abf](https://github.com/0x0007b/XBVK/commit/858cd6abf750af0616a29a1d3f62c564ef1f408c) |
| [5headsmartbtw/leonida-framelab](https://github.com/5headsmartbtw/leonida-framelab) | main | [c3d404b65](https://github.com/5headsmartbtw/leonida-framelab/commit/c3d404b65ff31f3377a16dc4483774cc0711239d) |
| [7jycwjmbfn-eng/scenegate-vi](https://github.com/7jycwjmbfn-eng/scenegate-vi) | — | Не удалось получить |
| [Aoody743/MetalVI](https://github.com/Aoody743/MetalVI) | main | [c6e693a83](https://github.com/Aoody743/MetalVI/commit/c6e693a833d4a490a3db2a9749a5da800e72e61e) |
| [Batushn/KestrelX](https://github.com/Batushn/KestrelX) | main | [cd55dac83](https://github.com/Batushn/KestrelX/commit/cd55dac8376ab94e7c88290eefcd3559420779c1) |
| [Belobug/VIctory-Belobug-AMD](https://github.com/Belobug/VIctory-Belobug-AMD) | rx9070xt | [81ebb7bdc](https://github.com/Belobug/VIctory-Belobug-AMD/commit/81ebb7bdc9b7ca6ec2f3169973f50be77c7c803c) |
| [DesignWithTommy/Neonbridge](https://github.com/DesignWithTommy/Neonbridge) | main | [762a13d01](https://github.com/DesignWithTommy/Neonbridge/commit/762a13d011bb35cee861802f9f285e9ae1f7dcbf) |
| [Geckomacabre/vx-layer](https://github.com/Geckomacabre/vx-layer) | main | [ac69b9647](https://github.com/Geckomacabre/vx-layer/commit/ac69b96477ee4f59fcfcd16b9cd0a0862c467cc2) |
| [IAmNotSiob/leonida-ce](https://github.com/IAmNotSiob/leonida-ce) | main | [b3c6eadfc](https://github.com/IAmNotSiob/leonida-ce/commit/b3c6eadfc428eca06c2235d4383c8dbe3dd69cb6) |
| [Its3rr0rsWRLD/XPortPC](https://github.com/Its3rr0rsWRLD/XPortPC) | main | [40218cd69](https://github.com/Its3rr0rsWRLD/XPortPC/commit/40218cd69af60186b1a3fe707f208d368599f25b) |
| [JMAN730/project-flamingo](https://github.com/JMAN730/project-flamingo) | main | [d7aa42a45](https://github.com/JMAN730/project-flamingo/commit/d7aa42a45a0a63423db29086f798ace539301f0c) |
| [Joaco9020/mangrove](https://github.com/Joaco9020/mangrove) | main | [8c7bb8581](https://github.com/Joaco9020/mangrove/commit/8c7bb85813ab9c62d1249a7d53e115778e5e7771) |
| [KretliJ/victory-monitor](https://github.com/KretliJ/victory-monitor) | main | [b8c25227d](https://github.com/KretliJ/victory-monitor/commit/b8c25227df61a5dfcfa1db66b28f7cb152053099) |
| [LeonidaReforge/Leonida](https://github.com/LeonidaReforge/Leonida) | — | Не удалось получить |
| [LooperSalty/AnyXboxX](https://github.com/LooperSalty/AnyXboxX) | main | [c4c93bdc4](https://github.com/LooperSalty/AnyXboxX/commit/c4c93bdc413191a9dc909998d2d53080a3f0c880) |
| [Marvisak/VIctory](https://github.com/Marvisak/VIctory) | main | [63bcca43c](https://github.com/Marvisak/VIctory/commit/63bcca43c6a00a758510398fa43096ce7e4f7df0) |
| [MiamiGame/XTP](https://github.com/MiamiGame/XTP) | main | [9b822f588](https://github.com/MiamiGame/XTP/commit/9b822f58870e351613666129ca5621c6a4955fb7) |
| [OpenCommunityEdition/OpenScarlett](https://github.com/OpenCommunityEdition/OpenScarlett) | main | [e043ba44c](https://github.com/OpenCommunityEdition/OpenScarlett/commit/e043ba44c9b894656939f21d4d33ef2c97e5f081) |
| [PastiiJay/klbf-lab](https://github.com/PastiiJay/klbf-lab) | main | [420e1e124](https://github.com/PastiiJay/klbf-lab/commit/420e1e12485f0f652bfc2989723a273cab51669a) |
| [PastiiJay/klbf-lab-beta](https://github.com/PastiiJay/klbf-lab-beta) | klbf-lab | [b6ba1c50d](https://github.com/PastiiJay/klbf-lab-beta/commit/b6ba1c50dc8d89fcb43f758333ec843c0a9a9123) |
| [R0Y00/Xbox2Windows](https://github.com/R0Y00/Xbox2Windows) | main | [e76f8acd5](https://github.com/R0Y00/Xbox2Windows/commit/e76f8acd5a269bfec48ea65203f2b7868fb14df3) |
| [ReverendOzmund/xseries-wine](https://github.com/ReverendOzmund/xseries-wine) | main | [89aa2462c](https://github.com/ReverendOzmund/xseries-wine/commit/89aa2462ce57c96fa3b1584c05e3d5dd6b7d8b84) |
| [ThatRecompDev/five-star-recomp](https://github.com/ThatRecompDev/five-star-recomp) | main | [397a2335e](https://github.com/ThatRecompDev/five-star-recomp/commit/397a2335ebf950303f0a9629fd1b2a7b2214726f) |
| [Zettrox/ztrx](https://github.com/Zettrox/ztrx) | — | Не удалось получить |
| [ZigZagBoi1/ScarlettPort](https://github.com/ZigZagBoi1/ScarlettPort) | main | [771f5ce51](https://github.com/ZigZagBoi1/ScarlettPort/commit/771f5ce51f783e0f11916f9086a2b203a0bb62ef) |
| [akimfomin/PortBridge](https://github.com/akimfomin/PortBridge) | main | [2223a0b6a](https://github.com/akimfomin/PortBridge/commit/2223a0b6a4dbaac1e98f8f90204b190296c4ef75) |
| [boykopovar/AnyBox](https://github.com/boykopovar/AnyBox) | main | [9c0347351](https://github.com/boykopovar/AnyBox/commit/9c03473518fbfdd9b354c4ceff7a787ed55d481c) |
| [brcly/TuxBox](https://github.com/brcly/TuxBox) | main | [4f7fa84c0](https://github.com/brcly/TuxBox/commit/4f7fa84c0e1667bcb164986c13d6c1fe9876e349) |
| [californiaAlmonds/OpenScarlett](https://github.com/californiaAlmonds/OpenScarlett) | main | [7220ce949](https://github.com/californiaAlmonds/OpenScarlett/commit/7220ce949800a959535086ce175b1e13b738aa16) |
| [clquwu/leonida-ultimate](https://github.com/clquwu/leonida-ultimate) | ultimate | [c9bd989ee](https://github.com/clquwu/leonida-ultimate/commit/c9bd989eef71eb0513292b9a405d2c5912a1c069) |
| [cmyk-ux/r4y](https://github.com/cmyk-ux/r4y) | main | [034bf2e1f](https://github.com/cmyk-ux/r4y/commit/034bf2e1fb2f708dc612225a733e00ee05426dbb) |
| [fablinoo/palmwave](https://github.com/fablinoo/palmwave) | — | Не удалось получить |
| [fxceless/victory-fork](https://github.com/fxceless/victory-fork) | main | [18ea64478](https://github.com/fxceless/victory-fork/commit/18ea644783b3dfe82082d52c9f3dc600a9f176a9) |
| [idvwork/rebox](https://github.com/idvwork/rebox) | — | Не удалось получить |
| [jadeowaowa/scarlett-layer](https://github.com/jadeowaowa/scarlett-layer) | main | [0e436b3e1](https://github.com/jadeowaowa/scarlett-layer/commit/0e436b3e1c654765b193c1cb705918fbf101b10b) |
| [mewiof/Holy-Interoperability](https://github.com/mewiof/Holy-Interoperability) | main | [a991f51c6](https://github.com/mewiof/Holy-Interoperability/commit/a991f51c6726b390ba85bbfed1b27434f28201b1) |
| [myokex/victory-amd](https://github.com/myokex/victory-amd) | vi-fx3 | [aa8399e5b](https://github.com/myokex/victory-amd/commit/aa8399e5b5e96af2cab80d01aa636c772cdae54e) |
| [nvpro-samples/vk_compute_mipmaps](https://github.com/nvpro-samples/vk_compute_mipmaps) | main | [6c248f554](https://github.com/nvpro-samples/vk_compute_mipmaps/commit/6c248f554e91329875e9860f2258019a32b44ee9) |
| [pablogonz12/Scarlight](https://github.com/pablogonz12/Scarlight) | main | [9a432787b](https://github.com/pablogonz12/Scarlight/commit/9a432787b6f40411063517363afa71a6ba86674e) |
| [pragyaangaur/VIctory-macOS](https://github.com/pragyaangaur/VIctory-macOS) | main | [b6dd0b184](https://github.com/pragyaangaur/VIctory-macOS/commit/b6dd0b184277fc307b93a4cc90d23dca9f05e7b3) |
| [rpatty-dev/PercyScarlett](https://github.com/rpatty-dev/PercyScarlett) | main | [e44c465e4](https://github.com/rpatty-dev/PercyScarlett/commit/e44c465e47ab5b29ca87777cd00875e2ae0d8c0d) |
| [sammwyy/xvalkyrie](https://github.com/sammwyy/xvalkyrie) | main | [ae50d83e8](https://github.com/sammwyy/xvalkyrie/commit/ae50d83e8117446d557d0d96ca53f720c797b71f) |
| [scarlett-commons/scarlett-commons](https://github.com/scarlett-commons/scarlett-commons) | main | [fa6ad1d45](https://github.com/scarlett-commons/scarlett-commons/commit/fa6ad1d452b937e2544a9190f9418e219b3dc84a) |
| [sub-north/xbox-hle-lab](https://github.com/sub-north/xbox-hle-lab) | main | [8863028b4](https://github.com/sub-north/xbox-hle-lab/commit/8863028b486dedf660303fcd3c756b05bbbebf91) |
| [ubiquitarianism/leonida](https://github.com/ubiquitarianism/leonida) | main | [3abb99cad](https://github.com/ubiquitarianism/leonida/commit/3abb99cad9e2cc3a356a7f78eb310b6ca93aae00) |
| [uiliannn/VItoriaBr](https://github.com/uiliannn/VItoriaBr) | main | [85615ad3d](https://github.com/uiliannn/VItoriaBr/commit/85615ad3d78b8efc9c42d34538f9099a6d3cb30a) |
| [vitutu1/victory-perf](https://github.com/vitutu1/victory-perf) | — | Не удалось получить |
| [xcl-dev/xcl](https://github.com/xcl-dev/xcl) | main | [b49be1836](https://github.com/xcl-dev/xcl/commit/b49be1836844fe0b0cdb3211dce3cb7fb4e21ac7) |

В [центральном обсуждении][future] можно взять сопровождение проверки, источника или компонента. Для начала достаточно назвать работу, точную версию и один результат, который сможет проверить другой человек. [Запуск проекта][maint] · [Открытые задачи Test Lab][forms]

[start]: https://github.com/akimfomin/PortBridge/commit/ea9caeb024211b55330b1c8663233974fd60ed81
[lab]: https://github.com/akimfomin/PortBridge/commit/0f09c81f56c999d52715a8dbb5fd72258b16ec9f
[search]: SEARCH-EVALUATION.md
[radar]: https://github.com/akimfomin/PortBridge/commit/ec513d743cfa80c04d58dd9d9a3de237a2194db5
[log]: COMMUNITY-COORDINATION.md
[d16]: https://github.com/LooperSalty/AnyXboxX/commit/b15d8821bffcd8fbc98e56f41daf07fc91118192
[warp]: https://github.com/LooperSalty/AnyXboxX/commit/becaf7829d2aa03c293e0b52125fc740c5590ea1
[bc7]: https://github.com/LooperSalty/AnyXboxX/pull/202
[pillow]: https://github.com/akimfomin/PortBridge/blob/b1c330e5c03f3467a73a593cb7a4edcc8180dafd/research/anyxboxx-188-textures/BC7-INDEPENDENT.md
[fma]: https://github.com/LooperSalty/AnyXboxX/pull/203
[c133]: https://github.com/LooperSalty/AnyXboxX/commit/71d4c615c6981280b95c11290fd48ef015b5d4cb
[lyrnc]: https://github.com/akimfomin/PortBridge/issues/19#issuecomment-7136020663
[gfx]: https://github.com/LooperSalty/AnyXboxX/pull/188#issuecomment-7166158013
[gfxcode]: https://github.com/LooperSalty/AnyXboxX/commit/c5ca937c371d8b21e56feb36f3d009ecffe5765a
[frame]: https://github.com/5headsmartbtw/leonida-framelab/commit/d1da938ecf7b4e3d3faf40e5046907ba48986125
[joe]: https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7160148587
[klbf]: https://github.com/xcl-dev/xcl/pull/1100#issuecomment-7144197194
[victory]: https://github.com/Marvisak/VIctory/pull/571#issuecomment-7128201680
[main90]: https://github.com/akimfomin/PortBridge/tree/2223a0b6a4dbaac1e98f8f90204b190296c4ef75/research/pipeline-readiness/ssa-quad-projection
[ssa]: https://github.com/akimfomin/xcl/commit/5d04cc10fa11654179d4bde0c1fcdc1d7ffb2cbc
[raw]: https://github.com/akimfomin/PortBridge/blob/806a4c0dec2364c8881e1efb437964ac4aa42b27/research/pipeline-readiness/structural-suite/night/vulkan/mobile-nerf/translated/measurements.json
[receipt]: ../research/pipeline-readiness/structural-suite/night/ssa-mask-projection/consumer-demand
[ask87]: https://github.com/akimfomin/PortBridge/issues/87
[wave]: https://github.com/akimfomin/xcl/commit/d3e7725f9f48c39c18e7b6e011ec76423edb0004
[dark]: https://github.com/xcl-dev/xcl/issues/2584#issuecomment-7178879816
[luck]: https://github.com/xcl-dev/xcl/issues/2584#issuecomment-7179418085
[wrun]: https://github.com/akimfomin/PortBridge/blob/6b772bc2805809e966ddc42bb933f10546e361ec/research/pipeline-readiness/structural-suite/night/wave32-carry/precise/README.md
[scratch]: ../research/xcl-compact-scratch-adoption
[kal]: https://github.com/xcl-dev/xcl/pull/2322#issuecomment-7167441435
[ett]: https://github.com/xcl-dev/xcl/pull/2126#issuecomment-7162128623
[dfb]: https://github.com/akimfomin/xcl/commit/dfb580beccbc1fe4353544a5068245d502de9bfa
[c1713]: https://github.com/ubiquitarianism/leonida/pull/1713
[pot]: https://github.com/ubiquitarianism/leonida/pull/1713#issuecomment-7161475134
[fork]: https://github.com/clquwu/leonida-ultimate/commit/e7124f97bff187968a30931fb31e7c42bd88622b
[cbench]: https://github.com/akimfomin/PortBridge/tree/049b46286518c20d98dc74ae700e66599110d964/research/continued-layout-range-coalescing
[k78]: https://github.com/akimfomin/PortBridge/pull/78
[kfix]: https://github.com/akimfomin/PortBridge/commit/14bacd57bca9d7244f8ba964b5ce499248f21bc2
[k84]: https://github.com/akimfomin/PortBridge/issues/84#issuecomment-7179304828
[k85]: https://github.com/akimfomin/PortBridge/issues/85#issuecomment-7175680680
[nv]: https://github.com/nvpro-samples/vk_compute_mipmaps/issues/4#issuecomment-7171169383
[mip]: https://github.com/akimfomin/PortBridge/blob/cb0faec3b66e9d97f120de17288f1e5435757156/research/mipmap-contract/benchmark/OPEN-TEXTURES.md
[nvrepo]: https://github.com/nvpro-samples/vk_compute_mipmaps/tree/6c248f554e91329875e9860f2258019a32b44ee9
[bl]: https://github.com/akimfomin/PortBridge/tree/88cede556d9613a6e09964a1c7fdc15fc9449a0c/research/geometry-residency/viewport
[hal]: https://github.com/akimfomin/PortBridge/tree/c07750453d6b0b70218a5f94edd851deb1500b8f/research/halide-gpu-waits
[arch77]: https://github.com/akimfomin/PortBridge/tree/64280ea4688f152100360403adb33f527f36c0a9/research/pipeline-readiness
[pr77]: https://github.com/akimfomin/PortBridge/pull/77
[p77lane]: https://github.com/akimfomin/PortBridge/blob/9c2616998e176806565ee1a0076dc4efb7ae4dc1/research/pipeline-readiness/structural-suite/LANE-MASKS.md
[ref62]: https://github.com/akimfomin/PortBridge/tree/1c74fd6253bcb5c20ab8be7db56e5ee4df61f7e3/research/transfer-planner/physical
[ref67]: https://github.com/akimfomin/PortBridge/tree/52934fc07afd5039f1234fc58450afea41e9bc26/research
[ref74]: https://github.com/akimfomin/PortBridge/tree/d78d300a3659e6ecb7a621a607aacaa88af4a64b/research
[eco]: ECOSYSTEM-AUDIT-2026-11-25.md
[license]: ../LICENSE
[future]: https://github.com/akimfomin/PortBridge/issues/91
[maint]: PASSIVE-MAINTENANCE.md
[forms]: https://akimfomin.github.io/PortBridge/#/lab
[coverage]: https://akimfomin.github.io/PortBridge/data/health.json

[forkline]: https://github.com/clquwu/leonida-ultimate/compare/e7124f97bff187968a30931fb31e7c42bd88622b...c9bd989eef71eb0513292b9a405d2c5912a1c069
[added]: https://github.com/Ahmet-Dedeler/awesome-gta6-reverse-engineering/issues/25#issuecomment-7164547746
[declined]: https://github.com/vuyp/gta6-pc-race/issues/6#issuecomment-7160857502
[halinputs]: https://github.com/akimfomin/PortBridge/blob/c07750453d6b0b70218a5f94edd851deb1500b8f/research/halide-gpu-waits/REPRODUCTION_INPUTS.md
[hallicense]: https://github.com/halide/Halide/blob/v22.1.0/LICENSE.txt
[board]: https://github.com/Github-Samuel/sixonpc/blob/e721e0f98d4baf3dd0a95e70c4555410f33a98c2/board.mjs#L187
