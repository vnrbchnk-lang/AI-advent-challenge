# Журнал — Неделя 4 (MCP)

> Тема недели — `04-mcp-summary.md`. Растущий пакет `week4/agent/`, единая команда `agent16`
> (`pip install -e week4`). Каждый день добавляет слой; функционал дней — командами внутри CLI.

---

### День 16 — подключение MCP
- Статус: готово (живой запуск CLI — за пользователем, для видео)
- Файлы: `week4/pyproject.toml`, `week4/agent/__init__.py`, `week4/agent/mcp_client.py`,
  `week4/agent/cli.py`
- Задание: установить MCP SDK/клиент; минимальный код, который устанавливает MCP-соединение и
  получает от MCP список доступных инструментов. Проверить: соединение устанавливается; список
  инструментов корректно возвращается. Результат: код, подключающийся к MCP и выводящий список tools.
- Что сделано:
  - Поставлен официальный Python SDK `mcp` (1.28.0) через `pip install -e week4`; зарегистрирована
    команда `agent16 = agent.cli:main`.
  - `mcp_client.py` — `McpClient.list_remote_tools(url)`: `streamablehttp_client` → `ClientSession` →
    `initialize()` → `list_tools()`, нормализует в `{name, description, input_schema}`.
  - `cli.py` — единый агент-CLI (rich + prompt_toolkit, navy, без эмодзи). Команда `/demo16`:
    подключается к публичному **DeepWiki MCP** (`https://mcp.deepwiki.com/mcp`, Streamable HTTP,
    без авторизации), печатает список tools rich-таблицей. Сетевые ошибки ловятся в понятную панель.
  - Проверено (без ProxyAPI-токенов): соединение установлено, DeepWiki вернул 3 tools
    (`read_wiki_structure`, `read_wiki_contents`, `ask_question`); entry-point `agent16` импортируется
    и зарегистрирован.
- Сверх ТЗ: красивый CLI-каркас под всю неделю (правило 12), который дорастает до агента дней 17–19.
- Ссылка на сдачу: —

---

### День 17 — первый свой MCP-инструмент (Wikipedia)
- Статус: готово (живой запуск CLI — за пользователем)
- Файлы: `week4/agent/server/__init__.py`, `server/wiki.py`, `server/app.py`, `agent/mcp_agent.py`,
  `agent/cli.py`
- Задание: свой MCP-сервер вокруг API; регистрация инструмента; описание входных параметров; возврат
  результата; вызов из приложения и использование результата.
- Что сделано:
  - `server/app.py` — FastMCP-сервер (stdio), tools `wiki_search`/`wiki_fetch` вокруг Wikipedia API
    (`ru.wikipedia.org/w/api.php`, без ключа, через `requests` в `server/wiki.py`).
  - Описание входных параметров — через `Annotated[..., Field(description=...)]` (pydantic), описание
    инструмента — через `@mcp.tool(description=...)`; без докстрингов/комментариев (правило 10).
  - `mcp_agent.py` — `McpAgent`: поднимает сервер subprocess'ом по stdio, держит постоянное соединение
    через фоновый asyncio-loop (`run_coroutine_threadsafe`); `list_tools()`, `call_tool()`.
  - `cli.py` — команда `/search <запрос>` вызывает MCP-tool `wiki_search` и печатает результат таблицей;
    `/tools` — список инструментов своего сервера.
  - Проверено (без ProxyAPI): соединение поднялось, сервер отдал 7 tools, `/search Python` вернул статьи.
- Сверх ТЗ: постоянное соединение (а не разовый вызов) — нужно для дня 18 (живой фон-поток).
- Ссылка на сдачу: —

### День 18 — планировщик и фоновые задачи
- Статус: готово (живой запуск CLI — за пользователем)
- Файлы: `week4/agent/server/scheduler.py`, `server/app.py`, `agent/cli.py`
- Задание: MCP-инструмент с отложенным/периодическим выполнением; сохранять данные (JSON/SQLite);
  выполняться по расписанию; возвращать агрегированный результат. Результат: агент 24/7 с периодической
  сводкой.
- Что сделано:
  - `server/scheduler.py` — SQLite (`store/reminders.db`): таблицы `reminders`, `events`. Демон-поток
    (стартует при запуске сервера): каждые 3с гасит due-напоминания (fired + event), каждые 30с пишет
    tick (периодический сбор). Функции `remind_add`/`reminders_list`/`summary_run`.
  - MCP-tools `remind_add`, `reminders_list`, `summary_run` в `app.py`. Сервер «24/7»: живёт пока открыт
    `agent16` либо запущен отдельно `python -m agent.server.app`.
  - `cli.py` — `/remind <+сек|ISO> <текст>`, `/reminders`, `/summary`.
  - Проверено: напоминание `+2` сработало фоном (`fired`), SQLite пережил перезапуск, `summary_run` дал
    агрегат (всего/сработало/ожидает/тики).
- Сверх ТЗ: лог `events` + тики для наглядного «периодического сбора».
- Ссылка на сдачу: —

### День 19 — композиция MCP-инструментов (пайплайн)
- Статус: готово; детерминированный пайплайн проверен по структуре, живой прогон (summarize/ask = LLM) —
  за пользователем (правило 11, токены ProxyAPI)
- Файлы: `week4/agent/server/pipeline.py`, `server/app.py`, `agent/mcp_agent.py`, `agent/cli.py`
- Задание: несколько MCP-инструментов (search/summarize/saveToFile); пайплайн «получить→обработать→
  сохранить»; автоматическое выполнение цепочки; корректность передачи данных. Результат: автоматический
  пайплайн из нескольких MCP-tools.
- Что сделано:
  - `server/pipeline.py` — tools `summarize(text)` (LLM `gpt-4o-mini` через ProxyAPI) и
    `save_to_file(name, content)` (пишет в `store/`). На сервере теперь 7 tools.
  - `mcp_agent.py` — **детерминированный** `run_pipeline(query)`: `wiki_search` → `wiki_fetch` →
    `summarize` → `save_to_file`; результат каждого шага явно передаётся в следующий, стадии печатаются.
  - `mcp_agent.py` — **LLM-режим** (сверх ТЗ) `ask(goal)`: MCP-tools → OpenAI `tools` schema, цикл
    tool_calls (модель сама выбирает инструменты), лимит шагов.
  - `cli.py` — `/pipeline <запрос>` (детерминированный) и `/ask <цель>` (автономный LLM).
  - Проверено без LLM: цепочка структурно собрана, search/fetch/save работают; summarize и `/ask` требуют
    `PROXYAPI_KEY` → прогон пользователя.
- Сверх ТЗ: режим `/ask` (автономный выбор инструментов LLM).
- ВНИМАНИЕ: перед видео — пользователю проверить поддержку OpenAI `tools` в ProxyAPI одиночным
  smoke-вызовом; детерминированный `/pipeline` от этого не зависит.
- Ссылка на сдачу: —
