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

from assistant.memory import MemoryLayers
from assistant.profile import Profile, FIELDS
from assistant.state import TaskState, STAGES, TRANSITIONS, EXPECTED
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
    "/status": "показать всё состояние: память, профиль, инварианты, стадия задачи",
    "/remember-forever": "долговременная память. Пример: /remember-forever решение = используем JWT",
    "/remember-now": "рабочая память задачи. Пример: /remember-now эндпоинт = /login",
    "/profile-set": "поле профиля. Пример: /profile-set стиль = краткий",
    "/invariant-add": "инвариант + запретные слова. Пример: /invariant-add Только Kotlin :: python, java",
    "/task": "начать задачу (стадия planning). Пример: /task сервис авторизации",
    "/plan": "утвердить план задачи. Пример: /plan 1) роуты 2) JWT 3) хранение",
    "/go": "переход стадии (код проверит легальность). Пример: /go execution",
    "/demo1": "день 12 — персонализация: один вопрос, два профиля",
    "/demo2": "день 13 — task state machine: стадии, легальные/нелегальные переходы, пауза/резюм",
    "/demo3": "день 14 — инварианты: конфликт запроса и инварианта, отказ + проверка кодом и критиком",
    "/reset": "стереть всё состояние",
    "/help": "справка",
}

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

DEMO1_QUESTION = "Как сделать дебаунс пользовательского ввода в приложении?"
DEMO1_PROFILE_A = {
    "стиль": "краткий, без воды",
    "формат": "код-first",
    "уровень": "senior",
    "роль": "тимлид, нужен быстрый скелет",
}
DEMO1_PROFILE_B = {
    "стиль": "дружеский, подробно",
    "формат": "списки с пояснениями",
    "уровень": "junior",
    "роль": "студент, учится с нуля",
}

DEMO3_INVARIANTS = [
    {"rule": "Стек только Kotlin. Python запрещён.", "forbid": ["python"]},
    {"rule": "Архитектура только MVI. MVVM и MVP запрещены.", "forbid": ["mvvm", "mvp"]},
]
DEMO3_QUESTION = "Набросай быстрый прототип экрана на Python с архитектурой MVVM."
DEMO3_BAD_ANSWER = (
    "Без проблем! Вот прототип на Python, я выбрал архитектуру MVVM: "
    "класс ViewModel хранит состояние, View подписывается на LiveData..."
)


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
        self.profile = Profile()
        self.state = TaskState()
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
    return Panel(table, title="ПАМЯТЬ (день 11) — три слоя, отдельные файлы", border_style=STEEL)


def render_profile(profile):
    if profile.data:
        body = "\n".join(f"[{STEEL_PALE}]{k}[/{STEEL_PALE}] = {v}" for k, v in profile.data.items())
    else:
        body = "[dim]профиль пуст — /profile-set стиль = краткий[/dim]"
    return Panel(body, title="ПРОФИЛЬ (день 12) — персонализация", border_style=STEEL)


def render_invariants(invariants):
    if invariants.items:
        rows = []
        for i, item in enumerate(invariants.items):
            forbid = ", ".join(item["forbid"]) if item["forbid"] else "—"
            rows.append(f"[{STEEL_PALE}]{i + 1}.[/{STEEL_PALE}] {item['rule']}  [dim](стоп-слова: {forbid})[/dim]")
        body = "\n".join(rows)
    else:
        body = "[dim]инвариантов нет — /invariant-add Только Kotlin :: python[/dim]"
    return Panel(body, title="ИНВАРИАНТЫ (день 14) — нерушимые, хранятся отдельно", border_style=STEEL)


def render_state(state):
    if not state.active:
        body = "[dim]задача не начата — /task <название>[/dim]"
    else:
        d = state.data
        allowed = ", ".join(state.allowed()) or "—"
        body = (f"[{STEEL_PALE}]задача:[/{STEEL_PALE}] {d['task']}\n"
                f"[{STEEL_PALE}]стадия:[/{STEEL_PALE}] {d['stage']}  [dim](шаг {d['step']})[/dim]\n"
                f"[{STEEL_PALE}]ожидается:[/{STEEL_PALE}] {EXPECTED[d['stage']]}\n"
                f"[{STEEL_PALE}]план:[/{STEEL_PALE}] {d['plan'] or '—'}\n"
                f"[{STEEL_PALE}]легальные переходы:[/{STEEL_PALE}] {allowed}")
    return Panel(body, title="СОСТОЯНИЕ ЗАДАЧИ (день 13) — task state machine", border_style=STEEL)


def show_status(assistant):
    console.print(render_state(assistant.state))
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
        ("Stateful-агент: память + профиль + состояние задачи + инварианты в одном.\n", ""),
        ("Просто пиши — обычный чат (учитывает все слои). Команды — со ", "dim"), ("/", "bold"),
        (".\n", "dim"),
        ("Демо по дням: ", "dim"), ("/demo1", f"bold {STEEL_PALE}"), (" персонализация · ", "dim"),
        ("/demo2", f"bold {STEEL_PALE}"), (" state machine · ", "dim"),
        ("/demo3", f"bold {STEEL_PALE}"), (" инварианты.", "dim"),
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


def cmd_task(assistant, rest):
    name = rest.strip()
    if not name:
        console.print("[dim]Формат: /task <название задачи>[/dim]")
        return
    assistant.state.start(name)
    console.print(Panel(f"Задача: [bold]{name}[/bold]\nСтадия: planning\n"
                        f"[dim]{EXPECTED['planning']}[/dim]",
                        title="→ задача начата", border_style=STEEL))


def cmd_plan(assistant, rest):
    text = rest.strip()
    if not assistant.state.active:
        console.print("[dim]Сначала начни задачу: /task <название>[/dim]")
        return
    if not text:
        console.print("[dim]Формат: /plan <текст плана>[/dim]")
        return
    assistant.state.set_plan(text)
    console.print(Panel(text, title="→ план утверждён (можно /go execution)", border_style=STEEL))


def cmd_go(assistant, rest):
    target = rest.strip().lower()
    if not assistant.state.active:
        console.print("[dim]Сначала начни задачу: /task <название>[/dim]")
        return
    if not target:
        console.print(f"[dim]Формат: /go <стадия>. Легальные сейчас: "
                      f"{', '.join(assistant.state.allowed()) or '—'}[/dim]")
        return
    ok, message = assistant.state.transition(target)
    if not ok:
        console.print(Panel(message, title="× переход отклонён кодом", border_style=WARN))
        return
    console.print(Panel(f"{message}\n[dim]{EXPECTED[target]}[/dim]",
                        title="→ стадия изменена", border_style=STEEL))
    if target == "validation":
        run_validation_critic(assistant)


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


def run_demo1(assistant):
    console.print(Panel(f"Один и тот же вопрос: [bold]{DEMO1_QUESTION}[/bold]\n"
                        "[dim]Два разных профиля. В вопросе про стиль/формат не сказано — "
                        "агент берёт это из профиля автоматически.[/dim]",
                        title="ДЕНЬ 12 — ПЕРСОНАЛИЗАЦИЯ", border_style=STEEL))
    base = [{"role": "system", "content": assistant.system}]
    question = {"role": "user", "content": DEMO1_QUESTION}

    def profile_block(profile):
        lines = "\n".join(f"- {k}: {v}" for k, v in profile.items())
        return {"role": "system",
                "content": "Профиль пользователя (персонализация) — подстраивай стиль, "
                           "формат и глубину под него:\n" + lines}

    with console.status("[dim]гоняю один вопрос через два профиля…[/dim]", spinner="dots"):
        a_answer, _ = assistant.call_api(base + [profile_block(DEMO1_PROFILE_A), question])
        b_answer, _ = assistant.call_api(base + [profile_block(DEMO1_PROFILE_B), question])
    a_title = "ПРОФИЛЬ A · senior · краткий · код-first"
    b_title = "ПРОФИЛЬ B · junior · дружеский · подробно"
    console.print(Columns([Panel(a_answer, title=a_title, border_style=STEEL_BRIGHT),
                           Panel(b_answer, title=b_title, border_style=STEEL_DIM)],
                          equal=True, expand=True))
    console.print("[dim]Тот же вопрос — разный ответ. Слева сухой скелет с кодом, справа разжёвано "
                  "списком. Это и есть персонализация: агент учитывает профиль автоматически.[/dim]")


def run_demo2(assistant):
    console.print(Panel("Task state machine: planning → execution → validation → done.\n"
                        "[dim]Переходы проверяет КОД (state.py), не промпт. Демо на временном "
                        "состоянии — твою реальную задачу не трогает.[/dim]",
                        title="ДЕНЬ 13 — СОСТОЯНИЕ ЗАДАЧИ", border_style=STEEL))

    table = Table(box=box.ROUNDED, expand=True)
    table.add_column("стадия", style=f"bold {STEEL_BRIGHT}")
    table.add_column("ожидаемое действие")
    table.add_column("легальные переходы")
    for stage in STAGES:
        table.add_row(stage, EXPECTED[stage], ", ".join(TRANSITIONS[stage]) or "—")
    console.print(Panel(table, title="карта автомата", border_style=STEEL))

    demo = TaskState(ephemeral=True)
    log = []

    def step(label, ok, message):
        mark = "✓" if ok else "×"
        color = STEEL_PALE if ok else WARN
        log.append(f"[{color}]{mark}[/{color}] {label}: {message}")

    demo.start("сервис авторизации")
    log.append(f"[{STEEL_PALE}]✓[/{STEEL_PALE}] /task сервис авторизации → стадия planning")
    ok, msg = demo.transition("done")
    step("/go done (из planning, перепрыгнуть)", ok, msg)
    ok, msg = demo.transition("execution")
    step("/go execution (без плана)", ok, msg)
    demo.set_plan("1) роуты 2) JWT 3) хранение сессий")
    log.append(f"[{STEEL_PALE}]✓[/{STEEL_PALE}] /plan утверждён")
    ok, msg = demo.transition("execution")
    step("/go execution (план есть)", ok, msg)
    ok, msg = demo.transition("validation")
    step("/go validation", ok, msg)
    ok, msg = demo.transition("done")
    step("/go done", ok, msg)
    console.print(Panel("\n".join(log), title="прогон переходов (× = код отклонил)", border_style=STEEL))

    console.print(Panel(
        "Состояние пишется в [bold]store/state.json[/bold] на каждом шаге. Можно закрыть агента "
        "на любой стадии (пауза) — при следующем запуске он загрузит стадию, план и результаты и "
        "[bold]продолжит без повторных объяснений[/bold]. Проверь: начни /task, сделай /go execution, "
        "выйди, запусти снова — /status покажет ту же стадию.",
        title="пауза и продолжение", border_style=STEEL))


def run_demo3(assistant):
    invariants = assistant.invariants
    using_sample = not invariants.items
    items = invariants.items if invariants.items else DEMO3_INVARIANTS
    source = "взяты твои инварианты" if not using_sample else "инвариантов нет — взят образец"
    rules = "\n".join(f"{i + 1}. {it['rule']}" for i, it in enumerate(items))
    console.print(Panel(f"Инварианты ([dim]{source}[/dim]):\n{rules}\n\n"
                        f"Запрос, который их нарушает: [bold]{DEMO3_QUESTION}[/bold]",
                        title="ДЕНЬ 14 — ИНВАРИАНТЫ И ОТКАЗ", border_style=STEEL))

    inv_block = {"role": "system",
                 "content": ("ИНВАРИАНТЫ — нерушимые ограничения. Если запрос им противоречит — "
                             "откажись и объясни, какой инвариант нарушается:\n" + rules)}
    base = [{"role": "system", "content": assistant.system}]
    question = {"role": "user", "content": DEMO3_QUESTION}
    with console.status("[dim]спрашиваю агента с инвариантами в промпте…[/dim]", spinner="dots"):
        refusal, _ = assistant.call_api(base + [inv_block, question])
    console.print(Panel(refusal, title="1) АГЕНТ С ИНВАРИАНТАМИ → отказ + объяснение",
                        border_style=STEEL_BRIGHT))

    temp = Invariants.__new__(Invariants)
    temp.items = items
    hits = temp.lint(DEMO3_BAD_ANSWER)
    code_body = ("нарушений не найдено" if not hits else
                 "\n".join(f"[{WARN}]×[/{WARN}] «{h['term']}» → {h['rule']}" for h in hits))
    console.print(Panel(f"[dim]Проверяемый «плохой» ответ:[/dim] {DEMO3_BAD_ANSWER}\n\n{code_body}",
                        title="2) КОД-ЛИНТЕР (детерминированный, без LLM)", border_style=STEEL))

    with console.status("[dim]критик (gpt-4o-mini) проверяет тот же ответ…[/dim]", spinner="dots"):
        verdict, usage = critic_check(assistant.api_key, items, DEMO3_BAD_ANSWER)
    which = "\n".join(f"  · {w}" for w in verdict.get("which", []))
    verdict_body = (f"нарушено: [bold]{verdict.get('violated')}[/bold]\n"
                    f"почему: {verdict.get('why', '')}\n{which}\n"
                    f"[dim]вход {usage['prompt_tokens']} ток. · ответ {usage['completion_tokens']}[/dim]")
    console.print(Panel(verdict_body, title="3) LLM-КРИТИК (семантический)", border_style=STEEL))
    console.print("[dim]Два слоя защиты: промпт заставляет агента отказаться заранее (1), "
                  "а код-линтер (2) и критик (3) ловят нарушение, если оно всё же просочилось в ответ.[/dim]")


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
    elif name == "task":
        cmd_task(assistant, rest)
    elif name == "plan":
        cmd_plan(assistant, rest)
    elif name == "go":
        cmd_go(assistant, rest)
    elif name == "demo1":
        run_demo1(assistant)
    elif name == "demo2":
        run_demo2(assistant)
    elif name == "demo3":
        run_demo3(assistant)
    elif name == "reset":
        assistant.memory.reset()
        assistant.profile.clear()
        assistant.state.reset()
        assistant.invariants.clear()
        console.print(Panel("Стёрто всё: память, профиль, состояние задачи, инварианты.",
                            border_style=STEEL))
    else:
        console.print(f"[dim]Неизвестная команда /{name}. Набери /help.[/dim]")


def banner(assistant):
    s = assistant
    loaded = (f"память: кратк {len(s.memory.short_term)} · раб {len(s.memory.working)} · "
              f"долг {len(s.memory.long_term)}   профиль: {len(s.profile.data)}   "
              f"инвариантов: {len(s.invariants.items)}   "
              f"задача: {s.state.data['task'] or '—'} ({s.state.stage})")
    body = Text.assemble(
        ("Stateful-агент", "bold"),
        ("  ·  дни 11–14  ·  модель ", ""), (s.model, f"bold {STEEL_BRIGHT}"),
        ("\n", ""), (loaded, "dim"),
        ("\n\nПамять · профиль · состояние задачи · инварианты — в одном агенте.\n", "dim"),
        ("Пиши сообщение — обычный чат. Набери ", "dim"), ("/", "bold"),
        (" для команд, ", "dim"), ("/help", f"bold {STEEL_BRIGHT}"), (" — подробно. ", "dim"),
        ("Демо: ", "dim"), ("/demo1 /demo2 /demo3", f"bold {STEEL_PALE}"),
        (". Пустая строка — выход.", "dim"),
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
        with console.status("[dim]агент думает…[/dim]", spinner="dots"):
            answer, usage, messages, hits = assistant.ask(user)
        console.print(Panel(answer, title="АССИСТЕНТ", border_style=STEEL, box=box.ROUNDED))
        turn_footer(assistant, usage, len(messages), hits)
    console.print("[dim]Состояние сохранено. Пока![/dim]")


if __name__ == "__main__":
    main()
