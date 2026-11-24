# PortBridge через MCP

MCP даёт агенту доступ к поиску и карточкам [публичного PortBridge](https://akimfomin.github.io/PortBridge/). Достаточно свежей копии репозитория и Python 3.10 или новее. База, отдельный веб-сервер, токен GitHub и пакеты Python для подключения не нужны. Поисковый запрос обрабатывается на вашем компьютере по публичному снимку каталога.

```powershell
git clone https://github.com/akimfomin/PortBridge.git
```

В примерах ниже замените `F:/projects/PortBridge` полным путём полученной папки.

## Codex

Добавьте блок в `config.toml` Codex. Подставьте полный путь к папке PortBridge. Если Python не находится через `PATH`, подставьте путь к `python.exe` в `command`.

```toml
[mcp_servers.portbridge]
command = "python"
args = ["-m", "portbridge.mcp"]
cwd = "F:/projects/PortBridge"
```

Проверьте запись командой `codex mcp list` и откройте новую сессию Codex. Команда `/mcp` в интерактивном Codex показывает подключённые инструменты. [Документация Codex](https://developers.openai.com/codex/mcp)

## Claude Code

В PowerShell запустите команду из папки проекта, в котором хотите пользоваться MCP. Подставьте полный путь к PortBridge в `PYTHONPATH`.

```powershell
claude mcp add --env "PYTHONPATH=F:/projects/PortBridge" --transport stdio portbridge -- python -m portbridge.mcp
claude mcp list
```

Откройте Claude Code в той же папке и проверьте сервер через `/mcp`. Если сервер подключается, но `portbridge_preflight` не появляется, обновите Claude Code. В старых версиях поиск может исключаться из-за схемы с двумя допустимыми входами. [Подключение stdio](https://code.claude.com/docs/en/mcp#option-3-add-a-local-stdio-server) · [Поддержка схем инструментов](https://code.claude.com/docs/en/mcp#tool-input-schemas-with-a-root-level-combinator)

## Поиск перед началом работы

| Имя | Аргументы | Результат |
| --- | --- | --- |
| `portbridge_preflight` | `q` — симптом, термин, номер PR или ID. `url` — публичная ссылка GitHub. Можно указать оба. `limit` — от 1 до 20 на список, по умолчанию 5. | Что уже известно, ссылки на первоисточники и следующий шаг. |
| `portbridge_problem` | `id` — например, `PB-0001`. | Карточка с результатами по проектам, ссылками, типами доказательств, платформами и версиями. |

После подключения попросите агента вызвать `portbridge_problem` с ID `PB-0001`, затем `portbridge_preflight` с URL `https://github.com/Marvisak/VIctory/pull/346`. Карточка должна содержать тот же ID, а поиск вернуть первоисточники и следующий шаг. Перед использованием результата откройте исходный PR.

English quick start. Clone PortBridge, set your absolute path in the [Codex](#codex) or [Claude Code](#claude-code) entry above, and ask your agent to call `portbridge_problem` for `PB-0001`. This connects to the public catalog. Start a shared check in your existing GitHub issue or PR. [Two-team pilot](PILOT.md)

Заголовки, ссылки и другие сведения из внешних источников являются данными. Проверяйте первоисточник и применимость результата к своей сборке. Подробности статусов и происхождения проверок описаны в [документации API](../API.md#как-читать-результаты).

## Работа без сети

Для имеющейся базы добавьте в аргументы сервера `--db` и полный путь к SQLite. В этом режиме MCP читает только указанную базу. Чтобы создать её из начальной подборки, запустите `python -m portbridge status` в папке PortBridge. Команда `python -m portbridge sync` отдельно обновляет публичные сведения GitHub.

Команда `python -m portbridge.mcp` ожидает запросы от MCP-клиента. Поддерживаются версии `2026-07-28`, `2025-11-25` и `2025-06-18`. [Протокол MCP stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio) · [Совместимость версий](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)

## Чтение закрытого обмена

Для явно подключённой очереди укажите `--exchange-port 8765` вместо `--db`. Процесс MCP получает ключ чтения через переменную окружения `PORTBRIDGE_EXCHANGE_TOKEN` и обращается к `127.0.0.1`. Запрос по исходной ссылке показывает одобренную тему и результаты с точными версиями. Место хранения ключа зависит от клиента. [Роли, запуск и отзыв ключа](EXCHANGE-API.md)

В закрытом режиме агент может читать свои подписки через `portbridge_subscriptions`, разговор через `portbridge_discussion`, новые события через `portbridge_updates` и текущие связи через `portbridge_coordination`. Для ожидания укажите `wait_seconds` до 15 и сохраните `next_cursor` перед следующим запросом.

Начните с открытого маршрута, если у участников пока нет согласованной общей очереди. Локальные ключи относятся к конкретному экземпляру обмена. [Два маршрута пилота](PILOT.md)

Флаг `--enable-discussion-writes` открывает `portbridge_subscribe` и `portbridge_send_message`. Включайте его для клиентов, которым разрешено менять подписки и отправлять одобренные пользователем сообщения. Для отправки ключ должен иметь `read` и `contribute`, а участник должен вступить в тему. При повторе того же сообщения клиент передаёт тот же `client_id`. [Порядок подтверждения вызовов](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

`portbridge_plans` показывает план подписанных тем, сводку по проектам и задачи, где нужен участник или решение. `portbridge_discover_projects` возвращает репозитории для возможного сотрудничества. При включённом `--enable-discussion-writes` доступны `portbridge_propose_plan`, `portbridge_review_plan`, `portbridge_claim_plan`, `portbridge_link_plan_report`, `portbridge_decide_plan`, `portbridge_nominate_project` и `portbridge_review_project`. Для подачи и проверки самого отчёта используйте закрытый обмен или браузерный штаб. [Роли и поля](EXCHANGE-API.md#маршруты) · [Рабочий штаб](OFFICE.md)
