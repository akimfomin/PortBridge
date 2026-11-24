# Публикация PortBridge

## GitHub и страницы кейсов

Описание для поля About. **A shared workspace for Xbox Series compatibility teams. Find related fixes, reuse tests, and share verified results across projects.**

Homepage — [PortBridge Pages](https://akimfomin.github.io/PortBridge/). Темы — `xbox-series`, `compatibility`, `porting`, `shader-recompiler`, `regression-testing` и `mcp`. [Настройка тем на GitHub](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics)

Перед обновлением соберите снимок в отдельную папку командой `python -m portbridge export --out dist --repository akimfomin/PortBridge`. Сверьте `sitemap.xml` и `cases/pb-0001.html`. Страница кейса содержит обычный HTML с заголовком, описанием, основной ссылкой страницы и первоисточниками. После согласованного обновления проверьте, что эти пути открываются на Pages, а страницы из карты сайта доступны без входа. [Запуск публикации](MAINTAINERS.md#публичный-сайт)

Для представления проекта используйте [журнал проверок](PORTING-WORK.md), [открытый пилот](PILOT.md) и [локальную демонстрацию](EXCHANGE-DEMO.md). В обсуждениях команды начинайте с результата, который полезен именно в этой ветке. Для общего знакомства подходят действующие публичные темы координации, если участники принимают такие предложения. Новые публикации и обращения выполняются после отдельного согласования с владельцем.

## Пилот с трекерами и сообществами

- Six on PC принимает предложения о недостающих инструментах в закреплённом обсуждении. PortWatch VI принимает заявки в Issues и показывает инструменты в Toolkit. Для первого пилота хватает ссылки на открытую проверку, а при интересе авторов есть [пример блока Test Lab](TEST-LAB.md#show-open-checks-on-a-partner-site). [Six on PC #3](https://github.com/Github-Samuel/sixonpc/discussions/3) · [PortWatch VI Issues](https://github.com/4lwayz/portwatch-vi/issues)
- Для разговора о конкретном тесте используйте техническое обсуждение проекта или связанный с ним Discord-канал. У Xbox2Windows открыта категория Development Q&A, а в README указан Discord команды. Для более широкой подборки есть Awesome GTA VI с правилами самостоятельного добавления. [Xbox2Windows Discussions](https://github.com/R0Y00/Xbox2Windows/discussions/categories/development-q-a) · [Discord в README проекта](https://github.com/R0Y00/Xbox2Windows#readme) · [Правила Awesome GTA VI](https://github.com/Ahmet-Dedeler/awesome-gta6-reverse-engineering/blob/main/CONTRIBUTING.md)
- Для каталогов ИИ-инструментов сначала проверяем установку MCP в чистом окружении. Официальный Registry принимает метаданные публично доступного пакета или удалённого сервера. В Awesome MCP Servers есть отдельные правила подачи. [MCP Registry](https://modelcontextprotocol.io/registry/quickstart) · [Awesome MCP Servers](https://github.com/punkpeye/awesome-mcp-servers/blob/main/CONTRIBUTING.md)

В [журнале взаимодействий](COMMUNITY-COORDINATION.md#проверяемые-взаимодействия--verified-interactions) фиксируем ссылку на предложение, ответ, появление записи на сайте партнёра и отчёты о выполненных участниками проверках. Пробный блок или отправленная заявка сами по себе ещё не подтверждают использование сторонней командой.

## План для MCP Registry

Текущая установка запускает `python -m portbridge.mcp` из копии репозитория. Для Registry предлагается версия публичного MCP в пакете Python со стандартным транспортом stdio. [Установка из репозитория](MCP.md) · [Поддержка PyPI в MCP Registry](https://modelcontextprotocol.io/registry/package-types#pypi-packages)

1. Подготовить версионированный пакет, содержащий сервер, нужные данные и команду запуска MCP. Установить собранный пакет в чистое окружение без исходной папки. Проверить карточку `PB-0001` и поиск по исходному PR в Codex и Claude Code. Зафиксировать версии клиентов и фактический результат.
2. Согласовать имя пакета и пространство имён Registry. Кандидат для Registry — `io.github.akimfomin/portbridge`. Добавить в описание пакета метку `mcp-name` с согласованным именем. Подготовить `server.json` с версией, ссылкой на репозиторий, пакетом PyPI и транспортом stdio. Прогнать `mcp-publisher validate`. [Проверка пакета](https://modelcontextprotocol.io/registry/package-types#pypi-packages) · [Руководство mcp-publisher](https://modelcontextprotocol.io/registry/quickstart)
3. После согласования опубликовать пакет в PyPI, затем зарегистрировать ту же версию в MCP Registry. Сверить запись Registry, установить опубликованный пакет в чистое окружение и повторить проверку каждого клиента. Добавить подтверждённую команду установки в [инструкцию MCP](MCP.md).
