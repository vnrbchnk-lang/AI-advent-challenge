import json
import os
import sys

import requests
from prompt_toolkit import PromptSession, prompt as pt_prompt
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

from assistant.memory import MemoryLayers
from assistant.profile import Profile, FIELDS
from assistant.state import TaskStore, STAGES, TRANSITIONS, EXPECTED
from assistant.invariants import Invariants
from assistant.validator import critic_check
from assistant.prompt_builder import build_messages

API_URL = "https://api.proxyapi.ru/openai/v1/chat/completions"
MAIN_MODEL = "gpt-4.1"
PRICES_RUB_PER_1M = {"gpt-4.1": {"input": 516, "output": 2062}}

SYSTEM_PROMPT = (
    "Ты — stateful-ассистент. У тебя есть слои контекста: инварианты (нерушимые ограничения), "
    "профиль пользователя (персонализация), состояние задачи (стадия), память. Всегда соблюдай "
    "инварианты, подстраивайся под профиль, держись текущей стадии задачи. Опирайся на то, что "
    "есть в контексте, не выдумывай. Отвечай по-русски, по существу."
)

STEEL = "#71797e"
STEEL_BRIGHT = "#9aa0a6"
STEEL_PALE = "#c2c7cc"
STEEL_DIM = "#4b4f52"
WARN = "#b58900"

COMMANDS = {
    "/status": "показать всё состояние: задачи, инварианты, профиль, память",
    "/task": "открыть задачу в её рабочем пространстве (создаёт новую или продолжает). Пример: /task сервис авторизации",
    "/interview": "стартовое интервью — собрать профиль вопросами",
    "/remember-forever": "долговременная память. Пример: /remember-forever решение = используем JWT",
    "/remember-now": "рабочая память. Пример: /remember-now эндпоинт = /login",
    "/profile-set": "поле профиля вручную. Пример: /profile-set стиль = краткий",
    "/invariant-add": "инвариант + запретные слова. Пример: /invariant-add Только Kotlin :: python, java",
    "/demo1": "память: один вопрос с твоей памятью и без неё",
    "/demo2": "персонализация: один вопрос с твоим профилем и без него",
    "/demo3": "состояние задачи: как стадия влияет на ответ + переходы автомата",
    "/demo4": "инварианты: ответ с твоими ограничениями и без них + проверка кодом и критиком",
    "/reset": "стереть всё состояние",
    "/help": "справка",
}

WORKSPACE_COMMANDS = {
    "/plan": "утвердить план задачи. Пример: /plan 1) роуты 2) JWT 3) хранение",
    "/next": "перейти на следующую стадию (код проверит легальность)",
    "/back": "вернуться на предыдущую стадию",
    "/status": "показать карточку этой задачи",
    "/pause": "приостановить задачу и выйти в общий чат",
    "/delete": "удалить эту задачу",
    "/help": "справка по рабочему пространству",
    "/exit": "выйти в общий чат (задача остаётся активной)",
}

MENU_STYLE = Style.from_dict({
    "prompt": f"{STEEL_BRIGHT} bold",
    "bottom-toolbar": "bg:#2a2d2e #9aa0a6",
    "completion-menu": "bg:#1b1d1e",
    "completion-menu.completion": "bg:#1b1d1e #8a8f94",
    "completion-menu.completion.current": "bg:#71797e #f0f2f4 bold",
    "completion-menu.meta.completion": "bg:#232627 #5f6469",
    "completion-menu.meta.completion.current": "bg:#71797e #d4d8dc",
    "scrollbar.background": "bg:#2a2d2e",
    "scrollbar.button": "bg:#71797e",
})

console = Console()

DEMO_MEM_FACTS = {
    "стек": "Kotlin",
    "архитектура": "только MVI, обязательная ViewModel",
    "запреты": "не Python, не RxJava",
}
DEMO_MEM_QUESTION = "Набросай старт сервиса авторизации для нашего проекта."

DEMO_PROFILE_SAMPLE = {
    "стиль": "краткий, без воды",
    "формат": "код-first",
    "уровень": "senior",
    "роль": "тимлид, нужен быстрый скелет",
}
DEMO_PROFILE_QUESTION = "Как сделать дебаунс пользовательского ввода в приложении?"

DEMO_STATE_QUESTION = "Сразу дай финальный код решения, без обсуждений и плана."
SAMPLE_STATE_BLOCK = (
    "Состояние текущей задачи (task state machine) — работай строго в рамках стадии, "
    "не перескакивай этапы:\n"
    "- задача: сервис авторизации\n"
    "- стадия: planning (шаг 0)\n"
    "- ожидаемое действие: составить план и утвердить его; код будет на стадии execution\n"
    "- утверждённый план: —"
)

DEMO_INV_INVARIANTS = [
    {"rule": "Стек только Kotlin. Python запрещён.", "forbid": ["python"]},
    {"rule": "Архитектура только MVI. MVVM и MVP запрещены.", "forbid": ["mvvm", "mvp"]},
]
DEMO_INV_QUESTION = "Набросай быстрый прототип экрана на Python с архитектурой MVVM."

INTERVIEW_QUESTIONS = [
    ("стиль", "Как тебе отвечать по стилю? (формальный / дружеский / краткий)"),
    ("формат", "В каком формате удобнее ответы? (списки / проза / код-first)"),
    ("уровень", "Твой уровень, чтобы выбрать глубину? (junior / middle / senior)"),
    ("роль", "Кто ты и зачем тебе агент? (роль и цель)"),
]

STATUS_LABEL = {"active": "в работе", "paused": "пауза", "done": "готово"}


class SlashCompleter(Completer):
    def __init__(self, commands):
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        for cmd, desc in self.commands.items():
            if cmd.startswith(text):
                yield Completion(cmd, start_position=-len(text),
                                 display=f" {cmd} ", display_meta=f" {desc} ")


class Assistant:
    def __init__(self):
        self.model = MAIN_MODEL
        self.system = SYSTEM_PROMPT
        self.api_key = os.environ["PROXYAPI_KEY"]
        self.memory = MemoryLayers()
        self.profile = Profile()
        self.state = TaskStore()
        self.invariants = Invariants()

    def call_api(self, messages, model=None):
        model = model or self.model
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": model, "messages": messages},
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"], data["usage"]

    def cost_rub(self, usage, model=None):
        model = model or self.model
        price = PRICES_RUB_PER_1M.get(model)
        if not price:
            return None
        return (usage["prompt_tokens"] * price["input"]
                + usage["completion_tokens"] * price["output"]) / 1_000_000

    def last_assistant(self):
        for message in reversed(self.memory.short_term):
            if message["role"] == "assistant":
                return message["content"]
        return ""

    def ask(self, text):
        self.memory.add_dialog("user", text)
        messages = build_messages(self.system, self.memory, self.profile,
                                  self.state, self.invariants)
        answer, usage = self.call_api(messages)
        self.memory.add_dialog("assistant", answer)
        hits = self.invariants.lint(answer)
        return answer, usage, messages, hits


def tasks_toolbar(store):
    if not store.tasks:
        return " задачи: нет — /task <имя> создаёт новую "
    parts = []
    for name, task in store.tasks.items():
        mark = " (тек.)" if name == store.current else ""
        parts.append(f"{name}: {task['stage']} / {STATUS_LABEL[task['status']]}{mark}")
    return " задачи:   " + "    ".join(parts) + " "


def ab_run(assistant, question, with_block, off_status):
    base = [{"role": "system", "content": assistant.system}]
    user = {"role": "user", "content": question}
    with console.status(off_status, spinner="dots"):
        off_answer, _ = assistant.call_api(base + [user])
        on_answer, _ = assistant.call_api(base + [{"role": "system", "content": with_block}, user])
    return off_answer, on_answer


def stage_pipeline(current=None):
    parts = []
    for i, s in enumerate(STAGES):
        if s == current:
            parts.append(f"[{STEEL_PALE} bold]\\[{s}][/{STEEL_PALE} bold]")
        else:
            parts.append(f"[dim]{s}[/dim]")
        if i < len(STAGES) - 1:
            parts.append("[dim]→[/dim]")
    return " ".join(parts)


def render_memory(memory):
    table = Table(box=box.ROUNDED, expand=True, show_lines=True)
    table.add_column("Слой", style="bold", no_wrap=True)
    table.add_column("Содержимое")
    short = "\n".join(f"[dim]{m['role']}:[/dim] {m['content']}" for m in memory.short_term) or "[dim]пусто[/dim]"
    working = "\n".join(f"[{STEEL_PALE}]{k}[/{STEEL_PALE}] = {v}" for k, v in memory.working.items()) or "[dim]пусто[/dim]"
    long_term = "\n".join(f"[{STEEL_PALE}]{k}[/{STEEL_PALE}] = {v}" for k, v in memory.long_term.items()) or "[dim]пусто[/dim]"
    table.add_row(Text("КРАТКОСРОЧНАЯ", style=STEEL_BRIGHT), short)
    table.add_row(Text("РАБОЧАЯ", style=STEEL_BRIGHT), working)
    table.add_row(Text("ДОЛГОВРЕМЕННАЯ", style=STEEL_BRIGHT), long_term)
    return Panel(table, title="ПАМЯТЬ — три слоя, отдельные файлы", border_style=STEEL)


def render_profile(profile):
    if profile.data:
        body = "\n".join(f"[{STEEL_PALE}]{k}[/{STEEL_PALE}] = {v}" for k, v in profile.data.items())
    else:
        body = "[dim]профиль пуст — /interview или /profile-set стиль = краткий[/dim]"
    return Panel(body, title="ПРОФИЛЬ — персонализация", border_style=STEEL)


def render_invariants(invariants):
    if invariants.items:
        rows = []
        for i, item in enumerate(invariants.items):
            forbid = ", ".join(item["forbid"]) if item["forbid"] else "—"
            rows.append(f"[{STEEL_PALE}]{i + 1}.[/{STEEL_PALE}] {item['rule']}  [dim](стоп-слова: {forbid})[/dim]")
        body = "\n".join(rows)
    else:
        body = "[dim]инвариантов нет — /invariant-add Только Kotlin :: python[/dim]"
    return Panel(body, title="ИНВАРИАНТЫ — нерушимые, хранятся отдельно", border_style=STEEL)


def render_tasks(store):
    if not store.tasks:
        body = (f"[{STEEL_PALE}]стадии:[/{STEEL_PALE}] {stage_pipeline(None)}\n"
                "[dim]задач нет — /task <имя> создаёт и открывает рабочее пространство[/dim]")
        return Panel(body, title="ЗАДАЧИ — task state machine (мультизадачность)", border_style=STEEL)
    table = Table(box=box.ROUNDED, expand=True)
    table.add_column("задача", style=f"bold {STEEL_BRIGHT}", no_wrap=True)
    table.add_column("стадия")
    table.add_column("статус", no_wrap=True)
    table.add_column("шаг", justify="right", no_wrap=True)
    table.add_column("план")
    for name, task in store.tasks.items():
        marker = f" [{STEEL_PALE}](тек.)[/{STEEL_PALE}]" if name == store.current else ""
        plan = (task["plan"][:40] + "…") if task["plan"] and len(task["plan"]) > 40 else (task["plan"] or "—")
        table.add_row(name + marker, task["stage"], STATUS_LABEL[task["status"]],
                      str(task["step"]), plan)
    return Panel(table, title="ЗАДАЧИ — task state machine (мультизадачность)", border_style=STEEL)


def show_status(assistant):
    console.print(render_tasks(assistant.state))
    console.print(render_invariants(assistant.invariants))
    console.print(render_profile(assistant.profile))
    console.print(render_memory(assistant.memory))


def show_help():
    table = Table(box=box.SIMPLE, expand=True, show_header=False)
    table.add_column("команда", style=f"bold {STEEL_BRIGHT}", no_wrap=True)
    table.add_column("что делает")
    for cmd, desc in COMMANDS.items():
        table.add_row(cmd, desc)
    intro = Text.assemble(
        ("Stateful-агент: память + профиль + задачи (стадии) + инварианты в одном.\n", ""),
        ("Просто пиши — обычный чат (учитывает все слои). Команды — со ", "dim"), ("/", "bold"),
        (".\n", "dim"),
        ("Задачи: ", "dim"), ("/task <имя>", f"bold {STEEL_PALE}"),
        (" открывает рабочее пространство со стадиями planning→execution→validation→done. "
         "Список задач всегда виден в нижней панели.\n", "dim"),
        ("Демо = ", "dim"), ("с твоими данными и без них", f"bold {STEEL_PALE}"), (": ", "dim"),
        ("/demo1", f"bold {STEEL_PALE}"), (" память · ", "dim"),
        ("/demo2", f"bold {STEEL_PALE}"), (" профиль · ", "dim"),
        ("/demo3", f"bold {STEEL_PALE}"), (" состояние · ", "dim"),
        ("/demo4", f"bold {STEEL_PALE}"), (" инварианты.", "dim"),
    )
    console.print(Panel(intro, border_style=STEEL, title="Как пользоваться"))
    console.print(Panel(table, border_style=STEEL, title="Команды"))


def parse_kv(rest, fallback_key):
    body = rest.strip()
    if not body:
        return None, None
    if "=" in body:
        key, value = (part.strip() for part in body.split("=", 1))
        return key, value
    return fallback_key, body


def run_interview(assistant):
    console.print(Panel("Стартовое интервью — соберём профиль пользователя по пунктам. "
                        "Пустой ответ = пропустить поле. Ctrl-C = выйти из интервью.",
                        title="ИНТЕРВЬЮ ДЛЯ ПРОФИЛЯ", border_style=STEEL))
    collected = 0
    for key, question in INTERVIEW_QUESTIONS:
        hint = FIELDS.get(key, "")
        console.print(Text.assemble((f"{question}\n", f"{STEEL_BRIGHT} bold"), (hint, "dim")))
        try:
            answer = pt_prompt("  › ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]интервью прервано — что успели, то сохранено[/dim]")
            break
        if answer:
            assistant.profile.set(key, answer)
            collected += 1
    console.print(Panel(f"Записано полей: {collected}. Профиль теперь подмешивается в каждый запрос.",
                        title="интервью завершено", border_style=STEEL))
    console.print(render_profile(assistant.profile))


def cmd_profile_set(assistant, rest):
    key, value = parse_kv(rest, None)
    if not key:
        console.print("[dim]Формат: /profile-set поле = значение. Поля: "
                      + ", ".join(FIELDS) + "[/dim]")
        return
    assistant.profile.set(key, value)
    console.print(Panel(f"[{STEEL_PALE}]{key}[/{STEEL_PALE}] = {value}",
                        title="→ профиль", border_style=STEEL))


def cmd_invariant_add(assistant, rest):
    body = rest.strip()
    if not body:
        console.print("[dim]Формат: /invariant-add <правило> :: стоп-слово1, стоп-слово2[/dim]")
        return
    if "::" in body:
        rule, terms = body.split("::", 1)
        forbid = [t.strip() for t in terms.split(",") if t.strip()]
    else:
        rule, forbid = body, []
    assistant.invariants.add(rule.strip(), forbid)
    note = ("стоп-слова: " + ", ".join(forbid)) if forbid else "без стоп-слов (ловит только критик)"
    console.print(Panel(f"{rule.strip()}\n[dim]{note}[/dim]",
                        title="→ инвариант", border_style=STEEL))


def show_workspace_header(store, name):
    task = store.tasks[name]
    forward = store.forward_target(name)
    back = store.back_target(name)
    nav = []
    if forward and forward in TRANSITIONS[task["stage"]]:
        nav.append(f"/next → {forward}")
    elif forward:
        nav.append(f"/next → {forward} [dim](после условий)[/dim]")
    if back and back in TRANSITIONS[task["stage"]]:
        nav.append(f"/back → {back}")
    nav_line = "   ".join(nav) or "дальше некуда (задача завершена)"
    body = (f"[{STEEL_PALE}]задача:[/{STEEL_PALE}] {name}   "
            f"[{STEEL_PALE}]статус:[/{STEEL_PALE}] {STATUS_LABEL[task['status']]}\n"
            f"[{STEEL_PALE}]стадии:[/{STEEL_PALE}] {stage_pipeline(task['stage'])}\n"
            f"[{STEEL_PALE}]ожидается:[/{STEEL_PALE}] {EXPECTED[task['stage']]}\n"
            f"[{STEEL_PALE}]план:[/{STEEL_PALE}] {task['plan'] or '—'}\n"
            f"[{STEEL_PALE}]навигация:[/{STEEL_PALE}] {nav_line}")
    console.print(Panel(body, title=f"РАБОЧЕЕ ПРОСТРАНСТВО ЗАДАЧИ · {name}", border_style=STEEL_BRIGHT,
                        box=box.DOUBLE))


def ask_in_task(assistant, name, text):
    assistant.memory.add_dialog("user", text)
    messages = build_messages(assistant.system, assistant.memory, assistant.profile,
                              assistant.state, assistant.invariants)
    with console.status("[dim]агент работает над задачей…[/dim]", spinner="dots"):
        answer, usage = assistant.call_api(messages)
    assistant.memory.add_dialog("assistant", answer)
    assistant.state.add_result(name, answer)
    hits = assistant.invariants.lint(answer)
    console.print(Panel(answer, title=f"АССИСТЕНТ · {name}", border_style=STEEL, box=box.ROUNDED))
    turn_footer(assistant, usage, len(messages), hits)


def workspace_next(assistant, name):
    store = assistant.state
    target = store.forward_target(name)
    if not target:
        console.print("[dim]Задача уже на стадии done.[/dim]")
        return
    ok, message = store.transition(name, target)
    if not ok:
        console.print(Panel(message, title="× переход отклонён кодом", border_style=WARN))
        return
    console.print(Panel(f"{message}\n[dim]{EXPECTED[target]}[/dim]",
                        title="→ стадия изменена", border_style=STEEL))
    if target == "validation":
        run_validation_critic(assistant)


def workspace_back(assistant, name):
    store = assistant.state
    target = store.back_target(name)
    if not target:
        console.print("[dim]Назад некуда — это первая стадия.[/dim]")
        return
    ok, message = store.transition(name, target)
    if not ok:
        console.print(Panel(message, title="× переход отклонён кодом", border_style=WARN))
        return
    console.print(Panel(f"{message}\n[dim]{EXPECTED[target]}[/dim]",
                        title="→ стадия изменена", border_style=STEEL))


def workspace_help():
    table = Table(box=box.SIMPLE, expand=True, show_header=False)
    table.add_column("команда", style=f"bold {STEEL_BRIGHT}", no_wrap=True)
    table.add_column("что делает")
    for cmd, desc in WORKSPACE_COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(Panel(table, border_style=STEEL,
                        title="рабочее пространство задачи — команды (просто текст = вопрос агенту)"))


def handle_workspace_cmd(assistant, name, cmd, rest):
    store = assistant.state
    if cmd == "plan":
        if not rest:
            console.print("[dim]Формат: /plan <текст плана>[/dim]")
            return False
        store.set_plan(name, rest)
        console.print(Panel(rest, title="→ план утверждён (теперь /next в execution)", border_style=STEEL))
    elif cmd == "next":
        workspace_next(assistant, name)
    elif cmd == "back":
        workspace_back(assistant, name)
    elif cmd in ("status", "show"):
        show_workspace_header(store, name)
    elif cmd == "help":
        workspace_help()
    elif cmd == "pause":
        store.pause(name)
        console.print(Panel(f"Задача «{name}» приостановлена (статус: пауза). "
                            f"Вернёшься — /task {name}.",
                            title="задача на паузе", border_style=STEEL))
        return True
    elif cmd == "delete":
        store.delete(name)
        console.print(Panel(f"Задача «{name}» удалена.", title="задача удалена", border_style=WARN))
        return True
    elif cmd == "exit":
        return True
    else:
        console.print(f"[dim]Неизвестная команда /{cmd}. Внутри задачи: /help.[/dim]")
    return False


def run_workspace(assistant, name):
    store = assistant.state
    store.enter(name)
    show_workspace_header(store, name)
    completer = SlashCompleter(WORKSPACE_COMMANDS)
    bindings = KeyBindings()

    @bindings.add("enter", filter=completion_is_selected)
    def _(event):
        event.current_buffer.complete_state = None

    session = PromptSession(completer=completer, complete_while_typing=True,
                            key_bindings=bindings, style=MENU_STYLE,
                            bottom_toolbar=lambda: tasks_toolbar(store))
    left_into_main = False
    while True:
        try:
            line = session.prompt(HTML(f"<prompt>{name} ›</prompt> ")).strip()
        except (EOFError, KeyboardInterrupt):
            store.leave()
            left_into_main = True
            break
        if line == "" or line.lower() == "exit":
            store.leave()
            left_into_main = True
            break
        if line.startswith("/"):
            wcmd, _, wrest = line[1:].partition(" ")
            if wcmd.lower() == "exit":
                store.leave()
                left_into_main = True
                break
            done = handle_workspace_cmd(assistant, name, wcmd.lower(), wrest.strip())
            if done:
                break
            continue
        ask_in_task(assistant, name, line)
    if left_into_main:
        console.print(f"[dim]Вышел из задачи «{name}». Она осталась в списке. Вернулся в общий чат.[/dim]")


def cmd_task(assistant, rest):
    name = rest.strip()
    store = assistant.state
    if not name:
        console.print(render_tasks(store))
        console.print("[dim]Открыть/создать: /task <имя>[/dim]")
        return
    if not store.exists(name):
        store.create(name)
        console.print(Panel(f"Создана задача: [bold]{name}[/bold]\n"
                            f"Стадии: {stage_pipeline('planning')}",
                            title="→ новая задача", border_style=STEEL))
    run_workspace(assistant, name)


def run_validation_critic(assistant):
    answer = assistant.last_assistant()
    if not answer:
        console.print("[dim]Нечего валидировать — в диалоге ещё нет ответа ассистента.[/dim]")
        return
    if not assistant.invariants.items:
        console.print("[dim]Инвариантов нет — критику нечего проверять.[/dim]")
        return
    hits = assistant.invariants.lint(answer)
    with console.status("[dim]критик (gpt-4o-mini) проверяет последний ответ на инварианты…[/dim]",
                        spinner="dots"):
        verdict, usage = critic_check(assistant.api_key, assistant.invariants.items, answer)
    show_verdict(hits, verdict, usage)


def show_verdict(lint_hits, verdict, usage):
    code_line = ("[bold]код-линтер:[/bold] нарушений нет" if not lint_hits else
                 "[bold]код-линтер:[/bold] " + "; ".join(
                     f"«{h['term']}» → {h['rule']}" for h in lint_hits))
    if verdict.get("violated"):
        critic_line = ("[bold]критик:[/bold] НАРУШЕНО — " + verdict.get("why", "")
                       + "\n" + "\n".join(f"  · {w}" for w in verdict.get("which", [])))
        border = WARN
        title = "ВАЛИДАЦИЯ — ответ нарушает инварианты"
    else:
        critic_line = "[bold]критик:[/bold] нарушений нет"
        border = STEEL
        title = "ВАЛИДАЦИЯ — ответ соответствует инвариантам"
    footer = f"[dim]критик: вход {usage['prompt_tokens']} ток. · ответ {usage['completion_tokens']}[/dim]"
    console.print(Panel(f"{code_line}\n{critic_line}\n{footer}", title=title, border_style=border))


def run_demo_memory(assistant, question=""):
    question = question.strip() or DEMO_MEM_QUESTION
    real = dict(assistant.memory.long_term)
    real.update(assistant.memory.working)
    using_sample = not real
    data = dict(DEMO_MEM_FACTS) if using_sample else real
    source = ("память пуста — взят образец (заполни /remember-forever)" if using_sample
              else "ТВОЯ память (долговременная + рабочая)")

    layers = Table(box=box.ROUNDED, expand=True, show_lines=True)
    layers.add_column("слой", style=f"bold {STEEL_BRIGHT}", no_wrap=True)
    layers.add_column("что хранит", no_wrap=True)
    layers.add_column("файл", no_wrap=True)
    layers.add_row("КРАТКОСРОЧНАЯ", "текущий диалог (последние реплики)", "short_term.json")
    layers.add_row("РАБОЧАЯ", "данные текущей задачи (KV)", "working.json")
    layers.add_row("ДОЛГОВРЕМЕННАЯ", "профиль, решения, знания", "long_term.json")
    console.print(Panel(layers, title="ТРИ СЛОЯ ПАМЯТИ (хранятся отдельно)", border_style=STEEL))

    console.print(Panel(f"Один и тот же вопрос: [bold]{question}[/bold]\n"
                        f"Данные памяти ([dim]{source}[/dim]): {data}\n"
                        "[dim]Слева — БЕЗ памяти, справа — С твоей памятью. Видно её вклад в ответ.[/dim]",
                        title="ВЛИЯНИЕ ПАМЯТИ НА ОТВЕТ", border_style=STEEL))
    block = "Память (постоянные факты о проекте и данные задачи): " + json.dumps(data, ensure_ascii=False)
    off, on = ab_run(assistant, question, block, "[dim]гоняю один вопрос с памятью и без…[/dim]")
    console.print(Columns([Panel(off, title="БЕЗ ПАМЯТИ", border_style=STEEL_DIM),
                           Panel(on, title="С ТВОЕЙ ПАМЯТЬЮ", border_style=STEEL_BRIGHT)],
                          equal=True, expand=True))
    console.print("[dim]Без памяти — обобщённый ответ (часто типовой стек). С памятью — учитывает "
                  "факты проекта. Демо живую память не меняет.[/dim]")


def run_demo_profile(assistant, question=""):
    question = question.strip() or DEMO_PROFILE_QUESTION
    using_sample = not assistant.profile.data
    data = dict(DEMO_PROFILE_SAMPLE) if using_sample else dict(assistant.profile.data)
    source = ("профиль пуст — взят образец (заполни /interview)" if using_sample
              else "ТВОЙ профиль")

    console.print(Panel("\n".join(f"[{STEEL_PALE}]{k}[/{STEEL_PALE}] = {v}" for k, v in data.items()),
                        title=f"ПРОФИЛЬ ({source})", border_style=STEEL))
    console.print(Panel(f"Один и тот же вопрос: [bold]{question}[/bold]\n"
                        "[dim]Про стиль/формат в вопросе не сказано. Слева — БЕЗ профиля, "
                        "справа — С твоим профилем. Агент подстраивается автоматически.[/dim]",
                        title="ВЛИЯНИЕ ПРОФИЛЯ НА ОТВЕТ", border_style=STEEL))
    block = ("Профиль пользователя (персонализация) — подстраивай стиль, формат и глубину под него:\n"
             + "\n".join(f"- {k}: {v}" for k, v in data.items()))
    off, on = ab_run(assistant, question, block, "[dim]гоняю один вопрос с профилем и без…[/dim]")
    console.print(Columns([Panel(off, title="БЕЗ ПРОФИЛЯ", border_style=STEEL_DIM),
                           Panel(on, title="С ТВОИМ ПРОФИЛЕМ", border_style=STEEL_BRIGHT)],
                          equal=True, expand=True))
    console.print("[dim]Тот же вопрос — разный тон, формат и глубина. Это и есть персонализация.[/dim]")


def run_demo_state(assistant, question=""):
    question = question.strip() or DEMO_STATE_QUESTION
    current = assistant.state.current_task()
    active = current is not None
    block = assistant.state.as_prompt() if active else SAMPLE_STATE_BLOCK
    stage = current["stage"] if active else "planning"
    source = (f"ТВОЯ задача «{assistant.state.current}», стадия {stage}" if active
              else "активной задачи нет — взят образец (стадия planning)")

    table = Table(box=box.ROUNDED, expand=True)
    table.add_column("стадия", style=f"bold {STEEL_BRIGHT}")
    table.add_column("ожидаемое действие")
    table.add_column("легальные переходы")
    for s in STAGES:
        marker = " ◀ сейчас" if s == stage else ""
        table.add_row(s + marker, EXPECTED[s], ", ".join(TRANSITIONS[s]) or "—")
    console.print(Panel(table, title="КАРТА АВТОМАТА (этап · шаг · ожидаемое действие)", border_style=STEEL))

    console.print(Panel(f"Один и тот же запрос: [bold]{question}[/bold]\n"
                        f"Состояние ([dim]{source}[/dim]).\n"
                        "[dim]Слева — БЕЗ состояния, справа — С состоянием. "
                        "Состояние не даёт агенту перепрыгнуть этап.[/dim]",
                        title="ВЛИЯНИЕ СОСТОЯНИЯ НА ОТВЕТ", border_style=STEEL))
    off, on = ab_run(assistant, question, block, "[dim]гоняю один запрос с состоянием и без…[/dim]")
    console.print(Columns([
        Panel(off, title="БЕЗ СОСТОЯНИЯ (прыгает сразу в код)", border_style=STEEL_DIM),
        Panel(on, title=f"С СОСТОЯНИЕМ (держит стадию {stage})", border_style=STEEL_BRIGHT),
    ], equal=True, expand=True))

    demo = TaskStore(ephemeral=True)
    demo.create("проверка переходов")
    ok_jump, msg_jump = demo.transition("проверка переходов", "done")
    demo.set_plan("проверка переходов", "план")
    ok_step, msg_step = demo.transition("проверка переходов", "execution")
    console.print(Panel(
        f"[{WARN}]×[/{WARN}] /next через этап (planning→done): {msg_jump}\n"
        f"[{STEEL_PALE}]✓[/{STEEL_PALE}] planning→execution (план есть): {msg_step}\n"
        "[dim]Легальность переходов проверяет КОД (state.py), не промпт — нелегальный отклоняется.[/dim]",
        title="ПЕРЕХОДЫ ПОД КОНТРОЛЕМ КОДА", border_style=STEEL))
    console.print(Panel(
        "[bold]Пауза:[/bold] /pause внутри задачи или просто выход — стадия и план пишутся в "
        "store/state.json.\n[bold]Продолжение без повторных объяснений:[/bold] /task <имя> снова — "
        "агент грузит стадию, план и результаты и продолжает с того же места.\n"
        "[dim]Несколько задач живут параллельно — список со статусами всегда в нижней панели.[/dim]",
        title="ПАУЗА, ПРОДОЛЖЕНИЕ, МУЛЬТИЗАДАЧНОСТЬ", border_style=STEEL))


def run_demo_invariants(assistant, question=""):
    question = question.strip() or DEMO_INV_QUESTION
    using_sample = not assistant.invariants.items
    items = list(DEMO_INV_INVARIANTS) if using_sample else assistant.invariants.items
    source = ("инвариантов нет — взят образец (заполни /invariant-add)" if using_sample
              else "ТВОИ инварианты")
    rules = "\n".join(f"{i + 1}. {it['rule']}" for i, it in enumerate(items))

    console.print(Panel(f"Инварианты ([dim]{source}[/dim], хранятся отдельным файлом):\n{rules}\n\n"
                        f"Один и тот же запрос: [bold]{question}[/bold]\n"
                        "[dim]Слева — БЕЗ инвариантов, справа — С твоими инвариантами.[/dim]",
                        title="ВЛИЯНИЕ ИНВАРИАНТОВ НА ОТВЕТ", border_style=STEEL))
    block = ("ИНВАРИАНТЫ — нерушимые ограничения. Если запрос им противоречит — откажись и объясни, "
             "какой инвариант нарушается:\n" + rules)
    off, on = ab_run(assistant, question, block, "[dim]гоняю один запрос с инвариантами и без…[/dim]")
    console.print(Columns([
        Panel(off, title="БЕЗ ИНВАРИАНТОВ (выполняет запрос)", border_style=STEEL_DIM),
        Panel(on, title="С ТВОИМИ ИНВАРИАНТАМИ (отказ + объяснение)", border_style=STEEL_BRIGHT),
    ], equal=True, expand=True))

    temp = Invariants.__new__(Invariants)
    temp.items = items
    hits = temp.lint(off)
    code_body = ("нарушений не найдено" if not hits else
                 "\n".join(f"[{WARN}]×[/{WARN}] «{h['term']}» → {h['rule']}" for h in hits))
    console.print(Panel(code_body, title="КОД-ЛИНТЕР по ответу БЕЗ инвариантов (детерминированно)",
                        border_style=STEEL))
    with console.status("[dim]критик (gpt-4o-mini) проверяет ответ без инвариантов…[/dim]", spinner="dots"):
        verdict, usage = critic_check(assistant.api_key, items, off)
    which = "\n".join(f"  · {w}" for w in verdict.get("which", []))
    verdict_body = (f"нарушено: [bold]{verdict.get('violated')}[/bold]\n"
                    f"почему: {verdict.get('why', '')}\n{which}\n"
                    f"[dim]вход {usage['prompt_tokens']} ток. · ответ {usage['completion_tokens']}[/dim]")
    console.print(Panel(verdict_body, title="LLM-КРИТИК по тому же ответу (семантический)", border_style=STEEL))
    console.print("[dim]Конфликт запрос↔инвариант: слева агент без правил выполняет (и линтер с критиком "
                  "ловят нарушение), справа агент с инвариантами отказывается и объясняет. Инварианты "
                  "работают и в промпте, и в коде.[/dim]")


def turn_footer(assistant, usage, n_messages, hits):
    cost = assistant.cost_rub(usage)
    cost_str = f" · {cost:.4f} ₽" if cost is not None else ""
    console.print(Text(f"вход {usage['prompt_tokens']} ток. · ответ {usage['completion_tokens']} · "
                       f"в запросе {n_messages} сообщ.{cost_str}", style="dim"))
    if hits:
        warn = "; ".join(f"«{h['term']}» → {h['rule']}" for h in hits)
        console.print(Panel(f"код-линтер: ответ задевает инвариант — {warn}",
                            title="внимание", border_style=WARN))


def handle_command(assistant, name, rest):
    if name == "help":
        show_help()
    elif name == "status":
        show_status(assistant)
    elif name == "task":
        cmd_task(assistant, rest)
    elif name == "interview":
        run_interview(assistant)
    elif name == "remember-forever":
        key, value = parse_kv(rest, assistant.memory.next_note_key())
        if not key:
            console.print("[dim]Формат: /remember-forever название = содержимое[/dim]")
            return
        assistant.memory.remember(key, value)
        console.print(Panel(f"[{STEEL_PALE}]{key}[/{STEEL_PALE}] = {value}",
                            title="→ долговременная память", border_style=STEEL))
    elif name == "remember-now":
        fallback = f"пункт_{len(assistant.memory.working) + 1}"
        key, value = parse_kv(rest, fallback)
        if not key:
            console.print("[dim]Формат: /remember-now название = содержимое[/dim]")
            return
        assistant.memory.set_task(key, value)
        console.print(Panel(f"[{STEEL_PALE}]{key}[/{STEEL_PALE}] = {value}",
                            title="→ рабочая память", border_style=STEEL))
    elif name == "profile-set":
        cmd_profile_set(assistant, rest)
    elif name == "invariant-add":
        cmd_invariant_add(assistant, rest)
    elif name == "demo1":
        run_demo_memory(assistant, rest)
    elif name == "demo2":
        run_demo_profile(assistant, rest)
    elif name == "demo3":
        run_demo_state(assistant, rest)
    elif name == "demo4":
        run_demo_invariants(assistant, rest)
    elif name == "reset":
        assistant.memory.reset()
        assistant.profile.clear()
        assistant.state.reset()
        assistant.invariants.clear()
        console.print(Panel("Стёрто всё: задачи, инварианты, профиль, память.", border_style=STEEL))
    else:
        console.print(f"[dim]Неизвестная команда /{name}. Набери /help.[/dim]")


def banner(assistant):
    s = assistant
    loaded = (f"память: кратк {len(s.memory.short_term)} · раб {len(s.memory.working)} · "
              f"долг {len(s.memory.long_term)}   профиль: {len(s.profile.data)}   "
              f"инвариантов: {len(s.invariants.items)}   задач: {len(s.state.tasks)}")
    body = Text.assemble(
        ("Stateful-агент", "bold"),
        ("  ·  память · профиль · задачи · инварианты  ·  модель ", ""),
        (s.model, f"bold {STEEL_BRIGHT}"),
        ("\n", ""), (loaded, "dim"),
        ("\nстадии задачи: planning → execution → validation → done", "dim"),
        ("\n\nПиши сообщение — обычный чат. ", "dim"),
        ("/task <имя>", f"bold {STEEL_PALE}"), (" — рабочее пространство задачи. ", "dim"),
        ("Набери ", "dim"), ("/", "bold"), (" для команд, ", "dim"),
        ("/help", f"bold {STEEL_BRIGHT}"), (" — подробно.\n", "dim"),
        ("Демо = ", "dim"), ("с твоими данными и без них", f"bold {STEEL_PALE}"),
        (": ", "dim"), ("/demo1 /demo2 /demo3 /demo4", f"bold {STEEL_PALE}"),
        (". Список задач — в нижней панели. Пустая строка — выход.", "dim"),
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

    session = PromptSession(completer=SlashCompleter(COMMANDS), complete_while_typing=True,
                            key_bindings=bindings, style=MENU_STYLE,
                            bottom_toolbar=lambda: tasks_toolbar(assistant.state))
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
        with console.status("[dim]агент думает…[/dim]", spinner="dots"):
            answer, usage, messages, hits = assistant.ask(user)
        console.print(Panel(answer, title="АССИСТЕНТ", border_style=STEEL, box=box.ROUNDED))
        turn_footer(assistant, usage, len(messages), hits)
    console.print("[dim]Состояние сохранено. Пока![/dim]")


if __name__ == "__main__":
    main()
