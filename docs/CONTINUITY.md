# Continue public compatibility work across projects

[Open pilot thread](https://github.com/akimfomin/PortBridge/issues/41) · [Test Lab](https://akimfomin.github.io/PortBridge/#/lab) · [По-русски](#по-русски)

If a source becomes unavailable, bring one public result that another team can use. Record the original author, exact revision, test input, setup, expected and observed result, and limits. Use the pilot thread to link the work to a current technical question. The author chooses whether to continue with it. The receiving team decides what to review and adopt.

We keep working public references and our own reproduction notes. Share source or artifacts only under applicable permissions and with the required notices. Use synthetic tests. Leave private data, game files, and credentials out of requests.

Record who reproduced the check and link the receiving team's decision. A local replay, a delivered report, and adoption are separate steps.

## Worked example with Continued #1026

yawn-animals added a one-line wait to the synthetic LDS test. The original report is still public in Continued. On an RX 6800 XT under Arch Linux the native run returned word 7 as `0x064aabcf` before the fix and `0x3579badc` after it. morodirule separately ran the translated test on an RTX 4070 under Linux and reported zero mismatches. GitHub closed the PR after its head fork was deleted. The change remains available in the original commit and was absent at the checked Continued main revision. [Author report](https://github.com/ubiquitarianism/leonida/pull/1026) · [RTX report](https://github.com/ubiquitarianism/leonida/pull/1026#issuecomment-7138695955) · [Closure event](https://github.com/ubiquitarianism/leonida/pull/1026#event-37167321018)

Use Git and Python 3.12 in a new public Continued checkout. Set your own Git identity for the local cherry-pick. The fetch must identify `40a2b1c6b60aac005cbe2ecaf4b1130a630d6494` and patch ID `4409b6894901e71ee6148c8dc752131ca1d18921`. Stop if the source is missing or those values differ.

```sh
git clone --no-checkout --filter=blob:none https://github.com/ubiquitarianism/leonida.git continued-1026-replay
cd continued-1026-replay
git fetch origin refs/pull/1026/head
git rev-parse FETCH_HEAD
git show --format= FETCH_HEAD | git patch-id --stable
```

After the two identifiers match, continue in the same checkout.

```sh
git switch --detach 6293c1c4f88c7ea2088ec595fea51362f1759996
git cherry-pick -x 40a2b1c6b60aac005cbe2ecaf4b1130a630d6494
git show --format= HEAD | git patch-id --stable
python -B -I tests/test_shader_checks.py
```

The local cherry-pick retains the author and the original commit reference. Its patch ID matches the original and it changes only `runtime/test/shaders/cs_lds_b64_cmpst.asm`. PortBridge ran all 87 CPU shader checks. It also got identical translated listings and all eight expected words on the pinned base and the replay, including `0x3579badc` at word 7. The hardware scheduling result comes from the author's original AMD run. [PortBridge case](https://akimfomin.github.io/PortBridge/cases/pb-0019.html) · [Original commit](https://github.com/ubiquitarianism/leonida/commit/40a2b1c6b60aac005cbe2ecaf4b1130a630d6494) · [Continued license](https://github.com/ubiquitarianism/leonida/blob/40a2b1c6b60aac005cbe2ecaf4b1130a630d6494/README.md#license)

The public Continued patch stays under its upstream terms. To resume the submission, work with the original author and the existing claim on Continued's board. The local replay is a verified handoff candidate. [Original claim](https://github.com/ubiquitarianism/leonida/issues/14#issuecomment-7138548249)

## Active places to continue

- Continued needs an independent AMD run for the exact synthetic 32-draw A/B in #511. Both pipeline modes should match the expected pixels. The omitted-draw control should show a mismatch. [Windows AMD task](https://akimfomin.github.io/PortBridge/#/lab?task=continued-511-repeated-draw)
- Scarlett Commons and Continued have a shared CPU case with an intentional failing control. The first run only needs Git and Python. [CPU task](https://akimfomin.github.io/PortBridge/#/lab?task=scarlett-commons-continued-add-basic)
- Continued #701 has a separate GPU readback question for ecox982745's exact synthetic D16 XYZ fixture. The independent CPU and general Wave64 graphics checks are already recorded. [Focused D16 request](https://github.com/akimfomin/PortBridge/issues/4#issuecomment-7142090936)
- 5headsmartbtw opened the attributed ports #996 and #1001 in Continued before the outage. In their separate FrameLab project, PortBridge independently passed all four binary and timeline semaphore cases on RTX 4070 Ti SUPER, including the cross-family queue check. [Public claim](https://github.com/ubiquitarianism/leonida/issues/14#issuecomment-7134638584) · [Continued #996](https://github.com/ubiquitarianism/leonida/pull/996) · [Continued #1001](https://github.com/ubiquitarianism/leonida/pull/1001) · [FrameLab report](https://github.com/5headsmartbtw/leonida-framelab/pull/12#issuecomment-7142089405)
- tahffo68hk-hash also has ongoing work in Continued that started before the outage. An independent tester reported a separate hardware run in #528. [Continued #528](https://github.com/ubiquitarianism/leonida/pull/528) · [Hardware report](https://github.com/ubiquitarianism/leonida/pull/528#issuecomment-7141739426)

The original Reforge address returned 404 at the 24 November check. The public author commits for the D16 fix and the presenter test were still reachable. They preserve links to the work and its authors. [Reforge](https://github.com/LeonidaReforge/Leonida) · [D16 by ecox982745](https://github.com/ecox982745/Leonida/commit/a300ba63d1a9a4cdfde1d64f136728545b4ab7b8) · [Presenter test by rizzzz64](https://github.com/rizzzz64/Leonida/commit/b84739e39aee69d2611dfc3982cc2ef35f876916)

## По-русски

Если исходный репозиторий недоступен, предложите один публичный результат. Укажите автора, ссылку, лицензию или разрешение, точную версию, стенд, ожидаемый и фактический результат. PortBridge поможет проверить, что его можно повторить и в каком действующем проекте он полезен. Автор выбирает, продолжать ли работу, принимающая команда решает, что использовать. [Публичная ветка пилота](https://github.com/akimfomin/PortBridge/issues/41)

В примере yawn-animals правка сохранилась в публичной истории Continued #1026 после удаления форка. Команды выше переносят её на проверенную версию Continued с сохранением авторства. На CPU прошли 87 проверок. Исходный замер поведения на AMD доступен в отчёте автора. [Карточка с результатами](https://akimfomin.github.io/PortBridge/cases/pb-0019.ru.html)

Если хотите взять готовую задачу, есть проверка 32 кадров на AMD под Windows и отдельный тест на процессоре для Scarlett Commons. [Задача AMD](https://akimfomin.github.io/PortBridge/?lang=ru#/lab?task=continued-511-repeated-draw) · [Задача CPU](https://akimfomin.github.io/PortBridge/?lang=ru#/lab?task=scarlett-commons-continued-add-basic)
