import json

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.text import Text

from devassist import config, tools_project
from devassist.assistant import DevAssistant
from devassist.llm import complete

NAVY = "#34568b"
NAVY_BRIGHT = "#6f9ad1"
NAVY_PALE = "#a9c8ee"
NAVY_DIM = "#223a5c"
WARN = "#b58900"
OK = "#5c9a5c"
BAD = "#a05252"

PROJECT = "advent"
MAX_STEPS = 20
MAX_TOOL_RESULT_CHARS = 8000
HISTORY_LIMIT = 60

TOOL_NAMES = [
    "project__list_files",
    "project__read_file",
    "project__grep",
    "rag_search",
    "project__write_file",
    "project__replace_in_file",
    "project__git_status",
    "project__git_diff",
    "project__git_log",
    "project__git_commit",
    "project__git_push",
]

SYSTEM = (
    "Ты — ассистент-разработчик, который работает прямо внутри репозитория AI Advent Challenge. "
    "Это учебный репозиторий: в корне CLAUDE.md с контекстом и правилами, README.md, журналы "
    "JOURNAL-week1..7.md с заданиями и итогами по дням, и каталоги week1..week7 с кодом.\n"
    "Общение свободное: человек ставит цель словами, ты сам решаешь, какие файлы прочитать, "
    "что найти и что изменить.\n"
    "Правила:\n"
    "1) Все инструменты вызывай с project='advent'.\n"
    "2) Сначала факты: смотри список файлов, читай их, ищи grep-ом или rag_search. Не выдумывай "
    "содержимое файлов и не отвечай по памяти.\n"
    "3) Файлы правишь сам через write_file и replace_in_file — не проси человека что-то вписать. "
    "Правя существующий файл, сперва прочитай его целиком, чтобы не потерять содержимое.\n"
    "4) Коммит и пуш делай ТОЛЬКО когда человек прямо об этом попросил. В git_commit передавай "
    "список изменённых файлов и осмысленное сообщение.\n"
    "5) Отвечай по-русски, коротко и по делу. В конце пиши, какие файлы изменил."
)


console = Console()

STYLE = Style.from_dict({
    "prompt": f"{NAVY_BRIGHT} bold",
    "bottom-toolbar": "bg:#16283f #a9c8ee",
})


def confirm_dangerous(name, arguments):
    body = Text()
    body.append("Опасная операция — нужно подтверждение человека.\n", style=WARN)
    body.append(f"{name}\n", style=f"bold {NAVY_BRIGHT}")
    body.append(json.dumps(arguments, ensure_ascii=False)[:800], style=NAVY_PALE)
    console.print(Panel(body, title="Подтверждение", border_style=WARN, box=box.ROUNDED))
    return Confirm.ask("Выполнить?", default=False)


def _shrink(payload):
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return text[:MAX_TOOL_RESULT_CHARS] + "… (результат обрезан)"


def _needs_project(schema):
    return "project" in (schema.get("properties") or {})


class DevChat:
    def __init__(self, assistant):
        self.assistant = assistant
        self.messages = [{"role": "system", "content": SYSTEM}]
        self.specs = assistant.registry.specs(
            [name for name in TOOL_NAMES if name in assistant.registry.tools])

    def _trim(self):
        if len(self.messages) <= HISTORY_LIMIT:
            return
        head = self.messages[0]
        tail = self.messages[-HISTORY_LIMIT:]
        while tail and tail[0]["role"] != "user":
            tail.pop(0)
        self.messages = [head] + tail

    def send(self, text, on_tool):
        self.messages.append({"role": "user", "content": text})
        for _ in range(MAX_STEPS):
            self._trim()
            message = complete(self.messages, model=config.MAIN_MODEL, temperature=0.1,
                               tools=self.specs, label="devagent")
            calls = message.get("tool_calls") or []
            self.messages.append({
                "role": "assistant",
                "content": message.get("content") or "",
                **({"tool_calls": calls} if calls else {}),
            })
            if not calls:
                return (message.get("content") or "").strip()
            for call in calls:
                name = call["function"]["name"]
                try:
                    arguments = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                tool = self.assistant.registry.tools.get(name)
                if tool and _needs_project(tool.schema) and not arguments.get("project"):
                    arguments["project"] = PROJECT
                outcome = self.assistant.executor.safe_call(name, arguments)
                on_tool(name, arguments, outcome)
                payload = outcome["result"] if outcome["ok"] else {"error": outcome["error"]}
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": _shrink(payload),
                })
        return "Достигнут лимит шагов — уточни задачу."


def show_tool(name, arguments, outcome):
    line = Text("  → ", style=NAVY_DIM)
    line.append(name, style=NAVY_BRIGHT)
    line.append(" " + json.dumps(arguments, ensure_ascii=False)[:110], style=NAVY_DIM)
    if not outcome["ok"]:
        line.append("  " + outcome["error"][:90], style=BAD)
    console.print(line)


def show_diff():
    status = tools_project.git_status(PROJECT)
    untracked = [item["path"] for item in status["files"] if item["status"] == "??"]
    payload = tools_project.git_diff(PROJECT, fallback=False)
    if not payload["diff"].strip() and not untracked:
        console.print(Text("  рабочее дерево чистое", style=NAVY_DIM))
        return
    if payload["diff"].strip():
        console.print(Panel(Text(payload["diff"][:6000], style=NAVY_PALE),
                            title=f"git diff — {', '.join(payload['files'])}",
                            border_style=OK, box=box.ROUNDED))
    if untracked:
        console.print(Text("  новые файлы: " + ", ".join(untracked), style=OK))


def _toolbar():
    branch = tools_project.git_branch(PROJECT)
    return HTML(f" <b>agent34</b>  репозиторий: {config.ADVENT_ROOT} | ветка: {branch['branch']}"
                f" | {'есть несохранённые правки' if branch['dirty'] else 'дерево чистое'} ")


def main():
    console.print(Panel.fit(
        Text("agent34  —  файловый ассистент по репозиторию (День 34)", style=f"bold {NAVY_BRIGHT}"),
        border_style=NAVY, box=box.ROUNDED,
        subtitle=Text("свободный чат · читает и правит файлы сам · diff · коммит и пуш",
                      style=NAVY_PALE)))
    console.print(Text("Просто пиши задачу словами. /diff — показать изменения, /exit — выход.",
                       style=NAVY_DIM))

    assistant = DevAssistant(servers=["project"], confirm=confirm_dangerous)
    with console.status(Text("поднимаю MCP-сервер проекта", style=NAVY_PALE), spinner="dots"):
        statuses = assistant.start()
    for item in statuses:
        if not item["connected"]:
            console.print(Text(f"сервер {item['server']} не поднялся: {item['error']}", style=WARN))
    chat = DevChat(assistant)

    session = PromptSession(style=STYLE, bottom_toolbar=_toolbar)
    while True:
        try:
            line = session.prompt(HTML("<prompt>ты ></prompt> ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in ("/exit", "/quit"):
            break
        if line == "/diff":
            show_diff()
            continue
        try:
            answer = chat.send(line, show_tool)
        except Exception as error:
            console.print(Panel(Text(f"{type(error).__name__}: {error}", style=WARN),
                                border_style=WARN, box=box.ROUNDED))
            continue
        console.print(Panel(Text(answer, style=NAVY_PALE), title="Ассистент",
                            border_style=NAVY, box=box.ROUNDED))
        show_diff()

    assistant.stop()
    console.print(Text("до встречи", style=NAVY_DIM))


if __name__ == "__main__":
    main()
