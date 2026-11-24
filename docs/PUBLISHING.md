# Публикация PortBridge

## GitHub и страницы кейсов

Описание для поля About. **A shared workspace for Xbox Series compatibility teams. Find related fixes, reuse tests, and share verified results across projects.**

Homepage — [PortBridge Pages](https://akimfomin.github.io/PortBridge/). Темы — `xbox-series`, `compatibility`, `porting`, `shader-recompiler`, `regression-testing` и `mcp`. [Настройка тем на GitHub](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics)

Перед обновлением соберите снимок в отдельную папку командой `python -m portbridge export --out dist --repository akimfomin/PortBridge`. Сверьте `sitemap.xml` и `cases/pb-0001.html`. Страница кейса содержит обычный HTML с заголовком, описанием, основной ссылкой страницы и первоисточниками. После согласованного обновления проверьте, что эти пути открываются на Pages, а страницы из карты сайта доступны без входа. [Запуск публикации](MAINTAINERS.md#публичный-сайт)

Для представления проекта используйте [журнал проверок](PORTING-WORK.md), [открытый пилот](PILOT.md) и [локальную демонстрацию](EXCHANGE-DEMO.md). В обсуждениях команды начинайте с результата, который полезен именно в этой ветке. Для общего знакомства подходят действующие публичные темы координации, если участники принимают такие предложения. Новые публикации и обращения выполняются после отдельного согласования с владельцем.

## План для MCP Registry

Текущая установка запускает `python -m portbridge.mcp` из копии репозитория. Для Registry предлагается версия публичного MCP в пакете Python со стандартным транспортом stdio. [Установка из репозитория](MCP.md) · [Поддержка PyPI в MCP Registry](https://modelcontextprotocol.io/registry/package-types#pypi-packages)

1. Подготовить версионированный пакет, содержащий сервер, нужные данные и команду запуска MCP. Установить собранный пакет в чистое окружение без исходной папки. Проверить карточку `PB-0001` и поиск по исходному PR в Codex и Claude Code. Зафиксировать версии клиентов и фактический результат.
2. Согласовать имя пакета и пространство имён Registry. Кандидат для Registry — `io.github.akimfomin/portbridge`. Добавить в описание пакета метку `mcp-name` с согласованным именем. Подготовить `server.json` с версией, ссылкой на репозиторий, пакетом PyPI и транспортом stdio. Прогнать `mcp-publisher validate`. [Проверка пакета](https://modelcontextprotocol.io/registry/package-types#pypi-packages) · [Руководство mcp-publisher](https://modelcontextprotocol.io/registry/quickstart)
3. После согласования опубликовать пакет в PyPI, затем зарегистрировать ту же версию в MCP Registry. Сверить запись Registry, установить опубликованный пакет в чистое окружение и повторить проверку каждого клиента. Добавить подтверждённую команду установки в [инструкцию MCP](MCP.md).
