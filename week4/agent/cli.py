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
from agent.mcp_agent import McpAgent, DEEPWIKI_URL

NAVY = "#34568b"
NAVY_BRIGHT = "#6f9ad1"
NAVY_PALE = "#a9c8ee"
NAVY_DIM = "#223a5c"
WARN = "#b58900"
OK = "#5c9a5c"

COMMANDS = {
    "/servers": "день 20: список зарегистрированных MCP-серверов и их статус",
    "/tools": "список инструментов всех серверов (с пометкой сервера)",
    "/flow": "день 20: длинный кросс-серверный флоу wiki→pipeline→scheduler. Пример: /flow квантовые компьютеры",
    "/research": "день 20: длинный флоу с DeepWiki: deepwiki→pipeline→scheduler. Пример: /research facebook/react",
    "/ask": "день 20: автономный агент — LLM сам выбирает инструменты с разных серверов. Пример: /ask найди про Питон и сохрани",
    "/demo20": "день 20: показать реестр серверов и план кросс-серверных вызовов",
    "/demo16": "день 16: подключиться к публичному DeepWiki MCP и показать список инструментов",
    "/search": "день 17: поиск в Википедии (сервер wiki). Пример: /search Python",
    "/remind": "день 18: добавить напоминание (сервер scheduler). Пример: /remind +30 проверить почту",
    "/reminders": "день 18: список напоминаний (сервер scheduler)",
    "/summary": "день 18: сводка планировщика (сервер scheduler)",
    "/pipeline": "день 19: алиас /flow (цепочка search→fetch→summarize→save)",
    "/help": "справка по командам",
    "/exit": "выйти",
}

FLOW_PLANS = [
    ("/flow <тема>", [
        ("wiki", "wiki_search"),
        ("wiki", "wiki_fetch"),
        ("pipeline", "summarize"),
        ("pipeline", "save_to_file"),
        ("scheduler", "remind_add"),
    ]),
    ("/research <owner/repo>", [
        ("deepwiki", "read_wiki_structure"),
        ("deepwiki", "ask_question"),
        ("pipeline", "summarize"),
        ("pipeline", "save_to_file"),
        ("scheduler", "remind_add"),
    ]),
]

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
    if not agent:
        return HTML(" <b>agent16</b>  Неделя 4 — MCP   |   серверы: не подключены ")
    servers = agent.servers()
    up = sum(1 for s in servers if s["ok"])
    tools = len(agent.list_tools())
    return HTML(f" <b>agent16</b>  Неделя 4 — MCP   |   серверов подключено: {up}/{len(servers)} · tools: {tools} ")


def banner():
    console.print(Panel.fit(
        Text("agent16  —  MCP-агент (Неделя 4)", style=f"bold {NAVY_BRIGHT}"),
        border_style=NAVY,
        box=box.ROUNDED,
        subtitle=Text("оркестрация нескольких MCP-серверов · кросс-серверный флоу", style=NAVY_PALE),
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


def _need_agent():
    if agent is None:
        console.print(Text("MCP-серверы не подключены (см. ошибку при старте).", style=WARN))
        return False
    return True


def cmd_servers():
    if not _need_agent():
        return
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("#", style=NAVY_DIM, justify="right", no_wrap=True)
    table.add_column("сервер", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("транспорт", style=NAVY_PALE, no_wrap=True)
    table.add_column("статус", no_wrap=True)
    table.add_column("tools", style=NAVY_PALE, justify="right")
    table.add_column("описание", style=NAVY_PALE)
    for i, srv in enumerate(agent.servers(), 1):
        if srv["ok"]:
            status = Text("подключён", style=OK)
        else:
            status = Text("ошибка: " + (srv["error"] or "—"), style=WARN)
        table.add_row(str(i), srv["name"], srv["transport"], status, str(srv["tools"]), srv["title"])
    console.print(Panel(table, title=Text("Зарегистрированные MCP-серверы", style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text("один агент-хост → несколько серверов", style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))


def show_tools():
    if not _need_agent():
        return
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("#", style=NAVY_DIM, justify="right", no_wrap=True)
    table.add_column("сервер", style=NAVY_BRIGHT, no_wrap=True)
    table.add_column("инструмент", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("неймспейс", style=NAVY_DIM, no_wrap=True)
    table.add_column("описание", style=NAVY_PALE)
    for i, tool in enumerate(agent.list_tools(), 1):
        description = (tool["description"] or "").strip().splitlines()
        table.add_row(str(i), tool["server"], tool["name"], tool["qualified"],
                      description[0] if description else "")
    console.print(Panel(table, title=Text("Инструменты всех серверов", style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text(f"всего инструментов: {len(agent.list_tools())}", style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))


def demo20():
    if not _need_agent():
        return
    cmd_servers()
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("флоу", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("шаг", style=NAVY_DIM, justify="right", no_wrap=True)
    table.add_column("сервер", style=NAVY_BRIGHT, no_wrap=True)
    table.add_column("инструмент", style=NAVY_PALE, no_wrap=True)
    for name, steps in FLOW_PLANS:
        for i, (server, tool) in enumerate(steps, 1):
            table.add_row(name if i == 1 else "", str(i), server, tool)
    console.print(Panel(table, title=Text("План кросс-серверных вызовов (порядок и маршрут)", style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text("запусти /flow или /research для живого прогона", style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))


def _render_flow(stages, result, title):
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("шаг", style=NAVY_DIM, justify="right", no_wrap=True)
    table.add_column("сервер", style=NAVY_BRIGHT, no_wrap=True)
    table.add_column("MCP-tool", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("передано дальше", style=NAVY_PALE)
    for i, (server, tool, info) in enumerate(stages, 1):
        table.add_row(str(i), server, tool, info)
    console.print(Panel(table, title=Text(title, style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text("данные идут от инструмента к инструменту через разные серверы", style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))
    if result and result.get("summary"):
        head = result.get("title") or result.get("repo") or ""
        console.print(Panel(Text(result["summary"], style=NAVY_PALE),
                            title=Text(f"Саммари «{head}» → {result.get('path','')}", style=f"bold {NAVY_BRIGHT}"),
                            border_style=NAVY, box=box.ROUNDED))


def cmd_flow(topic):
    if not _need_agent():
        return
    if not topic:
        console.print(Text("Укажи тему: /flow <запрос>", style=WARN))
        return
    console.print(Text("Кросс-серверный флоу: wiki → pipeline → scheduler ...", style=NAVY_PALE))
    try:
        stages, result = agent.run_flow(topic)
    except Exception as error:
        _error("Ошибка флоу", error)
        return
    _render_flow(stages, result, f"Флоу · {topic}")


def cmd_research(repo):
    if not _need_agent():
        return
    if not repo:
        console.print(Text("Укажи репозиторий: /research <owner/repo>. Пример: /research facebook/react", style=WARN))
        return
    console.print(Text("Кросс-серверный флоу: deepwiki → pipeline → scheduler ...", style=NAVY_PALE))
    try:
        stages, result = agent.run_research(repo)
    except Exception as error:
        _error("Ошибка флоу research (DeepWiki/обработка)", error)
        return
    _render_flow(stages, result, f"Research · {repo}")


def cmd_search(query):
    if not _need_agent():
        return
    if not query:
        console.print(Text("Укажи запрос: /search <текст>", style=WARN))
        return
    try:
        result = agent.call_tool("wiki", "wiki_search", {"query": query, "limit": 5})
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
                        subtitle=Text(f"сервер wiki · {len(rows)} статей", style=NAVY_PALE),
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
        result = agent.call_tool("scheduler", "remind_add", {"text": text, "run_at": run_at})
    except Exception as error:
        _error("Ошибка вызова MCP-tool remind_add", error)
        return
    console.print(Panel(
        Text(f"#{result['id']}  «{result['text']}»  сработает: {result['run_at']}", style=NAVY_PALE),
        title="Напоминание добавлено (сервер scheduler)", border_style=NAVY, box=box.ROUNDED))


def cmd_reminders():
    if not _need_agent():
        return
    result = agent.call_tool("scheduler", "reminders_list", {})
    rows = result.get("reminders", []) if isinstance(result, dict) else []
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("id", style=NAVY_DIM, justify="right")
    table.add_column("текст", style=f"bold {NAVY_BRIGHT}")
    table.add_column("сработать", style=NAVY_PALE)
    table.add_column("статус", style=NAVY_PALE)
    for row in rows:
        status = "сработало " + (row["fired_at"] or "") if row["fired"] else "ожидает"
        table.add_row(str(row["id"]), row["text"], row["run_at"], status)
    console.print(Panel(table, title="Напоминания (сервер scheduler)", border_style=NAVY, box=box.ROUNDED))


def cmd_summary():
    if not _need_agent():
        return
    data = agent.call_tool("scheduler", "summary_run", {})
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


def cmd_ask(goal):
    if not _need_agent():
        return
    if not goal:
        console.print(Text("Укажи цель: /ask <что сделать>", style=WARN))
        return
    console.print(Text("Агент думает и вызывает инструменты с разных серверов ...", style=NAVY_PALE))
    try:
        transcript, answer = agent.ask(goal)
    except Exception as error:
        _error("Ошибка LLM-режима (проверь PROXYAPI_KEY и поддержку tools)", error)
        return
    if transcript:
        table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
        table.add_column("#", style=NAVY_DIM, justify="right")
        table.add_column("сервер", style=NAVY_BRIGHT, no_wrap=True)
        table.add_column("инструмент", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
        table.add_column("аргументы", style=NAVY_PALE)
        for i, step in enumerate(transcript, 1):
            table.add_row(str(i), step["server"], step["tool"], json.dumps(step["arguments"], ensure_ascii=False))
        console.print(Panel(table, title="Вызовы инструментов (LLM сам выбрал сервер и tool)", border_style=NAVY, box=box.ROUNDED))
    console.print(Panel(Text(answer, style=NAVY_PALE), title="Ответ агента", border_style=NAVY, box=box.ROUNDED))


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
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("#", style=NAVY_DIM, justify="right", no_wrap=True)
    table.add_column("инструмент", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("описание", style=NAVY_PALE)
    for i, tool in enumerate(tools, 1):
        description = (tool["description"] or "").strip().splitlines()
        table.add_row(str(i), tool["name"], description[0] if description else "")
    console.print(Panel(table, title=Text(f"DeepWiki MCP  ·  {DEEPWIKI_URL}", style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text(f"соединение установлено · инструментов: {len(tools)}", style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))


def dispatch(line):
    parts = line.split(maxsplit=1)
    command = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""
    if command == "/servers":
        cmd_servers()
    elif command == "/tools":
        show_tools()
    elif command == "/flow" or command == "/pipeline":
        cmd_flow(rest)
    elif command == "/research":
        cmd_research(rest)
    elif command == "/ask":
        cmd_ask(rest)
    elif command == "/demo20":
        demo20()
    elif command == "/demo16":
        demo16()
    elif command == "/search":
        cmd_search(rest)
    elif command == "/remind":
        cmd_remind(rest)
    elif command == "/reminders":
        cmd_reminders()
    elif command == "/summary":
        cmd_summary()
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
        up = sum(1 for s in agent.servers() if s["ok"])
        console.print(Text(f"MCP-серверов подключено: {up}/{len(agent.servers())} · инструментов: {len(agent.list_tools())}", style=NAVY_PALE))
    except Exception as error:
        _error("Не удалось поднять MCP-серверы", error)


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
