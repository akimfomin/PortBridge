# Координация PortBridge · две серии проверок · 28 ноября 2026, МСК

PortBridge сверил 20 открытых PR с актуальными целевыми ветками шести проектов и ещё 20 пар потенциально пересекающихся PR. В первой серии 16 чистых совмещений и 4 конфликта. Во второй серии 12 чистых совмещений и 8 конфликтов. Проверки выполнялись в изолированных Git-репозиториях. Для пар использованы полные вершины PR вместе с их зависимостями.

Для каждого PR проверены существующие запуски GitHub Actions на точной вершине. У 9 PR успешные прогоны, у 3 есть ошибки, у 8 ожидается разрешение на запуск. В таблице 20 следующих проверок поведения. В эту серию вошли проверки Git и просмотр уже выполненных CI. Отдельные GPU-прогоны требуют тестировщика. Полный результат и закреплённые SHA доступны в [JSON](coordination-waves-2026-11-28.json).

## Переданные результаты

- Vice-Tay сохранила заявки в своём обсуждении. PortBridge предложил проверять сразу список свободных задач и возвращать найденные проверки в исходный PR без установки. Согласие на пилот с PortBridge пока не подтверждено. [Решение TaynanGT по своему обсуждению](https://github.com/TaynanGT/Vice-Tay/issues/273#issuecomment-7219416199) · [Предложение PortBridge](https://github.com/TaynanGT/Vice-Tay/issues/273#issuecomment-7230521445)
- Vice-Tay #388 и #379 совмещаются чисто. Передали совместный контроль двух отображений памяти и проверки уведомлений для обеих таблиц текстур. [Передача авторам](https://github.com/TaynanGT/Vice-Tay/pull/388#issuecomment-7230619436)
- KainanP реализовал поведение PortBridge для занятого пула AnyXboxX и добавил тест перехода с 4 на 2 блока. Позже PortBridge выявил конфликт с актуальным `main`, где порог зависит от конфигурации. В тесте следует использовать фактический порог после rebase. [Подтверждение автора](https://github.com/LooperSalty/AnyXboxX/pull/550#issuecomment-7230084159) · [Следующая правка](https://github.com/LooperSalty/AnyXboxX/pull/550#issuecomment-7230573166)
- Для AnyXboxX открыта одна проверка на 12 ГБ. Приглашён Anon64 на основании его опубликованных замеров XCL на RTX 3060 12 ГБ. Результат пока не поступил. [Задача Test Lab](https://github.com/akimfomin/PortBridge/issues/132) · [Приглашение](https://github.com/akimfomin/PortBridge/issues/132#issuecomment-7230663294)
- Совмещение XCL #2898 с #3039 потребовало разнести объявления двух пулов. Локально собрали дерево без конфликтных маркеров. `git diff --check` прошёл. Сборка и проверки поведения этого дерева ещё открыты. throny независимо опубликовал конфликт и предложил сначала принимать #2898. Дальнейшая проверка должна исключить попадание индекса системной памяти в свободный пул видеопамяти. [Результат рецензента XCL](https://github.com/xcl-dev/xcl/pull/3039#issuecomment-7230644016)

У VIctory уже есть публичная таблица заявок, Continued требует объявлять выбранную работу до открытия PR, XCL ведёт подтверждаемую двумя участниками таблицу дублей. Эти процессы дают собственные точки для передачи межкомандных находок. [VIctory](https://github.com/Marvisak/VIctory/issues/1633) · [Continued](https://github.com/ProjectLeonida/mandy/issues/1608) · [XCL](https://github.com/xcl-dev/xcl/issues/1607)

## Серия 1 · 20 PR против принимающих веток

| PR | Целевая ревизия и дерево | CI на вершине | Следующая проверка |
| --- | --- | --- | --- |
| [TaynanGT/Vice-Tay #388](https://github.com/TaynanGT/Vice-Tay/pull/388) | `fe7c6e52` · Чисто | Нет прогона | Run the two `a_title_write_*` regressions. With #379 also applied, repeat with two mapped addresses and a write that straddles a mapped range. Check bytes and notices independently. |
| [TaynanGT/Vice-Tay #357](https://github.com/TaynanGT/Vice-Tay/pull/357) | `fe7c6e52` · Чисто | Нет прогона | Repeat an interleaved same-scene comparison with heap pacing off/on. Record visible spikes and rendered frame times on Series S and Series X separately. |
| [TaynanGT/Vice-Tay #263](https://github.com/TaynanGT/Vice-Tay/pull/263) | `fe7c6e52` · Чисто | Нет прогона | Run `stress_decommit_recommit_reuse_no_corruption_and_os_commit_drops` after resolving the target tree. Check contents after reuse and private commit separately. |
| [TaynanGT/Vice-Tay #379](https://github.com/TaynanGT/Vice-Tay/pull/379) | `fe7c6e52` · Чисто | Нет прогона | Run the pinned two-view Windows regression. Check both texture heaps and the unrelated page, with completed writes and with a notice drain during a copy. |
| [LooperSalty/AnyXboxX #550](https://github.com/LooperSalty/AnyXboxX/pull/550) | `4079f2b5` · Конфликт | Нет прогона | Run both busy-pool controls. After rebase use the effective configured pool line for the 12 GB test and preserve the 81%-fill observation at the old head. |
| [LooperSalty/AnyXboxX #568](https://github.com/LooperSalty/AnyXboxX/pull/568) | `4079f2b5` · Конфликт | Нет прогона | After resolving host.rs, run `timing_notes_commands_without_full_device_removed_data`. Compare timing off, light DRED with timing, and full DRED marker ordering. |
| [LooperSalty/AnyXboxX #555](https://github.com/LooperSalty/AnyXboxX/pull/555) | `4079f2b5` · Конфликт | Нет прогона | After rebase, compare unset versus main staging-cache reuse and copied mip contents. With the switch on, separately check explicit readback after a base mip change. |
| [LooperSalty/AnyXboxX #350](https://github.com/LooperSalty/AnyXboxX/pull/350) | `4079f2b5` · Конфликт | Нет прогона | After resolving the six target files, run the re-commit/reuse and staged-copy tests on the same tree. Verify the default mode before drawing performance conclusions. |
| [ProjectLeonida/mandy #2405](https://github.com/ProjectLeonida/mandy/pull/2405) | `d4428519` · Чисто | Нет прогона | Check Vulkan replay tile count on Arc A770. Keep native D3D12 separate. In the mixed-mask CPU fixture, reject B while A still reads back. |
| [ProjectLeonida/mandy #2379](https://github.com/ProjectLeonida/mandy/pull/2379) | `d4428519` · Чисто | Нет прогона | Run `tests/test_gpu_results.py` and compare the accepted V100 record. Require all three runs and the named failure in the overview. |
| [ProjectLeonida/mandy #1437](https://github.com/ProjectLeonida/mandy/pull/1437) | `d4428519` · Чисто | Нет прогона | Run `tests/test_run_semantic_tests.py`. Missing or untrustworthy output must fail, while a real success and an explicit permitted skip retain their semantics. |
| [Marvisak/VIctory #3628](https://github.com/Marvisak/VIctory/pull/3628) | `63bcca43` · Чисто | Нет прогона | On the opt-in build, test no SDK folder with a CPU-only command and a GPU command. With official Agility plus compatible WARP, expect a cold generated pipeline and a repeat cache hit. |
| [Marvisak/VIctory #3623](https://github.com/Marvisak/VIctory/pull/3623) | `63bcca43` · Чисто | Нет прогона | Repeat the author’s synthetic slow-list fixture with stable versus delayed timestamp reporting. Preserve the per-command output and avoid a duplicate timestamp readback. |
| [Marvisak/VIctory #3274](https://github.com/Marvisak/VIctory/pull/3274) | `63bcca43` · Чисто | Нет прогона | Use `a_texture_read_with_no_writer_does_not_wait_for_the_texture_map`. Pair it with the late writer at the same memory address to catch false negative caching. |
| [Marvisak/VIctory #2633](https://github.com/Marvisak/VIctory/pull/2633) | `63bcca43` · Чисто | Нет прогона | Run `emit::halves_random_tests` and the focused late cross-half read control on a physical Wave32 device. Track cases that are refused separately. |
| [xcl-dev/xcl #3036](https://github.com/xcl-dev/xcl/pull/3036) | `d1be8103` · Чисто | Нет прогона | On nvidia-dev, compare immediate versus deferred stencil, topology and scissors with one generated pipeline pair. Verify final pixels, the cache and queue order. |
| [xcl-dev/xcl #2898](https://github.com/xcl-dev/xcl/pull/2898) | `d1be8103` · Чисто | Нет прогона | Run `reuse_tile_packs_fuller_heaps_so_nearly_empty_pools_retire`. Check the cooling boundary and a fully empty heap. Keep the system-memory pool separate if combined with #3039. |
| [xcl-dev/xcl #3039](https://github.com/xcl-dev/xcl/pull/3039) | `d1be8103` · Чисто | Нет прогона | Run `a_system_memory_page_is_told_apart_and_cools_in_its_own_pool`. Combine with a same-index local heap control and an L0-backed shader read in a separate run. |
| [fxceless/victory-fork #1286](https://github.com/fxceless/victory-fork/pull/1286) | `2eade68c` · Чисто | Нет прогона | Run `ram_trim` and the GPU copy reuse control on the exact branch. Track private commit and byte equality separately, and isolate the switch if comparing frame times. |
| [fxceless/victory-fork #1126](https://github.com/fxceless/victory-fork/pull/1126) | `2eade68c` · Чисто | Нет прогона | Run `dxil_opt_hw_gpu_bit_exact_parity_and_validation` with a real adapter and the same DXIL baseline. If combined with #1140, compare all four flag combinations. |

XCL #3036, #2898 и #3039 фактически направлены в `nvidia-dev`. Параллельная проверка прямого переноса на `main` дала конфликты. В основной таблице использован `nvidia-dev`.

## Серия 2 · 20 пар

| PR | Проверенные вершины | Дерево Git |
| --- | --- | --- |
| [Vice-Tay #388](https://github.com/TaynanGT/Vice-Tay/pull/388) · [#379](https://github.com/TaynanGT/Vice-Tay/pull/379) | `0334d598` + `ecc003e1` | Чисто |
| [Vice-Tay #388](https://github.com/TaynanGT/Vice-Tay/pull/388) · [#357](https://github.com/TaynanGT/Vice-Tay/pull/357) | `0334d598` + `6d20a254` | Чисто |
| [Vice-Tay #388](https://github.com/TaynanGT/Vice-Tay/pull/388) · [#263](https://github.com/TaynanGT/Vice-Tay/pull/263) | `0334d598` + `4f5de4ec` | Чисто |
| [Vice-Tay #357](https://github.com/TaynanGT/Vice-Tay/pull/357) · [#263](https://github.com/TaynanGT/Vice-Tay/pull/263) | `6d20a254` + `4f5de4ec` | Чисто |
| [Vice-Tay #357](https://github.com/TaynanGT/Vice-Tay/pull/357) · [#379](https://github.com/TaynanGT/Vice-Tay/pull/379) | `6d20a254` + `ecc003e1` | Чисто |
| [Vice-Tay #263](https://github.com/TaynanGT/Vice-Tay/pull/263) · [#379](https://github.com/TaynanGT/Vice-Tay/pull/379) | `4f5de4ec` + `ecc003e1` | Чисто |
| [AnyXboxX #550](https://github.com/LooperSalty/AnyXboxX/pull/550) · [#350](https://github.com/LooperSalty/AnyXboxX/pull/350) | `4d8fb188` + `4142924b` | `pool.rs` |
| [AnyXboxX #555](https://github.com/LooperSalty/AnyXboxX/pull/555) · [#354](https://github.com/LooperSalty/AnyXboxX/pull/354) | `6708faf2` + `b106642e` | `host.rs`, `host.rs`, `resource.rs`, `texture.rs` |
| [AnyXboxX #568](https://github.com/LooperSalty/AnyXboxX/pull/568) · [#570](https://github.com/LooperSalty/AnyXboxX/pull/570) | `2e1939d5` + `6245785d` | `lancer-gta6.md`, `running-gta6.md`, `README-fxceless.md` |
| [AnyXboxX #550](https://github.com/LooperSalty/AnyXboxX/pull/550) · [#555](https://github.com/LooperSalty/AnyXboxX/pull/555) | `4d8fb188` + `6708faf2` | Чисто |
| [VIctory #3615](https://github.com/Marvisak/VIctory/pull/3615) · [#3585](https://github.com/Marvisak/VIctory/pull/3585) | `5b8f14e7` + `af08b8b1` | `watch.rs` |
| [VIctory #3623](https://github.com/Marvisak/VIctory/pull/3623) · [#3627](https://github.com/Marvisak/VIctory/pull/3627) | `8f5927ed` + `c59ae399` | Чисто |
| [VIctory #3274](https://github.com/Marvisak/VIctory/pull/3274) · [#3289](https://github.com/Marvisak/VIctory/pull/3289) | `6964f115` + `6d3e9539` | Чисто |
| [VIctory #2633](https://github.com/Marvisak/VIctory/pull/2633) · [#2711](https://github.com/Marvisak/VIctory/pull/2711) | `1b1ef216` + `f896d26e` | `translate.rs`, `draw.rs`, `shader_cache.rs`, `crosslane_tests.rs`, `lower.rs`, `memory_tests.rs`, `mod.rs`, `synthetic_tests.rs` |
| [xcl #3036](https://github.com/xcl-dev/xcl/pull/3036) · [#2898](https://github.com/xcl-dev/xcl/pull/2898) | `6f3ad70c` + `8cf249e5` | Чисто |
| [xcl #3036](https://github.com/xcl-dev/xcl/pull/3036) · [#3039](https://github.com/xcl-dev/xcl/pull/3039) | `6f3ad70c` + `7cce7d3d` | Чисто |
| [xcl #2898](https://github.com/xcl-dev/xcl/pull/2898) · [#3039](https://github.com/xcl-dev/xcl/pull/3039) | `8cf249e5` + `7cce7d3d` | `sparse.rs` |
| [xcl #2898](https://github.com/xcl-dev/xcl/pull/2898) · [#2759](https://github.com/xcl-dev/xcl/pull/2759) | `8cf249e5` + `e5404036` | `vram.rs` |
| [victory-fork #1286](https://github.com/fxceless/victory-fork/pull/1286) · [#1280](https://github.com/fxceless/victory-fork/pull/1280) | `3f3ec37d` + `97d270bf` | `host.rs`, `shadow.rs` |
| [victory-fork #1126](https://github.com/fxceless/victory-fork/pull/1126) · [#1140](https://github.com/fxceless/victory-fork/pull/1140) | `335c089b` + `f2d68c9d` | Чисто |

## Воспроизведение

Версия PortBridge [`f9da51bb`](https://github.com/akimfomin/PortBridge/commit/f9da51bbef688d4b71beea8c6d8b77f6a3705a84). Для одной записи передайте её публичный URL и точный `target` из JSON. Команда повторно проверяет текущую вершину PR. Если вершина изменилась, результат относится к новой паре ревизий.

```sh
python -m portbridge.merge_check https://github.com/LooperSalty/AnyXboxX/pull/550 4079f2b50b073935a8c64bf575b15f87ec91989b
python -m portbridge.merge_check https://github.com/xcl-dev/xcl/pull/2898 7cce7d3d4625ac8f90f146f1f89f25a613e32e76
python -m portbridge.preflight --url https://github.com/TaynanGT/Vice-Tay/issues/270
```
