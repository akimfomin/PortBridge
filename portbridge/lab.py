"""Reviewed volunteer checks with public procedures and pinned sources."""

from copy import deepcopy
import re


CHECKED_AT = "2026-11-24T15:51:11Z"
EQUIPMENT = ("amd", "cpu", "nvidia")
STATUSES = ("needs_run", "needs_revision", "awaiting_review", "blocked")
TASK_ID_PATTERN = r"^[a-z0-9-]{1,80}$"
PORTBRIDGE = "https://github.com/akimfomin/PortBridge"
CONTINUED = "https://github.com/ubiquitarianism/leonida"
REFORGE = "https://github.com/LeonidaReforge/Leonida"
XCL = "https://github.com/xcl-dev/xcl"
D16_REVIEW = f"{CONTINUED}/pull/701"
D16_REPRODUCTION = f"{D16_REVIEW}#issuecomment-7131731339"
RECT_REPORT = f"{CONTINUED}/pull/511#issuecomment-7130673446"
RECT_READBACK = f"{CONTINUED}/pull/511#issuecomment-7131186456"
BYTE_CARRY = f"{XCL}/pull/925#issuecomment-7129094971"
PRESENTER_REPORT = f"{REFORGE}/pull/86#issuecomment-7130696664"
FMA = f"{XCL}/pull/1100"
FMA_HEAD = "1b3fbc4bc8c3088e69d78f85a2e73f1cccf4df51"
XCL_SETUP = "https://github.com/akimfomin/xcl/blob"
CARRY = "https://github.com/LooperSalty/AnyXboxX/pull/133"
CARRY_HEAD = "9736508b0d201c641b119d2e4a18fb72f28bdde4"
CARRY_PROBE = f"{PORTBRIDGE}/blob/main/contrib/rdna2-carry-mask/README.md"
CARRY_PROBE_REVISION = "9923c3bba74f4a7f3249e0c820f2e6821327c1f4"
CARRY_REPORT = f"{PORTBRIDGE}/issues/19#issuecomment-7136020663"
CARRY_REPLY = f"{CARRY}#issuecomment-7136721736"
DRAW_SEQUENCE = f"{CONTINUED}/pull/511"
DRAW_HEAD = "88658f1b3fcdca2231358c18d09253a213dc8533"
DRAW_GUIDE = f"{PORTBRIDGE}/tree/main/contrib/continued-repeated-draw"
SCARLETT_ADAPTER = "https://github.com/scarlett-commons/scarlett-commons/issues/32"
SCARLETT_GUIDE = f"{PORTBRIDGE}/tree/de376382b79d75d635c1c04b31e030ebba979036/contrib/scarlett-commons-add-basic"
WAVE64_CASE = "https://github.com/LooperSalty/AnyXboxX/pull/147"
WAVE64_GUIDE = f"{PORTBRIDGE}/tree/main/contrib/rdna2-wave64-bpermute"
FRAMELAB = "https://github.com/5headsmartbtw/leonida-framelab"
FRAMELAB_HANDOFF = f"{FRAMELAB}/pull/12"
FRAMELAB_HANDOFF_HEAD = "82f069e82197e61b97f60bbcbcb7a3af7d3f8e77"


def revision(label, label_ru, repository, sha):
    return {"label": label, "sha": sha, "url": f"https://github.com/{repository}/commit/{sha}",
            "translations": {"ru": {"label": label_ru}}}


TASKS = (
    {
        "id": "pb-9-continued-first-frame",
        "priority": 1,
        "title": "Review the Continued first-frame pixel check",
        "projects": ["continued"],
        "equipment": ["amd", "nvidia"],
        "os": ["Windows"],
        "requirements": ["Vulkan adapter with geometry shader support", "C++ build tools and Vulkan headers"],
        "status": "awaiting_review", "evidence_stage": "reviewed_gpu", "adoption": "pending",
        "source_url": f"{PORTBRIDGE}/issues/9", "procedure_url": RECT_REPORT,
        "evidence_url": RECT_READBACK, "result_url": f"{CONTINUED}/pull/511",
        "revisions": [
            revision("Deferred pipelines #511", "Отложенная сборка #511", "VibeClauding/leonida-continued",
                     "88658f1b3fcdca2231358c18d09253a213dc8533"),
            revision("Rectangle lists #207", "Списки прямоугольников #207", "ubiquitarianism/leonida",
                     "21dc3889280dba49916f63342dab72750d3ee4b9"),
            revision("Vertex-word lifetime guard", "Защита данных вершин", "ubiquitarianism/leonida",
                     "b8572d92dba043bad5507a11931bcb4add7aa568"),
        ],
        "why": "Deferred creation has to preserve the vertex shader data that rectangle generation uses.",
        "evidence": "BadgersMC independently checked both modes on an RTX 3060 Ti. With LloydNicholson's guard, the rectangle and quad pixels matched in both modes.",
        "steps": [
            "Review the Windows Vulkan result and the exact component revisions in the report.",
            "If the team changes the combined code, retest d3d12_rect_list with LEONIDA_LAZY_PSO set to 0 and 1.",
            "Link the receiving decision or the new pixel report in the original discussion.",
        ],
        "expected": "Both modes pass the targeted rectangle check with the expected pixels.",
        "report": ["Combined commit, GPU, driver and Windows build", "Pixel readback and result for both modes"],
        "translations": {"ru": {
            "title": "Рассмотреть проверку пикселей первого кадра в Continued",
            "requirements": ["Видеокарта с Vulkan и поддержкой геометрических шейдеров", "Компилятор C++ и заголовки Vulkan"],
            "why": "При отложенной сборке нужно сохранить данные вершинного шейдера для отрисовки прямоугольников.",
            "evidence": "BadgersMC независимо проверил оба режима на RTX 3060 Ti. С защитой от LloydNicholson пиксели прямоугольников и четырёхугольников совпали в обоих режимах.",
            "steps": [
                "Сверьте результат Windows Vulkan и версии частей сборки в отчёте.",
                "Если общий код изменится, повторите d3d12_rect_list с LEONIDA_LAZY_PSO равным 0 и 1.",
                "Добавьте в исходное обсуждение ссылку на решение команды или новый отчёт о пикселях.",
            ],
            "expected": "Тест прямоугольников проходит в обоих режимах и возвращает ожидаемые пиксели.",
            "report": ["Общий коммит, видеокарта, драйвер и версия Windows", "Пиксели и итоги для обоих режимов"],
        }},
    },
    {
        "id": "pb-5-xcl-wave64",
        "priority": 2,
        "title": "Run the XCL byte-carry test on native Wave64",
        "projects": ["xcl"],
        "equipment": ["amd"],
        "os": ["Windows"],
        "requirements": ["AMD D3D12 adapter with native Wave64", "Rust", "DXC"],
        "status": "needs_run", "evidence_stage": "author_gpu", "adoption": "pending",
        "source_url": f"{PORTBRIDGE}/issues/5", "procedure_url": f"{PORTBRIDGE}/issues/5",
        "evidence_url": BYTE_CARRY, "result_url": f"{PORTBRIDGE}/issues/5",
        "revisions": [revision("Test PR", "PR с тестом", "akimfomin/xcl", "3858abc46e4c9c3b9db5e4ae648d6636c37bfb51")],
        "why": "A native Wave64 run checks byte carry within each 32-lane half on AMD hardware.",
        "evidence": "Both cases passed on NVIDIA at the listed revision. The original receiving PR closed. Record an AMD result in PortBridge #5 and agree on a current XCL baseline before proposing a new PR.",
        "steps": [
            "Check out the pinned test PR. Select the AMD adapter and set XCL_REQUIRE_GPU=wave64.",
            "Run gpu_wave32_program_in_wave64_hardware to confirm native Wave64 is available.",
            "Run the two ds_permute_b32 tests as described in the procedure.",
        ],
        "expected": "The adapter check and both byte-carry tests pass without skips.",
        "report": ["Commit, GPU, driver, Windows build and DXC version", "Both test summaries and any skip or failure"],
        "translations": {"ru": {
            "title": "Проверить перенос байта в XCL на аппаратном Wave64",
            "requirements": ["Видеокарта AMD с D3D12 и аппаратным Wave64", "Rust", "DXC"],
            "why": "Проверка на AMD покажет, работает ли перенос байта внутри каждой половины аппаратной волны.",
            "evidence": "На указанной версии оба теста прошли на NVIDIA. Исходный PR закрыли. Результат AMD можно оставить в PortBridge #5, а перед новым PR нужно согласовать актуальную версию XCL.",
            "steps": [
                "Перейдите на указанную версию PR, выберите AMD и задайте XCL_REQUIRE_GPU=wave64.",
                "Убедитесь, что доступен аппаратный Wave64, тестом gpu_wave32_program_in_wave64_hardware.",
                "Запустите оба теста ds_permute_b32 по инструкции.",
            ],
            "expected": "Проверка видеокарты и оба теста проходят без пропусков.",
            "report": ["Коммит, видеокарта, драйвер, версия Windows и DXC", "Итоги двух запусков, пропуски и ошибки"],
        }},
    },
    {
        "id": "pb-9-reforge-present",
        "priority": 3,
        "title": "Verify Reforge Present cancellation on AMD",
        "projects": ["reforge"],
        "equipment": ["amd"],
        "os": ["Windows"],
        "requirements": ["AMD adapter with Vulkan 1.3 and Win32 presentation", "C++ build tools and Vulkan headers"],
        "status": "blocked", "evidence_stage": "reviewed_gpu", "adoption": "pending",
        "source_url": f"{PORTBRIDGE}/issues/9", "procedure_url": f"{REFORGE}/pull/86",
        "evidence_url": PRESENTER_REPORT, "result_url": f"{PORTBRIDGE}/issues/9",
        "revisions": [
            revision("Test PR", "PR с тестом", "rizzzz64/Leonida", "b84739e39aee69d2611dfc3982cc2ef35f876916"),
            revision("Unchanged control", "Контроль без правок", "LeonidaReforge/Leonida",
                     "2ebde81ec07e530a3558bc3f7c4b79da6c37ab65"),
        ],
        "why": "The AMD run is paused. GitHub returned 404 for the original Reforge repository on 24 November 2026. A public source confirmed by its maintainers is needed before resuming.",
        "evidence": "Before the source became unavailable, the independent NVIDIA run passed twice. The same fixture failed on the unchanged runtime.",
        "steps": [
            "Wait for the original repository to return or for the maintainers to confirm its new address.",
            "Share that public source in PortBridge #9 so the pinned test and control can be rechecked.",
        ],
        "expected": "All six checks pass on the PR. Eight queued frames drain and the canceled ninth is refused.",
        "report": ["Commit, GPU, driver, Windows build and compiler", "Six check outcomes and the ninth-Present result"],
        "translations": {"ru": {
            "title": "Проверить отмену кадра Reforge на AMD",
            "requirements": ["Видеокарта AMD с Vulkan 1.3 и Win32", "Компилятор C++ и заголовки Vulkan"],
            "why": "Прогон на AMD приостановлен. 24 ноября 2026 года GitHub вернул 404 для исходного репозитория Reforge. Для продолжения нужен публичный источник, подтверждённый сопровождающими.",
            "evidence": "До потери доступа независимый тест на NVIDIA прошёл дважды. Та же проверка на исходной версии выявила ошибку.",
            "steps": [
                "Дождитесь восстановления исходного репозитория или подтверждения нового адреса сопровождающими.",
                "Оставьте подтверждённую публичную ссылку в PortBridge #9, чтобы сверить версии теста и контроля.",
            ],
            "expected": "В PR проходят все шесть проверок. Восемь кадров выходят из очереди, девятый отклонён.",
            "report": ["Коммит, видеокарта, драйвер, версия Windows и компилятора", "Итоги шести проверок и девятого кадра"],
        }},
    },
    {
        "id": "xcl-1100-fma",
        "priority": 4,
        "title": "Repeat the XCL FMA test on AMD RDNA4",
        "projects": ["xcl", "scarlett-layer"],
        "equipment": ["amd"],
        "os": ["Windows"],
        "requirements": ["AMD RDNA4 D3D12 adapter with native Wave64", "Rust", "DXC"],
        "status": "needs_run", "evidence_stage": "author_gpu", "adoption": "pending",
        "source_url": FMA, "procedure_url": f"{XCL_SETUP}/{FMA_HEAD}/README.md#tests",
        "evidence_url": FMA, "result_url": FMA,
        "revisions": [revision("Test PR", "PR с тестом", "akimfomin/xcl", FMA_HEAD)],
        "why": "The earlier XCL revision passed on RDNA2. The rebased revision still needs the native RDNA4 check.",
        "evidence": "The new PR head passed Wave32 and split Wave64 on NVIDIA. The independent AMD RDNA2 report belongs to the earlier revision.",
        "steps": [
            "Check out the pinned PR. Select the AMD RDNA4 adapter and set XCL_REQUIRE_GPU=wave64.",
            "Run gpu_wave32_program_in_wave64_hardware to confirm native Wave64 is available.",
            "Run gpu_fma_f32_abs_neg_clamp_oracle with the XCL GPU test setup.",
        ],
        "expected": "Both tests pass without skips. The FMA output includes wave64 split=false and 64/64 matching values.",
        "report": ["Commit, GPU, driver, Windows build and DXC version", "Adapter check, FMA result and any skipped case"],
        "translations": {"ru": {
            "title": "Повторить тест FMA в XCL на AMD RDNA4",
            "requirements": ["Видеокарта AMD RDNA4 с D3D12 и аппаратным Wave64", "Rust", "DXC"],
            "why": "Предыдущая версия прошла на AMD RDNA2. Обновлённую версию нужно проверить на аппаратном RDNA4.",
            "evidence": "Новая версия PR прошла Wave32 и разделённый Wave64 на NVIDIA. Независимый прогон AMD RDNA2 относится к предыдущей версии.",
            "steps": [
                "Перейдите на указанную версию PR, выберите AMD RDNA4 и задайте XCL_REQUIRE_GPU=wave64.",
                "Убедитесь, что доступен аппаратный Wave64, тестом gpu_wave32_program_in_wave64_hardware.",
                "Запустите gpu_fma_f32_abs_neg_clamp_oracle по инструкции XCL для GPU-тестов.",
            ],
            "expected": "Оба теста проходят без пропусков. В выводе FMA есть wave64 split=false и 64 из 64 совпадений.",
            "report": ["Коммит, видеокарта, драйвер, версия Windows и DXC", "Итог проверки видеокарты, FMA и пропуски"],
        }},
    },
    {
        "id": "pb-4-d16",
        "priority": 5,
        "title": "Follow the tested D16 fix in Continued",
        "projects": ["reforge", "continued"],
        "equipment": ["cpu"],
        "os": ["Windows", "macOS"],
        "requirements": ["Python for the synthetic CPU checks"],
        "status": "awaiting_review", "evidence_stage": "reviewed_cpu", "adoption": "pending",
        "source_url": f"{PORTBRIDGE}/issues/4", "procedure_url": f"{PORTBRIDGE}/issues/4",
        "evidence_url": D16_REPRODUCTION, "result_url": D16_REVIEW,
        "revisions": [
            revision("Continued base", "Исходная версия Continued", "ubiquitarianism/leonida",
                     "21625bca8c675c62f9dbffc318ce6a59d57faf31"),
            revision("Reforge follow-up", "Правка Reforge", "ecox982745/Leonida",
                     "a300ba63d1a9a4cdfde1d64f136728545b4ab7b8"),
            revision("Continued review revision", "Версия PR в Continued", "ubiquitarianism/leonida",
                     "66dbbf3e176880487617609547b02c98add60297"),
        ],
        "why": "The receiving team's decision tells both projects whether the tested fix will carry over.",
        "evidence": "Alongside 137 local CPU checks, an independent Apple M5 Pro run passed all 15 focused tests. A Continued contributor approved that revision. Follow the merge decision in #701.",
        "steps": [
            "Review the documented CPU result in the receiving discussion.",
            "To reproduce it, run the pinned baseline, tests-only control and full focused suite from the procedure.",
            "Link the receiving team's reply, test or commit in the coordination issue when available.",
        ],
        "expected": "The baseline passes 13 tests. The added tests expose seven misclassifications. The fix passes all 15.",
        "report": ["Tested revision, system, Python version and outcomes, or link to the receiving team's decision"],
        "translations": {"ru": {
            "title": "Проследить за проверенной правкой D16 в Continued",
            "requirements": ["Python для синтетических проверок на процессоре"],
            "why": "Решение Continued покажет обеим командам, будет ли использована проверенная правка.",
            "evidence": "У нас прошли 137 проверок на процессоре. Независимый прогон на Apple M5 Pro подтвердил все 15 целевых тестов. Участник Continued одобрил эту версию. Решение о слиянии можно проверить в #701.",
            "steps": [
                "Прочитайте результат проверки на процессоре в обсуждении Continued.",
                "Для повторения прогоните исходную версию, контроль с одними тестами и полный комплект по инструкции.",
                "Когда команда ответит, добавьте в задачу координации ссылку на ответ, тест или коммит.",
            ],
            "expected": "На исходной версии проходят 13 тестов. Новые тесты выявляют семь ошибок. С правкой проходят все 15.",
            "report": ["Коммит, система, версия Python и итоги тестов либо ссылка на решение команды"],
        }},
    },
    {
        "id": "anyxboxx-133-native-carry",
        "priority": 6,
        "title": "Review the AnyXboxX carry-mask result on native AMD RDNA2",
        "projects": ["anyxboxx"],
        "equipment": ["amd"],
        "os": ["Windows", "Linux"],
        "requirements": ["Physical AMD RDNA2 with Wave32", "HIP setup that launches native AMDGPU code objects"],
        "status": "awaiting_review", "evidence_stage": "reviewed_gpu", "adoption": "pending",
        "source_url": CARRY, "procedure_url": CARRY_PROBE,
        "evidence_url": CARRY_REPORT, "result_url": CARRY_REPLY,
        "revisions": [
            revision("AnyXboxX #133 follow-up", "Версия AnyXboxX #133", "LooperSalty/AnyXboxX", CARRY_HEAD),
            revision("Probe used as the reference", "Исходная проба", "akimfomin/PortBridge", CARRY_PROBE_REVISION),
        ],
        "why": "KainanP cited the native measurement in three docstrings in the open PR. The maintainer's merge decision is pending.",
        "evidence": "Lyrnc ran the PortBridge instruction sequence in a separate HIP harness on a physical gfx1036 Wave32 device. Both carry masks and the comparison control were 00000001 in all three runs.",
        "steps": [
            "Read Lyrnc's hardware report and KainanP's reply in AnyXboxX #133.",
            "Check the receiving team's decision and report a link to it in PortBridge #19.",
            "If the team needs a second hardware run, repeat the pinned probe on physical RDNA2 in Wave32.",
        ],
        "expected": "Controls expect initial EXEC ffffffff, zero sums, and compare_vcc 00000001. For each carry mask, 00000001 means inactive bits clear and ffffffff means they are preserved. Report mixed or other outputs as observed.",
        "report": ["PR revision, GPU target, driver, OS and assembler version", "Full output including the e32 and e64 carry masks"],
        "translations": {"ru": {
            "title": "Рассмотреть результат AnyXboxX по маскам переноса на AMD RDNA2",
            "requirements": ["Физическая видеокарта AMD RDNA2 с Wave32", "HIP с запуском кода AMDGPU напрямую на видеокарте"],
            "why": "KainanP сослался на аппаратный замер в трёх пояснениях в открытом PR. Решение о слиянии ожидается.",
            "evidence": "Lyrnc запустил последовательность инструкций PortBridge в своём стенде HIP на физической gfx1036 в Wave32. Обе маски переноса и контроль сравнения дали 00000001 во всех трёх прогонах.",
            "steps": [
                "Прочитайте аппаратный отчёт Lyrnc и ответ KainanP в AnyXboxX #133.",
                "Проверьте решение команды и добавьте ссылку на него в PortBridge #19.",
                "Если команде понадобится второй прогон, повторите указанную пробу на физической RDNA2 в Wave32.",
            ],
            "expected": "Контроль ожидает начальную EXEC ffffffff, обе суммы ноль и compare_vcc 00000001. Маска переноса 00000001 означает очистку неактивных битов, ffffffff означает сохранение. Укажите и любые другие значения.",
            "report": ["Версия PR, видеокарта, драйвер, ОС и версия ассемблера", "Полный вывод с масками переноса e32 и e64"],
        }},
    },
    {
        "id": "continued-511-repeated-draw",
        "priority": 7,
        "title": "Check repeated draws in Continued on AMD",
        "projects": ["continued", "scenegate-vi"],
        "equipment": ["amd"],
        "os": ["Windows"],
        "requirements": ["AMD Vulkan adapter", "Continued C++ build tools", "Vulkan SDK"],
        "status": "needs_run", "evidence_stage": "author_gpu", "adoption": "pending",
        "source_url": DRAW_SEQUENCE, "procedure_url": DRAW_GUIDE,
        "evidence_url": DRAW_GUIDE, "result_url": DRAW_SEQUENCE,
        "revisions": [revision("Continued #511", "Continued #511", "ubiquitarianism/leonida", DRAW_HEAD)],
        "why": "The pixel test compares 32 changing frames in both pipeline modes. A second GPU and the standard project build can verify the result.",
        "evidence": "PortBridge ran 3/3 positive checks and 3/3 omission controls in each mode on an RTX 4070 Ti SUPER.",
        "steps": [
            "Check that Continued still needs the run and use the pinned revision in a separate checkout.",
            "Inspect and apply the synthetic test patch, then build d3d12_draw_test with the official setup.",
            "Run the normal sequence and the omitted-draw control with LEONIDA_LAZY_PSO set to 0 and to 1.",
        ],
        "expected": "Both modes pass 32 frames of 4,096 RGBA8 pixels. Omitting draw 8 returns 44 with a mismatch at frame 7, pixel (0,0).",
        "report": ["Commit, AMD GPU, driver, Windows build and toolchain", "Both pipeline modes, positive output and the omission control"],
        "translations": {"ru": {
            "title": "Проверить последовательность кадров Continued на AMD",
            "requirements": ["Видеокарта AMD с Vulkan", "Инструменты сборки Continued", "Vulkan SDK"],
            "why": "Проверка сравнивает 32 кадра с меняющимся цветом в двух режимах. Нужен повтор на другой видеокарте и со штатной сборкой проекта.",
            "evidence": "На RTX 4070 Ti SUPER в каждом режиме прошли 3 из 3 обычных прогонов и 3 из 3 намеренно пропущенных отрисовок были обнаружены.",
            "steps": [
                "Сверьте, нужна ли проверка, и откройте указанную версию Continued в отдельной копии.",
                "Прочитайте и примените патч синтетического теста. Соберите d3d12_draw_test по инструкции проекта.",
                "В каждом режиме LEONIDA_LAZY_PSO от 0 до 1 запустите обычный тест и вариант с пропущенной отрисовкой.",
            ],
            "expected": "В обоих режимах совпадают все пиксели 32 кадров по 4 096 пикселей. При пропуске восьмой отрисовки тест возвращает код 44 и расхождение в кадре 7, пиксель (0,0).",
            "report": ["Коммит, видеокарта AMD, драйвер, версия Windows и инструменты сборки", "Результаты в обоих режимах и контроль с пропущенной отрисовкой"],
        }},
    },
    {
        "id": "scarlett-commons-continued-add-basic",
        "priority": 8,
        "title": "Independently repeat the Scarlett Commons addition case in Continued",
        "projects": ["scarlett-commons", "continued"],
        "equipment": ["cpu"],
        "os": ["Linux", "Windows"],
        "requirements": ["Git and Python 3.12", "Two clean public source checkouts"],
        "status": "needs_run", "evidence_stage": "author_cpu", "adoption": "pending",
        "source_url": SCARLETT_ADAPTER, "procedure_url": SCARLETT_GUIDE,
        "evidence_url": f"{SCARLETT_ADAPTER}#issuecomment-7140402183", "result_url": SCARLETT_ADAPTER,
        "revisions": [
            revision("Continued translator and CPU interpreter", "Транслятор и CPU-интерпретатор Continued",
                     "ubiquitarianism/leonida", "5496f79f93c41f1134ce4c9e1d2674aa00c6bb55"),
            revision("Scarlett Commons addition case", "Тест сложения Scarlett Commons",
                     "scarlett-commons/scarlett-commons", "ba9549c254647b9f6ef3b4e47684e69a668b9ec1"),
        ],
        "why": "An independent run can confirm that the shared addition case and its failing control are reproducible on a separate setup before adapter work.",
        "evidence": "PortBridge ran this one synthetic Wave32 case on the Continued CPU interpreter under Windows with Python 3.12.14. The Vulkan runner and full adapter are separate work.",
        "steps": [
            "Check Scarlett Commons #32 for a result on your setup. Prefer Linux, or use a separate clean Windows setup.",
            "Inspect the procedure and run compare.py with the two clean checkouts at the exact revisions below.",
            "Share your output or a blocking error in #32, with a link to this check.",
        ],
        "expected": "The case validator reports one case and zero problems. Addition returns 0x40700000. Replacing addition with subtraction returns 0x3f400000 and fails the original expectation.",
        "report": ["Both exact commits, OS and Python version", "Case validation, addition output and subtraction control"],
        "translations": {"ru": {
            "title": "Независимо повторить тест сложения Scarlett Commons в Continued",
            "requirements": ["Git и Python 3.12", "Две чистые копии публичных исходников"],
            "why": "Независимый прогон покажет, воспроизводятся ли общий тест сложения и контроль с ошибкой на другом стенде до работы над адаптером.",
            "evidence": "PortBridge прогнал один синтетический тест Wave32 на CPU-интерпретаторе Continued под Windows с Python 3.12.14. Запуск через Vulkan и полный адаптер требуют отдельной работы.",
            "steps": [
                "Проверьте в Scarlett Commons #32, есть ли результат для вашего стенда. Лучше использовать Linux, также подойдёт отдельный чистый стенд Windows.",
                "Прочитайте инструкцию и запустите compare.py с чистыми копиями двух проектов на указанных версиях.",
                "Оставьте вывод или ошибку, помешавшую прогону, в #32 со ссылкой на эту проверку.",
            ],
            "expected": "Проверка входных данных находит один тест без ошибок. Сложение даёт 0x40700000. Замена сложения вычитанием даёт 0x3f400000 и не проходит исходное сравнение.",
            "report": ["Оба точных коммита, ОС и версия Python", "Проверка входных данных, результат сложения и контроль с вычитанием"],
        }},
    },
    {
        "id": "anyxboxx-147-native-wave64-gather",
        "priority": 9,
        "title": "Measure native RDNA2 Wave64 lane gather for AnyXboxX",
        "projects": ["anyxboxx"],
        "equipment": ["amd"],
        "os": ["Windows", "Linux"],
        "requirements": ["Physical gfx1036 with native Wave64", "LLVM tools and a HIP module harness"],
        "status": "needs_run", "evidence_stage": "assembled_offline", "adoption": "pending",
        "source_url": WAVE64_CASE, "procedure_url": WAVE64_GUIDE,
        "evidence_url": f"{WAVE64_CASE}#issuecomment-7140576454", "result_url": WAVE64_CASE,
        "revisions": [revision("AnyXboxX translated Wave64 comparison", "Сравнение перевода Wave64 в AnyXboxX",
                               "LooperSalty/AnyXboxX", "28524547b9f0751581257279a329b8cae2f1dc1e")],
        "why": "The AnyXboxX reviewer identified a missing native measurement after running the translated HLSL. One native run can check the expected half-wave addressing.",
        "evidence": "PortBridge assembled and linked the synthetic probe for gfx1036. The object declares Wave64 and a maximum group size of 64. Native execution is pending.",
        "steps": [
            "Check AnyXboxX #147 for a native result or a volunteer already running the probe.",
            "Build the public probe and launch one 64-thread workgroup with an existing HIP module harness or the optional launcher.",
            "Report the output in #147. If the toolchain cannot launch native Wave64, report the environment and the error as a skip.",
        ],
        "expected": "All 64 lane and EXEC controls pass. For lane i, both addresses return 0xa5000000 OR (i XOR 1) if the gather stays within the current half.",
        "report": ["GPU target, driver, OS, assembler and module metadata", "Lane and EXEC controls and both output words for lanes 0, 31, 32 and 63, or all 64 rows"],
        "translations": {"ru": {
            "title": "Измерить чтение из соседнего потока в нативном Wave64 для AnyXboxX",
            "requirements": ["Физическая AMD gfx1036 с нативным Wave64", "LLVM и стенд запуска модулей HIP"],
            "why": "После прогона переведённого HLSL проверяющий AnyXboxX отметил, что аппаратного результата для исходной инструкции ещё нет. Один прогон проверит адресацию внутри половин волны.",
            "evidence": "PortBridge собрал синтетическую проверку для gfx1036. В параметрах полученного файла указаны Wave64 и группа до 64 потоков. Нужен аппаратный прогон.",
            "steps": [
                "Проверьте в AnyXboxX #147, есть ли аппаратный результат или доброволец уже выполняет прогон.",
                "Соберите проверку и запустите одну группу из 64 потоков в своём стенде HIP или через приложенный запускатель.",
                "Оставьте вывод в #147. Если нативный Wave64 недоступен, укажите стенд и ошибку как пропуск теста.",
            ],
            "expected": "Все 64 потока и обе половины маски EXEC проходят контроль. Для потока i оба адреса дают 0xa5000000 OR (i XOR 1), если чтение остаётся внутри своей половины.",
            "report": ["Модель AMD, драйвер, ОС, ассемблер и параметры модуля", "Контроль номера потока и EXEC, оба значения для потоков 0, 31, 32 и 63 либо результаты всех 64"],
        }},
    },
    {
        "id": "framelab-12-vulkan-handoff",
        "priority": 10,
        "title": "Repeat the FrameLab Vulkan queue handoff on AMD",
        "projects": ["framelab"],
        "equipment": ["amd"],
        "os": ["Windows", "Linux"],
        "requirements": ["Physical AMD GPU with Vulkan 1.2", "Khronos validation layer",
                         "CMake 3.20 or later and a C++20 compiler"],
        "status": "needs_run", "evidence_stage": "reviewed_gpu", "adoption": "pending",
        "source_url": FRAMELAB_HANDOFF,
        "procedure_url": f"{FRAMELAB}/blob/{FRAMELAB_HANDOFF_HEAD}/tests/vulkan-handoff/README.md",
        "evidence_url": f"{FRAMELAB_HANDOFF}#issuecomment-7142089405", "result_url": FRAMELAB_HANDOFF,
        "revisions": [revision("FrameLab #12 standalone Vulkan test", "Отдельный тест Vulkan FrameLab #12",
                               "5headsmartbtw/leonida-framelab", FRAMELAB_HANDOFF_HEAD)],
        "why": "An independent AMD run checks the same synthetic image and synchronization across another GPU vendor.",
        "evidence": ("The author's RTX 2050 and PortBridge's RTX 4070 Ti SUPER passed all four standalone cases. "
                     "The AMD check covers this fixture only."),
        "steps": [
            "Check FrameLab #12 for existing AMD evidence and use the pinned revision in a separate checkout.",
            "Build and run the unchanged tests/vulkan-handoff fixture with the pinned README and verbose CTest output.",
            "Confirm that the Adapter line associated with the results identifies a physical AMD GPU.",
            "Report the four case outcomes in #12. Record unsupported queue configurations or timeline semaphores as skips.",
        ],
        "expected": ("Binary and timeline waits pass for each supported same-family and cross-family queue setup, "
                     "with 64 matching pixels, a completed consumer fence and no validation diagnostics. "
                     "A run with no usable two-queue configuration is skipped."),
        "report": ["Commit, Adapter line, driver, OS, Vulkan SDK and validation layer versions",
                   "Queue family pairs, all four outcomes or skip reasons, pixel readback and validation diagnostics"],
        "translations": {"ru": {
            "title": "Повторить передачу изображения между очередями Vulkan в FrameLab на AMD",
            "requirements": ["Физическая видеокарта AMD с Vulkan 1.2", "Слой проверки Khronos",
                             "CMake 3.20 или новее и компилятор C++20"],
            "why": "Независимый прогон проверит синхронизацию и пиксели на видеокарте другого производителя.",
            "evidence": ("У автора на RTX 2050 и у PortBridge на RTX 4070 Ti SUPER прошли все четыре сценария. "
                         "Задача AMD охватывает этот отдельный тест."),
            "steps": [
                "Проверьте, есть ли уже результат AMD в FrameLab #12, и откройте указанную версию в отдельной копии.",
                "Соберите и запустите tests/vulkan-handoff без изменений по инструкции с подробным выводом CTest.",
                "Убедитесь, что строка Adapter, к которой относятся результаты, указывает на физическую видеокарту AMD.",
                "Оставьте результаты четырёх сценариев в #12. Недоступные сочетания очередей и виды семафоров отметьте как пропуски.",
            ],
            "expected": ("Оба вида семафоров проходят для каждого поддерживаемого сочетания очередей внутри одного семейства и между разными. "
                         "Все 64 пикселя совпадают, очередь-получатель завершает работу, проверка синхронизации не выдаёт сообщений. "
                         "При отсутствии подходящей пары очередей прогон пропускается."),
            "report": ["Коммит, строка Adapter, драйвер, ОС, версии Vulkan SDK и слоя проверки",
                       "Номера семейств очередей, итоги четырёх сценариев или причины пропуска, пиксели и диагностика"],
        }},
    },
)


def filter_lab(payload, *, equipment="", status="", task=""):
    if equipment and equipment not in EQUIPMENT:
        raise ValueError(f"equipment must be one of {', '.join(EQUIPMENT)}")
    if status and status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    if not isinstance(task, str) or task and not re.fullmatch(TASK_ID_PATTERN, task):
        raise ValueError("task must be a Test Lab identifier")
    return {**payload, "tasks": [
        entry for entry in payload["tasks"]
        if (not equipment or equipment in entry["equipment"]) and (not status or status == entry["status"])
        and (not task or task == entry["id"])
    ]}


def build_lab(*, equipment="", status="", task=""):
    payload = {"checked_at": CHECKED_AT, "filters": {"equipment": list(EQUIPMENT), "status": list(STATUSES)},
               "tasks": deepcopy(TASKS)}
    return filter_lab(payload, equipment=equipment, status=status, task=task)
