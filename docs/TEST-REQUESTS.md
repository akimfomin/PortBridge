# Test requests

Anyone with a GitHub account can ask for a compatibility check on hardware they lack. Choose **Request a test** on a ready task in the [Test Lab](https://akimfomin.github.io/PortBridge/#/lab), or describe a new check in the [request form](https://github.com/akimfomin/PortBridge/issues/new?template=test-request.yml). Include the equipment, exact public commit, and expected result. For a new test on a specific model, enter `amd: RX 9070 XT` or `nvidia: RTX 3060 Ti` in the Equipment field. Use synthetic inputs.

During passive maintenance, requests stay open for volunteers to find and answer. Posting or labeling a request sends no tester invitation. A maintainer who chooses to coordinate a particular test can manually invite one person in that issue. Participation is optional and there is no guaranteed response time.

Post the result or a link to it in the request. Include the tested commit, hardware, and outcome, including failures or skipped cases. PortBridge can then share that evidence with the original project. A link to a maintainer decision or adopted change records what the receiving project did with the result.

## For maintainers

1. Verify that the request is still useful, the source is public and pinned, and the test uses synthetic or public source-only inputs. For a custom request, check that its hardware field is specific enough for a useful invitation.
2. When a volunteer has already replied, coordinate in the request. If a separate invitation would help, review the current text, apply the `notify-testers` approval label and manually run **PortBridge test invitations** on `main` with the request number. For a task with a receiving PR, the recorded revision must still be its open head. Read the workflow result before following up.
3. Keep discussions and outcomes in the request. If someone asks to stop receiving invitations, honor that request before any further contact.

## По-русски

Допустим, тест уже прошёл на NVIDIA, а нужен ещё прогон на AMD. Нажмите **Запросить тест** в готовой карточке или опишите новый тест. Укажите нужное железо, точную версию кода и ожидаемый результат. Для конкретной модели можно указать, например, `amd: RX 9070 XT`. Отправьте запрос на GitHub. [Открыть Test Lab](https://akimfomin.github.io/PortBridge/?lang=ru#/lab)

В режиме пассивной поддержки запрос остаётся открытым для добровольцев. Создание запроса и добавление метки сами по себе никого не приглашают. Если сопровождающий возьмётся за конкретную проверку, он может вручную отправить одно приглашение в этой задаче. Участие добровольное, срок ответа не гарантирован. Результат и ссылку на него можно оставить прямо в обсуждении.
