import asyncio

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

DEEPWIKI_URL = "https://mcp.deepwiki.com/mcp"

NAVY = "#34568b"
NAVY_BRIGHT = "#6f9ad1"
NAVY_PALE = "#a9c8ee"
NAVY_DIM = "#223a5c"
WARN = "#b58900"

COMMANDS = {
    "/demo16": "подключиться к публичному DeepWiki MCP и показать список инструментов",
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
    return HTML(" <b>agent16</b>  Неделя 4 — MCP   |   /demo16  /help  /exit ")


def banner():
    console.print(Panel.fit(
        Text("agent16  —  MCP-агент (Неделя 4)", style=f"bold {NAVY_BRIGHT}"),
        border_style=NAVY,
        box=box.ROUNDED,
        subtitle=Text("День 16: подключение к MCP + список инструментов", style=NAVY_PALE),
    ))


def show_help():
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_edge=False)
    table.add_column("команда", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("что делает", style=NAVY_PALE)
    for name, meta in COMMANDS.items():
        table.add_row(name, meta)
    console.print(Panel(table, title="Команды", border_style=NAVY, box=box.ROUNDED))


def render_tools(url, tools):
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("#", style=NAVY_DIM, justify="right", no_wrap=True)
    table.add_column("инструмент", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("описание", style=NAVY_PALE)
    for i, tool in enumerate(tools, 1):
        description = tool["description"].strip().splitlines()
        first_line = description[0] if description else ""
        table.add_row(str(i), tool["name"], first_line)
    console.print(Panel(
        table,
        title=Text(f"MCP tools/list  ·  {url}", style=f"bold {NAVY_BRIGHT}"),
        subtitle=Text(f"соединение установлено · инструментов: {len(tools)}", style=NAVY_PALE),
        border_style=NAVY,
        box=box.ROUNDED,
    ))


def demo16():
    console.print(Text(f"Подключаюсь к {DEEPWIKI_URL} ...", style=NAVY_PALE))
    try:
        tools = asyncio.run(McpClient.list_remote_tools(DEEPWIKI_URL))
    except Exception as error:
        console.print(Panel(
            Text(f"Не удалось подключиться к MCP-серверу.\n{type(error).__name__}: {error}", style=WARN),
            title="Ошибка соединения",
            border_style=WARN,
            box=box.ROUNDED,
        ))
        return
    if not tools:
        console.print(Text("Соединение есть, но сервер не вернул инструментов.", style=WARN))
        return
    render_tools(DEEPWIKI_URL, tools)


def dispatch(line):
    command = line.split(maxsplit=1)[0]
    if command == "/demo16":
        demo16()
    elif command == "/help":
        show_help()
    else:
        console.print(Text(f"Неизвестная команда: {command}. /help — список.", style=WARN))


def main():
    banner()
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
    console.print(Text("Пока.", style=NAVY_PALE))


if __name__ == "__main__":
    main()
