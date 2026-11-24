# Локальный API обмена

Очередь обмена доступна на этом компьютере после явного запуска. Обычный каталог, GitHub Pages и стандартный MCP продолжают читать публичные сведения. Заявки и решения хранятся в отдельной базе обмена.

## Запуск и ключи

Из папки PortBridge создайте отдельные ключи для участника и проверяющего. Команда печатает ключ при создании. Храните его отдельно от кода и не передавайте в ссылках.

```powershell
python -m portbridge exchange-key --exchange-db .portbridge/exchange.sqlite3 --name "Team agent" --scope read --scope contribute
python -m portbridge exchange-key --exchange-db .portbridge/exchange.sqlite3 --name "Reviewer" --scope read --scope review
python -m portbridge serve --offline --exchange-db .portbridge/exchange.sqlite3
```

Адрес по умолчанию `http://127.0.0.1:8765/api/v1/exchange`. HTTP-клиент передаёт ключ только в заголовке `Authorization: Bearer …`. Браузерный запрос с `Origin` принимается только с того же локального адреса. Доступ между сайтами не открыт. Развёртывание в интернет не входит в этот режим. [Формат Bearer](https://www.rfc-editor.org/rfc/rfc6750.html#section-2.1) · [Проверка Origin](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#checking-the-origin-header)

Владелец может отозвать ключ командой `python -m portbridge exchange-revoke --exchange-db .portbridge/exchange.sqlite3 --name "Team agent"`. Активные отметки этого участника исчезают из списка, а авторство в принятых результатах сохраняется.

## Новая тема

Участник вызывает `POST /propose-topic` с исходной ссылкой и заголовком. Куратор открывает первоисточник, проверяет, что тема ещё не заведена, и принимает решение через `POST /review-topic`. После одобрения участники используют выданный ID для `/register` и `/submit`. Заявка указывает SHA, платформу, тип доказательства, исход и краткое наблюдение. Для провалившейся проверки допустим `outcome=failed`. Результат появляется у второго участника после отдельного одобрения.

Вторая установка читает результаты через свой ключ и `python -m portbridge.preflight --exchange-port 8765 --url <исходный-URL>`. Для MCP задаётся тот же порт. Установки используют одну согласованную очередь, а сохраняют свои локальные каталоги и настройки. Между машинами владелец отдельно согласовывает доступ к защищённому каналу, который выводит очередь на `127.0.0.1` у каждого участника. Локальная демонстрация работает без такого подключения. [Демонстрация](EXCHANGE-DEMO.md) · [Решение по архитектуре](decisions/002-reviewed-exchange-topics.md)

## Маршруты

| Метод и путь | Право | Запрос и результат |
| --- | --- | --- |
| `GET /work` | `read` | Опциональный `problem_id`. Текущие регистрации в `work`. |
| `POST /register` | `contribute` | `problem_id` и необязательный `ttl_seconds` от 60 до 86400, по умолчанию 3600. Регистрация в `work`. |
| `POST /propose-topic` | `contribute` | `source_url` публичного Issue, PR или коммита и краткий `title`. Повтор одного источника возвращает ту же заявку или готовый ID. |
| `GET /pending-topics` | `review` | Очередь предложенных тем для сверки с первоисточниками. |
| `POST /review-topic` | `review` | `source_url` и решение `accepted` или `rejected`. Одобренный ID можно использовать для регистрации и подачи отчёта. |
| `POST /submit` | `contribute` | Поля подтверждения ниже. Новая заявка в `result` со статусом `pending`. Точный повтор возвращает ранее сохранённую заявку и её текущий статус. |
| `GET /pending` | `review` | Необязательный `limit`. Заявки на проверку в `results`. |
| `POST /review` | `review` | `result_id`, `decision` (`accepted` или `rejected`) и необязательный `reason`. Решение в `result`. Проверяющий видит свою заявку, а решение по ней принимает другой человек. |
| `GET /evidence` | `read` | Обязательный `problem_id` и необязательный `limit`. Принятые результаты по этой карточке в `results`. |
| `GET /preflight` | `read` | `q` или `url`, либо оба. Точный ID или исходный URL возвращает одобренную `exchange_topic` и связанные `reviewed_reports`. В `report_contexts` указан возраст решения и сопоставление с известной текущей ревизией. |
| `POST /withdraw` | `review` | `result_id` и `reason`. Принятый отчёт исчезает из выдачи, в потоке появляется событие отзыва. |
| `GET /poll` | `read` | Необязательные `after` и `limit`. События `result_accepted` и `result_withdrawn`, затем `next_cursor`. Клиент убирает отозванный результат по его ID. |
| `GET /subscriptions` | `read` | ID тем, на которые подписан владелец ключа. |
| `POST /subscribe` | `read` | `problem_id` и `enabled`. Подписка даёт доступ к истории темы и будущим обновлениям. |
| `GET /thread` | `read` и подписка | `problem_id`, необязательные `after` и `limit` для истории сообщений. |
| `POST /message` | `read`, `contribute` и подписка | `problem_id`, `text` до 1600 символов, `client_id` от 8 до 80 символов из букв ASCII, цифр, `_`, `-`. Дополнительно `reply_to` и `source_url`. Точный повтор возвращает ту же запись. |
| `GET /updates` | `read` | Необязательные `after`, `limit`, `wait_seconds` от 0 до 15. Сообщения и изменения статуса отчёта по подписанным темам. Ответ включает `next_cursor` для этого маршрута. |
| `GET /coordination` | `read` и подписка | `problem_id`. Текущие связи по общим ревизиям и черновики для сопровождения. |
| `GET /plans` | `read` | До 60 планов подписанных тем. Опциональный `problem_id` для одной темы. Ответ включает `viewer`, `plans`, `topics` для вступления и `progress` со сводкой по этим планам. Сводка включает ID задач, которым нужен участник или решение, и ID подтверждённых проверок. |
| `POST /plan-propose` | `read`, `contribute` и подписка | `problem_id`, `objective`, `origin_url`, `comparison_url`. Два публичных PR или коммита из разных репозиториев. |
| `POST /plan-review` | `read`, `review` и подписка | `plan_id`, `decision` (`accept` или `decline`), необязательные `priority` от 1 до 3 и `requires` с ID ранее согласованных планов. |
| `POST /plan-claim` | `read`, `contribute` и подписка | `plan_id`. Необязательное `release=true` освобождает проверку. |
| `POST /plan-result` | `read`, `contribute` и подписка | `plan_id` и `result_id` после подачи отчёта через `/submit`. Отчёт должен принадлежать добровольцу, относиться к этой теме и проверенной версии исходного проекта. |
| `POST /plan-decision` | `read`, `review` и подписка | `plan_id`, `decision` (`adopt`, `investigate`, `defer`) и `reason`. Для `adopt` нужен одобренный успешный независимый или автоматический тест. |
| `GET /office-projects` | `read` | До 60 новых проектов, включая упоминания и предложения проверок. |
| `POST /project-nominate` | `read`, `contribute` | `repo` в формате `owner/repository`, `evidence_url` внутри репозитория и `next_step`. |
| `POST /project-review` | `read`, `review` | `repo` и `decision` (`compare` или `defer`). |

У всех маршрутов чтения есть `HEAD`. `limit` принимает числа от 1 до 100, по умолчанию 50. У `/preflight` предел от 1 до 20, по умолчанию 5, включая столько же принятых записей на каждую найденную карточку. Для записи нужен объект UTF-8 JSON, `Content-Type: application/json` и размер до 64 КиБ. Запрос с подходящим ключом и допустимыми данными возвращает 200. Ошибки доступа дают 401 или 403, отключённый маршрут или отсутствующая запись — 404, конфликт решения — 409.

Заявка содержит `problem_id`, `source_url` с публичным источником GitHub, полный `revision`, `platform`, `evidence_kind`, `outcome` и короткий `summary`. Указывайте фактически проверенную версию, конфигурацию, ожидаемый результат и результат проверки. Текст и ссылки в заявках служат для проверки. Решение `accepted` добавляет событие во внутреннюю очередь. Принятая запись сохраняет свой тип, включая `simulation`. Для изменения публичной карточки действует отдельное ревью PortBridge.

Чтобы отключить обмен, остановите локальный сервер и запустите его без `--exchange-db`. Сохранённые заявки останутся в своей базе.

Курсоры `/thread`, `/poll` и `/updates` относятся к разным потокам. Сообщение хранит признак автора `author_kind`: `participant` для подключённого участника и `portbridge` для автоматического уведомления. События подтверждения и отзыва в `/updates` содержат ID отчёта. Клиент читает принятый отчёт через `/evidence` и убирает его у себя при отзыве. [Настройка обсуждений](COORDINATION.md)
