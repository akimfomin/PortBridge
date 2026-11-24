# Какие проекты отслеживает PortBridge

PortBridge читает открытые задачи, изменения и сведения о проверках. Список источников помогает найти работу за пределами своей команды. Совместные проверки и переносы согласуют сопровождающие.

| Проект | За чем следим |
| --- | --- |
| [Leonida Continued](https://github.com/ubiquitarianism/leonida) | Сборки, проверки Vulkan и SPIR-V, порядок интеграции исправлений |
| [LeonidaReforge](https://github.com/LeonidaReforge/Leonida) | Публичный репозиторий и страница организации возвращают 404. Последнее успешное обновление PortBridge было 24 ноября в 21:21:57 МСК, в 21:41:02 МСК сборка уже видела 404. Проверенная история сохранена. Новый адрес от команды пока не подтверждён. [Журнал обновления](https://github.com/akimfomin/PortBridge/actions/runs/45461886343/job/138686401465) · [Запрос в PortBridge](https://github.com/akimfomin/PortBridge/issues/9) |
| [Leonida CE](https://github.com/IAmNotSiob/leonida-ce) | Изменения в прямом продолжении Leonida, которые могут пригодиться другим веткам |
| [VIctory](https://github.com/Marvisak/VIctory) | Реализация графики через D3D12 и тесты перевода RDNA2 в DXIL |
| [XCL](https://github.com/xcl-dev/xcl) | Проверки GPU, перевод шейдеров и отдельные сценарии Wave32/Wave64. Старые ссылки на `ivall/xcl` ведут к тем же работам. |
| [AnyXboxX](https://github.com/LooperSalty/AnyXboxX) | Синтетические проверки эталонного интерпретатора RDNA2 и генерации HLSL. [Принятый тест LDS](https://github.com/LooperSalty/AnyXboxX/pull/129) |
| [KestrelX](https://github.com/Batushn/KestrelX) | Синтетические проверки шейдеров и локальной памяти на AMD и NVIDIA |
| [XPortPC](https://github.com/Its3rr0rsWRLD/XPortPC) | Компактные тесты D3D12 и чтения данных между потоками |
| [Rebox](https://github.com/idvwork/rebox) | Отдельный Linux/Vulkan-путь для сравнения результата вычислительных шейдеров |
| [Scarlett Layer](https://github.com/jadeowaowa/scarlett-layer) | Синтетические сравнения RDNA2 и D3D12 и публичные проверки на WARP. Есть готовый случай для сравнения порядка операций FMA. [Исходный тест](https://github.com/jadeowaowa/scarlett-layer/blob/0e436b3e1c654765b193c1cb705918fbf101b10b/src/tests/scarlett_tests/tests_rdna2_oracle.cpp#L31-L46) |
| [Xbox2Windows](https://github.com/R0Y00/Xbox2Windows) | Синтетический тест сравнивает результаты обхода BVH на процессоре и GPU. Отдельная проверка измеряет нативный Wave64. [Опыты](https://github.com/R0Y00/Xbox2Windows/blob/c864f1380f0f408a50822470cbe3ce24c969fec6/docs/experiments.md) · [Отчёты](https://github.com/R0Y00/Xbox2Windows/issues/1) |
| [SceneGate VI](https://github.com/7jycwjmbfn-eng/scenegate-vi) | Синтетический гостевой тест D3D12 проверяет чтение кадра и треугольник. Сборка с гостевым DXIL проверяет ещё и результат вычислений. [Исходный тест](https://github.com/7jycwjmbfn-eng/scenegate-vi/blob/804b4f81cf2ce74ee085da0783442a37dfbb0e9e/tests/guest/d3d12_bridge_check.cpp) |
| [Palmwave](https://github.com/fablinoo/palmwave) | Проверка, что данные sparse-ресурса доступны после сигнала очереди. Перенос уже открыт в [XCL #433](https://github.com/ivall/xcl/pull/433). |
| [TuxBox](https://github.com/brcly/TuxBox) | Разбор времени кадров и перекрывающейся работы команд Vulkan. |
| [OpenScarlett](https://github.com/californiaAlmonds/OpenScarlett) | Проверки оконного представления кадров на WARP и звука через WASAPI. |
| [OpenScarlett Community Edition](https://github.com/OpenCommunityEdition/OpenScarlett) | Проверки памяти, включая выравнивание и общие страницы. [Лицензии компонентов](https://github.com/OpenCommunityEdition/OpenScarlett/blob/6ec7598ecd0746b89523e8dbf82bcafda9c52885/README.md#L209-L214) |
| [PercyScarlett](https://github.com/rpatty-dev/PercyScarlett) | Проверки вызовов PresentX и создания звукового движка XAudio2. |
| [VIctory macOS](https://github.com/pragyaangaur/VIctory-macOS) | Отдельная реализация Metal и отчёты автора о проверках на Apple M4. |
| [XValkyrie](https://github.com/sammwyy/xvalkyrie) | Синтетический тест проверяет входы, выходы и предел в четыре вершины геометрического шейдера для списка прямоугольников. [Исходный тест](https://github.com/sammwyy/xvalkyrie/blob/4e02c6815d254764a266a2de30994d96cfaef0b0/tests/console_shader.cpp#L160-L184) |
| [Holy Interoperability](https://github.com/mewiof/Holy-Interoperability) | Синтетический тест D3D12 сверяет пиксели после перестановок потоков внутри группы из четырёх. PortBridge получает коммиты и результаты CI. Список PR недоступен через GitHub API. [Исходный тест](https://github.com/mewiof/Holy-Interoperability/blob/a991f51c6726b390ba85bbfed1b27434f28201b1/tests/unit/test_shader_execute.cpp#L358-L417) |
| [Scarlett Commons](https://github.com/scarlett-commons/scarlett-commons) | Общие синтетические тесты шейдеров и формат отчётов. PortBridge проверил первый случай сложения на CPU-интерпретаторе Continued. [Воспроизведение](../contrib/scarlett-commons-add-basic) |
| [Five Star Recomp](https://github.com/ThatRecompDev/five-star-recomp) | В исходниках есть сравнение операций над потоками через WARP с расчётом на CPU. [Исходный тест](https://github.com/ThatRecompDev/five-star-recomp/blob/2d1aee93adccd6b2c5e34ab0427c33daa008dce8/tests/FiveStar.Shaders.Tests/WaveEmulationTests.cs#L34-L59) |
| [Leonida FrameLab](https://github.com/5headsmartbtw/leonida-framelab) | PortBridge независимо проверил четыре варианта передачи кадров через Vulkan на RTX. Отдельный прогон на AMD открыт в Test Lab. [Отчёт](https://github.com/5headsmartbtw/leonida-framelab/pull/12#issuecomment-7142089405) · [Задача Test Lab](https://akimfomin.github.io/PortBridge/?lang=ru#/lab?task=framelab-12-vulkan-handoff) |

Сверяйте одинаковый вход и ожидаемый результат на каждом стенде. При переносе теста или кода указывайте исходный репозиторий и автора. [Где нужна помощь](PORTING-WORK.md) · [Предложить источник или улучшение](https://github.com/akimfomin/PortBridge/issues/new?template=idea.yml)

## Как находим дополнительные источники

Сверено 24 ноября 2026 года. Трекеры помогают найти репозиторий, обсуждение или инструмент. В каталог PortBridge попадают ссылки на проверенные исходники, а сведения о тесте привязываются к версии и отчёту автора.

| Трекер | Как использовали |
| --- | --- |
| Six on PC | JSON даёт ссылки на проекты и инструменты, RSS — новости. По ссылке проверили исходники и синтетические тесты Xbox2Windows. Лицензия на данные трекера не найдена. [JSON](https://sixonpc.com/data.json) · [RSS](https://sixonpc.com/feed.xml) · [Репозиторий](https://github.com/Github-Samuel/sixonpc) |
| PortWatch VI | В запросе на добавление проекта нашли SceneGate VI и сверили файл теста и лицензию MIT. JSON и RSS доступны. Лицензия на данные трекера не найдена. [Запрос #48](https://github.com/4lwayz/portwatch-vi/issues/48) · [JSON](https://portwatch-vi.xyz/data/tracker.json) · [RSS](https://portwatch-vi.xyz/news/feed.xml) |
| GTA VI PC Race | Публичная страница подсказывает, какие репозитории и обсуждения стоит открыть. Стадии и прогнозы принадлежат редакции трекера. [Страница и методика](https://vuyp.github.io/gta6-pc-race/) |

Обычная синхронизация загружает открытые задачи, PR и коммиты отслеживаемых репозиториев. Она также проверяет три трекера и поиск GitHub с интервалом не менее шести часов для каждого источника. PortBridge сохраняет имена репозиториев и ссылку на источник обнаружения. Полученные ссылки идут на проверку и не подключают репозиторий к индексу автоматически. При недоступности источника его последний успешный список помечается как сохранённый.

На странице [«Проекты»](https://akimfomin.github.io/PortBridge/#/projects) открываются карта возможностей и список кандидатов. Каждая запись карты относится к одному коду, отчёту, тесту или принятой правке. Сведения доступны также в [JSON](https://akimfomin.github.io/PortBridge/data/ecosystem.json) и через MCP `portbridge_ecosystem`. Для партнёрских сайтов доступна отдельная [очередь задач Test Lab](TEST-LAB.md#for-integrations).
