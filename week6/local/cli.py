from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from local import localllm, ragbridge

NAVY = "#34568b"
NAVY_BRIGHT = "#6f9ad1"
NAVY_PALE = "#a9c8ee"
NAVY_DIM = "#223a5c"
WARN = "#b58900"
OK = "#5c9a5c"

COMMANDS = {
    "/models": "день 26: список локальных моделей (HTTP /api/tags) — доказательство «работает локально»",
    "/ask": "день 26: один запрос к локальной LLM + статистика скорости. Пример: /ask объясни рекурсию",
    "/demo26": "день 26: 3 запроса разной сложности (факт / рассуждение / код) к локальной модели",
    "/chat": "день 27: интерактивный чат с локальной LLM, без облака",
    "/demo27": "день 27: приложение (CLI) поверх локальной модели — вход в чат",
    "/localrag": "день 28: RAG-ответ полностью локально (ретрив + генерация). Пример: /localrag стек клиента",
    "/compare28": "день 28: тот же вопрос локальная vs облачная (gpt-4.1) рядом. Пример: /compare28 режимы игры",
    "/demo28": "день 28: локальный RAG vs облачный на вопросе из базы",
    "/demo29": "день 29: оптимизация — до/после параметров и промпта + квант Q4 vs Q8",
    "/optimize": "день 29: то же на своём вопросе. Пример: /optimize как работает травма карты",
    "/params": "день 29: показать/менять tuned-параметры. /params | /params temperature 0.1 | /params model q8",
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
index = None

tuned_params = {"temperature": 0.1, "num_ctx": 4096, "num_predict": 220, "model": "q4"}
MODEL_ALIASES = {"q4": localllm.CHAT_MODEL, "q8": localllm.Q8_MODEL}


def _tuned_call_kwargs():
    return dict(
        model=MODEL_ALIASES[tuned_params["model"]],
        temperature=tuned_params["temperature"],
        num_ctx=tuned_params["num_ctx"],
        num_predict=tuned_params["num_predict"],
    )


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
    status = "Ollama отвечает" if localllm.is_available() else "Ollama НЕ отвечает"
    rag = "индекс загружен" if index else "индекс не загружен"
    return HTML(f" <b>agent26</b>  Неделя 6 — Локальные LLM | модель: {localllm.CHAT_MODEL}"
                f" | {status} | {rag} ")


def banner():
    console.print(Panel.fit(
        Text("agent26  —  Локальные LLM (Неделя 6)", style=f"bold {NAVY_BRIGHT}"),
        border_style=NAVY,
        box=box.ROUNDED,
        subtitle=Text("запуск · интеграция · RAG локально · оптимизация", style=NAVY_PALE),
    ))
    if not localllm.is_available():
        console.print(Text("Ollama не отвечает на localhost:11434 — запусти сервис (ollama serve).", style=WARN))


def show_help():
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
    lines = Text()
    for point in points:
        lines.append("- ", style=NAVY_DIM)
        lines.append(point + "\n", style=NAVY_PALE)
    console.print(Panel(lines, title=Text(f"День {day} — {title}", style=f"bold {NAVY_BRIGHT}"),
                        border_style=NAVY_BRIGHT, box=box.DOUBLE))


def _stats_line(stats):
    if not stats:
        return ""
    return (f"{stats['seconds']} c · {stats['tokens']} токенов · {stats['tok_per_s']} tok/s"
            f" · загрузка {stats['load_seconds']} c · {stats['model']}")


def _answer_panel(text, stats, title, border=NAVY):
    body = Text(text, style=NAVY_PALE)
    console.print(Panel(body, title=Text(title, style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text(_stats_line(stats), style=NAVY_DIM),
                        border_style=border, box=box.ROUNDED))


def _load_index():
    global index
    if index is None:
        index = ragbridge.load_index()
    return index


def cmd_models():
    try:
        models = localllm.list_models()
    except Exception as error:
        _error("Ошибка обращения к Ollama (localhost:11434)", error)
        return
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("модель", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("параметры", style=NAVY_PALE)
    table.add_column("квант", style=NAVY_PALE)
    table.add_column("размер", style=NAVY_PALE, justify="right")
    for model in models:
        table.add_row(model["name"], model["params"], model["quant"], f"{model['size_gb']} GB")
    console.print(Panel(table, title=Text("Локальные модели (HTTP GET /api/tags)", style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text("модели развёрнуты на этой машине, интернет не нужен", style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))


def cmd_ask(prompt):
    try:
        with console.status(Text("Локальная модель думает", style=NAVY_PALE)):
            text, stats = localllm.ask(prompt)
        _answer_panel(text, stats, "Ответ локальной LLM")
    except Exception as error:
        _error("Ошибка запроса к локальной модели", error)


def demo26():
    _day_header(26, "Запуск локальной LLM", [
        f"модель {localllm.CHAT_MODEL} развёрнута локально, доступ по HTTP localhost:11434",
        "3 запроса разной сложности: простой факт / рассуждение / генерация кода",
        "каждый ответ — с замером скорости (tok/s, латентность)",
    ])
    cmd_models()
    requests_by_level = [
        ("Простой", "Назови столицу Австралии одним словом."),
        ("Рассуждение", "В корзине 3 красных и 5 синих шаров. Вынули один синий. "
                        "Какова вероятность вынуть красный следующим? Реши пошагово."),
        ("Код", "Напиши функцию на Python, которая возвращает n-е число Фибоначчи итеративно."),
    ]
    for level, prompt in requests_by_level:
        try:
            console.print(Text(f"[{level}] {prompt}", style=f"bold {NAVY_BRIGHT}"))
            with console.status(Text("Локальная модель думает", style=NAVY_PALE)):
                text, stats = localllm.ask(prompt)
            _answer_panel(text, stats, f"Ответ — {level}")
        except Exception as error:
            _error("Ошибка запроса к локальной модели", error)
            return


def cmd_chat():
    history = []

    def chat_toolbar():
        return HTML(f" <b>локальный чат</b> | модель: {localllm.CHAT_MODEL}"
                    f" | облако: выкл | сообщений: {len(history)} ")

    console.print(Panel(Text("Чат с локальной LLM. Всё считается на этой машине, без облака. "
                             "/reset — очистить историю, /exit — выход.", style=NAVY_PALE),
                        title=Text("Локальный чат (день 27)", style=f"bold {NAVY_BRIGHT}"),
                        border_style=NAVY, box=box.ROUNDED))
    session = PromptSession(style=MENU_STYLE, bottom_toolbar=chat_toolbar)
    while True:
        try:
            text = session.prompt(HTML('<prompt>чат &gt; </prompt>')).strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not text:
            continue
        if text == "/exit":
            break
        if text == "/reset":
            history.clear()
            console.print(Text("история очищена", style=OK))
            continue
        history.append({"role": "user", "content": text})
        try:
            with console.status(Text("Локальная модель отвечает", style=NAVY_PALE)):
                answer, stats = localllm.chat(history)
            history.append({"role": "assistant", "content": answer})
            _answer_panel(answer, stats, "Локальная LLM")
        except Exception as error:
            history.pop()
            _error("Ошибка чата", error)


def _render_local_rag(result, title="Локальный RAG-ответ"):
    border = NAVY if result["status"] == "ok" else WARN
    _answer_panel(result["answer"], result.get("stats"), title, border)
    if result["sources"]:
        table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
        table.add_column("источник", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
        table.add_column("секция", style=NAVY_PALE)
        table.add_column("chunk_id", style=NAVY_DIM, no_wrap=True)
        for source in result["sources"]:
            table.add_row(source["source"], source["section"][:44], source["chunk_id"])
        console.print(Panel(table, title=Text("Источники (локальный ретрив, bge-m3)", style=f"bold {NAVY_BRIGHT}"),
                            border_style=NAVY, box=box.ROUNDED))


def cmd_localrag(question):
    if _load_index() is None:
        console.print(Text("Индекс недели 5 не найден — построй его: agent21 -> /fetch /index.", style=WARN))
        return
    try:
        with console.status(Text("Локальный ретрив + локальная генерация", style=NAVY_PALE)):
            result = ragbridge.answer_local(question, index, {"top_k": 3})
        _render_local_rag(result)
    except Exception as error:
        _error("Ошибка локального RAG", error)


def cmd_compare28(question):
    if _load_index() is None:
        console.print(Text("Индекс недели 5 не найден — построй его: agent21 -> /fetch /index.", style=WARN))
        return
    try:
        with console.status(Text("Гоняю локальную и облачную модель на одном контексте", style=NAVY_PALE)):
            local_result, cloud_result = ragbridge.compare(question, index, {"top_k": 3})
    except Exception as error:
        _error("Ошибка сравнения (облачная сторона требует PROXYAPI_KEY)", error)
        return
    local_panel = Panel(
        Text(local_result["answer"], style=NAVY_PALE),
        title=Text(f"Локальная ({localllm.CHAT_MODEL})", style=f"bold {NAVY_BRIGHT}"),
        subtitle=Text(_stats_line(local_result.get("stats")), style=NAVY_DIM),
        border_style=NAVY, box=box.ROUNDED)
    cloud_panel = Panel(
        Text(cloud_result["answer"], style=NAVY_PALE),
        title=Text("Облачная (gpt-4.1, ProxyAPI)", style=f"bold {WARN}"),
        subtitle=Text(f"{cloud_result.get('seconds', '?')} c · интернет + оплата токенов", style=NAVY_DIM),
        border_style=WARN, box=box.ROUNDED)
    console.print(Columns([local_panel, cloud_panel], equal=True, expand=True))
    console.print(Panel(Text(
        "Оцени на видео: качество (полнота/точность ответа), скорость (секунды),"
        " стабильность (формат, отсутствие срывов). Ретрив у обоих одинаковый и локальный.",
        style=NAVY_PALE), title=Text("Что сравнить", style=f"bold {NAVY_BRIGHT}"),
        border_style=NAVY, box=box.ROUNDED))


def demo28():
    _day_header(28, "Локальная LLM + RAG", [
        "ретрив недели 5 полностью локальный: эмбеддинги bge-m3 + numpy-индекс",
        "генерация — локальная модель вместо облачной; вся цепочка на машине",
        "сравнение с облаком (gpt-4.1): качество / скорость / стабильность",
    ])
    cmd_compare28("Какой стек и архитектура у проекта клиента?")


def _footprint_line():
    try:
        loaded = localllm.running_models()
    except Exception:
        return ""
    return " · ".join(f"{m['name']}: {m['size_gb']} GB (CPU {m['cpu_gb']} / VRAM {m['vram_gb']})"
                      for m in loaded)


def cmd_params(args):
    parts = args.split()
    if len(parts) == 2:
        key, value = parts
        try:
            if key == "temperature":
                tuned_params[key] = float(value)
            elif key in ("num_ctx", "num_predict"):
                tuned_params[key] = int(value)
            elif key == "model" and value in MODEL_ALIASES:
                tuned_params[key] = value
            else:
                console.print(Text("Ключи: temperature <float>, num_ctx <int>, num_predict <int>,"
                                   " model <q4|q8>", style=WARN))
                return
        except ValueError:
            console.print(Text(f"Неверное значение для {key}: {value}", style=WARN))
            return
    elif parts:
        console.print(Text("Формат: /params  или  /params <ключ> <значение>", style=WARN))
        return
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_edge=False)
    table.add_column("параметр", style=f"bold {NAVY_BRIGHT}")
    table.add_column("значение", style=NAVY_PALE)
    table.add_column("смысл", style=NAVY_DIM)
    rows = [
        ("temperature", str(tuned_params["temperature"]), "разброс/креативность (0 — детерминированно)"),
        ("num_ctx", str(tuned_params["num_ctx"]), "окно контекста в токенах"),
        ("num_predict", str(tuned_params["num_predict"]), "максимум токенов в ответе"),
        ("model", f"{tuned_params['model']} ({MODEL_ALIASES[tuned_params['model']]})", "квантование: q4 | q8"),
    ]
    for row in rows:
        table.add_row(*row)
    console.print(Panel(table, title=Text("Tuned-параметры дня 29 (строка «после»)", style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text("меняй командой /params <ключ> <значение>, затем /optimize или /demo29",
                                      style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))


QUANT_PROMPT = "Объясни простыми словами, что такое RAG в LLM. Ровно 2 предложения, по-русски."


def _speed_table(title, rows, subtitle=""):
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("конфигурация", style=f"bold {NAVY_BRIGHT}")
    table.add_column("секунды", justify="right", style=NAVY_PALE)
    table.add_column("tok/s", justify="right", style=NAVY_PALE)
    table.add_column("токенов", justify="right", style=NAVY_PALE)
    for label, stats in rows:
        stats = stats or {}
        table.add_row(label, str(stats.get("seconds", "—")),
                      str(stats.get("tok_per_s", "—")), str(stats.get("tokens", "—")))
    console.print(Panel(table, title=Text(title, style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text(subtitle, style=NAVY_DIM), border_style=NAVY, box=box.ROUNDED))


def _optimize(question):
    if _load_index() is None:
        console.print(Text("Индекс недели 5 не найден — построй его: agent21 -> /fetch /index.", style=WARN))
        return
    tuned_settings = {"top_k": 3}
    tuned = {**_tuned_call_kwargs(), "model": localllm.CHAT_MODEL}
    localllm.unload(localllm.Q8_MODEL)
    param_runs = [
        ("До: дефолт (temp 0.3, промпт общий, num_ctx по умолчанию)",
         dict(model=localllm.CHAT_MODEL, temperature=0.3, num_ctx=None, num_predict=None)),
        (f"После: tuned (temp {tuned['temperature']}, num_ctx {tuned['num_ctx']},"
         f" num_predict {tuned['num_predict']}, prompt под кейс)", tuned),
    ]
    param_rows = []
    for label, params in param_runs:
        try:
            console.print(Text(label, style=f"bold {NAVY_BRIGHT}"))
            with console.status(Text("RAG-запрос к локальной модели (Q4)", style=NAVY_PALE)):
                result = ragbridge.answer_local(question, index, tuned_settings, **params)
            _answer_panel(result["answer"], result.get("stats"), label)
            param_rows.append((label, result.get("stats")))
        except Exception as error:
            _error("Ошибка прогона параметров", error)
            param_rows.append((label, None))
    _speed_table("Параметры и промпт: до/после (RAG, Q4)", param_rows,
                 "тот же вопрос по базе, меняются только параметры и prompt-шаблон")

    console.print(Text("Квантование: Q4_K_M vs Q8_0 на коротком запросе (без тяжёлого контекста, "
                       "чтобы Q8 уместился в память ноутбука)", style=f"bold {NAVY_BRIGHT}"))
    quant_rows = []
    for model in (localllm.CHAT_MODEL, localllm.Q8_MODEL):
        try:
            localllm.unload(localllm.Q8_MODEL if model == localllm.CHAT_MODEL else localllm.CHAT_MODEL)
            with console.status(Text(f"Запрос к {model}", style=NAVY_PALE)):
                text, stats = localllm.ask(QUANT_PROMPT, model=model, temperature=0.1, num_predict=120)
            _answer_panel(text, stats, model)
            quant_rows.append((model, stats))
        except Exception as error:
            _error(f"Ошибка прогона {model}", error)
            quant_rows.append((model, None))
    _speed_table("Квантование: Q4 vs Q8", quant_rows,
                 f"футпринт загруженной модели: {_footprint_line()}")

    console.print(Panel(Text(
        "Оцени на видео: качество ответов до/после (точность, формат, полнота) и Q4 vs Q8;"
        " скорость (tok/s) и потребление (футпринт /api/ps). Q4 легче и быстрее, Q8 точнее и тяжелее.",
        style=NAVY_PALE), title=Text("Выводы", style=f"bold {NAVY_BRIGHT}"),
        border_style=NAVY, box=box.ROUNDED))


def demo29():
    _day_header(29, "Оптимизация локальной LLM", [
        "кейс: QA по базе хакатона; крутим temperature / num_ctx / num_predict + prompt-шаблон",
        "параметры «после» меняются вручную командой /params (temperature, num_ctx, num_predict)",
        "квантование: Q4_K_M vs Q8_0 на коротком запросе (Q8 тяжёлый для 15GB RAM с большим контекстом)",
        "сравнение: качество до/после, скорость (tok/s), потребление (футпринт /api/ps)",
    ])
    _optimize("Опиши кратко механику травмы и смерти карты в игре.")


def dispatch(text):
    if " " in text:
        name, args = text.split(" ", 1)
    else:
        name, args = text, ""
    args = args.strip()
    if name == "/models":
        cmd_models()
    elif name == "/ask":
        cmd_ask(args) if args else console.print(Text("нужен запрос: /ask <текст>", style=WARN))
    elif name == "/demo26":
        demo26()
    elif name == "/chat":
        cmd_chat()
    elif name == "/demo27":
        _day_header(27, "Интеграция локальной LLM в приложение", [
            "это приложение (CLI-утилита agent26) шлёт запросы в локальную модель",
            "получает и показывает ответы; облачные модели не используются",
        ])
        cmd_chat()
    elif name == "/localrag":
        cmd_localrag(args) if args else console.print(Text("нужен вопрос: /localrag <вопрос>", style=WARN))
    elif name == "/compare28":
        cmd_compare28(args) if args else console.print(Text("нужен вопрос: /compare28 <вопрос>", style=WARN))
    elif name == "/demo28":
        demo28()
    elif name == "/optimize":
        _optimize(args) if args else console.print(Text("нужен вопрос: /optimize <вопрос>", style=WARN))
    elif name == "/demo29":
        demo29()
    elif name == "/params":
        cmd_params(args)
    elif name == "/help":
        show_help()
    else:
        console.print(Text("Неизвестная команда, /help.", style=WARN))


def main():
    banner()
    show_help()
    session = PromptSession(completer=CommandCompleter(), style=MENU_STYLE,
                            bottom_toolbar=_bottom_toolbar)
    while True:
        try:
            text = session.prompt(HTML('<prompt>agent26 &gt; </prompt>')).strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not text:
            continue
        if text == "/exit":
            break
        try:
            dispatch(text)
        except Exception as error:
            _error("Ошибка команды", error)
    console.print(Text("до встречи", style=NAVY_DIM))


if __name__ == "__main__":
    main()
