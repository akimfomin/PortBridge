# Какие проекты отслеживает PortBridge

PortBridge читает открытые задачи, изменения и сведения о проверках. Список источников помогает найти работу за пределами своей команды. Совместные проверки и переносы согласуют сопровождающие.

| Проект | За чем следим |
| --- | --- |
| [Leonida Continued](https://github.com/ubiquitarianism/leonida) | Сборки, проверки Vulkan и SPIR-V, порядок интеграции исправлений |
| [LeonidaReforge](https://github.com/LeonidaReforge/Leonida) | Переносы из Continued, отдельные прогоны на Vulkan и ограничения применимости |
| [Leonida CE](https://github.com/IAmNotSiob/leonida-ce) | Изменения в прямом продолжении Leonida, которые могут пригодиться другим веткам |
| [VIctory](https://github.com/Marvisak/VIctory) | Реализация графики через D3D12 и тесты перевода RDNA2 в DXIL |
| [XCL](https://github.com/ivall/xcl) | Проверки GPU, перевод шейдеров и отдельные сценарии Wave32/Wave64 |
| [AnyXboxX](https://github.com/LooperSalty/AnyXboxX) | Синтетические проверки эталонного интерпретатора RDNA2 и генерации HLSL. [Принятый тест LDS](https://github.com/LooperSalty/AnyXboxX/pull/129) |
| [KestrelX](https://github.com/Batushn/KestrelX) | Синтетические проверки шейдеров и локальной памяти на AMD и NVIDIA |
| [XPortPC](https://github.com/Its3rr0rsWRLD/XPortPC) | Компактные тесты D3D12 и чтения данных между потоками |
| [Rebox](https://github.com/idvwork/rebox) | Отдельный Linux/Vulkan-путь для сравнения результата вычислительных шейдеров |
| [Scarlett Layer](https://github.com/jadeowaowa/scarlett-layer) | Синтетические сравнения RDNA2 и D3D12 и публичные проверки на WARP. Есть готовый случай для сравнения порядка операций FMA. [Исходный тест](https://github.com/jadeowaowa/scarlett-layer/blob/0e436b3e1c654765b193c1cb705918fbf101b10b/src/tests/scarlett_tests/tests_rdna2_oracle.cpp#L31-L46) |

Сверяйте одинаковый вход и ожидаемый результат на каждом стенде. При переносе теста или кода указывайте исходный репозиторий и автора. [Где нужна помощь](PORTING-WORK.md) · [Предложить источник или улучшение](https://github.com/akimfomin/PortBridge/issues/new?template=idea.yml)
