import json
import os
import sys

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from assistant.memory import MemoryLayers, build_messages, LAYER_TITLES

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

console = Console()


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
    table.add_column("Слой", style="bold", no_wrap=True)
    table.add_column("Содержимое")
    short = "\n".join(f"[dim]{m['role']}:[/dim] {m['content']}" for m in memory.short_term) or "[dim]пусто[/dim]"
    working = "\n".join(f"[cyan]{k}[/cyan] = {v}" for k, v in memory.working.items()) or "[dim]пусто[/dim]"
    long_term = "\n".join(f"[green]{k}[/green] = {v}" for k, v in memory.long_term.items()) or "[dim]пусто[/dim]"
    table.add_row(Text("КРАТКОСРОЧНАЯ", style="yellow"), short)
    table.add_row(Text("РАБОЧАЯ", style="cyan"), working)
    table.add_row(Text("ДОЛГОВРЕМЕННАЯ", style="green"), long_term)
    return table


def show_layers(memory):
    console.print(Panel(layers_table(memory), title="🧠 Память ассистента (3 слоя, хранятся отдельно)",
                        border_style="magenta"))


def show_prompt(assistant):
    messages = assistant.build()
    table = Table(box=box.SIMPLE, expand=True)
    table.add_column("#", justify="right", style="dim", no_wrap=True)
    table.add_column("role", no_wrap=True)
    table.add_column("откуда / содержимое")
    for i, m in enumerate(messages, 1):
        table.add_row(str(i), m["role"], m["content"])
    flags = (f"long_term: {'ON' if assistant.use_long_term else 'OFF'}   "
             f"working: {'ON' if assistant.use_working else 'OFF'}")
    console.print(Panel(table, title=f"📤 Что реально уходит в запрос  [dim]({flags})[/dim]",
                        border_style="blue"))


def turn_footer(assistant, usage, n_messages):
    cost = assistant.cost_rub(usage)
    text = (f"вход {usage['prompt_tokens']} ток. · ответ {usage['completion_tokens']} · "
            f"в запросе {n_messages} сообщ. · {cost:.4f} ₽  ·  "
            f"long_term {'ON' if assistant.use_long_term else 'OFF'} / "
            f"working {'ON' if assistant.use_working else 'OFF'}")
    console.print(Text(text, style="dim"))


HELP = """[bold]Команды памяти (явный выбор, что и куда):[/bold]
  [green]remember[/green] ключ = значение   → долговременная (профиль/решения/знания)
  [green]remember[/green] текст             → долговременная (автоключ)
  [cyan]task[/cyan] ключ = значение         → рабочая (данные текущей задачи)
  [yellow]обычное сообщение[/yellow]        → краткосрочная (диалог) + ответ

[bold]Просмотр:[/bold]
  [magenta]layers[/magenta]      три слоя памяти    [blue]prompt[/blue]   что реально уходит в запрос

[bold]Управление:[/bold]
  forget ключ      убрать из долговременной
  newtask          очистить рабочую (сменили задачу)
  clear            очистить диалог (краткосрочную)
  reset            стереть всю память
  longterm on|off  подмешивать ли долговременную (демо влияния на ответ)
  working on|off   подмешивать ли рабочую
  help             эта справка     exit / пусто   выход"""


def handle_command(assistant, user):
    memory = assistant.memory
    low = user.lower()
    if low in ("help", "?"):
        console.print(Panel(HELP, border_style="cyan", title="Справка"))
        return True
    if low == "layers":
        show_layers(memory)
        return True
    if low == "prompt":
        show_prompt(assistant)
        return True
    if low == "reset":
        memory.reset()
        console.print(Panel("Вся память стёрта (все 3 слоя).", border_style="red"))
        return True
    if low == "newtask":
        memory.clear_working()
        console.print(Panel("Рабочая память очищена — начали новую задачу. "
                            "Долговременная и диалог сохранены.", border_style="cyan"))
        return True
    if low == "clear":
        memory.clear_dialog()
        console.print(Panel("Краткосрочная память (диалог) очищена.", border_style="yellow"))
        return True
    if low in ("longterm on", "longterm off"):
        assistant.use_long_term = low.endswith("on")
        console.print(f"[dim]Долговременная память в запросе: {'ON' if assistant.use_long_term else 'OFF'}[/dim]")
        return True
    if low in ("working on", "working off"):
        assistant.use_working = low.endswith("on")
        console.print(f"[dim]Рабочая память в запросе: {'ON' if assistant.use_working else 'OFF'}[/dim]")
        return True
    if low.startswith("forget "):
        key = user.split(maxsplit=1)[1].strip()
        if memory.forget(key):
            console.print(f"[dim]Убрано из долговременной: {key}[/dim]")
        else:
            console.print(f"[dim]Ключа '{key}' в долговременной нет.[/dim]")
        return True
    if low.startswith("remember "):
        body = user.split(maxsplit=1)[1].strip()
        if "=" in body:
            key, value = body.split("=", 1)
            key, value = key.strip(), value.strip()
        else:
            key, value = memory.next_note_key(), body
        memory.remember(key, value)
        console.print(Panel(f"[green]{key}[/green] = {value}", title="→ долговременная память",
                            border_style="green"))
        return True
    if low.startswith("task "):
        body = user.split(maxsplit=1)[1].strip()
        if "=" in body:
            key, value = body.split("=", 1)
            key, value = key.strip(), value.strip()
        else:
            key, value = f"пункт_{len(memory.working) + 1}", body
        memory.set_task(key, value)
        console.print(Panel(f"[cyan]{key}[/cyan] = {value}", title="→ рабочая память",
                            border_style="cyan"))
        return True
    return False


def banner(assistant):
    memory = assistant.memory
    loaded = (f"загружено: краткосрочная {len(memory.short_term)} · "
              f"рабочая {len(memory.working)} · долговременная {len(memory.long_term)}")
    body = Text.assemble(
        ("Ассистент с явной моделью памяти", "bold"),
        ("\nДень 11 · модель ", ""), (assistant.model, "bold cyan"),
        ("\n", ""), (loaded, "dim"),
        ("\n\nТри слоя памяти хранятся в отдельных файлах в ", "dim"),
        ("store/", "bold"), (". 'help' — команды.", "dim"),
    )
    console.print(Panel(body, border_style="magenta", box=box.DOUBLE))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    assistant = Assistant()
    banner(assistant)
    while True:
        try:
            user = console.input("[bold magenta]Ты ›[/bold magenta] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user == "" or user.lower() == "exit":
            break
        if handle_command(assistant, user):
            continue
        with console.status("[dim]ассистент думает…[/dim]", spinner="dots"):
            answer, usage, messages = assistant.ask(user)
        console.print(Panel(answer, title="🤖 Ассистент", border_style="green", box=box.ROUNDED))
        turn_footer(assistant, usage, len(messages))
    console.print("[dim]Память сохранена. Пока![/dim]")


if __name__ == "__main__":
    main()
