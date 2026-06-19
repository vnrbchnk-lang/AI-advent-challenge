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
from assistant.swarm import run_swarm, STAGE_ROLES, MEMBER_MODEL
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

NAVY = "#34568b"
NAVY_BRIGHT = "#6f9ad1"
NAVY_PALE = "#a9c8ee"
NAVY_DIM = "#223a5c"
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
    "/demo5": "контролируемые переходы: допустимые состояния, запрет перепрыгнуть этап, пауза/продолжение",
    "/reset": "стереть всё состояние",
    "/help": "справка",
}

WORKSPACE_COMMANDS = {
    "/next": "ОСНОВНОЕ: разрешить переход на следующую стадию (рой новой стадии отработает сам)",
    "/back": "вернуть задачу на предыдущую стадию (рой отработает заново)",
    "/council": "перезапустить рой текущей стадии (он и так отрабатывает авто при входе)",
    "/status": "показать карточку этой задачи",
    "/plan": "вручную переписать план (обычно его делает рой planning). Пример: /plan 1) роуты 2) JWT",
    "/pause": "приостановить задачу и выйти в общий чат",
    "/delete": "удалить эту задачу",
    "/help": "справка по рабочему пространству",
    "/exit": "выйти в общий чат (задача остаётся активной)",
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
            parts.append(f"[{NAVY_PALE} bold]\\[{s}][/{NAVY_PALE} bold]")
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
    working = "\n".join(f"[{NAVY_PALE}]{k}[/{NAVY_PALE}] = {v}" for k, v in memory.working.items()) or "[dim]пусто[/dim]"
    long_term = "\n".join(f"[{NAVY_PALE}]{k}[/{NAVY_PALE}] = {v}" for k, v in memory.long_term.items()) or "[dim]пусто[/dim]"
    table.add_row(Text("КРАТКОСРОЧНАЯ", style=NAVY_BRIGHT), short)
    table.add_row(Text("РАБОЧАЯ", style=NAVY_BRIGHT), working)
    table.add_row(Text("ДОЛГОВРЕМЕННАЯ", style=NAVY_BRIGHT), long_term)
    return Panel(table, title="ПАМЯТЬ — три слоя, отдельные файлы", border_style=NAVY)


def render_profile(profile):
    if profile.data:
        body = "\n".join(f"[{NAVY_PALE}]{k}[/{NAVY_PALE}] = {v}" for k, v in profile.data.items())
    else:
        body = "[dim]профиль пуст — /interview или /profile-set стиль = краткий[/dim]"
    return Panel(body, title="ПРОФИЛЬ — персонализация", border_style=NAVY)


def render_invariants(invariants):
    if invariants.items:
        rows = []
        for i, item in enumerate(invariants.items):
            forbid = ", ".join(item["forbid"]) if item["forbid"] else "—"
            rows.append(f"[{NAVY_PALE}]{i + 1}.[/{NAVY_PALE}] {item['rule']}  [dim](стоп-слова: {forbid})[/dim]")
        body = "\n".join(rows)
    else:
        body = "[dim]инвариантов нет — /invariant-add Только Kotlin :: python[/dim]"
    return Panel(body, title="ИНВАРИАНТЫ — нерушимые, хранятся отдельно", border_style=NAVY)


def render_tasks(store):
    if not store.tasks:
        body = (f"[{NAVY_PALE}]стадии:[/{NAVY_PALE}] {stage_pipeline(None)}\n"
                "[dim]задач нет — /task <имя> создаёт и открывает рабочее пространство[/dim]")
        return Panel(body, title="ЗАДАЧИ — task state machine (мультизадачность)", border_style=NAVY)
    table = Table(box=box.ROUNDED, expand=True)
    table.add_column("задача", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("стадия")
    table.add_column("статус", no_wrap=True)
    table.add_column("шаг", justify="right", no_wrap=True)
    table.add_column("план")
    for name, task in store.tasks.items():
        marker = f" [{NAVY_PALE}](тек.)[/{NAVY_PALE}]" if name == store.current else ""
        plan = (task["plan"][:40] + "…") if task["plan"] and len(task["plan"]) > 40 else (task["plan"] or "—")
        table.add_row(name + marker, task["stage"], STATUS_LABEL[task["status"]],
                      str(task["step"]), plan)
    return Panel(table, title="ЗАДАЧИ — task state machine (мультизадачность)", border_style=NAVY)


def show_status(assistant):
    console.print(render_tasks(assistant.state))
    console.print(render_invariants(assistant.invariants))
    console.print(render_profile(assistant.profile))
    console.print(render_memory(assistant.memory))


def show_help():
    table = Table(box=box.SIMPLE, expand=True, show_header=False)
    table.add_column("команда", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("что делает")
    for cmd, desc in COMMANDS.items():
        table.add_row(cmd, desc)
    intro = Text.assemble(
        ("Stateful-агент: память + профиль + задачи (стадии) + инварианты в одном.\n", ""),
        ("Просто пиши — обычный чат (учитывает все слои). Команды — со ", "dim"), ("/", "bold"),
        (".\n", "dim"),
        ("Задачи: ", "dim"), ("/task <имя>", f"bold {NAVY_PALE}"),
        (" открывает рабочее пространство со стадиями planning→execution→validation→done. "
         "Список задач всегда виден в нижней панели.\n", "dim"),
        ("Демо = ", "dim"), ("с твоими данными и без них", f"bold {NAVY_PALE}"), (": ", "dim"),
        ("/demo1", f"bold {NAVY_PALE}"), (" память · ", "dim"),
        ("/demo2", f"bold {NAVY_PALE}"), (" профиль · ", "dim"),
        ("/demo3", f"bold {NAVY_PALE}"), (" состояние · ", "dim"),
        ("/demo4", f"bold {NAVY_PALE}"), (" инварианты · ", "dim"),
        ("/demo5", f"bold {NAVY_PALE}"), (" контролируемые переходы.\n", "dim"),
        ("Рой агентов: ", "dim"), ("на каждой стадии задачи", f"bold {NAVY_PALE}"),
        (" авто отрабатывает рой (5 ролей + оркестратор). Стадию двигаешь ", "dim"),
        ("только ты", f"bold {NAVY_PALE}"), (" командой ", "dim"), ("/next", f"bold {NAVY_PALE}"),
        (" — агент перейти не может.", "dim"),
    )
    console.print(Panel(intro, border_style=NAVY, title="Как пользоваться"))
    console.print(Panel(table, border_style=NAVY, title="Команды"))


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
                        title="ИНТЕРВЬЮ ДЛЯ ПРОФИЛЯ", border_style=NAVY))
    collected = 0
    for key, question in INTERVIEW_QUESTIONS:
        hint = FIELDS.get(key, "")
        console.print(Text.assemble((f"{question}\n", f"{NAVY_BRIGHT} bold"), (hint, "dim")))
        try:
            answer = pt_prompt("  › ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]интервью прервано — что успели, то сохранено[/dim]")
            break
        if answer:
            assistant.profile.set(key, answer)
            collected += 1
    console.print(Panel(f"Записано полей: {collected}. Профиль теперь подмешивается в каждый запрос.",
                        title="интервью завершено", border_style=NAVY))
    console.print(render_profile(assistant.profile))


def cmd_profile_set(assistant, rest):
    key, value = parse_kv(rest, None)
    if not key:
        console.print("[dim]Формат: /profile-set поле = значение. Поля: "
                      + ", ".join(FIELDS) + "[/dim]")
        return
    assistant.profile.set(key, value)
    console.print(Panel(f"[{NAVY_PALE}]{key}[/{NAVY_PALE}] = {value}",
                        title="→ профиль", border_style=NAVY))


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
                        title="→ инвариант", border_style=NAVY))


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
    body = (f"[{NAVY_PALE}]задача:[/{NAVY_PALE}] {name}   "
            f"[{NAVY_PALE}]статус:[/{NAVY_PALE}] {STATUS_LABEL[task['status']]}\n"
            f"[{NAVY_PALE}]стадии:[/{NAVY_PALE}] {stage_pipeline(task['stage'])}\n"
            f"[{NAVY_PALE}]ожидается:[/{NAVY_PALE}] {EXPECTED[task['stage']]}\n"
            f"[{NAVY_PALE}]план:[/{NAVY_PALE}] {task['plan'] or '—'}\n"
            f"[{NAVY_PALE}]навигация:[/{NAVY_PALE}] {nav_line}")
    console.print(Panel(body, title=f"РАБОЧЕЕ ПРОСТРАНСТВО ЗАДАЧИ · {name}", border_style=NAVY_BRIGHT,
                        box=box.DOUBLE))


def ask_in_task(assistant, name, text):
    assistant.memory.add_dialog("user", text)
    messages = build_messages(assistant.system, assistant.memory, assistant.profile,
                              assistant.state, assistant.invariants)
    with console.status("[dim]агент работает над задачей…[/dim]", spinner="dots"):
        answer, usage = assistant.call_api(messages)
    assistant.memory.add_dialog("assistant", answer)
    hits = assistant.invariants.lint(answer)
    console.print(Panel(answer, title=f"АССИСТЕНТ · {name}", border_style=NAVY, box=box.ROUNDED))
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
                        title="→ стадия изменена (разрешил ты командой /next)", border_style=NAVY))
    if target in STAGE_ROLES:
        run_stage_swarm(assistant, name, target)
    elif target == "done":
        show_done_report(assistant, name)


def show_done_report(assistant, name):
    task = assistant.state.tasks[name]
    plan = task["plan"] or "—"
    if task["results"]:
        results = "\n\n".join(f"[{NAVY_PALE}]шаг {i + 1}[/{NAVY_PALE}]\n{r}"
                              for i, r in enumerate(task["results"]))
    else:
        results = "[dim]результатов стадий нет[/dim]"
    console.print(Panel(f"[{NAVY_PALE}]задача:[/{NAVY_PALE}] {name}   "
                        f"[{NAVY_PALE}]шагов:[/{NAVY_PALE}] {task['step']}\n"
                        f"[{NAVY_PALE}]утверждённый план:[/{NAVY_PALE}]\n{plan}\n\n"
                        f"[{NAVY_PALE}]итоги стадий (рой):[/{NAVY_PALE}]\n{results}",
                        title=f"DONE · финальная сводка задачи «{name}»", border_style=NAVY_BRIGHT,
                        box=box.DOUBLE))


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
                        title="→ стадия изменена (разрешил ты командой /back)", border_style=NAVY))
    if target in STAGE_ROLES:
        run_stage_swarm(assistant, name, target)


def workspace_help():
    table = Table(box=box.SIMPLE, expand=True, show_header=False)
    table.add_column("команда", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("что делает")
    for cmd, desc in WORKSPACE_COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(Panel(table, border_style=NAVY,
                        title="рабочее пространство задачи — команды (просто текст = вопрос агенту)"))


STAGE_RESULT_HINT = {
    "planning": "Сводный план роя записан как план задачи. Дальше — твоё решение: /next в execution "
                "(код пустит, т.к. план утверждён). Агент сам стадию не сменит.",
    "execution": "Итог реализации роя записан в результаты задачи. Готов проверять — твоё решение: /next в validation.",
    "validation": "Вердикт роя записан в результаты. Если всё чисто — твоё решение: /next в done.",
}


def run_stage_swarm(assistant, name, stage):
    store = assistant.state
    if stage not in STAGE_ROLES:
        return
    task = store.tasks[name]
    roles = STAGE_ROLES[stage]
    roles_n = len(roles)
    prev_result = task["results"][-1] if task["results"] else None
    profile_text = "\n".join(f"- {k}: {v}" for k, v in assistant.profile.data.items())
    console.print(Panel(
        f"Задача: [bold]{name}[/bold]   стадия: [bold]{stage}[/bold]\n"
        f"Рой из [bold]{roles_n}[/bold] агентов ([dim]{MEMBER_MODEL}[/dim]) — каждый со своей стороны: "
        + ", ".join(r for r, _ in roles) + ".\n"
        f"[dim]Оркестратор ({assistant.model}) знает запрос, профиль, инварианты, план и прошлые стадии — "
        "сведёт мнения и возразит при конфликте. Стадию двигаешь только ты командой /next.[/dim]",
        title=f"РОЙ АГЕНТОВ · стадия {stage}", border_style=NAVY))
    with console.status(f"[dim]{roles_n} агентов работают над стадией {stage}, затем оркестратор сводит…[/dim]",
                        spinner="dots"):
        opinions, synthesis, member_usage, orch_usage = run_swarm(
            assistant.api_key, stage, name, task["plan"], prev_result,
            assistant.invariants.items, profile_text)
    console.print(Columns([Panel(o["text"], title=o["role"], border_style=NAVY_DIM) for o in opinions],
                          equal=True, expand=True))
    console.print(Panel(synthesis, title=f"ОРКЕСТРАТОР · итог стадии {stage}",
                        border_style=NAVY_BRIGHT, box=box.DOUBLE))
    if stage == "planning":
        store.set_plan(name, synthesis)
    else:
        store.add_result(name, f"[{stage}] {synthesis}")
    orch_cost = assistant.cost_rub(orch_usage)
    cost_str = f" · оркестратор {orch_cost:.4f} ₽" if orch_cost is not None else ""
    console.print(Text(
        f"рой ({MEMBER_MODEL} ×{roles_n}): вход {member_usage['prompt_tokens']} ток. · "
        f"ответ {member_usage['completion_tokens']}   |   "
        f"оркестратор ({assistant.model}): вход {orch_usage['prompt_tokens']} ток. · "
        f"ответ {orch_usage['completion_tokens']}{cost_str}", style="dim"))
    console.print(Panel(STAGE_RESULT_HINT[stage], title=f"→ стадия {stage}: рой отработал", border_style=NAVY))


def handle_workspace_cmd(assistant, name, cmd, rest):
    store = assistant.state
    if cmd == "council":
        run_stage_swarm(assistant, name, store.tasks[name]["stage"])
    elif cmd == "plan":
        if not rest:
            console.print("[dim]Формат: /plan <текст плана>[/dim]")
            return False
        store.set_plan(name, rest)
        console.print(Panel(rest, title="→ план утверждён (теперь /next в execution)", border_style=NAVY))
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
                            title="задача на паузе", border_style=NAVY))
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


def run_workspace(assistant, name, fresh=False):
    store = assistant.state
    store.enter(name)
    show_workspace_header(store, name)
    if fresh:
        run_stage_swarm(assistant, name, "planning")
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
    fresh = not store.exists(name)
    if fresh:
        store.create(name)
        console.print(Panel(f"Создана задача: [bold]{name}[/bold]\n"
                            f"Стадии: {stage_pipeline('planning')}\n"
                            "[dim]Сейчас на стадии planning отработает рой агентов. Дальше двигаешь ты — /next.[/dim]",
                            title="→ новая задача", border_style=NAVY))
    run_workspace(assistant, name, fresh)


def run_demo_memory(assistant, question=""):
    question = question.strip() or DEMO_MEM_QUESTION
    real = dict(assistant.memory.long_term)
    real.update(assistant.memory.working)
    using_sample = not real
    data = dict(DEMO_MEM_FACTS) if using_sample else real
    source = ("память пуста — взят образец (заполни /remember-forever)" if using_sample
              else "ТВОЯ память (долговременная + рабочая)")

    layers = Table(box=box.ROUNDED, expand=True, show_lines=True)
    layers.add_column("слой", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    layers.add_column("что хранит", no_wrap=True)
    layers.add_column("файл", no_wrap=True)
    layers.add_row("КРАТКОСРОЧНАЯ", "текущий диалог (последние реплики)", "short_term.json")
    layers.add_row("РАБОЧАЯ", "данные текущей задачи (KV)", "working.json")
    layers.add_row("ДОЛГОВРЕМЕННАЯ", "профиль, решения, знания", "long_term.json")
    console.print(Panel(layers, title="ТРИ СЛОЯ ПАМЯТИ (хранятся отдельно)", border_style=NAVY))

    console.print(Panel(f"Один и тот же вопрос: [bold]{question}[/bold]\n"
                        f"Данные памяти ([dim]{source}[/dim]): {data}\n"
                        "[dim]Слева — БЕЗ памяти, справа — С твоей памятью. Видно её вклад в ответ.[/dim]",
                        title="ВЛИЯНИЕ ПАМЯТИ НА ОТВЕТ", border_style=NAVY))
    block = "Память (постоянные факты о проекте и данные задачи): " + json.dumps(data, ensure_ascii=False)
    off, on = ab_run(assistant, question, block, "[dim]гоняю один вопрос с памятью и без…[/dim]")
    console.print(Columns([Panel(off, title="БЕЗ ПАМЯТИ", border_style=NAVY_DIM),
                           Panel(on, title="С ТВОЕЙ ПАМЯТЬЮ", border_style=NAVY_BRIGHT)],
                          equal=True, expand=True))
    console.print("[dim]Без памяти — обобщённый ответ (часто типовой стек). С памятью — учитывает "
                  "факты проекта. Демо живую память не меняет.[/dim]")


def run_demo_profile(assistant, question=""):
    question = question.strip() or DEMO_PROFILE_QUESTION
    using_sample = not assistant.profile.data
    data = dict(DEMO_PROFILE_SAMPLE) if using_sample else dict(assistant.profile.data)
    source = ("профиль пуст — взят образец (заполни /interview)" if using_sample
              else "ТВОЙ профиль")

    console.print(Panel("\n".join(f"[{NAVY_PALE}]{k}[/{NAVY_PALE}] = {v}" for k, v in data.items()),
                        title=f"ПРОФИЛЬ ({source})", border_style=NAVY))
    console.print(Panel(f"Один и тот же вопрос: [bold]{question}[/bold]\n"
                        "[dim]Про стиль/формат в вопросе не сказано. Слева — БЕЗ профиля, "
                        "справа — С твоим профилем. Агент подстраивается автоматически.[/dim]",
                        title="ВЛИЯНИЕ ПРОФИЛЯ НА ОТВЕТ", border_style=NAVY))
    block = ("Профиль пользователя (персонализация) — подстраивай стиль, формат и глубину под него:\n"
             + "\n".join(f"- {k}: {v}" for k, v in data.items()))
    off, on = ab_run(assistant, question, block, "[dim]гоняю один вопрос с профилем и без…[/dim]")
    console.print(Columns([Panel(off, title="БЕЗ ПРОФИЛЯ", border_style=NAVY_DIM),
                           Panel(on, title="С ТВОИМ ПРОФИЛЕМ", border_style=NAVY_BRIGHT)],
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
    table.add_column("стадия", style=f"bold {NAVY_BRIGHT}")
    table.add_column("ожидаемое действие")
    table.add_column("легальные переходы")
    for s in STAGES:
        marker = " ◀ сейчас" if s == stage else ""
        table.add_row(s + marker, EXPECTED[s], ", ".join(TRANSITIONS[s]) or "—")
    console.print(Panel(table, title="КАРТА АВТОМАТА (этап · шаг · ожидаемое действие)", border_style=NAVY))

    console.print(Panel(f"Один и тот же запрос: [bold]{question}[/bold]\n"
                        f"Состояние ([dim]{source}[/dim]).\n"
                        "[dim]Слева — БЕЗ состояния, справа — С состоянием. "
                        "Состояние не даёт агенту перепрыгнуть этап.[/dim]",
                        title="ВЛИЯНИЕ СОСТОЯНИЯ НА ОТВЕТ", border_style=NAVY))
    off, on = ab_run(assistant, question, block, "[dim]гоняю один запрос с состоянием и без…[/dim]")
    console.print(Columns([
        Panel(off, title="БЕЗ СОСТОЯНИЯ (прыгает сразу в код)", border_style=NAVY_DIM),
        Panel(on, title=f"С СОСТОЯНИЕМ (держит стадию {stage})", border_style=NAVY_BRIGHT),
    ], equal=True, expand=True))

    demo = TaskStore(ephemeral=True)
    demo.create("проверка переходов")
    ok_jump, msg_jump = demo.transition("проверка переходов", "done")
    demo.set_plan("проверка переходов", "план")
    ok_step, msg_step = demo.transition("проверка переходов", "execution")
    console.print(Panel(
        f"[{WARN}]×[/{WARN}] /next через этап (planning→done): {msg_jump}\n"
        f"[{NAVY_PALE}]✓[/{NAVY_PALE}] planning→execution (план есть): {msg_step}\n"
        "[dim]Легальность переходов проверяет КОД (state.py), не промпт — нелегальный отклоняется.[/dim]",
        title="ПЕРЕХОДЫ ПОД КОНТРОЛЕМ КОДА", border_style=NAVY))
    console.print(Panel(
        "[bold]Пауза:[/bold] /pause внутри задачи или просто выход — стадия и план пишутся в "
        "store/state.json.\n[bold]Продолжение без повторных объяснений:[/bold] /task <имя> снова — "
        "агент грузит стадию, план и результаты и продолжает с того же места.\n"
        "[dim]Несколько задач живут параллельно — список со статусами всегда в нижней панели.[/dim]",
        title="ПАУЗА, ПРОДОЛЖЕНИЕ, МУЛЬТИЗАДАЧНОСТЬ", border_style=NAVY))


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
                        title="ВЛИЯНИЕ ИНВАРИАНТОВ НА ОТВЕТ", border_style=NAVY))
    block = ("ИНВАРИАНТЫ — нерушимые ограничения. Если запрос им противоречит — откажись и объясни, "
             "какой инвариант нарушается:\n" + rules)
    off, on = ab_run(assistant, question, block, "[dim]гоняю один запрос с инвариантами и без…[/dim]")
    console.print(Columns([
        Panel(off, title="БЕЗ ИНВАРИАНТОВ (выполняет запрос)", border_style=NAVY_DIM),
        Panel(on, title="С ТВОИМИ ИНВАРИАНТАМИ (отказ + объяснение)", border_style=NAVY_BRIGHT),
    ], equal=True, expand=True))

    temp = Invariants.__new__(Invariants)
    temp.items = items
    hits = temp.lint(off)
    code_body = ("нарушений не найдено" if not hits else
                 "\n".join(f"[{WARN}]×[/{WARN}] «{h['term']}» → {h['rule']}" for h in hits))
    console.print(Panel(code_body, title="КОД-ЛИНТЕР по ответу БЕЗ инвариантов (детерминированно)",
                        border_style=NAVY))
    with console.status("[dim]критик (gpt-4o-mini) проверяет ответ без инвариантов…[/dim]", spinner="dots"):
        verdict, usage = critic_check(assistant.api_key, items, off)
    which = "\n".join(f"  · {w}" for w in verdict.get("which", []))
    verdict_body = (f"нарушено: [bold]{verdict.get('violated')}[/bold]\n"
                    f"почему: {verdict.get('why', '')}\n{which}\n"
                    f"[dim]вход {usage['prompt_tokens']} ток. · ответ {usage['completion_tokens']}[/dim]")
    console.print(Panel(verdict_body, title="LLM-КРИТИК по тому же ответу (семантический)", border_style=NAVY))
    console.print("[dim]Конфликт запрос↔инвариант: слева агент без правил выполняет (и линтер с критиком "
                  "ловят нарушение), справа агент с инвариантами отказывается и объясняет. Инварианты "
                  "работают и в промпте, и в коде.[/dim]")


def run_demo_transitions(assistant):
    table = Table(box=box.ROUNDED, expand=True)
    table.add_column("состояние", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("ожидаемое действие")
    table.add_column("разрешённые переходы")
    for s in STAGES:
        table.add_row(s, EXPECTED[s], ", ".join(TRANSITIONS[s]) or "— (терминальное)")
    console.print(Panel(table, title="ДОПУСТИМЫЕ СОСТОЯНИЯ И РАЗРЕШЁННЫЕ ПЕРЕХОДЫ (state.py)",
                        border_style=NAVY))
    console.print(Panel(f"Конвейер: {stage_pipeline(None)}\n"
                        "[dim]Легальность перехода решает КОД (TaskStore.transition), не промпт. "
                        "Конспект: «для жёстких запретов нужен код — текстовые правила теряются после "
                        "summary/compacting».[/dim]",
                        title="контролируемый жизненный цикл задачи", border_style=NAVY))

    demo = TaskStore(ephemeral=True)
    demo.create("демо-задача")
    rows = []
    ok, msg = demo.transition("демо-задача", "done")
    rows.append((ok, "planning → done (перепрыгнуть через 2 этапа)", msg))
    ok, msg = demo.transition("демо-задача", "validation")
    rows.append((ok, "planning → validation (перепрыгнуть execution)", msg))
    ok, msg = demo.transition("демо-задача", "execution")
    rows.append((ok, "planning → execution БЕЗ утверждённого плана", msg))
    illegal = "\n".join(
        f"[{WARN}]×[/{WARN}] {label}\n    [dim]ответ кода:[/dim] {msg}" for ok, label, msg in rows)
    console.print(Panel(illegal + "\n\n[dim]Каждая попытка «перепрыгнуть» отклонена детерминированно — "
                        "состояние задачи не изменилось.[/dim]",
                        title="ПОПЫТКИ ПЕРЕЙТИ В НЕДОПУСТИМОЕ СОСТОЯНИЕ → отказ кода", border_style=WARN))

    legal = []
    demo.set_plan("демо-задача", "1) роуты 2) JWT 3) хранилище")
    legal.append(("план утверждён", "теперь execution разблокирован"))
    for target in ("execution", "validation", "done"):
        ok, msg = demo.transition("демо-задача", target)
        legal.append((msg, "ok" if ok else "ОТКАЗ"))
    ok_term, msg_term = demo.transition("демо-задача", "execution")
    legal_body = "\n".join(f"[{NAVY_PALE}]✓[/{NAVY_PALE}] {a} [dim]({b})[/dim]" for a, b in legal)
    legal_body += f"\n[{WARN}]×[/{WARN}] done → execution: {msg_term} [dim](done терминально)[/dim]"
    console.print(Panel(legal_body, title="ЛЕГАЛЬНЫЙ ПУТЬ (planning→execution→validation→done) проходит",
                        border_style=NAVY))

    paused = TaskStore(ephemeral=True)
    paused.create("оплата")
    paused.set_plan("оплата", "1) выбрать провайдера 2) вебхуки 3) идемпотентность")
    paused.transition("оплата", "execution")
    paused.add_result("оплата", "набросал роуты платежей")
    paused.pause("оплата")
    snap = paused.tasks["оплата"]
    paused.enter("оплата")
    after = paused.tasks["оплата"]
    console.print(Panel(
        f"[bold]Пауза[/bold] (/pause или выход): статус → [{NAVY_PALE}]{STATUS_LABEL[snap['status']]}[/{NAVY_PALE}], "
        f"стадия [{NAVY_PALE}]{snap['stage']}[/{NAVY_PALE}], план и результаты записаны в store/state.json.\n"
        f"[bold]Продолжение[/bold] (/task оплата): статус → [{NAVY_PALE}]{STATUS_LABEL[after['status']]}[/{NAVY_PALE}], "
        f"стадия [{NAVY_PALE}]{after['stage']}[/{NAVY_PALE}], план «{after['plan']}», "
        f"результатов: {len(after['results'])}.\n"
        "[dim]Агент поднимает стадию, план и результаты — продолжает с того же места без повторных объяснений.[/dim]",
        title="ПАУЗА И КОРРЕКТНОЕ ПРОДОЛЖЕНИЕ", border_style=NAVY))
    console.print("[dim]Реакция ассистента вживую: на стадии planning блок состояния в промпте заставляет LLM "
                  "не выдавать финальный код, а вернуть к плану (см. /demo3). Жёсткий стоп — всё равно код выше.[/dim]")


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
        console.print(Panel(f"[{NAVY_PALE}]{key}[/{NAVY_PALE}] = {value}",
                            title="→ долговременная память", border_style=NAVY))
    elif name == "remember-now":
        fallback = f"пункт_{len(assistant.memory.working) + 1}"
        key, value = parse_kv(rest, fallback)
        if not key:
            console.print("[dim]Формат: /remember-now название = содержимое[/dim]")
            return
        assistant.memory.set_task(key, value)
        console.print(Panel(f"[{NAVY_PALE}]{key}[/{NAVY_PALE}] = {value}",
                            title="→ рабочая память", border_style=NAVY))
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
    elif name == "demo5":
        run_demo_transitions(assistant)
    elif name == "reset":
        assistant.memory.reset()
        assistant.profile.clear()
        assistant.state.reset()
        assistant.invariants.clear()
        console.print(Panel("Стёрто всё: задачи, инварианты, профиль, память.", border_style=NAVY))
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
        (s.model, f"bold {NAVY_BRIGHT}"),
        ("\n", ""), (loaded, "dim"),
        ("\nстадии задачи: planning → execution → validation → done", "dim"),
        ("\n\nПиши сообщение — обычный чат. ", "dim"),
        ("/task <имя>", f"bold {NAVY_PALE}"), (" — рабочее пространство задачи. ", "dim"),
        ("Набери ", "dim"), ("/", "bold"), (" для команд, ", "dim"),
        ("/help", f"bold {NAVY_BRIGHT}"), (" — подробно.\n", "dim"),
        ("Демо: ", "dim"), ("/demo1 /demo2 /demo3 /demo4 /demo5", f"bold {NAVY_PALE}"),
        (".  На каждой стадии задачи рой агентов отрабатывает авто; стадию двигаешь только ты — ", "dim"),
        ("/next", f"bold {NAVY_PALE}"), (".\n", "dim"),
        ("Список задач — в нижней панели. Пустая строка — выход.", "dim"),
    )
    console.print(Panel(body, border_style=NAVY, box=box.DOUBLE))


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
        console.print(Panel(answer, title="АССИСТЕНТ", border_style=NAVY, box=box.ROUNDED))
        turn_footer(assistant, usage, len(messages), hits)
    console.print("[dim]Состояние сохранено. Пока![/dim]")


if __name__ == "__main__":
    main()
