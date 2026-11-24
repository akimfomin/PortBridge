"""Reviewed volunteer checks with public procedures and pinned sources."""

from copy import deepcopy


CHECKED_AT = "2026-11-24T14:16:39Z"
EQUIPMENT = ("amd", "cpu", "nvidia")
STATUSES = ("needs_run", "needs_revision", "awaiting_review")
PORTBRIDGE = "https://github.com/akimfomin/PortBridge"
CONTINUED = "https://github.com/ubiquitarianism/leonida"
REFORGE = "https://github.com/LeonidaReforge/Leonida"
XCL = "https://github.com/ivall/xcl"
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
CARRY_HEAD = "e2af2d38e48b5a0019dae5c78aa398cc71c42c8d"
CARRY_DISCUSSION = f"{CARRY}#issuecomment-7133362035"
CARRY_PROBE = f"{PORTBRIDGE}/blob/main/contrib/rdna2-carry-mask/README.md"


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
        "status": "needs_run", "evidence_stage": "reviewed_gpu", "adoption": "pending",
        "source_url": f"{PORTBRIDGE}/issues/9", "procedure_url": f"{REFORGE}/pull/86",
        "evidence_url": PRESENTER_REPORT, "result_url": f"{REFORGE}/pull/86",
        "revisions": [
            revision("Test PR", "PR с тестом", "rizzzz64/Leonida", "b84739e39aee69d2611dfc3982cc2ef35f876916"),
            revision("Unchanged control", "Контроль без правок", "LeonidaReforge/Leonida",
                     "2ebde81ec07e530a3558bc3f7c4b79da6c37ab65"),
        ],
        "why": "An AMD run extends the existing NVIDIA evidence for the canceled ninth Present.",
        "evidence": "The independent NVIDIA run passed twice. The same fixture failed on the unchanged runtime.",
        "steps": [
            "Check out the pinned PR and build only vk_presenter_sync_test on Windows.",
            "Run the synthetic test on the AMD adapter. Check whether the canceled ninth Present is refused.",
            "For a comparison, run the identical fixture with the pinned unchanged runtime.",
        ],
        "expected": "All six checks pass on the PR. Eight queued frames drain and the canceled ninth is refused.",
        "report": ["Commit, GPU, driver, Windows build and compiler", "Six check outcomes and the ninth-Present result"],
        "translations": {"ru": {
            "title": "Проверить отмену кадра Reforge на AMD",
            "requirements": ["Видеокарта AMD с Vulkan 1.3 и Win32", "Компилятор C++ и заголовки Vulkan"],
            "why": "Прогон на AMD дополнит результат NVIDIA по отмене девятого кадра.",
            "evidence": "На NVIDIA независимый тест прошёл дважды. Та же проверка на исходной версии выявила ошибку.",
            "steps": [
                "Перейдите на указанную версию PR и соберите только vk_presenter_sync_test на Windows.",
                "Запустите синтетический тест на AMD. Проверьте, что отменённый девятый кадр отклонён.",
                "Для сравнения запустите тот же тест с указанной исходной версией.",
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
        "title": "Measure AnyXboxX carry masks on native AMD RDNA2",
        "projects": ["anyxboxx"],
        "equipment": ["amd"],
        "os": ["Windows", "Linux"],
        "requirements": ["Physical AMD RDNA2 with Wave32", "HIP setup that launches native AMDGPU code objects"],
        "status": "needs_run", "evidence_stage": "assembled_offline", "adoption": "pending",
        "source_url": CARRY, "procedure_url": CARRY_PROBE,
        "evidence_url": CARRY_DISCUSSION, "result_url": CARRY,
        "revisions": [revision("AnyXboxX #133", "Версия AnyXboxX #133", "LooperSalty/AnyXboxX", CARRY_HEAD)],
        "why": "The receiving team asked whether a partial EXEC mask clears or preserves carry bits on inactive lanes.",
        "evidence": "PortBridge assembled the synthetic gfx1036 probe with LLVM. The receiving PR models cleared bits. A native run is still needed to measure the hardware behavior.",
        "steps": [
            "Check that AnyXboxX #133 is open at the listed revision and the team still needs the result.",
            "Build the source-only HIP probe and run one native Wave32 on physical AMD RDNA2.",
            "Report both carry masks and the control values in AnyXboxX #133.",
        ],
        "expected": "The control values are initial EXEC ffffffff and zero sums. For each carry mask, 00000001 means inactive bits clear and ffffffff means they are preserved. Report mixed or other outputs as observed.",
        "report": ["PR revision, GPU target, driver, OS and assembler version", "Full output including the e32 and e64 carry masks"],
        "translations": {"ru": {
            "title": "Измерить маски переноса AnyXboxX на AMD RDNA2",
            "requirements": ["Физическая видеокарта AMD RDNA2 с Wave32", "HIP с запуском кода AMDGPU напрямую на видеокарте"],
            "why": "Команда хочет узнать, сохраняются ли биты переноса для неактивных потоков при неполной маске EXEC.",
            "evidence": "PortBridge собрал синтетическую пробу для gfx1036 через LLVM. Код в PR очищает биты. Поведение физической видеокарты ещё нужно измерить.",
            "steps": [
                "Убедитесь, что AnyXboxX #133 открыт на указанной версии и результат ещё нужен.",
                "Соберите HIP-пробу из исходников и запустите одну волну Wave32 на физической AMD RDNA2.",
                "Отправьте обе маски переноса и контрольные значения в AnyXboxX #133.",
            ],
            "expected": "Начальная маска EXEC равна ffffffff, обе суммы равны нулю. Маска переноса 00000001 означает очистку неактивных битов, ffffffff означает сохранение. Укажите и любые другие значения.",
            "report": ["Версия PR, видеокарта, драйвер, ОС и версия ассемблера", "Полный вывод с масками переноса e32 и e64"],
        }},
    },
)


def filter_lab(payload, *, equipment="", status=""):
    if equipment and equipment not in EQUIPMENT:
        raise ValueError(f"equipment must be one of {', '.join(EQUIPMENT)}")
    if status and status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    return {**payload, "tasks": [
        task for task in payload["tasks"]
        if (not equipment or equipment in task["equipment"]) and (not status or status == task["status"])
    ]}


def build_lab(*, equipment="", status=""):
    payload = {"checked_at": CHECKED_AT, "filters": {"equipment": list(EQUIPMENT), "status": list(STATUSES)},
               "tasks": deepcopy(TASKS)}
    return filter_lab(payload, equipment=equipment, status=status)
