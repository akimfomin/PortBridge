# Test requests

Anyone with a GitHub account can ask for a compatibility check on hardware they lack. Choose **Request a test** on a ready task in the [Test Lab](https://akimfomin.github.io/PortBridge/#/lab), or describe a new check in the [request form](https://github.com/akimfomin/PortBridge/issues/new?template=test-request.yml). Include the equipment, exact public commit, and expected result. For a new test on a specific model, enter `amd: RX 9070 XT` or `nvidia: RTX 3060 Ti` in the Equipment field. Use synthetic inputs.

Once a maintainer reviews the request, PortBridge can invite one person in that GitHub issue. It searches selected public test threads and checks a list of verified reports from connected projects. The recipient can take the check or decline by replying in the issue. Joining PortBridge in advance is optional. If there is no suitable report yet, the request stays open for a volunteer.

Post the result or a link to it in the request. Include the tested commit, hardware, and outcome, including failures or skipped cases. PortBridge can then share that evidence with the original project. A link to a maintainer decision or adopted change records what the receiving project did with the result.

## For maintainers

1. Verify that the request is still useful, the source is public and pinned, and the test uses synthetic or public source-only inputs. For a custom request, check that its hardware field is specific enough for a useful invitation.
2. Apply the `notify-testers` label to approve one invitation. For a task with a receiving PR, the invitation requires the recorded revision to still be its open head. Check the workflow result and the comment in the original request. If GitHub did not start the workflow, review the current issue text, then run **PortBridge test invitations** on `main` with its issue number. Leave a note if the available reports have no suitable match.
3. Keep discussions and outcomes in the request. If someone asks to stop receiving invitations, honor that request before any further contact.

## По-русски

Допустим, тест уже прошёл на NVIDIA, а нужен ещё прогон на AMD. Нажмите **Запросить тест** в готовой карточке или опишите новый тест. Укажите нужное железо, точную версию кода и ожидаемый результат. Для конкретной модели можно указать, например, `amd: RX 9070 XT`. Отправьте запрос на GitHub. [Открыть Test Lab](https://akimfomin.github.io/PortBridge/?lang=ru#/lab)

После проверки запроса PortBridge подберёт человека по публичным отчётам о его тестах и пригласит его прямо в задаче на GitHub. Предварительная подписка не нужна. Получатель может согласиться или отказаться в комментарии. Если он запустит проверку, там же можно оставить результат и передать его в исходный проект.
