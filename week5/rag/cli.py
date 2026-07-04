import json

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

from rag import corpus, chunking, embedder, evalset
from rag.index import VectorIndex
from rag.rag import answer_no_rag, answer_rag, generate_answer, REFUSAL
from rag.retrieval import DEFAULTS, retrieve
from rag.taskmemory import ChatMemory

NAVY = "#34568b"
NAVY_BRIGHT = "#6f9ad1"
NAVY_PALE = "#a9c8ee"
NAVY_DIM = "#223a5c"
WARN = "#b58900"
OK = "#5c9a5c"

COMMANDS = {
    "/fetch": "день 21: собрать корпус из C:\\Alaba (md + txt + pdf) в rag/docs",
    "/index": "день 21: построить ОБА индекса (fixed и structural) с эмбеддингами bge-m3",
    "/search": "день 21: топ-5 чанков из обоих индексов рядом. Пример: /search механика травмы",
    "/ask": "дни 22-24: RAG-ответ с источниками и цитатами. Пример: /ask какой стек у клиента",
    "/raw": "день 22: ответ БЕЗ RAG (модель из общих знаний). Пример: /raw какой стек у клиента",
    "/eval": "день 22: прогон 10 контрольных вопросов (с RAG / без RAG) с проверкой источников",
    "/mode": "день 23: настройки поиска. /mode | /mode rerank on | /mode threshold 0.45 | /mode strategy fixed",
    "/compare23": "день 23: сырой топ vs после фильтра и реранка. Пример: /compare23 режимы игры",
    "/check": "день 24: чек 10 вопросов — источники/цитаты/цитаты дословны",
    "/chat": "день 25: мини-чат с RAG, историей и памятью задачи",
    "/demo21": "день 21: корпус, статистика двух стратегий чанкинга, пример поиска",
    "/demo22": "день 22: один вопрос с RAG и без RAG рядом",
    "/demo23": "день 23: сравнение выдачи до и после фильтрации на примере",
    "/demo24": "день 24: ответ с цитатами + вопрос мимо базы (режим «не знаю»)",
    "/demo25": "день 25: подсказка сценария и вход в чат",
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
indexes = {}
settings = dict(DEFAULTS)
active_strategy = "structural"


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
    parts = [" <b>agent21</b>  Неделя 5 — RAG "]
    if indexes:
        counts = " · ".join(f"{s}: {len(ix.chunks)} чанков" for s, ix in sorted(indexes.items()))
        parts.append(f"| {counts} ")
    else:
        parts.append("| индексы не построены (/index) ")
    flags = f"| стратегия: {active_strategy} · rerank: {'on' if settings['rerank'] else 'off'}" \
            f" · rewrite: {'on' if settings['rewrite'] else 'off'} · порог: {settings['threshold']} "
    parts.append(flags)
    return HTML("".join(parts))


def banner():
    console.print(Panel.fit(
        Text("agent21  —  RAG-агент (Неделя 5)", style=f"bold {NAVY_BRIGHT}"),
        border_style=NAVY,
        box=box.ROUNDED,
        subtitle=Text("индексация · поиск · реранкинг · цитаты · чат с памятью", style=NAVY_PALE),
    ))
    if not embedder.is_available():
        console.print(Text("Ollama не отвечает на localhost:11434 — запусти сервис.", style=WARN))


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


def _load_indexes():
    for strategy in chunking.STRATEGIES:
        if strategy not in indexes and VectorIndex.exists(strategy):
            indexes[strategy] = VectorIndex.load(strategy)


def _need_index():
    _load_indexes()
    if active_strategy not in indexes:
        console.print(Text("Индекс не построен — сначала /fetch и /index.", style=WARN))
        return False
    return True


def cmd_fetch():
    with console.status(Text("Собираю корпус из C:\\Alaba", style=NAVY_PALE)):
        documents = corpus.collect()
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("#", style=NAVY_DIM, justify="right")
    table.add_column("группа", style=NAVY_BRIGHT, no_wrap=True)
    table.add_column("файл", style=f"bold {NAVY_BRIGHT}")
    table.add_column("заголовок", style=NAVY_PALE)
    table.add_column("символов", style=NAVY_PALE, justify="right")
    for i, doc in enumerate(documents, 1):
        table.add_row(str(i), doc["group"], doc["file"], doc["title"][:50], f"{doc['n_chars']:,}")
    total = sum(d["n_chars"] for d in documents)
    console.print(Panel(table, title=Text("Корпус собран", style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text(f"документов: {len(documents)} · всего символов: {total:,}"
                                      f" (~{total // 1800} страниц)", style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))


def _stats_table(stats_by_strategy):
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("стратегия", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
    table.add_column("чанков", justify="right", style=NAVY_PALE)
    table.add_column("средний размер", justify="right", style=NAVY_PALE)
    table.add_column("мин", justify="right", style=NAVY_PALE)
    table.add_column("макс", justify="right", style=NAVY_PALE)
    table.add_column("рваный конец", justify="right", style=NAVY_PALE)
    for strategy, stats in stats_by_strategy.items():
        table.add_row(strategy, str(stats["count"]), str(stats["avg"]),
                      str(stats["min"]), str(stats["max"]), str(stats["broken_end"]))
    return table


def cmd_index():
    documents = corpus.load_documents()
    if not documents:
        cmd_fetch()
        documents = corpus.load_documents()
    stats_by_strategy = {}
    for strategy in chunking.STRATEGIES:
        chunks = chunking.chunk_corpus(documents, strategy)
        stats_by_strategy[strategy] = chunking.stats(chunks)
        with console.status(Text(f"Эмбеддинги {strategy}: 0/{len(chunks)}", style=NAVY_PALE)) as status:
            def report(done, total):
                status.update(Text(f"Эмбеддинги {strategy}: {done}/{total}", style=NAVY_PALE))
            index = VectorIndex.build(strategy, chunks, progress=report)
        path = index.save()
        indexes[strategy] = index
        console.print(Text(f"индекс {strategy}: {len(chunks)} чанков -> {path.name}", style=OK))
    console.print(Panel(_stats_table(stats_by_strategy),
                        title=Text("Сравнение стратегий чанкинга", style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text("fixed: 1600 символов + overlap 200 · structural: по заголовкам",
                                      style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))


def _hits_table(hits, title):
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, title=title,
                  title_style=f"bold {NAVY_BRIGHT}")
    table.add_column("скор", justify="right", style=OK, no_wrap=True)
    table.add_column("документ · секция", style=NAVY_PALE)
    table.add_column("чанк", style=NAVY_DIM, overflow="fold")
    for score, chunk in hits:
        table.add_row(f"{score:.3f}", f"{chunk['title'][:34]}\n{chunk['section'][:34]}",
                      chunk["text"][:110] + "…")
    return table


def cmd_search(query):
    _load_indexes()
    if not indexes:
        console.print(Text("Индексы не построены — /index.", style=WARN))
        return
    with console.status(Text("Ищу в обоих индексах", style=NAVY_PALE)):
        vector = embedder.embed_one(query)
        results = {s: ix.search(vector, 5) for s, ix in sorted(indexes.items())}
    console.print(Columns(
        [Panel(_hits_table(hits, strategy), border_style=NAVY, box=box.ROUNDED)
         for strategy, hits in results.items()],
        equal=True, expand=True,
    ))


def _render_answer(result, title="Ответ (RAG)"):
    style = OK if result["status"] == "ok" else WARN
    console.print(Panel(Text(result["answer"], style=NAVY_PALE),
                        title=Text(title, style=f"bold {NAVY_BRIGHT}"),
                        border_style=style if result["status"] != "ok" else NAVY,
                        box=box.ROUNDED))
    if result["sources"]:
        table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
        table.add_column("источник", style=f"bold {NAVY_BRIGHT}", no_wrap=True)
        table.add_column("секция", style=NAVY_PALE)
        table.add_column("chunk_id", style=NAVY_DIM, no_wrap=True)
        table.add_column("что взято", style=NAVY_PALE)
        for source in result["sources"]:
            table.add_row(source["source"], source["section"][:44], source["chunk_id"],
                          source["reason"][:60])
        console.print(Panel(table, title=Text("Источники", style=f"bold {NAVY_BRIGHT}"),
                            border_style=NAVY, box=box.ROUNDED))
    if result["quotes"]:
        lines = Text()
        for quote in result["quotes"]:
            mark = "дословно" if quote["verified"] else "НЕ НАЙДЕНА В ЧАНКЕ"
            lines.append(f"[{quote.get('chunk_id', '?')}] ", style=NAVY_DIM)
            lines.append(f"«{quote.get('text', '')[:220]}»\n", style=NAVY_PALE)
            lines.append(f"  проверка кодом: {mark}\n", style=OK if quote["verified"] else WARN)
        console.print(Panel(lines, title=Text("Цитаты", style=f"bold {NAVY_BRIGHT}"),
                            subtitle=Text("каждая цитата проверена: подстрока ли она чанка", style=NAVY_PALE),
                            border_style=NAVY, box=box.ROUNDED))


def cmd_ask(question):
    if not _need_index():
        return
    try:
        with console.status(Text("Ищу контекст и спрашиваю LLM", style=NAVY_PALE)):
            result = answer_rag(question, indexes[active_strategy], settings)
        _render_answer(result)
    except Exception as error:
        _error("Ошибка RAG-ответа (проверь PROXYAPI_KEY)", error)


def cmd_raw(question):
    try:
        with console.status(Text("Спрашиваю LLM без RAG", style=NAVY_PALE)):
            answer = answer_no_rag(question)
        console.print(Panel(Text(answer, style=NAVY_PALE),
                            title=Text("Ответ БЕЗ RAG (общие знания модели)", style=f"bold {WARN}"),
                            border_style=WARN, box=box.ROUNDED))
    except Exception as error:
        _error("Ошибка запроса (проверь PROXYAPI_KEY)", error)


def cmd_eval():
    if not _need_index():
        return
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("#", style=NAVY_DIM, justify="right")
    table.add_column("вопрос", style=f"bold {NAVY_BRIGHT}", overflow="fold")
    table.add_column("без RAG", style=NAVY_DIM, overflow="fold")
    table.add_column("с RAG", style=NAVY_PALE, overflow="fold")
    table.add_column("источники", no_wrap=True)
    hits = 0
    for i, item in enumerate(evalset.QUESTIONS, 1):
        with console.status(Text(f"Вопрос {i}/10: {item['question'][:50]}", style=NAVY_PALE)):
            plain = answer_no_rag(item["question"])
            result = answer_rag(item["question"], indexes[active_strategy], settings)
        ok = result["status"] == "ok" and evalset.sources_hit(item["expected_sources"], result["sources"])
        hits += ok
        table.add_row(str(i), f"{item['question']}\nожидание: {item['expectation'][:80]}…",
                      plain[:160] + "…", result["answer"][:160] + "…",
                      Text("совпали", style=OK) if ok else Text("нет", style=WARN))
    console.print(Panel(table, title=Text("10 контрольных вопросов: с RAG vs без RAG",
                                          style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text(f"ожидаемые источники найдены: {hits}/10 · стратегия {active_strategy}"
                                      f" · rerank {'on' if settings['rerank'] else 'off'}", style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))


def cmd_mode(args):
    parts = args.split()
    global active_strategy
    if len(parts) == 2:
        key, value = parts
        if key == "strategy" and value in chunking.STRATEGIES:
            active_strategy = value
        elif key in ("rerank", "rewrite"):
            settings[key] = value == "on"
        elif key == "threshold":
            settings["threshold"] = float(value)
        elif key == "topk":
            settings["top_k"] = int(value)
        elif key == "topn":
            settings["top_n"] = int(value)
        elif key == "rerankmin":
            settings["rerank_min"] = int(value)
        else:
            console.print(Text("Не понял. Ключи: strategy, rerank, rewrite, threshold, topk, topn, rerankmin",
                               style=WARN))
            return
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM, show_edge=False)
    table.add_column("параметр", style=f"bold {NAVY_BRIGHT}")
    table.add_column("значение", style=NAVY_PALE)
    table.add_column("смысл", style=NAVY_DIM)
    rows = [
        ("strategy", active_strategy, "какой индекс используется (fixed | structural)"),
        ("rewrite", "on" if settings["rewrite"] else "off", "переписывать вопрос перед поиском (gpt-4o-mini)"),
        ("topn", str(settings["top_n"]), "сколько чанков берём из векторного поиска"),
        ("threshold", str(settings["threshold"]), "порог косинусного скора: ниже — отсекаем"),
        ("rerank", "on" if settings["rerank"] else "off", "LLM-реранк оставшихся (gpt-4o-mini, 0-10)"),
        ("rerankmin", str(settings["rerank_min"]), "минимальная LLM-оценка, чтобы чанк выжил"),
        ("topk", str(settings["top_k"]), "сколько чанков уходит в промпт"),
    ]
    for row in rows:
        table.add_row(*row)
    console.print(Panel(table, title=Text("Конвейер поиска (день 23)", style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text("rewrite -> поиск topN -> порог -> реранк -> topK", style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))


def cmd_compare23(question):
    if not _need_index():
        return
    index = indexes[active_strategy]
    baseline = {**settings, "rewrite": False, "rerank": False, "threshold": 0.0}
    tuned = {**settings, "rewrite": True, "rerank": True}
    try:
        with console.status(Text("Гоняю оба режима поиска и оба ответа", style=NAVY_PALE)):
            before = retrieve(index, question, baseline)
            after = retrieve(index, question, tuned)
            answer_before = generate_answer(question, before)
            answer_after = generate_answer(question, after)
    except Exception as error:
        _error("Ошибка сравнения (нужен PROXYAPI_KEY для rewrite/rerank)", error)
        return
    if after["query"] != question:
        console.print(Panel(Text(f"{question}\n-> {after['query']}", style=NAVY_PALE),
                            title=Text("Query rewrite", style=f"bold {NAVY_BRIGHT}"),
                            border_style=NAVY, box=box.ROUNDED))
    kept_ids = {chunk["chunk_id"] for _, chunk in after["final"]}
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("скор", justify="right", style=NAVY_PALE, no_wrap=True)
    table.add_column("LLM", justify="right", style=NAVY_PALE, no_wrap=True)
    table.add_column("документ · секция", style=NAVY_PALE)
    table.add_column("судьба", no_wrap=True)
    dropped_threshold_ids = {c["chunk_id"] for _, c in after["dropped_threshold"]}
    dropped_rerank_ids = {c["chunk_id"] for _, c in after["dropped_rerank"]}
    position_by_id = {c["chunk_id"]: p for p, (_, c) in
                      enumerate([(s, c) for s, c in after["raw"] if s >= tuned["threshold"]], 1)}
    shown = before["raw"][:12]
    for score, chunk in shown:
        cid = chunk["chunk_id"]
        llm = after["llm_scores"].get(position_by_id.get(cid, -1), "")
        if cid in kept_ids:
            fate = Text("в промпт", style=OK)
        elif cid in dropped_threshold_ids:
            fate = Text("срезан порогом", style=WARN)
        elif cid in dropped_rerank_ids:
            fate = Text("срезан реранком", style=WARN)
        else:
            fate = Text("за пределами topK", style=NAVY_DIM)
        table.add_row(f"{score:.3f}", str(llm), f"{chunk['title'][:40]} · {chunk['section'][:40]}", fate)
    console.print(Panel(table, title=Text(f"До фильтрации (показаны первые {len(shown)} из {len(before['raw'])}) и что с ними стало",
                                          style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text(f"порог {tuned['threshold']} + реранк gpt-4o-mini >= {tuned['rerank_min']}"
                                      f" -> в промпт ушло {len(after['final'])}", style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))
    _render_answer(answer_before,
                   title=f"Ответ БЕЗ пайплайна (сырой топ-{len(before['final'])}, без порога и реранка)")
    _render_answer(answer_after,
                   title=f"Ответ С пайплайном (порог {tuned['threshold']} + реранк -> {len(after['final'])} чанков)")


def cmd_check():
    if not _need_index():
        return
    table = Table(box=box.SIMPLE_HEAD, border_style=NAVY_DIM)
    table.add_column("#", style=NAVY_DIM, justify="right")
    table.add_column("вопрос", style=f"bold {NAVY_BRIGHT}", overflow="fold")
    table.add_column("источники", no_wrap=True)
    table.add_column("цитаты", no_wrap=True)
    table.add_column("дословны", no_wrap=True)
    table.add_column("смысл совпал (видео)", style=NAVY_DIM, no_wrap=True)
    for i, item in enumerate(evalset.QUESTIONS, 1):
        with console.status(Text(f"Вопрос {i}/10", style=NAVY_PALE)):
            result = answer_rag(item["question"], indexes[active_strategy], settings)
        has_sources = bool(result["sources"])
        has_quotes = bool(result["quotes"])
        verified = has_quotes and all(q["verified"] for q in result["quotes"])
        table.add_row(str(i), item["question"],
                      Text("есть", style=OK) if has_sources else Text("нет", style=WARN),
                      Text("есть", style=OK) if has_quotes else Text("нет", style=WARN),
                      Text("да", style=OK) if verified else Text("нет", style=WARN),
                      "[ ]")
    console.print(Panel(table, title=Text("День 24: источники и цитаты в каждом ответе",
                                          style=f"bold {NAVY_BRIGHT}"),
                        subtitle=Text("«дословны» — цитата найдена подстрокой в чанке (проверка кодом)",
                                      style=NAVY_PALE),
                        border_style=NAVY, box=box.ROUNDED))


def cmd_chat():
    if not _need_index():
        return
    memory = ChatMemory()
    console.print(Panel(Text("Чат с RAG и памятью задачи. Внутри: /state — память, /reset — сброс, "
                             "/exit — выход. История и state переживают перезапуск.", style=NAVY_PALE),
                        title=Text("Мини-чат (день 25)", style=f"bold {NAVY_BRIGHT}"),
                        border_style=NAVY, box=box.ROUNDED))

    def chat_toolbar():
        goal = memory.state["goal"] or "не определена"
        facts = len(memory.state["clarified"]) + len(memory.state["constraints"])
        return HTML(f" <b>чат</b> | цель: {goal[:60]} | фактов в памяти: {facts}"
                    f" | сообщений: {len(memory.history)} ")

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
        if text == "/state":
            console.print(Panel(Text(json.dumps(memory.state, ensure_ascii=False, indent=1),
                                     style=NAVY_PALE),
                                title=Text("Память задачи", style=f"bold {NAVY_BRIGHT}"),
                                border_style=NAVY, box=box.ROUNDED))
            continue
        if text == "/reset":
            memory.reset()
            console.print(Text("память очищена", style=OK))
            continue
        try:
            chat_settings = {**settings, "rewrite": True}
            with console.status(Text("Ищу контекст с учётом диалога", style=NAVY_PALE)):
                result = answer_rag(text, indexes[active_strategy], chat_settings,
                                    history_text=memory.history_text(),
                                    history_messages=memory.recent_messages())
            _render_answer(result)
            memory.add_exchange(text, result["answer"])
            with console.status(Text("Обновляю память задачи", style=NAVY_PALE)):
                memory.update_state(text, result["answer"])
        except Exception as error:
            _error("Ошибка чата", error)


def _day_header(day, title, points):
    lines = Text()
    for point in points:
        lines.append("- ", style=NAVY_DIM)
        lines.append(point + "\n", style=NAVY_PALE)
    console.print(Panel(lines, title=Text(f"День {day} — {title}", style=f"bold {NAVY_BRIGHT}"),
                        border_style=NAVY_BRIGHT, box=box.DOUBLE))


def _show_sample_chunk():
    if active_strategy not in indexes:
        return
    sample = next((c for c in indexes[active_strategy].chunks if "травм" in c["section"].lower()),
                  indexes[active_strategy].chunks[0])
    meta = {k: sample[k] for k in ("chunk_id", "strategy", "source", "title", "section", "n_chars")}
    body = Text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n\n", style=NAVY_PALE)
    body.append(sample["text"][:260] + "…", style=NAVY_DIM)
    console.print(Panel(body, title=Text("Чанк с метаданными (как хранится в индексе)",
                                         style=f"bold {NAVY_BRIGHT}"),
                        border_style=NAVY, box=box.ROUNDED))


def demo21():
    _day_header(21, "Индексация документов", [
        "корпус: база хакатона C:\\Alaba — markdown + txt + PDF (pypdf)",
        "эмбеддинги локальные: Ollama bge-m3, данные заказчика не покидают машину",
        "две стратегии чанкинга: fixed (1600+overlap 200) vs structural (по заголовкам)",
        "индекс: JSON + numpy, метаданные у каждого чанка",
    ])
    cmd_fetch()
    documents = corpus.load_documents()
    stats_by_strategy = {s: chunking.stats(chunking.chunk_corpus(documents, s))
                         for s in chunking.STRATEGIES}
    console.print(Panel(_stats_table(stats_by_strategy),
                        title=Text("Две стратегии чанкинга на одном корпусе", style=f"bold {NAVY_BRIGHT}"),
                        border_style=NAVY, box=box.ROUNDED))
    _load_indexes()
    _show_sample_chunk()
    if indexes:
        console.print(Text("пример поиска: /search как работает травма карты", style=NAVY_DIM))
        cmd_search("как работает травма карты")


def demo22():
    _day_header(22, "Первый RAG-запрос", [
        "вопрос -> векторный поиск -> чанки в промпт -> gpt-4.1",
        "сравнение: тот же вопрос без RAG (общие знания) и с RAG (факты проекта)",
        "10 контрольных вопросов с автопроверкой источников — /eval",
    ])
    question = "Какой размер колоды и лимиты по редкости карт?"
    console.print(Text(f"вопрос: {question}", style=f"bold {NAVY_BRIGHT}"))
    cmd_raw(question)
    cmd_ask(question)
    console.print(Text("полный прогон 10 вопросов: /eval", style=NAVY_DIM))


def demo23():
    _day_header(23, "Реранкинг и фильтрация", [
        "конвейер: rewrite -> поиск topN=20 -> порог косинуса -> LLM-реранк 0-10 -> topK=5",
        "векторная близость не равна релевантности — реранк отсеивает похожее-но-не-то",
        "все ручки крутятся через /mode; ниже — судьба каждого чанка",
    ])
    cmd_mode("")
    cmd_compare23("какие режимы игры будут в MVP")


def demo24():
    _day_header(24, "Цитаты, источники, анти-галлюцинации", [
        "каждый ответ: Ответ + Источники (source/section/chunk_id) + Цитаты",
        "цитаты проверяет КОД — подстрока чанка, пометка «дословно»",
        "слабый контекст -> «не знаю» ДО вызова LLM (детерминированный гейт)",
        "чек 10 вопросов — /check",
    ])
    cmd_ask("Как работает механика травмы и смерти карты?")
    question = "Какая столица Австралии?"
    console.print(Text(f"вопрос мимо базы: {question}", style=f"bold {NAVY_BRIGHT}"))
    if not _need_index():
        return
    result = answer_rag(question, indexes[active_strategy], settings)
    _render_answer(result, title="Ответ" if result["status"] == "ok" else "Режим «не знаю» (код-гейт, LLM не вызывалась)")


def demo25():
    _day_header(25, "Мини-чат с RAG + память задачи", [
        "история диалога (окно 8) + rewrite коротких вопросов по контексту («а лечение?»)",
        "память задачи {goal, clarified, constraints, glossary} — экстрактор gpt-4o-mini",
        "источники в каждом ответе; /state — память; переживает перезапуск",
        "сценарий: спроси про правила, уточняй, зафиксируй ограничение, проверь /state",
    ])
    cmd_chat()


def dispatch(text):
    if " " in text:
        name, args = text.split(" ", 1)
    else:
        name, args = text, ""
    args = args.strip()
    if name == "/fetch":
        cmd_fetch()
    elif name == "/index":
        cmd_index()
    elif name == "/search":
        cmd_search(args) if args else console.print(Text("нужен запрос: /search <вопрос>", style=WARN))
    elif name == "/ask":
        cmd_ask(args) if args else console.print(Text("нужен вопрос: /ask <вопрос>", style=WARN))
    elif name == "/raw":
        cmd_raw(args) if args else console.print(Text("нужен вопрос: /raw <вопрос>", style=WARN))
    elif name == "/eval":
        cmd_eval()
    elif name == "/mode":
        cmd_mode(args)
    elif name == "/compare23":
        cmd_compare23(args) if args else console.print(Text("нужен вопрос: /compare23 <вопрос>", style=WARN))
    elif name == "/check":
        cmd_check()
    elif name == "/chat":
        cmd_chat()
    elif name == "/demo21":
        demo21()
    elif name == "/demo22":
        demo22()
    elif name == "/demo23":
        demo23()
    elif name == "/demo24":
        demo24()
    elif name == "/demo25":
        demo25()
    elif name == "/help":
        show_help()
    else:
        console.print(Text("Неизвестная команда, /help.", style=WARN))


def main():
    banner()
    _load_indexes()
    show_help()
    session = PromptSession(completer=CommandCompleter(), style=MENU_STYLE,
                            bottom_toolbar=_bottom_toolbar)
    while True:
        try:
            text = session.prompt(HTML('<prompt>agent21 &gt; </prompt>')).strip()
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
