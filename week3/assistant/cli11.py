import json
import os
import sys

import requests
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich import box

from assistant.memory import MemoryLayers, build_messages

API_URL = "https://api.proxyapi.ru/openai/v1/chat/completions"
MAIN_MODEL = "gpt-5.2"
PRICES_RUB_PER_1M = {"gpt-5.2": {"input": 531, "output": 4245}}

SYSTEM_PROMPT = (
    "Ты — ассистент с явной моделью памяти из трёх слоёв. "
    "Долговременную память (профиль, решения, знания) считай постоянными фактами о "
    "пользователе и проекте и всегда им следуй. Рабочую память считай контекстом текущей "
    "задачи. Краткосрочную — это текущий диалог. Опирайся на то, что есть в памяти, не "
    "выдумывай того, чего там нет. Отвечай по-русски, по существу, кратко."
)

LONG_TERM_PREFIX = ("Долговременная память (профиль, решения, знания) — "
                    "учитывай как постоянные факты о пользователе и проекте: ")

DEMO_PROFILE = {
    "имя": "Иван",
    "стек": "Kotlin",
    "архитектура": "только MVI, обязательная ViewModel",
    "запреты": "не использовать Python и RxJava",
}
DEMO_QUESTION = "Набросай старт сервиса авторизации для нашего проекта."

COMMANDS = {
    "/remember": "запомнить навсегда → долговременная. Пример: /remember стек = Kotlin",
    "/task": "данные текущей задачи → рабочая. Пример: /task бюджет = 500к",
    "/layers": "показать все три слоя памяти",
    "/prompt": "показать, что реально уходит в запрос модели",
    "/demo": "A/B: один вопрос с памятью и без (влияние на ответ)",
    "/forget": "убрать факт из долговременной. Пример: /forget стек",
    "/newtask": "очистить рабочую память (сменили задачу)",
    "/clear": "очистить диалог (краткосрочную память)",
    "/reset": "стереть всю память (все три слоя)",
    "/longterm": "подмешивать ли долговременную: /longterm on | off",
    "/working": "подмешивать ли рабочую: /working on | off",
    "/help": "показать справку",
    "/exit": "выход",
}

console = Console()


class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        parts = text.split(" ")
        if len(parts) == 1:
            for cmd, desc in COMMANDS.items():
                if cmd.startswith(parts[0]):
                    yield Completion(cmd, start_position=-len(parts[0]),
                                     display=cmd, display_meta=desc)
        elif len(parts) == 2 and parts[0] in ("/longterm", "/working"):
            for opt, meta in (("on", "включить"), ("off", "выключить")):
                if opt.startswith(parts[1]):
                    yield Completion(opt, start_position=-len(parts[1]),
                                     display=opt, display_meta=meta)


class Assistant:
    def __init__(self):
        self.model = MAIN_MODEL
        self.system = SYSTEM_PROMPT
        self.api_key = os.environ["PROXYAPI_KEY"]
        self.memory = MemoryLayers()
        self.use_long_term = True
        self.use_working = True

    def build(self):
        return build_messages(self.memory, self.system, self.use_long_term, self.use_working)

    def call_api(self, messages):
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages},
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"], data["usage"]

    def cost_rub(self, usage):
        price = PRICES_RUB_PER_1M[self.model]
        return (usage["prompt_tokens"] * price["input"]
                + usage["completion_tokens"] * price["output"]) / 1_000_000

    def ask(self, text):
        self.memory.add_dialog("user", text)
        messages = self.build()
        answer, usage = self.call_api(messages)
        self.memory.add_dialog("assistant", answer)
        return answer, usage, messages


def layers_table(memory):
    table = Table(box=box.ROUNDED, expand=True, show_lines=True)
    table.add_column("Слой памяти", style="bold", no_wrap=True)
    table.add_column("Что это", no_wrap=True)
    table.add_column("Содержимое")
    short = "\n".join(f"[dim]{m['role']}:[/dim] {m['content']}" for m in memory.short_term) or "[dim]пусто[/dim]"
    working = "\n".join(f"[cyan]{k}[/cyan] = {v}" for k, v in memory.working.items()) or "[dim]пусто[/dim]"
    long_term = "\n".join(f"[green]{k}[/green] = {v}" for k, v in memory.long_term.items()) or "[dim]пусто[/dim]"
    table.add_row(Text("КРАТКОСРОЧНАЯ", style="yellow"), "текущий диалог", short)
    table.add_row(Text("РАБОЧАЯ", style="cyan"), "данные текущей задачи", working)
    table.add_row(Text("ДОЛГОВРЕМЕННАЯ", style="green"), "профиль, решения, знания", long_term)
    return table


def show_layers(memory):
    console.print(Panel(layers_table(memory), title="🧠 Память ассистента (три слоя, хранятся отдельно)",
                        border_style="magenta"))


def show_prompt(assistant):
    messages = assistant.build()
    table = Table(box=box.SIMPLE, expand=True)
    table.add_column("#", justify="right", style="dim", no_wrap=True)
    table.add_column("роль", no_wrap=True)
    table.add_column("содержимое")
    for i, m in enumerate(messages, 1):
        table.add_row(str(i), m["role"], m["content"])
    flags = (f"долговременная: {'ВКЛ' if assistant.use_long_term else 'ВЫКЛ'}   "
             f"рабочая: {'ВКЛ' if assistant.use_working else 'ВЫКЛ'}")
    console.print(Panel(table, title=f"📤 Что реально уходит в запрос  [dim]({flags})[/dim]",
                        border_style="blue"))


def run_demo(assistant):
    base = [{"role": "system", "content": assistant.system}]
    user_msg = {"role": "user", "content": DEMO_QUESTION}
    long_block = {"role": "system",
                  "content": LONG_TERM_PREFIX + json.dumps(DEMO_PROFILE, ensure_ascii=False)}
    off_messages = base + [user_msg]
    on_messages = base + [long_block, user_msg]
    console.print(Panel(f"Вопрос: [bold]{DEMO_QUESTION}[/bold]\n\nДолговременная память (профиль): "
                        f"{DEMO_PROFILE}", title="🔬 Демо: влияние памяти на ответ",
                        border_style="magenta"))
    with console.status("[dim]гоняю один вопрос с памятью и без…[/dim]", spinner="dots"):
        off_answer, off_usage = assistant.call_api(off_messages)
        on_answer, on_usage = assistant.call_api(on_messages)
    off_panel = Panel(off_answer, title="❌ БЕЗ долговременной памяти",
                      border_style="red", subtitle=f"{off_usage['prompt_tokens']} вход. ток.")
    on_panel = Panel(on_answer, title="✅ С долговременной памятью",
                     border_style="green", subtitle=f"{on_usage['prompt_tokens']} вход. ток.")
    console.print(Columns([off_panel, on_panel], equal=True, expand=True))
    console.print("[dim]Тот же вопрос. Слева профиль не подмешан — модель берёт ходовой "
                  "вариант (обычно Python). Справа из долговременной памяти приходит "
                  "Kotlin/MVI и запреты — ответ другой. Живую память это не трогает.[/dim]")


def turn_footer(assistant, usage, n_messages):
    cost = assistant.cost_rub(usage)
    text = (f"вход {usage['prompt_tokens']} ток. · ответ {usage['completion_tokens']} · "
            f"в запросе {n_messages} сообщ. · {cost:.4f} ₽  ·  "
            f"долговременная {'ВКЛ' if assistant.use_long_term else 'ВЫКЛ'} / "
            f"рабочая {'ВКЛ' if assistant.use_working else 'ВЫКЛ'}")
    console.print(Text(text, style="dim"))


def show_help():
    intro = Text.assemble(
        ("Просто пиши сообщение — это обычный чат (попадает в краткосрочную память).\n", ""),
        ("Команды начинаются со ", ""), ("/", "bold"),
        (" — набери ", ""), ("/", "bold"), (" и появится список.\n\n", ""),
        ("Память — это заметки вида ", "dim"), ("НАЗВАНИЕ = СОДЕРЖИМОЕ", "bold"),
        (".\nНапример ", "dim"), ("/remember стек = Kotlin", "bold green"),
        (" → название «стек», содержимое «Kotlin».\n", "dim"),
        ("Без «=» название придумается само.", "dim"),
    )
    table = Table(box=box.SIMPLE, expand=True, show_header=False)
    table.add_column("команда", style="bold cyan", no_wrap=True)
    table.add_column("что делает")
    for cmd, desc in COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(Panel(intro, border_style="cyan", title="Как пользоваться"))
    console.print(Panel(table, border_style="cyan", title="Команды"))


def handle_command(assistant, name, rest):
    memory = assistant.memory
    if name == "help":
        show_help()
        return True
    if name == "layers":
        show_layers(memory)
        return True
    if name == "prompt":
        show_prompt(assistant)
        return True
    if name == "demo":
        run_demo(assistant)
        return True
    if name == "reset":
        memory.reset()
        console.print(Panel("Вся память стёрта (все три слоя).", border_style="red"))
        return True
    if name == "newtask":
        memory.clear_working()
        console.print(Panel("Рабочая память очищена — начали новую задачу. "
                            "Долговременная и диалог сохранены.", border_style="cyan"))
        return True
    if name == "clear":
        memory.clear_dialog()
        console.print(Panel("Краткосрочная память (диалог) очищена.", border_style="yellow"))
        return True
    if name in ("longterm", "working"):
        if rest.lower() not in ("on", "off"):
            console.print(f"[dim]Формат: /{name} on  или  /{name} off[/dim]")
            return True
        value = rest.lower() == "on"
        if name == "longterm":
            assistant.use_long_term = value
        else:
            assistant.use_working = value
        label = "Долговременная" if name == "longterm" else "Рабочая"
        console.print(f"[dim]{label} память в запросе: {'ВКЛ' if value else 'ВЫКЛ'}[/dim]")
        return True
    if name == "forget":
        key = rest.strip()
        if not key:
            console.print("[dim]Формат: /forget название[/dim]")
        elif memory.forget(key):
            console.print(f"[dim]Убрано из долговременной: {key}[/dim]")
        else:
            console.print(f"[dim]Факта «{key}» в долговременной нет.[/dim]")
        return True
    if name in ("remember", "task"):
        body = rest.strip()
        if not body:
            console.print(f"[dim]Формат: /{name} название = содержимое  (или просто /{name} текст)[/dim]")
            return True
        if "=" in body:
            key, value = body.split("=", 1)
            key, value = key.strip(), value.strip()
        elif name == "remember":
            key, value = memory.next_note_key(), body
        else:
            key, value = f"пункт_{len(memory.working) + 1}", body
        if name == "remember":
            memory.remember(key, value)
            console.print(Panel(f"[green]{key}[/green] = {value}",
                                title="→ долговременная память", border_style="green"))
        else:
            memory.set_task(key, value)
            console.print(Panel(f"[cyan]{key}[/cyan] = {value}",
                                title="→ рабочая память", border_style="cyan"))
        return True
    console.print(f"[dim]Неизвестная команда /{name}. Набери /help.[/dim]")
    return True


def banner(assistant):
    memory = assistant.memory
    loaded = (f"загружено: краткосрочная {len(memory.short_term)} · "
              f"рабочая {len(memory.working)} · долговременная {len(memory.long_term)}")
    body = Text.assemble(
        ("Ассистент с явной моделью памяти", "bold"),
        ("\nДень 11 · модель ", ""), (assistant.model, "bold cyan"),
        ("\n", ""), (loaded, "dim"),
        ("\n\nПиши сообщение — обычный чат. Набери ", "dim"), ("/", "bold"),
        (" для списка команд, ", "dim"), ("/help", "bold cyan"), (" — подробно.", "dim"),
    )
    console.print(Panel(body, border_style="magenta", box=box.DOUBLE))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    assistant = Assistant()
    banner(assistant)
    session = PromptSession(completer=SlashCompleter(), complete_while_typing=True)
    while True:
        try:
            user = session.prompt("Ты › ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user == "" or user.lower() in ("exit", "/exit"):
            break
        if user.startswith("/"):
            parts = user[1:].split(maxsplit=1)
            name = parts[0].lower() if parts else ""
            rest = parts[1] if len(parts) > 1 else ""
            handle_command(assistant, name, rest)
            continue
        with console.status("[dim]ассистент думает…[/dim]", spinner="dots"):
            answer, usage, messages = assistant.ask(user)
        console.print(Panel(answer, title="🤖 Ассистент", border_style="green", box=box.ROUNDED))
        turn_footer(assistant, usage, len(messages))
    console.print("[dim]Память сохранена. Пока![/dim]")


if __name__ == "__main__":
    main()
