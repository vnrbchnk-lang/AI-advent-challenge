import json
import os
import sys

import requests
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.filters import completion_is_selected
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich import box

from assistant.memory import MemoryLayers, build_messages

API_URL = "https://api.proxyapi.ru/openai/v1/chat/completions"
MAIN_MODEL = "gpt-4.1"
PRICES_RUB_PER_1M = {"gpt-4.1": {"input": 516, "output": 2062}}

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
    "/remember-forever": "запомнить навсегда (профиль, факты). Пример: /remember-forever стек = Kotlin",
    "/remember-now": "запомнить для текущей задачи. Пример: /remember-now бюджет = 500к",
    "/show-memory": "показать все три слоя памяти",
    "/demo": "как ТВОЯ память влияет на ответ. Можно задать вопрос: /demo <вопрос>",
    "/reset": "стереть всю память",
    "/help": "справка",
}

STEEL = "#71797e"
STEEL_BRIGHT = "#9aa0a6"
STEEL_PALE = "#c2c7cc"
STEEL_DIM = "#4b4f52"

MENU_STYLE = Style.from_dict({
    "prompt": f"{STEEL_BRIGHT} bold",
    "completion-menu": "bg:#1b1d1e",
    "completion-menu.completion": "bg:#1b1d1e #8a8f94",
    "completion-menu.completion.current": "bg:#71797e #f0f2f4 bold",
    "completion-menu.meta.completion": "bg:#232627 #5f6469",
    "completion-menu.meta.completion.current": "bg:#71797e #d4d8dc",
    "scrollbar.background": "bg:#2a2d2e",
    "scrollbar.button": "bg:#71797e",
})

console = Console()


class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        for cmd, desc in COMMANDS.items():
            if cmd.startswith(text):
                yield Completion(cmd, start_position=-len(text),
                                 display=f" {cmd} ", display_meta=f" {desc} ")


class Assistant:
    def __init__(self):
        self.model = MAIN_MODEL
        self.system = SYSTEM_PROMPT
        self.api_key = os.environ["PROXYAPI_KEY"]
        self.memory = MemoryLayers()

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
        messages = build_messages(self.memory, self.system)
        answer, usage = self.call_api(messages)
        self.memory.add_dialog("assistant", answer)
        return answer, usage, messages


def show_memory(memory):
    table = Table(box=box.ROUNDED, expand=True, show_lines=True)
    table.add_column("Слой памяти", style="bold", no_wrap=True)
    table.add_column("Что хранит", no_wrap=True)
    table.add_column("Содержимое")
    short = "\n".join(f"[dim]{m['role']}:[/dim] {m['content']}" for m in memory.short_term) or "[dim]пусто[/dim]"
    working = "\n".join(f"[{STEEL_PALE}]{k}[/{STEEL_PALE}] = {v}" for k, v in memory.working.items()) or "[dim]пусто[/dim]"
    long_term = "\n".join(f"[{STEEL_PALE}]{k}[/{STEEL_PALE}] = {v}" for k, v in memory.long_term.items()) or "[dim]пусто[/dim]"
    table.add_row(Text("КРАТКОСРОЧНАЯ", style=STEEL_BRIGHT), "текущий диалог", short)
    table.add_row(Text("РАБОЧАЯ", style=STEEL_BRIGHT), "данные текущей задачи", working)
    table.add_row(Text("ДОЛГОВРЕМЕННАЯ", style=STEEL_BRIGHT), "профиль, решения, знания", long_term)
    console.print(Panel(table, title="ПАМЯТЬ АССИСТЕНТА — три слоя, хранятся в отдельных файлах",
                        border_style=STEEL))


def run_demo(assistant, question=""):
    profile = dict(assistant.memory.long_term)
    using_sample = not profile
    if using_sample:
        profile = dict(DEMO_PROFILE)
    question = question.strip() or DEMO_QUESTION
    base = [{"role": "system", "content": assistant.system}]
    user_msg = {"role": "user", "content": question}
    long_block = {"role": "system",
                  "content": LONG_TERM_PREFIX + json.dumps(profile, ensure_ascii=False)}
    source = ("долговременная память пуста — взят образец" if using_sample
              else "взята твоя долговременная память")
    console.print(Panel(f"Вопрос: [bold]{question}[/bold]\n\nДолговременная память ([dim]{source}[/dim]): "
                        f"{profile}", title="ВЛИЯНИЕ ПАМЯТИ НА ОТВЕТ",
                        border_style=STEEL))
    with console.status("[dim]гоняю один вопрос с памятью и без…[/dim]", spinner="dots"):
        off_answer, _ = assistant.call_api(base + [user_msg])
        on_answer, _ = assistant.call_api(base + [long_block, user_msg])
    off_panel = Panel(off_answer, title="БЕЗ ПАМЯТИ", border_style=STEEL_DIM)
    on_panel = Panel(on_answer, title="С ПАМЯТЬЮ (ПРОФИЛЬ)", border_style=STEEL_BRIGHT)
    console.print(Columns([off_panel, on_panel], equal=True, expand=True))
    console.print("[dim]Тот же вопрос. Слева память не подмешана — модель отвечает обобщённо. "
                  "Справа подмешана долговременная память — ответ учитывает её факты. "
                  "Сам прогон живую память не меняет.[/dim]")


def turn_footer(assistant, usage, n_messages):
    cost = assistant.cost_rub(usage)
    console.print(Text(f"вход {usage['prompt_tokens']} ток. · ответ {usage['completion_tokens']} · "
                       f"в запросе {n_messages} сообщ. · {cost:.4f} ₽", style="dim"))


def show_help():
    intro = Text.assemble(
        ("Просто пиши сообщение — это обычный чат (попадает в краткосрочную память).\n", ""),
        ("Команды начинаются со ", ""), ("/", "bold"),
        (" — набери ", ""), ("/", "bold"), (" и появится список.\n\n", ""),
        ("Запоминание — это заметка ", "dim"), ("название = содержимое", "bold"),
        (".\n  ", "dim"), ("/remember-forever стек = Kotlin", f"bold {STEEL_PALE}"),
        (" → запомнит навсегда (профиль/факты).\n  ", "dim"),
        ("/remember-now бюджет = 500к", f"bold {STEEL_PALE}"), (" → запомнит для текущей задачи.\n", "dim"),
        ("Можно и без «=» — просто ", "dim"), ("/remember-forever люблю краткие ответы", STEEL_PALE),
        (", название придумается само.", "dim"),
    )
    table = Table(box=box.SIMPLE, expand=True, show_header=False)
    table.add_column("команда", style=f"bold {STEEL_BRIGHT}", no_wrap=True)
    table.add_column("что делает")
    for cmd, desc in COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(Panel(intro, border_style=STEEL, title="Как пользоваться"))
    console.print(Panel(table, border_style=STEEL, title="Команды"))


def save_fact(memory, store, name, rest):
    body = rest.strip()
    if not body:
        console.print(f"[dim]Формат: /{name} название = содержимое  (или просто /{name} текст)[/dim]")
        return
    if "=" in body:
        key, value = (part.strip() for part in body.split("=", 1))
    elif store == "long":
        key, value = memory.next_note_key(), body
    else:
        key, value = f"пункт_{len(memory.working) + 1}", body
    if store == "long":
        memory.remember(key, value)
        console.print(Panel(f"[{STEEL_PALE}]{key}[/{STEEL_PALE}] = {value}",
                            title="→ долговременная память", border_style=STEEL))
    else:
        memory.set_task(key, value)
        console.print(Panel(f"[{STEEL_PALE}]{key}[/{STEEL_PALE}] = {value}",
                            title="→ рабочая память", border_style=STEEL))


def handle_command(assistant, name, rest):
    memory = assistant.memory
    if name == "help":
        show_help()
    elif name == "show-memory":
        show_memory(memory)
    elif name == "demo":
        run_demo(assistant, rest)
    elif name == "reset":
        memory.reset()
        console.print(Panel("Вся память стёрта (все три слоя).", border_style=STEEL))
    elif name == "remember-forever":
        save_fact(memory, "long", "remember-forever", rest)
    elif name == "remember-now":
        save_fact(memory, "working", "remember-now", rest)
    else:
        console.print(f"[dim]Неизвестная команда /{name}. Набери /help.[/dim]")


def banner(assistant):
    memory = assistant.memory
    loaded = (f"загружено: краткосрочная {len(memory.short_term)} · "
              f"рабочая {len(memory.working)} · долговременная {len(memory.long_term)}")
    body = Text.assemble(
        ("Ассистент с явной моделью памяти", "bold"),
        ("\nДень 11 · модель ", ""), (assistant.model, f"bold {STEEL_BRIGHT}"),
        ("\n", ""), (loaded, "dim"),
        ("\n\nПиши сообщение — обычный чат. Набери ", "dim"), ("/", "bold"),
        (" для команд, ", "dim"), ("/help", f"bold {STEEL_BRIGHT}"), (" — подробно. Пустая строка — выход.", "dim"),
    )
    console.print(Panel(body, border_style=STEEL, box=box.DOUBLE))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    assistant = Assistant()
    banner(assistant)
    bindings = KeyBindings()

    @bindings.add("enter", filter=completion_is_selected)
    def _(event):
        event.current_buffer.complete_state = None

    session = PromptSession(completer=SlashCompleter(), complete_while_typing=True,
                            key_bindings=bindings, style=MENU_STYLE)
    while True:
        try:
            user = session.prompt(HTML("<prompt>Ты ›</prompt> ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user == "" or user.lower() in ("exit", "/exit"):
            break
        if user.startswith("/"):
            parts = user[1:].split(maxsplit=1)
            handle_command(assistant, parts[0].lower() if parts else "",
                           parts[1] if len(parts) > 1 else "")
            continue
        with console.status("[dim]ассистент думает…[/dim]", spinner="dots"):
            answer, usage, messages = assistant.ask(user)
        console.print(Panel(answer, title="АССИСТЕНТ", border_style=STEEL, box=box.ROUNDED))
        turn_footer(assistant, usage, len(messages))
    console.print("[dim]Память сохранена. Пока![/dim]")


if __name__ == "__main__":
    main()
