# Follow-through from the 50 public handoffs

The source of truth for these 50 outbound links is [the first campaign audit](https://github.com/akimfomin/PortBridge/blob/3e53950701713c6259eb7028eef2ae594d948fda/audit/LATEST.md). All 50 original comments were found in public GitHub discussion listings. The entries below have subsequent posts from another human account. Reviews, unrelated updates, requests, an explicit adoption and a separate reproduction remain different outcomes. The other 32 threads had no subsequent public message from another human account at this read.

| Original outbound | Subsequent source links |
| --- | --- |
| [AnyXboxX #454](https://github.com/LooperSalty/AnyXboxX/pull/454#issuecomment-7205087487) | [mauroalvare](https://github.com/LooperSalty/AnyXboxX/pull/454#issuecomment-7205307619) |
| [victory-fork #1393](https://github.com/fxceless/victory-fork/pull/1393#issuecomment-7205145118) | [UwUCammie](https://github.com/fxceless/victory-fork/pull/1393#issuecomment-7205439168) |
| [AnyXboxX #449](https://github.com/LooperSalty/AnyXboxX/issues/449#issuecomment-7205184273) | [KainanP](https://github.com/LooperSalty/AnyXboxX/issues/449#issuecomment-7206246860) |
| [xcl #2910](https://github.com/xcl-dev/xcl/pull/2910#issuecomment-7205205815) | [fromthemoonx](https://github.com/xcl-dev/xcl/pull/2910#issuecomment-7205391801) · [KOLESNiii](https://github.com/xcl-dev/xcl/pull/2910#discussion_r4714525020) · [KOLESNiii](https://github.com/xcl-dev/xcl/pull/2910#pullrequestreview-6081962370) · [KOLESNiii](https://github.com/xcl-dev/xcl/pull/2910#issuecomment-7206489501) |
| [klbf-lab #86](https://github.com/PastiiJay/klbf-lab/issues/86#issuecomment-7205205908) | [PastiiJay](https://github.com/PastiiJay/klbf-lab/issues/86#issuecomment-7205221785) |
| [AnyXboxX #436](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7205213561) | [LooperSalty](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7205296487) |
| [xcl #2908](https://github.com/xcl-dev/xcl/issues/2908#issuecomment-7205310457) | [CryingLaughing](https://github.com/xcl-dev/xcl/issues/2908#issuecomment-7206798381) |
| [VIctory-7900XTX #27](https://github.com/jtrudeau1530/VIctory-7900XTX/pull/27#issuecomment-7205556913) | [UwUCammie](https://github.com/jtrudeau1530/VIctory-7900XTX/pull/27#issuecomment-7205708084) |
| [VIctory-7900XTX #237](https://github.com/avatarmanz/VIctory-7900XTX/pull/237#issuecomment-7205598787) | [Jesper-Andersson](https://github.com/avatarmanz/VIctory-7900XTX/pull/237#issuecomment-7205899562) |
| [VIctory-7900XTX #386](https://github.com/avatarmanz/VIctory-7900XTX/pull/386#issuecomment-7205598843) | [UwUCammie](https://github.com/avatarmanz/VIctory-7900XTX/pull/386#issuecomment-7205984874) · [UwUCammie](https://github.com/avatarmanz/VIctory-7900XTX/pull/386#issuecomment-7206676743) |
| [leonida #2352](https://github.com/ubiquitarianism/leonida/pull/2352#issuecomment-7205599124) | [ecox982745](https://github.com/ubiquitarianism/leonida/pull/2352#issuecomment-7205880035) |
| [victory-fork #1333](https://github.com/fxceless/victory-fork/pull/1333#issuecomment-7205727397) | [CwWwWwW](https://github.com/fxceless/victory-fork/pull/1333#issuecomment-7205834214) |
| [portwatch-vi #233](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7206144658) | [leixner](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7206219321) · [UwUCammie](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7206398500) |
| [xcl #2916](https://github.com/xcl-dev/xcl/pull/2916#issuecomment-7206328392) | [vibryxcx](https://github.com/xcl-dev/xcl/pull/2916#issuecomment-7206399186) |
| [Vice-Tay #91](https://github.com/TaynanGT/Vice-Tay/pull/91#issuecomment-7206299280) | [HabibUrRehmanBhattii](https://github.com/TaynanGT/Vice-Tay/pull/91#issuecomment-7206859809) |
| [victory-fork #1414](https://github.com/fxceless/victory-fork/pull/1414#issuecomment-7206317317) | [Filip722](https://github.com/fxceless/victory-fork/pull/1414#issuecomment-7206583060) |
| [xcl #2920](https://github.com/xcl-dev/xcl/issues/2920#issuecomment-7206406424) | [andrewDoing](https://github.com/xcl-dev/xcl/issues/2920#issuecomment-7206656661) |
| [xcl #2869](https://github.com/xcl-dev/xcl/issues/2869#issuecomment-7206407695) | [Natakout](https://github.com/xcl-dev/xcl/issues/2869#issuecomment-7206623336) |

## Run the existing workflow with an agent

- AnyXboxX #465 merges cleanly on `4340aac1a494b9649c00e0e1ad2c6fbe6ea00e80` at head `f9e426063fff21619ecb5e15498d58a21ade7e77`. Anyone can run the same check using the documented PR+SHA input. The Git test reports no changed test file because the relevant regression sits inside `resource.rs`. [Pinned host test and 8 GB recipe](https://github.com/akimfomin/PortBridge/issues/107#issuecomment-7206929868)
- VIctory #1414 response by Filip722 supplies the exact fixture `4f1640797187b37666cab4a78175830bd20c2ed8` and correction `f189f9a3a670f67feb18a8c6b5efafe3f32ac509`. These public revisions are suitable for a second synthetic hardware report. [Agent recipe and expected outcomes](https://github.com/akimfomin/PortBridge/issues/106#issuecomment-7206930100)
- For XCL CopyTiles and Continued placed write-back, the credited authors already ran the controls that PortBridge suggested. [Evidence submission #108](https://github.com/akimfomin/PortBridge/issues/108) links both exact before/after pairs, what can be borrowed, and what was actually tested. This is a reference for adjacent work without needing to ask the same contributors to repeat it.
- The independent XCL factory comparison is linked in [Lab #103](https://github.com/akimfomin/PortBridge/issues/103#issuecomment-7206944673) alongside the inbox D3D12 experiment. andrewDoing owned the test and measurements. Other vendors remain open.

```sh
python -B -m portbridge.merge_check https://github.com/LooperSalty/AnyXboxX/pull/465 4340aac1a494b9649c00e0e1ad2c6fbe6ea00e80
```

## PortWatch and BM-v1 adoption trial

[The live results widget](https://akimfomin.github.io/PortBridge/partner.html?kind=result) displays the frametime-report story and the attributed Mac report. The existing PortWatch proposal now links the widget. The tracker and any scoring change remain under the maintainer's control. [Updated proposal](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7206556537)

Tested [frametime-report v0.3.0](https://github.com/leixner/frametime-report/releases/tag/v0.3.0), exact commit `2e637f41d10371f542d1fe8eb9c54499e5d267ff`. Make an ordinary `frametime-log v1` file with marks a=0 ms, b=200000 ms, c=400000 ms. Include `scene=city-walk`, `settings.profile=series-s`, `settings.output=1920x1080`. Window a to b has 1,995 intervals of 100 ms followed by 99, 200, 201 ms. Window b to c has 2,000 intervals of 100 ms. Use elapsed milliseconds as the first field of every frame line and the interval as the second field.

```sh
python -I ftreport.py summarize example.ftlog --skip 0 --from-mark a --until-mark b
python -I ftreport.py summarize example.ftlog --skip 0 --from-mark b --until-mark c
```

| Window | Duration | Frames | Freezes above 200 ms | Longest interval | Median-relative stutters |
| --- | ---: | ---: | ---: | ---: | ---: |
| a–b | 200 s | 1,998 | 1 | 201 ms | 0 |
| b–c | 200 s | 2,000 | 0 | 100 ms | 0 |

Both windows passed the tool's checks. The count uses BM-v1's strict threshold, with a separate metric for median-relative stutters. Record the original time origin and window definitions. Do not infer that an interval-based capture has counted idle time before its first present. [Versioned specification](https://github.com/leixner/frametime-report/blob/2e637f41d10371f542d1fe8eb9c54499e5d267ff/SPEC.md) · [Lab discussion](https://github.com/akimfomin/PortBridge/issues/99#issuecomment-7206945697)

## Вторая волна контактов

| Кому | Что было сделано до сообщения | Публичный итог |
| --- | --- | --- |
| nidscode, Vice-Tay | Проверка слияния AnyXboxX #466 и готовый Lab #109 для стенда с 16 ГБ | [Предложение](https://github.com/TaynanGT/Vice-Tay/issues/97#issuecomment-7207146355) |
| KainanP, AnyXboxX | Закреплены отдельно база сравнения одной правки и более поздняя принимающая версия | [Возврат результата](https://github.com/LooperSalty/AnyXboxX/pull/466#issuecomment-7207175840) |
| Endoykoo, новый публичный форк | Сверены два разных отрезка исходного отчёта. 270 секунд относятся ко всему запуску | [Предложение](https://github.com/4lwayz/portwatch-vi/issues/240#issuecomment-7207156664) |
| denisngeu, Glc6 | Отдельно отмечены первая неудачная и вторая удачная попытки загрузки. Производительность относится к успешной попытке | [Предложение](https://github.com/4lwayz/portwatch-vi/issues/237#issuecomment-7207160665) |
| leixner, frametime-report | Воспроизведено ложное совпадение фаз и проверен способ его избежать в выпущенной версии | [Обсуждение](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7207165350) |

На момент повторного чтения все пять сообщений видны в GitHub. В PortWatch #233 UwUCammie вернулся с предложением `capture.phase` и отдельным учётом времени до первого кадра. По остальным новым публикациям ответов пока нет. Также проверены #98, #99, #106 и #107 PortBridge, ответы PortWatch и KLBF. Новое самостоятельное использование пока не подтверждено. Ранее независимые результаты сохраняются в предыдущих разделах. [Ответ UwUCammie](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7207200361) · [Последний найденный успешный запуск по расписанию](https://github.com/akimfomin/PortBridge/actions/runs/45917400112)

### Воспроизведение

```sh
python -B -m portbridge.merge_check https://github.com/LooperSalty/AnyXboxX/pull/466 5a08a334ef216eff98d2c7d9a9166f94c9ef70ed
```

Ожидается `clean merge`, `head=02bc88444ba29bfe47d44b2c76537839117ab2aa`, `merge_base=b6d86cf8226b718d1efd80da1131945840d6820d`, один изменённый исходник `shadow.rs`. Тест рядом с кодом назван `window_budget_counts_the_copies_that_cannot_go`. Ранний блок `shadow::window_tests` и аппаратный прогон с Watch/High описаны в карточке. По этому пункту PortBridge выполнил Git-проверку и сверку исходника. [Форма и полный рецепт](https://github.com/akimfomin/PortBridge/issues/109#issuecomment-7207139616)

Для сравнения фаз сохраните скрипт из комментария к #99 как `compare_capture_phases.py` и скачайте [ftreport.py v0.3.0 на точной ревизии](https://github.com/leixner/frametime-report/blob/2e637f41d10371f542d1fe8eb9c54499e5d267ff/ftreport.py). Запустите `python -I compare_capture_phases.py ftreport.py`. Оба отрезка валидны, по 200 секунд. У первого 9,99 FPS, p95 100 мс и одна пауза больше 200 мс. У второго 10,00 FPS, p95 125 мс и ни одной такой паузы. При равном `scene` вывод `like for like`. После добавления отдельного имени прогретой сцены вывод `NOT like for like (differs in scene)`. Для настоящего холодного старта отдельно фиксируется начало отсчёта и состояние кэша. [Скрипт, результаты и форма ответа](https://github.com/akimfomin/PortBridge/issues/99#issuecomment-7207139869)

Дополнительная проверка после ответа UwUCammie. В команду `summarize` на синтетическом примере добавлены `--set capture.phase=cold_boot --set capture.launchToFirstAcceptedPresentMs=750`. Команда завершилась успешно, но оба поля отсутствуют в `capture` результата. В 750 мс нет измерения реального запуска. Для изменения формата предлагается проверять одинаковую фазу при разных метках, явно разные фазы и пару с отсутствующей фазой. [Проверка версии и условия](https://github.com/akimfomin/PortBridge/issues/99#issuecomment-7207220632)

## Ведущие команды и проверки NVIDIA

### AnyXboxX #476

```sh
python -B -m portbridge.merge_check https://github.com/LooperSalty/AnyXboxX/pull/476 b62053fe70078deac140ec43039d7ce0af3c6b17
```

Результат `clean merge`, head `f482803499f4f10f356922686643cf2f042e6fec`, merge base `4340aac1a494b9649c00e0e1ad2c6fbe6ea00e80`. Три изменённых файла, включая [тесты](https://github.com/LooperSalty/AnyXboxX/blob/f482803499f4f10f356922686643cf2f042e6fec/third_party/victory/crates/victory-shader/src/emit/intersect_tests.rs). Проверка адресной арифметики ниже использует только CPU и не запускает компилятор шейдеров. Сохраните как `check_bvh_address.py` и запустите `python -I check_bvh_address.py`.

```python
import random

u32 = (1 << 32) - 1
u64 = (1 << 64) - 1

def oracle(w0, w1, pointer, pointer_high):
    base = (w0 | ((w1 & 0xff) << 32)) << 8
    full_pointer = pointer | ((pointer_high or 0) << 32)
    return (base + ((full_pointer >> 3) << 6)) & u64

def halves(w0, w1, pointer, pointer_high):
    lo_base = (w0 << 8) & u32
    hi_base = ((w1 & 0xff) << 8) | (w0 >> 24)
    lo_off = ((pointer & ~7) << 3) & u32
    hi_off = (((pointer_high or 0) << 3) | (pointer >> 29)) & u32
    lo = (lo_base + lo_off) & u32
    hi = (hi_base + hi_off + int(lo < lo_base)) & u32
    return (hi << 32) | lo

cases = [(0x00ffffff, 0, 0x25, None), (0x00ffffff, 0, 0x25, 1)]
assert [halves(*v) for v in cases] == [0x100000000, 0x900000000]
rng = random.Random(476)
for i in range(100_000):
    words = [rng.getrandbits(32) for _ in range(4)]
    if i & 1:
        words[-1] = None
    assert halves(*words) == oracle(*words)
print("2 targeted vectors, 100000 deterministic random vectors: PASS")
```

[Переданные результаты](https://github.com/LooperSalty/AnyXboxX/pull/476#issuecomment-7207477061). [Замеры mauroalvare](https://github.com/LooperSalty/AnyXboxX/pull/476#issuecomment-7207479425) подтверждают свои тесты на RTX и небольшой проигрыш 0,005 мс для удачно расположенных четырёх дочерних узлов. Эти GPU-замеры принадлежат автору и не являются измерением игрового кадра.

### VIctory #1419 и XCL

В [AMD RDNA2 ISA, таблица 4](https://docs.amd.com/api/khub/documents/Et~wpu9g~Ffl7d9q0QZ~Og/content#page=24) режимы FP32 занимают биты 0–1 и 4–5, а режимы обработки NaN учитывают биты 8–9. Проверено на коротких контрольных масках, что запись длиной два бита с позиции 2 не пересекается с `0x333`, запись с позиции 1 или 3 пересекается, отдельно пересекаются запись в бит 8 и запись в бит 9. Это различает границы записи, а не доказывает семантику незнакомого участка программы. [VIctory #1419](https://github.com/fxceless/victory-fork/pull/1419#issuecomment-7207409583)

XCL #2931. Автор [свёл независимые замеры](https://github.com/xcl-dev/xcl/pull/2931#issuecomment-7207276633): создаваемые рабочие потоки сократились примерно с 640 до 4, процесс использовал примерно на 10 МиБ меньше пиковой выделенной памяти, холодное время остаётся примерно тем же. В #2939 ettehn проверил другой механизм и дал физический результат в одном синтетическом случае. [Первичный результат](https://github.com/xcl-dev/xcl/issues/2939#issuecomment-7207407756) · [Дополнительная проверка PortBridge](https://github.com/xcl-dev/xcl/issues/2939#issuecomment-7207445228)

### Принятая правка VIctory #1419 и независимый прогон

ByFxbian [прямо подтвердил](https://github.com/fxceless/victory-fork/pull/1419#issuecomment-7207518729), что изменил PR по замечанию PortBridge. На [head `8d1162e31491ca8c462356e921b31f39ee99d58d`](https://github.com/fxceless/victory-fork/commit/8d1162e31491ca8c462356e921b31f39ee99d58d) разрешён только наблюдавшийся непосредственный вызов с записью нуля в двухбитное поле округления FP16/FP64. Прочие изменения MODE по-прежнему отвергаются. Диагностика разделена на неподдержанное выходное значение, модификаторы, запись EXEC и неподдержанный код операции. Автор проверил обновление на RTX 3070.

PortBridge проверил тот же точный head на физической RTX 4070 Ti SUPER, драйвер 617.14, Windows 11 28000.3501, Rust 1.100.0 gnullvm, LLVM-MinGW, набор DXC 1.9.2609.5. Только публичные синтетические программы, без игровой нагрузки.

```powershell
$env:VICTORY_WAVE_PAIRS='1'
$env:VICTORY_WAVE_PAIRS_FP32='non-ieee-rne-ftz'
$env:VICTORY_SHADER_OPT='127'
$env:VICTORY_GROUP_SYNC='2'
$env:VICTORY_WAVE_WHY='1'
cargo test --locked --release -p victory-shader --features host --lib paired_fp32 -- --include-ignored --nocapture --test-threads=1
```

| Синтетическая проверка | Побитовые сравнения на GPU | Результат |
| --- | ---: | --- |
| `nvidia_paired_fp32_min_max` | 20 | PASS |
| `nvidia_paired_fp32_mode_writes` | 3 | PASS, также пройдены пять проверок отказа компилятора |
| `nvidia_paired_fp32_ordered_sum` | 14 | PASS |
| `paired_fp32_refuses_an_unconfirmed_guest_mode` | — | PASS, проверка отказа без подтверждённого режима |

Во всех GPU-случаях диагностика показала `paired=true threads=[32, 1, 1]`, DXIL валидирован. Итог `4 passed; 0 failed; 0 ignored; 260 filtered out`, 4,78 секунды. SHA-256 локального файла тестов `f494ee32b387bf03167b8bfdb23d2d707f2484962c28286e797c2f8d5105d799`. Первый прогон с одним указанием режима дал три отказа и не обеспечил запуск нужного пути. Явное включение парного режима и заданной маски оптимизаций устранило это отличие постановки. Состояние двух программ воды и результата изображения остаётся открытым. [Независимый отчёт PortBridge в PR](https://github.com/fxceless/victory-fork/pull/1419#issuecomment-7207563987)

### Continued и Mac

У контрольных версий Continued `b4b7756e8c64e7ae8b310288d543db0e428c0796` и `d1dff7949be62b6609c3c2ca937df7f50fbf1305` совпадает Git blob шейдера `9763e233f63689b87d664c15a37dbe72c99913e4`. Различаются Git blobs оболочки проверки и C++ исполняемого теста. Принимающий прогон должен указать чистый build, точный драйвер и строку с гранью 4. [Рецепт и доказательства](https://github.com/akimfomin/PortBridge/issues/111#issuecomment-7207400733)

VIctory macOS #478 действительно в `main` как `0c0d5ca7f990fa4dee5c088933f2d184fb2229aa`; кандидатом был `273475d713abca9083c78dc5b0e3d47f5bf44c2e`. На Windows и RTX 4070 Ti SUPER 617.14 проверка возможностей D3D12 вернула, в порядке RTV, typed view, typed store, кортежи `86: 1/0/0`, `115: 0/0/0`, `28: 1/1/1`. Сборка и исходник для самостоятельного запуска доступны в публичной карточке. Самостоятельной проверки этими командами на D3DMetal пока нет. [Проба и исходник](https://github.com/akimfomin/PortBridge/issues/110#issuecomment-7207400958) · [Предложение трекеру](https://github.com/4lwayz/portwatch-vi/issues/231#issuecomment-7207455097)

## XCL #2939 · нативная проверка на второй карте

[Ettehn подтвердил](https://github.com/xcl-dev/xcl/issues/2939#issuecomment-7207601447) добавление контроля PortBridge в локальный набор XCL: 4 passed, 0 failed, 0 skipped на RTX 5070 Ti Laptop (621.24). Его тест подменял результат создания и использовал настоящий исходный объект. Такие проверки подтверждают логику счётчиков XCL.

[CryingLaughing](https://github.com/xcl-dev/xcl/issues/2939#issuecomment-7207685075) затем повторил предложенный контроль на точном `8b957bec6f82495aec940944c6bf47faa02db590` плюс [наблюдатель `384face6`](https://github.com/CryingLaughing/xcl/commit/384face6152aa980be8597d13728cc6c43ad0f90), RTX 4080, 621.01. Два отдельных процесса с заполненным кэшем успешно завершили по 800 вызовов с переданным объектом кэша, ни один не потребовал отдельного повторного вызова без объекта. При сравнении возвращённых байтов с входными длина совпала, содержимое различалось в 619 и 522 случаях, всего 1 141. Счётчик повторного использования XCL вырос на 1 600. Внутреннее состояние кэша драйвера не измерялось.

PortBridge запустил самостоятельный пример на физической NVIDIA RTX 4070 Ti SUPER, драйвер 617.14, Windows 11 28000.3501, LLVM-MinGW и DXC 1.9.2609.5. Шейдер создан специально для теста, подпись ресурсов пуста. Кэш-пакет получен на той же карте через `GetCachedBlob`, а в одном из входов к нему дописаны 16 нулевых байт. Пример сравнивает количество вызовов для двух стратегий из обсуждения. [Контракт D3D12](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ns-d3d12-d3d12_cached_pipeline_state) · [CreateComputePipelineState](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device-createcomputepipelinestate)

Из корня репозитория в Windows, с DXC и Windows SDK-совместимым Clang:

```powershell
dxc -T cs_6_0 -E main -Fo pso.dxil audit/fixtures/d3d12-cache-probe.hlsl
clang++ -std=c++17 -O2 -static audit/fixtures/d3d12-cache-probe.cpp -o pso.exe -ld3d12 -ldxgi
.\pso.exe pso.dxil
```

| Вход на RTX 4070 Ti SUPER | Передано → возвращено, байт | Создания при проверке длины → при сохранении результата |
| --- | ---: | ---: |
| Исходный пакет | 1 422 → 1 422 | 1 → 1 |
| Пакет с 16 нулевыми байтами после конца | 1 438 → 1 422 | 2 → 1 |

Оба первых вызова возвращали `S_OK` во всех четырёх свежих процессах. В первом запуске данные одинаковой длины различались в обеих стратегиях. В трёх повторениях первые данные совпали при варианте `size`, а при варианте `keep` различались. Это наблюдение относится к конкретной последовательности вызовов и драйверу. Равенство содержимого не доказывает попадание в кэш. Стратегия в образце повторяет только развилку после создания. Замеров задержки, запуска игры или производительности приложения не было. Цифры размера относятся к непрозрачному объекту кэша.

[Результат и ссылки на оба внешних отчёта возвращены в XCL](https://github.com/xcl-dev/xcl/issues/2939#issuecomment-7207445228).

### Первый шаг поиска регрессии VIctory

`git rev-list --bisect-vars --ancestry-path 52ac4ec0f8a03f103c146e60228e53612759d435..d154dcb15b1d659eea99ad9fbbcd09eddee23957` выдал `c005a245f073e2897bbb709cdc73fe53eb7d5f9b`, `bisect_good=7`, `bisect_bad=7`, `bisect_all=16`. Проверена достижимость родителя. Это точка первого добровольного запуска, результат которой выбирает половину диапазона. [Вывод передан автору](https://github.com/fxceless/victory-fork/issues/1420#issuecomment-7207661854)

## Новые проверки для ведущих команд

### Стратегия записи кэша в XCL #2940

Источник `ee919a6407afdaefeb295fa0bc3feb0d1868581c`. Для воспроизведения сохраните из [`shaders.rs` исходной ревизии](https://github.com/KOLESNiii/xcl/blob/ee919a6407afdaefeb295fa0bc3feb0d1868581c/crates/xcl/src/shaders.rs#L1668-L1814) код от `enum BlobBuild<P, E>` до комментария перед `used_compute`. Это включает саму функцию и неизменённые восемь тестов автора. Добавьте следующий тест:

```rust
#[test]
fn observes_get_blob_on_uncached_creation() {
    let calls = std::cell::Cell::new(0);
    let built = build_with_blob(None, false, |_| Ok::<_, ()>(42u32), |_| {
        calls.set(calls.get() + 1);
        Some(vec![1u8; 32])
    });
    assert!(matches!(built, BlobBuild::Made { pso: 42, .. }));
    assert_eq!(calls.get(), 1);
}
```

Запуск `rustc --test --edition 2024 --crate-name xcl_blob_checks xcl_blob_checks.rs`, затем `xcl_blob_checks --test-threads=1`. На Windows использован Rust 1.100.0 gnullvm и LLVM-MinGW. Итог 9 passed, 0 failed, 0 ignored. GPU не использовался.

При `XCL_PSO_DISK_CACHE=0` [путь отсутствует](https://github.com/KOLESNiii/xcl/blob/ee919a6407afdaefeb295fa0bc3feb0d1868581c/crates/xcl/src/hle/d3d12x/real.rs#L4530-L4541). В черновике [замыкание всё равно экспортирует и копирует байты](https://github.com/KOLESNiii/xcl/blob/ee919a6407afdaefeb295fa0bc3feb0d1868581c/crates/xcl/src/shaders.rs#L1613-L1634). В [старом пути без файла](https://github.com/xcl-dev/xcl/blob/8b957bec6f82495aec940944c6bf47faa02db590/crates/xcl/src/shaders.rs#L1570-L1580) обе операции пропускались. В случае прогретого кэша старый путь считывал длину без Rust-копии; черновик создаёт Vec ещё до сравнения размера. Рекомендация оставить корректность одного создания, пропускать экспорт без пути и отдельно оценить копирование при прогретом кэше. Сборка всего XCL и аппаратный прогон этого head не выполнялись. [Переданное ревью](https://github.com/xcl-dev/xcl/pull/2940#issuecomment-7207809226)

### Проверка обратной связи для текстур

Проверка [VIctory `4c604661`](https://github.com/fxceless/victory-fork/blob/4c60466140f4bccd2252427b6f2cfbc658c16906/crates/victory-gpu/src/descriptor/host.rs#L2403-L2418) показывает, что отложенная публикация уже сверяет индекс и поколение записи. Аналогичный контроль нужен при чтении отметок кадром позже. Пример моделирует известную при записи команд привязку. При неизвестной привязке результаты следует учитывать как диагностические и исключать из решений об освобождении памяти.

Сохраните следующий пример в файл `feedback.py` и запустите `python -I feedback.py`:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Descriptor:
    view: int
    generation: int

def receive(slots_at_recording, slots_at_readback, sampled_slots):
    return {
        slots_at_recording[slot]
        for slot in sampled_slots
        if slots_at_recording[slot] == slots_at_readback.get(slot)
    }

slot = ("shader-visible-heap-a", 240)
never_sampled = ("shader-visible-heap-a", 241)
old_view = Descriptor(301, 7)
new_view = Descriptor(302, 8)
untouched = Descriptor(303, 4)
recorded = {slot: old_view, never_sampled: untouched}
created_handles = {slot, never_sampled}
samples = {slot}

assert receive(recorded, recorded, samples) == {old_view}
assert {recorded[s] for s in created_handles} - receive(recorded, recorded, samples) == {untouched}
live = {slot: new_view, never_sampled: untouched}
assert {live[s] for s in samples} == {new_view}
assert receive(recorded, live, samples) == set()
other_heap = ("shader-visible-heap-b", 240)
assert receive(recorded, {other_heap: old_view}, samples) == set()
print("PASS: stable sample, unused handle, recycled descriptor, distinct heap")
```

Результат `PASS: stable sample, unused handle, recycled descriptor, distinct heap`. Это проверка правила сопоставления, без оценки стоимости и пригодности реального прототипа. [Переданная проверка](https://github.com/fxceless/victory-fork/issues/1423#issuecomment-7207798274)

## Earlier outstanding adoption checks

Three new addressed offers were posted to HabibUrRehmanBhattii, Solarthis and Epic-Y. A current upstream decision and a ready input are linked from each. Follow-up replies from a new participant or acceptance of the PortWatch/FrameLab integration have not yet been observed. The GitHub Action, MCP and bare tools still have separate evidence from their technical readiness. No external repository received an installation.

## Новые участники и ответы 27 ноября

### VIctory-4GB

Проверяемый SHA форка `b72f3bd9476f745587a674ba5729516137eb1e89`, голова открытого VIctory #1419 `8d1162e31491ca8c462356e921b31f39ee99d58d`, база изменения `1f5d17a6b149f5ef95ba6d0be8826f4f9b62e363`. В Git-репозитории, содержащем все три ревизии:

```text
git merge-tree --write-tree --name-only --merge-base=1f5d17a6b149f5ef95ba6d0be8826f4f9b62e363 b72f3bd9476f745587a674ba5729516137eb1e89 8d1162e31491ca8c462356e921b31f39ee99d58d
```

Выход 1: конфликт содержимого `lower.rs`, конфликты изменения и удаления `paired.rs` и `wave64_after_loop.rs`. Для исходной проверки, где адрес кодирует `lane ^ 32`, модель RDNA 2 выбирает `(lane & 32) | (((lane ^ 32) + offset // 4) & 31)`. Модель старого пути выбирает `((lane ^ 32) + offset // 4) & 63`. При смещении 0 ошибочны все 64 значения старого пути, при 128 оба пути совпадают на всех 64 значениях. Форк уже содержит тест на смещения и частичную активность. Из точного дерева форка предложен один повтор на прежней RTX 3050. PortBridge проверил модель и исходники, физический тест остался открытым. [Функция и тест](https://github.com/Dathinel/victory-4gb/blob/b72f3bd9476f745587a674ba5729516137eb1e89/crates/victory-shader/src/emit/wave64_tests.rs#L91-L145) · [Предложение](https://github.com/Dathinel/victory-4gb/issues/10#issuecomment-7207943312)

```text
cargo test --locked -p victory-shader bpermute_reads_active_sources_within_each_half -- --nocapture
```

### ApexVI

Сохраните [исходный `tools/frametime.py`](https://raw.githubusercontent.com/KevinPratap/ApexVI/9a17be6cd57514a616b9a95e5cb069f28749897f/tools/frametime.py) как `frametime.py` в текущей папке. SHA-256 исходного файла `a183bcbcb15fdebd832dbcc386f4e3ebaa316b3df422c2c6b1b7a0aec3dd21f3`. Пример запускается Python 3, нужны только локальные синтетические строки:

```python
from pathlib import Path
from subprocess import check_output
from tempfile import TemporaryDirectory
import sys

cold = "5 fps, 200 ms/frame (140 preparing: copies 2 ms; 12 on the GPU; 1 copying back), 3400 draws/frame\n" * 2
warm = "20 fps, 50 ms/frame (30 preparing: copies 2 ms; 12 on the GPU; 1 copying back), 3400 draws/frame\n" * 2
with TemporaryDirectory() as tmp:
    for label, rows in [("cold", cold), ("warm", warm), ("mixed", cold + warm)]:
        fixture = Path(tmp) / (label + ".txt")
        fixture.write_text(rows, encoding="utf-8")
        result = check_output([sys.executable, "-I", "frametime.py", str(fixture)], text=True)
        print(label, result.strip())
```

Результаты `cold 2 samples: fps 5.00, ms 200, prep 140`, `warm 2 samples: fps 20.00, ms 50, prep 30`, `mixed 4 samples: fps 12.50, ms 125, prep 85`. Данные участника пока не пересчитывались. [Предложение](https://github.com/4lwayz/portwatch-vi/issues/212#issuecomment-7207963789) · [Готовый рецепт Lab](https://github.com/akimfomin/PortBridge/issues/99#issuecomment-7207139869)

### XCL: очистка кэша

На Windows во временном каталоге создан файл `.last-used`. После `os.utime` для времени на 15 суток раньше первый наблюдатель сохранил решение `age > 14 * 86400`. Второй шаг переписал время тем же `os.utime` на текущее. Повторное чтение давало `false`, прежний результат оставался `true`. Это фиксированный порядок двух чтений из реального файла. Ветку XCL и удаление здесь не запускали. Активность двух процессов и допустимое время хранения остаются отдельными вопросами. [Источник ветки](https://github.com/Koaio/xcl/blob/74698efa53b022a54230038757df67828aa102a9/crates/xcl/src/gpu/recomp/pso.rs#L499-L534) · [Сообщение в XCL](https://github.com/xcl-dev/xcl/issues/2900#issuecomment-7207960004)

### Ответы по прежним проверкам

- **VIctory #1423.** Granite900 описал, как будет хранить ключ из кучи, позиции и поколения для каждой отправки команд. Подтвердил добавление четырёх проверок в прототип. На момент сверки это решение автора в обсуждении. [Ответ](https://github.com/fxceless/victory-fork/issues/1423#issuecomment-7207955353)
- **XCL #2940.** andrewDoing подтвердил замечание шестью прогонами с трассировкой и нашёл копирование 3 070 байт даже при отключённом дисковом кэше. ettehn на RTX 5070 Ti Laptop получил 12 PASS в черновике и с локальным изменением. В исходной версии тестовый blob 1 418 байт заменён на 1 402 байта за один вызов создания. Исполнение и трассировка принадлежат этим участникам. Замера пользовательской задержки и слияния правки ещё нет. [Трассировка](https://github.com/xcl-dev/xcl/pull/2940#issuecomment-7207890471) · [Аппаратный результат](https://github.com/xcl-dev/xcl/pull/2940#issuecomment-7207891768)


## Проверки для VIctory и AnyXboxX 27 ноября

| Получатель | Данные и проверка | Состояние |
| --- | --- | --- |
| spk-c, VIctory | [Исходный замер](https://github.com/fxceless/victory-fork/issues/1418#issuecomment-7207254719). Просмотрены строки профиля в `0211f7925775499770bcaed2ee896ea90e71e449`. Синтетические проверки запуска скрипта: обычная сопоставимая пара, ложное ускорение с пропущенными отрисовками, пустой счётчик очереди, короткий файл и отсутствие фаз. Пример 370,6 → 100 мс сопровождался 5 100 → 350 отрисовками и 4 600 пропусками. [Скрипт и процедура](victory-heap-profile.md) | [Предложение опубликовано](https://github.com/fxceless/victory-fork/issues/1418#issuecomment-7208127401). GPU не запускали. |
| KainanP, AnyXboxX | Ревизия `02bc88444ba29bfe47d44b2c76537839117ab2aa`. Сверены [учёт копий](https://github.com/LooperSalty/AnyXboxX/blob/02bc88444ba29bfe47d44b2c76537839117ab2aa/third_party/victory/crates/victory-gpu/src/shadow.rs#L3267-L3277) и [телеметрия освобождения](https://github.com/LooperSalty/AnyXboxX/blob/02bc88444ba29bfe47d44b2c76537839117ab2aa/third_party/victory/crates/victory-gpu/src/shadow.rs#L3384-L3396). Два входа в CPU-модели `(4 << 20, in_place=true)` и `(8 << 20, in_place=false)` дают 12 МиБ длины диапазонов и 8 МиБ учтённых копий. Отдельная тема VIctory #1250 найдена командой `python -B -m portbridge.preflight --url https://github.com/LooperSalty/AnyXboxX/pull/466 --limit 4`. Проверка исходника #1250 подтвердила, что он устраняет двойное резервирование памяти GPU при смене пути размещения. | [PR #466](https://github.com/LooperSalty/AnyXboxX/pull/466#issuecomment-7208112675) и [Lab #109](https://github.com/akimfomin/PortBridge/issues/109#issuecomment-7207139616) обновлены. Потребление RAM не измерялось. |
| LooperSalty, AnyXboxX | Ревизия `b62053fe70078deac140ec43039d7ce0af3c6b17`, `gameinput.rs`. Из фактических веток `key_code` извлечены принятые имена и правило одного символа. Контроль `Enter/C/Z` → `0x0D/0x43/0x5A`, `Space/LeftShift` → отсутствие события. Оба способа программного ввода используют этот парсер. [Участок исходника](https://github.com/LooperSalty/AnyXboxX/blob/b62053fe70078deac140ec43039d7ce0af3c6b17/third_party/victory/crates/victory-hle/src/modules/gameinput.rs#L1327-L1426) | [Готовая проверка передана](https://github.com/LooperSalty/AnyXboxX/issues/478#issuecomment-7208153664). Физическую клавиатуру, фокус окна и реакцию игры не проверяли. |
