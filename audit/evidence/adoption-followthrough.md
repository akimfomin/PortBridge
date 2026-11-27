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

### Continued и Mac

У контрольных версий Continued `b4b7756e8c64e7ae8b310288d543db0e428c0796` и `d1dff7949be62b6609c3c2ca937df7f50fbf1305` совпадает Git blob шейдера `9763e233f63689b87d664c15a37dbe72c99913e4`. Различаются Git blobs оболочки проверки и C++ исполняемого теста. Принимающий прогон должен указать чистый build, точный драйвер и строку с гранью 4. [Рецепт и доказательства](https://github.com/akimfomin/PortBridge/issues/111#issuecomment-7207400733)

VIctory macOS #478 действительно в `main` как `0c0d5ca7f990fa4dee5c088933f2d184fb2229aa`; кандидатом был `273475d713abca9083c78dc5b0e3d47f5bf44c2e`. На Windows и RTX 4070 Ti SUPER 617.14 проверка возможностей D3D12 вернула, в порядке RTV, typed view, typed store, кортежи `86: 1/0/0`, `115: 0/0/0`, `28: 1/1/1`. Сборка и исходник для самостоятельного запуска доступны в публичной карточке. Самостоятельной проверки этими командами на D3DMetal пока нет. [Проба и исходник](https://github.com/akimfomin/PortBridge/issues/110#issuecomment-7207400958) · [Предложение трекеру](https://github.com/4lwayz/portwatch-vi/issues/231#issuecomment-7207455097)

## Earlier outstanding adoption checks

Three new addressed offers were posted to HabibUrRehmanBhattii, Solarthis and Epic-Y. A current upstream decision and a ready input are linked from each. Follow-up replies from a new participant or acceptance of the PortWatch/FrameLab integration have not yet been observed. The GitHub Action, MCP and bare tools still have separate evidence from their technical readiness. No external repository received an installation.
