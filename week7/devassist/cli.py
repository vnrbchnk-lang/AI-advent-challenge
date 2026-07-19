import json
import time

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

from devassist import agentloop, config, index as index_module, metrics, qa, retrieval, review as review_module, status as status_module, support, tools_project
from devassist.assistant import DevAssistant

NAVY = "#34568b"
NAVY_BRIGHT = "#6f9ad1"
NAVY_PALE = "#a9c8ee"
NAVY_DIM = "#223a5c"
WARN = "#b58900"
OK = "#5c9a5c"
BAD = "#a05252"

COMMANDS = {
    "/index": "построить индексы RAG. /index — все, /index alaba | advent | support",
    "/servers": "день 31: подключённые MCP-серверы и их состояние",
    "/tools": "реестр инструментов (Tool Registry): источник, опасность, описание",
    "/help": "день 31: вопрос о проекте. Пример: /help как устроена авторизация",
    "/demo31": "день 31: ассистент разработчика — git через MCP + документация + отказ вне базы",
    "/review": "день 32: AI-ревью изменений. /review [проект] [base] [head]",
    "/demo32": "день 32: ревью демонстрационной ветки с подсаженными нарушениями",
    "/tickets": "день 33: список тикетов поддержки (MCP-сервер тикетов)",
    "/support": "день 33: ответ по тикету. Пример: /support T-1207",
    "/demo33": "день 33: поддержка — тикет авторизации, тикет экономики, вопрос без данных",
    "/task": "день 34: цель для файлового агента. Пример: /task найди где начисляются монеты",
    "/sandbox": "день 34: песочница (клон проекта). /sandbox | /sandbox reset | /sandbox diff",
    "/demo34": "день 34: два сценария — поиск по коду и генерация файла с diff",
    "/status": "день 35: черновик недельного статуса заказчику. /status [дней]",
    "/demo35": "день 35: собрать статус за 14 дней и показать источники",
    "/metrics": "метрики пайплайна: latency P50/P95, токены, стоимость",
    "/commands": "список команд",
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
assistant = None


class CommandCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return
        word = document.get_word_before_cursor(WORD=True)
        for name, meta in COMMANDS.items():
            if name.startswith(text.split()[0] if text.split() else text):
                yield Completion(name, start_position=-len(word), display=name, display_meta=meta)


def confirm_dangerous(name, arguments):
    body = Text()
    body.append("Инструмент помечен как опасный (запись данных).\n", style=WARN)
    body.append(f"{name}\n", style=f"bold {NAVY_BRIGHT}")
    body.append(json.dumps(arguments, ensure_ascii=False)[:600], style=NAVY_PALE)
    console.print(Panel(body, title="Требуется подтверждение человека", border_style=WARN, box=box.ROUNDED))
    return Confirm.ask("Выполнить?", default=False)


def _bottom_toolbar():
    if not assistant:
        return HTML(" agent31 ")
    connected = sum(1 for item in assistant.bridge.status() if item["connected"])
    built = [name for name in config.PROJECTS if assistant.has_index(name)]
    return HTML(f" <b>agent31</b>  Неделя 7 — Ассистент разработчика | MCP-серверов: {connected}"
                f" | инструментов: {len(assistant.registry.tools)}"
                f" | индексы: {', '.join(built) or 'нет'} ")


def banner():
    console.print(Panel.fit(
        Text("agent31  —  Ассистент разработчика (Неделя 7)", style=f"bold {NAVY_BRIGHT}"),
        border_style=NAVY,
        box=box.ROUNDED,
        subtitle=Text("RAG по проекту · MCP · ревью PR · поддержка · файлы · статус", style=NAVY_PALE),
    ))


def show_commands():
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_edge=False)
    table.add_column("команда", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("что делает", style=NAVY_PALE)
    for name, meta in COMMANDS.items():
        table.add_row(name, meta)
    console.print(Panel(table, title="Команды", border_style=NAVY, box=box.ROUNDED))


def _error(title, error):
    console.print(Panel(Text(f"{type(error).__name__}: {error}", style=WARN),
                        title=title, border_style=WARN, box=box.ROUNDED))


def _day_header(day, title, points):
    body = Text()
    for point in points:
        body.append("- ", style=NAVY_DIM)
        body.append(point + "\n", style=NAVY_PALE)
    console.print(Panel(body, title=Text(f"День {day} — {title}", style=f"bold {NAVY_BRIGHT}"),
                        border_style=NAVY_BRIGHT, box=box.DOUBLE))


def show_servers():
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_edge=False)
    table.add_column("сервер", style=f"bold {NAVY_BRIGHT}")
    table.add_column("транспорт", style=NAVY_PALE)
    table.add_column("статус")
    table.add_column("tools", justify="right", style=NAVY_PALE)
    table.add_column("описание", style=NAVY_PALE)
    for item in assistant.bridge.status():
        state = Text("подключён", style=OK) if item["connected"] else Text(item["error"] or "нет связи", style=BAD)
        table.add_row(item["server"], "stdio", state, str(item["tools"]), item["title"])
    console.print(Panel(table, title="MCP-серверы", border_style=NAVY, box=box.ROUNDED))


def show_tools():
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_edge=False)
    table.add_column("инструмент", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("источник", style=NAVY_PALE, no_wrap=True)
    table.add_column("опасный", justify="center")
    table.add_column("описание", style=NAVY_PALE)
    for row in assistant.registry.rows():
        mark = Text("да", style=WARN) if row["dangerous"] else Text("нет", style=NAVY_DIM)
        table.add_row(row["name"], row["source"], mark, row["description"][:90])
    console.print(Panel(table, title="Tool Registry", border_style=NAVY, box=box.ROUNDED))


def build_index(name):
    def progress(done, total):
        console.print(Text(f"  эмбеддинги {done}/{total}", style=NAVY_DIM), end="\r")

    started = time.time()
    with console.status(Text(f"строю индекс {name}", style=NAVY_PALE), spinner="dots"):
        built, documents, skipped = index_module.build_project(name, progress=progress)
    stats = built.stats()
    console.print(Panel(
        Text(f"файлов: {stats['files']}  чанков: {stats['chunks']}  {stats['by_kind']}\n"
             f"модель: {stats['model']} ({stats['dim']})  время: {round(time.time() - started, 1)} с\n"
             f"пропущено файлов: {len(skipped)}", style=NAVY_PALE),
        title=f"Индекс {name}", border_style=NAVY, box=box.ROUNDED))
    for item in skipped[:5]:
        console.print(Text(f"  пропущен {item['path']}: {item['reason']}", style=WARN))


def _sources_table(hits):
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_edge=False)
    table.add_column("#", justify="right", style=NAVY_DIM)
    table.add_column("источник", style=NAVY_PALE)
    table.add_column("вид", style=NAVY_DIM)
    table.add_column("близость", justify="right", style=NAVY_PALE)
    for position, (score, chunk) in enumerate(hits, 1):
        table.add_row(str(position), retrieval.label(chunk), chunk["kind"], f"{score:.3f}")
    return table


def show_answer(result, title):
    if result["git"].get("available"):
        console.print(Text(
            f"  git через MCP: ветка {result['git']['branch']} · HEAD {result['git']['head']} · "
            f"{'есть незакоммиченные правки' if result['git']['dirty'] else 'дерево чистое'}",
            style=NAVY_DIM))
    style = BAD if result["refused"] else NAVY
    console.print(Panel(Text(result["answer"], style=NAVY_PALE), title=title,
                        border_style=style, box=box.ROUNDED,
                        subtitle=Text(f"уверенность: {result['confidence']}", style=NAVY_DIM)))
    if result["retrieval"]["final"]:
        console.print(_sources_table(result["retrieval"]["final"]))
    if result["quotes"]:
        table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_edge=False)
        table.add_column("проверка", justify="center")
        table.add_column("цитата", style=NAVY_PALE)
        table.add_column("источник", style=NAVY_DIM)
        for quote in result["quotes"]:
            mark = Text("совпала", style=OK) if quote["valid"] else Text("не найдена", style=BAD)
            table.add_row(mark, quote["quote"][:150], quote.get("label", "")[:60])
        console.print(Panel(table, title="Цитаты проверены кодом (подстрока фрагмента)",
                            border_style=NAVY_DIM, box=box.ROUNDED))


def cmd_help(question, project="alaba"):
    if not question:
        console.print(Text("нужен вопрос: /help как устроена авторизация", style=WARN))
        return
    if not assistant.has_index(project):
        console.print(Text(f"индекс {project} не построен — выполни /index {project}", style=WARN))
        return
    with console.status(Text("ищу в базе проекта и спрашиваю модель", style=NAVY_PALE), spinner="dots"):
        result = qa.answer(assistant, question, project)
    show_answer(result, f"/help — {question[:60]}")


def cmd_review(parts):
    project = parts[0] if parts else "advent"
    base = parts[1] if len(parts) > 1 else ""
    head = parts[2] if len(parts) > 2 else ""
    if not assistant.has_index(project):
        console.print(Text(f"индекс {project} не построен — выполни /index {project}", style=WARN))
        return
    with console.status(Text("получаю diff через MCP и запускаю трёх субагентов", style=NAVY_PALE),
                        spinner="dots"):
        result = review_module.review(assistant, project, base, head)
    diff = result["diff"]
    console.print(Text(f"  diff через MCP: {diff['range']} · файлов {len(diff['files'])} · "
                       f"{len(diff['diff'])} символов", style=NAVY_DIM))
    if result["empty"]:
        console.print(Text("изменений нет", style=WARN))
        return
    for part in result["parts"]:
        title = part["dimension"]["title"] if isinstance(part["dimension"], dict) else str(part["dimension"])
        body = Text()
        if part.get("error"):
            body.append(part["error"], style=BAD)
        elif not part["findings"]:
            body.append("замечаний нет", style=OK)
        for item in part.get("findings", []):
            severity = item.get("severity", "мелочь")
            color = {"критично": BAD, "важно": WARN}.get(severity, NAVY_DIM)
            body.append(f"[{severity}] ", style=color)
            body.append(f"{item.get('file', '?')}", style=NAVY_BRIGHT)
            if item.get("line"):
                body.append(f":{item['line']}", style=NAVY_DIM)
            body.append(f"\n  {item.get('title', '')}\n", style=NAVY_PALE)
            if item.get("fix"):
                body.append(f"  что сделать: {item['fix']}\n", style=NAVY_DIM)
            if item.get("source"):
                body.append(f"  основание: {item['source']}\n", style=NAVY_DIM)
        console.print(Panel(body, title=title, border_style=NAVY, box=box.ROUNDED))
    console.print(Text(f"  всего замечаний: {len(result['findings'])}", style=NAVY_DIM))


def cmd_tickets():
    payload = assistant.executor.call("tickets__list_tickets", {})
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_edge=False)
    table.add_column("тикет", style=f"bold {NAVY_BRIGHT}")
    table.add_column("статус", style=NAVY_PALE)
    table.add_column("создан", style=NAVY_DIM)
    table.add_column("тема", style=NAVY_PALE)
    table.add_column("теги", style=NAVY_DIM)
    for item in payload["tickets"]:
        table.add_row(item["id"], item["status"], item["created"], item["subject"], ", ".join(item["tags"]))
    console.print(Panel(table, title="Тикеты (MCP-сервер tickets)", border_style=NAVY, box=box.ROUNDED))


def cmd_support(parts):
    if not assistant.has_index("support"):
        console.print(Text("индекс support не построен — выполни /index support", style=WARN))
        return
    if parts and parts[0].upper().startswith("T-"):
        ticket_id, question = parts[0], " ".join(parts[1:])
        with console.status(Text("читаю тикет через MCP и ищу в базе поддержки", style=NAVY_PALE),
                            spinner="dots"):
            result = support.answer_ticket(assistant, ticket_id, question)
        ticket = result["ticket"]["ticket"]
        user = result["ticket"]["user"]
        console.print(Text(f"  тикет {ticket['id']} · {ticket['subject']} · пользователь {user['name']} "
                           f"({user['device']}, версия {user['app_version']})", style=NAVY_DIM))
    else:
        question = " ".join(parts)
        if not question:
            console.print(Text("нужен тикет или вопрос: /support T-1207", style=WARN))
            return
        with console.status(Text("ищу в базе поддержки", style=NAVY_PALE), spinner="dots"):
            result = support.answer_general(assistant, question)
    show_answer(result, "Ответ пользователю")
    if result["escalate"]:
        console.print(Panel(Text("Данных не хватает — эскалация на инженера, ответ пользователю не отправляем.",
                                 style=WARN), border_style=WARN, box=box.ROUNDED))
    if result["ticket"]:
        outcome = assistant.executor.safe_call("tickets__add_note", {
            "ticket_id": result["ticket"]["ticket"]["id"], "text": support.note_text(result)})
        if outcome["ok"]:
            console.print(Text(f"  заметка добавлена в тикет (всего {outcome['result']['notes']})", style=OK))
        else:
            console.print(Text(f"  заметка не добавлена: {outcome['error']}", style=NAVY_DIM))


def _steps_table(steps):
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_edge=False)
    table.add_column("шаг", justify="right", style=NAVY_DIM)
    table.add_column("инструмент", style=f"bold {NAVY_BRIGHT}")
    table.add_column("аргументы", style=NAVY_PALE)
    table.add_column("итог")
    for record in steps:
        mark = Text("ок", style=OK) if record["ok"] else Text(record["summary"][:60], style=BAD)
        table.add_row(str(record["step"]), record["tool"],
                      json.dumps(record["arguments"], ensure_ascii=False)[:70], mark)
    return table


def cmd_task(goal):
    if not goal:
        console.print(Text("нужна цель: /task найди все места, где начисляются монеты", style=WARN))
        return
    tools_project.sandbox_prepare()
    with console.status(Text("агент сам выбирает инструменты", style=NAVY_PALE), spinner="dots"):
        result = agentloop.run_goal(assistant, goal)
    console.print(_steps_table(result["steps"]))
    console.print(Panel(Text(result["answer"], style=NAVY_PALE), title="Отчёт агента",
                        border_style=NAVY, box=box.ROUNDED,
                        subtitle=Text(f"шагов: {len(result['steps'])} · остановка: {result['stopped']}",
                                      style=NAVY_DIM)))
    show_sandbox_diff()


def show_sandbox_diff():
    try:
        payload = tools_project.sandbox_diff()
    except Exception as error:
        _error("песочница", error)
        return
    if not payload["diff"].strip():
        console.print(Text("  в песочнице изменений нет", style=NAVY_DIM))
        return
    console.print(Panel(Text(payload["diff"][:4000], style=NAVY_PALE),
                        title=f"Изменения в песочнице ({', '.join(payload['files']) or 'новые файлы'})",
                        border_style=OK, box=box.ROUNDED))
    untracked = tools_project._git("sandbox", "status", "--porcelain")
    new_files = [line[3:] for line in untracked.splitlines() if line.startswith("??")]
    if new_files:
        console.print(Text("  новые файлы: " + ", ".join(new_files), style=OK))


def cmd_sandbox(parts):
    action = parts[0] if parts else ""
    if action == "diff":
        show_sandbox_diff()
        return
    payload = tools_project.sandbox_prepare(reset=action == "reset")
    console.print(Panel(Text(f"{payload['path']}\nдействие: {payload['action']}", style=NAVY_PALE),
                        title="Песочница", border_style=NAVY, box=box.ROUNDED))


def cmd_status(parts):
    days = int(parts[0]) if parts and parts[0].isdigit() else 7
    with console.status(Text("собираю коммиты, задачи и созвоны", style=NAVY_PALE), spinner="dots"):
        payload = status_module.draft(assistant, "alaba", days)
    text = status_module.to_markdown(payload)
    console.print(Panel(Text(text, style=NAVY_PALE), title="Черновик статуса заказчику",
                        border_style=NAVY, box=box.ROUNDED))
    console.print(Text("  источники: " + json.dumps(payload["sources"], ensure_ascii=False), style=NAVY_DIM))
    if Confirm.ask("Сохранить черновик в файл?", default=True):
        path = status_module.save(payload, text)
        console.print(Text(f"  сохранено: {path}", style=OK))


def cmd_metrics():
    rows, total = metrics.summary()
    if not rows:
        console.print(Text("метрик пока нет", style=WARN))
        return
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_edge=False)
    table.add_column("этап", style=f"bold {NAVY_BRIGHT}")
    table.add_column("вызовов", justify="right", style=NAVY_PALE)
    table.add_column("сбоев", justify="right")
    table.add_column("P50, с", justify="right", style=NAVY_PALE)
    table.add_column("P95, с", justify="right", style=NAVY_PALE)
    table.add_column("токенов", justify="right", style=NAVY_PALE)
    table.add_column("руб.", justify="right", style=NAVY_PALE)
    for row in rows:
        fails = Text(str(row["fails"]), style=BAD if row["fails"] else NAVY_DIM)
        table.add_row(row["label"], str(row["calls"]), fails, str(row["p50"]), str(row["p95"]),
                      str(row["tokens"]), str(row["cost_rub"]))
    console.print(Panel(table, title="Метрики пайплайна", border_style=NAVY, box=box.ROUNDED,
                        subtitle=Text(f"итого вызовов {total['calls']} · токенов {total['tokens']} · "
                                      f"{total['cost_rub']} руб.", style=NAVY_DIM)))


def demo31():
    _day_header(31, "Ассистент разработчика", [
        "RAG по документации, схемам данных и коду проекта «Личная культура»",
        "MCP-сервер проекта даёт живую git-ветку и статус рабочего дерева",
        "ответ с проверенными цитатами; вне базы — честный отказ",
    ])
    show_servers()
    for question in [
        "на какой ветке сейчас проект и что менялось последним коммитом",
        "какие поля у карты и где лежит схема данных",
        "как устроена авторизация пользователя",
        "как приготовить борщ",
    ]:
        console.print(Text(f"\n> /help {question}", style=f"bold {NAVY_BRIGHT}"))
        cmd_help(question)


def demo32():
    _day_header(32, "Автоматизация ревью кода", [
        "diff берётся через MCP-инструмент project__git_diff",
        "RAG подмешивает правила и код этого же репозитория",
        "три субагента параллельно: баги, архитектура, конвенции проекта",
        "тот же код запускается в GitHub Action на pull_request",
    ])
    cmd_review(["advent", "main", "demo/day32-review"])


def demo33():
    _day_header(33, "Ассистент поддержки пользователей", [
        "MCP-сервер тикетов: карточка пользователя, переписка, серверные логи",
        "RAG по FAQ и описанию продукта",
        "ответ с учётом контекста тикета; нет данных — эскалация человеку",
    ])
    cmd_tickets()
    for parts in [["T-1207"], ["T-1211"], ["почему у меня не начисляются алмазы за турнир"]]:
        console.print(Text(f"\n> /support {' '.join(parts)}", style=f"bold {NAVY_BRIGHT}"))
        cmd_support(parts)


def demo34():
    _day_header(34, "Ассистент для работы с файлами проекта", [
        "задаём цель, а не команду открыть файл",
        "агент сам выбирает инструменты: поиск, чтение, запись",
        "правки идут в песочницу-клон, живой репозиторий защищён кодом",
        "результат виден как git diff и воспроизводится повторно",
    ])
    cmd_sandbox(["reset"])
    for goal in [
        "найди все места на сервере, где начисляется или списывается игровая валюта, "
        "и собери таблицу файл-строка-что происходит",
        "изучи, как в проекте устроена авторизация, и создай в песочнице файл "
        "docs/adr/0001-auth.md с архитектурным решением: контекст, решение, последствия",
    ]:
        console.print(Text(f"\n> /task {goal}", style=f"bold {NAVY_BRIGHT}"))
        cmd_task(goal)


def demo35():
    _day_header(35, "Реальная задача: недельный статус заказчику", [
        "каждую неделю заказчику уходит статус — собираем его автоматически",
        "источники: git log, файл текущих задач, записи созвонов (всё через MCP)",
        "человек проверяет и отправляет — полностью автоматически не отправляем",
    ])
    cmd_status(["14"])


def dispatch(line):
    parts = line.split()
    command, rest = parts[0], parts[1:]
    if command == "/commands":
        show_commands()
    elif command == "/index":
        names = rest or list(config.PROJECTS)
        for name in names:
            if name in config.PROJECTS:
                build_index(name)
            else:
                console.print(Text(f"неизвестный индекс: {name}", style=WARN))
    elif command == "/servers":
        show_servers()
    elif command == "/tools":
        show_tools()
    elif command == "/help":
        cmd_help(" ".join(rest))
    elif command == "/review":
        cmd_review(rest)
    elif command == "/tickets":
        cmd_tickets()
    elif command == "/support":
        cmd_support(rest)
    elif command == "/task":
        cmd_task(" ".join(rest))
    elif command == "/sandbox":
        cmd_sandbox(rest)
    elif command == "/status":
        cmd_status(rest)
    elif command == "/metrics":
        cmd_metrics()
    elif command == "/demo31":
        demo31()
    elif command == "/demo32":
        demo32()
    elif command == "/demo33":
        demo33()
    elif command == "/demo34":
        demo34()
    elif command == "/demo35":
        demo35()
    else:
        console.print(Text(f"неизвестная команда {command} — смотри /commands", style=WARN))


def main():
    global assistant
    banner()
    assistant = DevAssistant(confirm=confirm_dangerous)
    with console.status(Text("поднимаю MCP-серверы", style=NAVY_PALE), spinner="dots"):
        statuses = assistant.start()
    for item in statuses:
        if not item["connected"]:
            console.print(Text(f"сервер {item['server']} не поднялся: {item['error']}", style=WARN))
    missing = [name for name in config.PROJECTS if not assistant.has_index(name)]
    if missing:
        console.print(Text(f"нет индексов: {', '.join(missing)} — построй командой /index", style=WARN))
    show_commands()

    session = PromptSession(completer=CommandCompleter(), style=MENU_STYLE,
                            bottom_toolbar=_bottom_toolbar)
    while True:
        try:
            line = session.prompt(HTML("<prompt>agent31 ></prompt> ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in ("/exit", "/quit"):
            break
        try:
            dispatch(line)
        except Exception as error:
            _error("ошибка команды", error)
    assistant.stop()
    console.print(Text("до встречи", style=NAVY_DIM))


if __name__ == "__main__":
    main()
