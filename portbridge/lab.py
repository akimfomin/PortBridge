"""Reviewed volunteer checks with public procedures and pinned sources."""

from copy import deepcopy


CHECKED_AT = "2026-11-24T12:06:04Z"
EQUIPMENT = ("amd", "cpu", "nvidia")
STATUSES = ("needs_run", "needs_revision", "awaiting_review")
PORTBRIDGE = "https://github.com/akimfomin/PortBridge"
CONTINUED = "https://github.com/ubiquitarianism/leonida"
REFORGE = "https://github.com/LeonidaReforge/Leonida"
XCL = "https://github.com/ivall/xcl"
D16_REPORT = f"{CONTINUED}/pull/265#issuecomment-7128554846"
RECT_REPORT = f"{CONTINUED}/pull/511#issuecomment-7130673446"
BYTE_CARRY = "https://github.com/maximecmb/xcl/pull/1"
PRESENTER_REPORT = f"{REFORGE}/pull/86#issuecomment-7130696664"
FMA = f"{XCL}/pull/1100"
XCL_SETUP = "https://github.com/akimfomin/xcl/blob"


def revision(label, label_ru, repository, sha):
    return {"label": label, "sha": sha, "url": f"https://github.com/{repository}/commit/{sha}",
            "translations": {"ru": {"label": label_ru}}}


TASKS = (
    {
        "id": "pb-9-continued-first-frame",
        "priority": 1,
        "title": "Compare the Continued rectangle check with deferred pipelines",
        "projects": ["continued"],
        "equipment": ["amd", "nvidia"],
        "os": ["Windows"],
        "requirements": ["Vulkan adapter with geometry shader support", "C++ build tools and Vulkan headers"],
        "status": "needs_revision", "evidence_stage": "reviewed_cpu", "adoption": "pending",
        "source_url": f"{PORTBRIDGE}/issues/9", "procedure_url": RECT_REPORT,
        "evidence_url": RECT_REPORT, "result_url": f"{CONTINUED}/pull/511",
        "revisions": [
            revision("Deferred pipelines #511", "Отложенная сборка #511", "VibeClauding/leonida-continued",
                     "88658f1b3fcdca2231358c18d09253a213dc8533"),
            revision("Rectangle lists #207", "Списки прямоугольников #207", "ubiquitarianism/leonida",
                     "21dc3889280dba49916f63342dab72750d3ee4b9"),
        ],
        "why": "Deferred creation has to preserve the vertex shader data that rectangle generation uses.",
        "evidence": "The CPU check reproduced the early release failure and recovered the expected synthetic geometry shader.",
        "steps": [
            "Identify a combined revision with the owners of #511 and #207 and post its commit hash before testing.",
            "On that combined revision, build the synthetic d3d12_rect_list test for Windows Vulkan.",
            "Run it with LEONIDA_LAZY_PSO set to 0 and 1 and compare both pixel readbacks.",
        ],
        "expected": "Both modes pass the targeted rectangle check with the expected pixels.",
        "report": ["Combined commit, GPU, driver and Windows build", "Pixel readback and result for both modes"],
        "translations": {"ru": {
            "title": "Сверить проверку прямоугольников Continued с отложенной сборкой",
            "requirements": ["Видеокарта с Vulkan и поддержкой геометрических шейдеров", "Компилятор C++ и заголовки Vulkan"],
            "why": "При отложенной сборке нужно сохранить данные вершинного шейдера для отрисовки прямоугольников.",
            "evidence": "Проверка на процессоре воспроизвела ошибку раннего освобождения данных и восстановила ожидаемый синтетический шейдер.",
            "steps": [
                "Согласуйте с авторами #511 и #207 общий коммит и укажите его в обсуждении до запуска.",
                "На этом коммите соберите синтетический тест d3d12_rect_list для Windows и Vulkan.",
                "Запустите тест с LEONIDA_LAZY_PSO равным 0 и 1 и сравните пиксели.",
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
        "evidence_url": BYTE_CARRY, "result_url": BYTE_CARRY,
        "revisions": [revision("Test PR", "PR с тестом", "akimfomin/xcl", "3858abc46e4c9c3b9db5e4ae648d6636c37bfb51")],
        "why": "A native Wave64 run checks byte carry within each 32-lane half on AMD hardware.",
        "evidence": "The test author passed both cases on NVIDIA in Wave32 and split Wave64.",
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
            "evidence": "У автора оба теста прошли на NVIDIA в Wave32 и разделённом Wave64.",
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
        "title": "Compare the XCL FMA test with Scarlett Layer on native Wave64",
        "projects": ["xcl", "scarlett-layer"],
        "equipment": ["amd"],
        "os": ["Windows"],
        "requirements": ["AMD D3D12 adapter with native Wave64", "Rust", "DXC"],
        "status": "needs_run", "evidence_stage": "author_gpu", "adoption": "pending",
        "source_url": FMA, "procedure_url": f"{XCL_SETUP}/c612b62656fb30eca308fd461209339f6a7c7d32/README.md#tests",
        "evidence_url": FMA, "result_url": FMA,
        "revisions": [revision("Test PR", "PR с тестом", "akimfomin/xcl", "c612b62656fb30eca308fd461209339f6a7c7d32")],
        "why": "The same Scarlett Layer inputs let XCL check its FMA modifier behavior on another GPU.",
        "evidence": "The PR author matched all 64 modified and 64 control results in Wave32 and split Wave64 on NVIDIA.",
        "steps": [
            "Check out the pinned draft PR. Select the AMD adapter and set XCL_REQUIRE_GPU=wave64.",
            "Run gpu_wave32_program_in_wave64_hardware to confirm native Wave64 is available.",
            "Run gpu_fma_f32_abs_neg_clamp_oracle with the XCL GPU test setup.",
        ],
        "expected": "Both tests pass without skips. The FMA output includes wave64 split=false and 64/64 matching values.",
        "report": ["Commit, GPU, driver, Windows build and DXC version", "Adapter check, FMA result and any skipped case"],
        "translations": {"ru": {
            "title": "Сверить тест FMA из Scarlett Layer в XCL на аппаратном Wave64",
            "requirements": ["Видеокарта AMD с D3D12 и аппаратным Wave64", "Rust", "DXC"],
            "why": "На тех же данных Scarlett Layer можно сверить модификаторы FMA в XCL на другой видеокарте.",
            "evidence": "У автора PR на NVIDIA совпали все 64 результата с модификаторами и 64 контрольных в обоих режимах.",
            "steps": [
                "Перейдите на указанную версию чернового PR, выберите AMD и задайте XCL_REQUIRE_GPU=wave64.",
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
        "title": "Review the Reforge D16 check in Continued",
        "projects": ["reforge", "continued"],
        "equipment": ["cpu"],
        "os": ["Windows"],
        "requirements": ["Python 3.12.14 for the recorded test setup"],
        "status": "awaiting_review", "evidence_stage": "reviewed_cpu", "adoption": "pending",
        "source_url": f"{PORTBRIDGE}/issues/4", "procedure_url": f"{PORTBRIDGE}/issues/4",
        "evidence_url": D16_REPORT, "result_url": f"{CONTINUED}/pull/265",
        "revisions": [
            revision("Continued base", "Исходная версия Continued", "ubiquitarianism/leonida",
                     "21625bca8c675c62f9dbffc318ce6a59d57faf31"),
            revision("Reforge follow-up", "Правка Reforge", "ecox982745/Leonida",
                     "a300ba63d1a9a4cdfde1d64f136728545b4ab7b8"),
        ],
        "why": "The receiving team's decision tells both projects whether the tested fix will carry over.",
        "evidence": "PortBridge reproduced seven misclassifications with the added checks and passed 15/15 with the fix.",
        "steps": [
            "Review the documented CPU result in the receiving discussion.",
            "To reproduce it, run the pinned baseline, tests-only control and full focused suite from the procedure.",
            "Link the receiving team's reply, test or commit in the coordination issue when available.",
        ],
        "expected": "The baseline passes 13 tests. The added tests expose seven misclassifications. The fix passes all 15.",
        "report": ["Tested revision, system, Python version and outcomes, or link to the receiving team's decision"],
        "translations": {"ru": {
            "title": "Сверить проверку D16 из Reforge в Continued",
            "requirements": ["Python 3.12.14 для повторения на том же окружении"],
            "why": "Решение Continued покажет обеим командам, будет ли использована проверенная правка.",
            "evidence": "PortBridge воспроизвёл семь ошибок классификации. С исправлением прошли 15 из 15 тестов.",
            "steps": [
                "Прочитайте результат проверки на процессоре в обсуждении Continued.",
                "Для повторения прогоните исходную версию, контроль с одними тестами и полный комплект по инструкции.",
                "Когда команда ответит, добавьте в задачу координации ссылку на ответ, тест или коммит.",
            ],
            "expected": "На исходной версии проходят 13 тестов. Новые тесты выявляют семь ошибок. С правкой проходят все 15.",
            "report": ["Коммит, система, версия Python и итоги тестов либо ссылка на решение команды"],
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
