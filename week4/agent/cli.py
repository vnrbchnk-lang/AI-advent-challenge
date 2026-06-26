import asyncio
import json

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from agent.mcp_client import McpClient
from agent.mcp_agent import McpAgent

DEEPWIKI_URL = "https://mcp.deepwiki.com/mcp"

NAVY = "#34568b"
NAVY_BRIGHT = "#6f9ad1"
NAVY_PALE = "#a9c8ee"
NAVY_DIM = "#223a5c"
WARN = "#b58900"

COMMANDS = {
    "/demo16": "день 16: подключиться к публичному DeepWiki MCP и показать список инструментов",
    "/tools": "список инструментов своего MCP-сервера",
    "/search": "день 17: поиск в Википедии через MCP-tool. Пример: /search Python",
    "/remind": "день 18: добавить напоминание. Пример: /remind +30 проверить почту",
    "/reminders": "день 18: список напоминаний со статусом",
    "/summary": "день 18: агрегированная сводка планировщика",
    "/pipeline": "день 19: цепочка search→fetch→summarize→save. Пример: /pipeline квантовые компьютеры",
    "/ask": "день 19: автономный агент (LLM сам выбирает инструменты). Пример: /ask найди и сохрани про Питон",
    "/help": "справка по командам",
    "/exit": "выйти",
}

MENU_STYLE = Style.from_dict({
    "prompt": f"{NAVY_BRIGHT} bold",
    "bottom-toolbar": "bg:#16283f #a9c8ee",
    "completion-menu": "bg:#0f1c2e",
    "completion-menu.completion": "bg:#0f1c2e #7f9fc4",
    "completion-menu.completion.current": "bg:#34568b #eaf1fb bold",
    "completion-menu.meta.completion": "bg:#152538 #5f7799",
    "completion-menu.meta.completion.current": "bg:#34568b #c8d8ef",
    "scrollbar.background": "bg:#16283f",
    "scrollbar.button": "bg:#34568b",
})

console = Console()
agent = None


class CommandCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return
        word = document.get_word_before_cursor(WORD=True)
        for name, meta in COMMANDS.items():
            if name.startswith(text):
                yield Completion(name, start_position=-len(word), display=name, display_meta=meta)


def _bottom_toolbar():
    count = len(agent.list_tools()) if agent else 0
    state = f"сервер: подключён · tools: {count}" if agent else "сервер: не подключён"
    return HTML(f" <b>agent16</b>  Неделя 4 — MCP   |   {state} ")


def banner():
    console.print(Panel.fit(
        Text("agent16  —  MCP-агент (Неделя 4)", style=f"bold {NAVY_BRIGHT}"),
        border_style=NAVY,
        box=box.ROUNDED,
        subtitle=Text("MCP: подключение · свой сервер · планировщик · пайплайн", style=NAVY_PALE),
    ))


def show_help():
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_edge=False)
    table.add_column("команда", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("что делает", style=NAVY_PALE)
    for name, meta in COMMANDS.items():
        table.add_row(name, meta)
    console.print(Panel(table, title="Команды", border_style=NAVY, box=box.ROUNDED))


def _error(title, error):
    console.print(Panel(
        Text(f"{type(error).__name__}: {error}", style=WARN),
        title=title,
        border_style=WARN,
        box=box.ROUNDED,
    ))


def _tools_table(title, subtitle, tools):
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("#", style=NAVY_DIM, justify="right", no_wrap=True)
    table.add_column("инструмент", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("описание", style=NAVY_PALE)
    for i, tool in enumerate(tools, 1):
        description = (tool["description"] or "").strip().splitlines()
        table.add_row(str(i), tool["name"], description[0] if description else "")
    console.print(Panel(
        table,
        title=Text(title, style=f"bold {NAVY_BRIGHT}"),
        subtitle=Text(subtitle, style=NAVY_PALE),
        border_style=NAVY,
        box=box.ROUNDED,
    ))


def demo16():
    console.print(Text(f"Подключаюсь к {DEEPWIKI_URL} ...", style=NAVY_PALE))
    try:
        tools = asyncio.run(McpClient.list_remote_tools(DEEPWIKI_URL))
    except Exception as error:
        _error("Ошибка соединения с DeepWiki", error)
        return
    if not tools:
        console.print(Text("Соединение есть, но сервер не вернул инструментов.", style=WARN))
        return
    _tools_table(f"DeepWiki MCP  ·  {DEEPWIKI_URL}", f"соединение установлено · инструментов: {len(tools)}", tools)


def show_tools():
    if not _need_agent():
        return
    _tools_table("Свой MCP-сервер (stdio)", f"инструментов: {len(agent.list_tools())}", agent.list_tools())


def cmd_search(query):
    if not _need_agent():
        return
    if not query:
        console.print(Text("Укажи запрос: /search <текст>", style=WARN))
        return
    try:
        result = agent.call_tool("wiki_search", {"query": query, "limit": 5})
    except Exception as error:
        _error("Ошибка вызова MCP-tool wiki_search", error)
        return
    rows = result.get("results", []) if isinstance(result, dict) else []
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("#", style=NAVY_DIM, justify="right")
    table.add_column("статья", style=f"bold {NAVY_BRIGHT}")
    table.add_column("фрагмент", style=NAVY_PALE)
    for i, row in enumerate(rows, 1):
        table.add_row(str(i), row["title"], row["snippet"])
    console.print(Panel(table, title=Text(f"wiki_search  ·  {query}", style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text(f"результат MCP-tool · {len(rows)} статей", style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))


def cmd_remind(rest):
    if not _need_agent():
        return
    parts = rest.split(maxsplit=1)
    if len(parts) < 2:
        console.print(Text("Формат: /remind <+секунды|ISO> <текст>. Пример: /remind +30 позвонить", style=WARN))
        return
    run_at, text = parts[0], parts[1]
    try:
        result = agent.call_tool("remind_add", {"text": text, "run_at": run_at})
    except Exception as error:
        _error("Ошибка вызова MCP-tool remind_add", error)
        return
    console.print(Panel(
        Text(f"#{result['id']}  «{result['text']}»  сработает: {result['run_at']}", style=NAVY_PALE),
        title="Напоминание добавлено", border_style=NAVY, box=box.ROUNDED))


def cmd_reminders():
    if not _need_agent():
        return
    result = agent.call_tool("reminders_list", {})
    rows = result.get("reminders", []) if isinstance(result, dict) else []
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("id", style=NAVY_DIM, justify="right")
    table.add_column("текст", style=f"bold {NAVY_BRIGHT}")
    table.add_column("сработать", style=NAVY_PALE)
    table.add_column("статус", style=NAVY_PALE)
    for row in rows:
        status = "сработало " + (row["fired_at"] or "") if row["fired"] else "ожидает"
        table.add_row(str(row["id"]), row["text"], row["run_at"], status)
    console.print(Panel(table, title="Напоминания", border_style=NAVY, box=box.ROUNDED))


def cmd_summary():
    if not _need_agent():
        return
    data = agent.call_tool("summary_run", {})
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_header=False)
    table.add_column("метрика", style=f"bold {NAVY_BRIGHT}")
    table.add_column("значение", style=NAVY_PALE)
    table.add_row("напоминаний всего", str(data["reminders_total"]))
    table.add_row("сработало", str(data["reminders_fired"]))
    table.add_row("ожидает", str(data["reminders_pending"]))
    table.add_row("тиков планировщика", str(data["scheduler_ticks"]))
    recent = ", ".join(r["text"] for r in data["recent_fired"]) or "—"
    table.add_row("последние сработавшие", recent)
    console.print(Panel(table, title=Text(f"Сводка планировщика · {data['generated_at']}", style=f"bold {NAVY_BRIGHT}"),
                        border_style=NAVY, box=box.ROUNDED))


def cmd_pipeline(query):
    if not _need_agent():
        return
    if not query:
        console.print(Text("Укажи тему: /pipeline <запрос>", style=WARN))
        return
    try:
        stages, result = agent.run_pipeline(query)
    except Exception as error:
        _error("Ошибка пайплайна", error)
        return
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("шаг", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("MCP-tool", style=NAVY_BRIGHT, no_wrap=True)
    table.add_column("передано дальше", style=NAVY_PALE)
    for i, (tool, info) in enumerate(stages, 1):
        table.add_row(str(i), tool, info)
    console.print(Panel(table, title=Text(f"Пайплайн · {query}", style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text("данные идут от инструмента к инструменту", style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))
    if result:
        console.print(Panel(Text(result["summary"], style=NAVY_PALE),
                            title=Text(f"Саммари «{result['title']}» → {result['path']}", style=f"bold {NAVY_BRIGHT}"),
                            border_style=NAVY, box=box.ROUNDED))


def cmd_ask(goal):
    if not _need_agent():
        return
    if not goal:
        console.print(Text("Укажи цель: /ask <что сделать>", style=WARN))
        return
    console.print(Text("Агент думает и вызывает инструменты ...", style=NAVY_PALE))
    try:
        transcript, answer = agent.ask(goal)
    except Exception as error:
        _error("Ошибка LLM-режима (проверь PROXYAPI_KEY и поддержку tools)", error)
        return
    if transcript:
        table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
        table.add_column("#", style=NAVY_DIM, justify="right")
        table.add_column("инструмент", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
        table.add_column("аргументы", style=NAVY_PALE)
        for i, step in enumerate(transcript, 1):
            table.add_row(str(i), step["tool"], json.dumps(step["arguments"], ensure_ascii=False))
        console.print(Panel(table, title="Вызовы инструментов (LLM сам выбрал)", border_style=NAVY, box=box.ROUNDED))
    console.print(Panel(Text(answer, style=NAVY_PALE), title="Ответ агента", border_style=NAVY, box=box.ROUNDED))


def _need_agent():
    if agent is None:
        console.print(Text("Свой MCP-сервер не подключён (см. ошибку при старте).", style=WARN))
        return False
    return True


def dispatch(line):
    parts = line.split(maxsplit=1)
    command = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""
    if command == "/demo16":
        demo16()
    elif command == "/tools":
        show_tools()
    elif command == "/search":
        cmd_search(rest)
    elif command == "/remind":
        cmd_remind(rest)
    elif command == "/reminders":
        cmd_reminders()
    elif command == "/summary":
        cmd_summary()
    elif command == "/pipeline":
        cmd_pipeline(rest)
    elif command == "/ask":
        cmd_ask(rest)
    elif command == "/help":
        show_help()
    else:
        console.print(Text(f"Неизвестная команда: {command}. /help — список.", style=WARN))


def _connect_agent():
    global agent
    try:
        candidate = McpAgent()
        candidate.connect()
        agent = candidate
        console.print(Text(f"Свой MCP-сервер подключён · инструментов: {len(agent.list_tools())}", style=NAVY_PALE))
    except Exception as error:
        _error("Не удалось поднять свой MCP-сервер", error)


def main():
    banner()
    _connect_agent()
    show_help()
    session = PromptSession(
        completer=CommandCompleter(),
        complete_while_typing=True,
        style=MENU_STYLE,
        bottom_toolbar=_bottom_toolbar,
    )
    while True:
        try:
            line = session.prompt(HTML("<prompt>agent16 ›</prompt> ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in ("/exit", "/quit"):
            break
        dispatch(line)
    if agent is not None:
        agent.close()
    console.print(Text("Пока.", style=NAVY_PALE))


if __name__ == "__main__":
    main()
