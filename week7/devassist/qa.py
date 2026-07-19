import re

from devassist import config, retrieval
from devassist.llm import chat_json

ANSWER_SYSTEM = (
    "Ты ассистент разработчика конкретного проекта. Отвечаешь ТОЛЬКО по предоставленным фрагментам "
    "документации, схем и кода и по данным git. Ничего не додумываешь: если фрагментов не хватает — "
    "пишешь, что данных в базе нет, и предлагаешь, где посмотреть. "
    "Отвечай на русском, по делу, без воды. "
    'Формат ответа — строго JSON: {"answer": "...", "sources": [номера фрагментов], '
    '"quotes": [{"source": номер, "quote": "дословная подстрока фрагмента"}], '
    '"confidence": "high|medium|low"}. '
    "Цитат — от одной до трёх. Цитата обязана быть НЕПРЕРЫВНОЙ дословной подстрокой указанного "
    "фрагмента: копируй символ в символ, одной строкой, без многоточий, без склейки разных мест, "
    "без переформулировок. Не можешь скопировать дословно — не приводи цитату."
)

NO_CONTEXT = "В проиндексированной базе проекта нет данных под этот вопрос."


def _normalize(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def validate_quotes(payload, hits):
    checked = []
    for item in payload.get("quotes", []):
        try:
            position = int(item.get("source", 0))
        except (TypeError, ValueError):
            continue
        if not 1 <= position <= len(hits):
            checked.append({**item, "valid": False, "reason": "нет такого фрагмента"})
            continue
        chunk = hits[position - 1][1]
        valid = _normalize(item.get("quote", "")) in _normalize(chunk["text"])
        checked.append({
            "source": position,
            "quote": item.get("quote", ""),
            "label": retrieval.label(chunk),
            "valid": valid,
            "reason": "" if valid else "цитаты нет в тексте фрагмента",
        })
    return checked


def git_context(executor, project):
    try:
        branch = executor.call("project__git_branch", {"project": project})
        status = executor.call("project__git_status", {"project": project})
    except Exception as error:
        return {"available": False, "error": f"{type(error).__name__}: {error}"}
    return {
        "available": True,
        "branch": branch["branch"],
        "head": branch["head"],
        "last_commit": branch["last_commit"],
        "dirty": branch["dirty"],
        "changed_files": [item["path"] for item in status["files"][:15]],
    }


def _git_block(context):
    if not context.get("available"):
        return "Данные git недоступны."
    lines = [
        f"Текущая ветка: {context['branch']} (HEAD {context['head']})",
        f"Последний коммит: {context['last_commit']}",
        f"Незакоммиченные правки: {'есть' if context['dirty'] else 'нет'}",
    ]
    if context["changed_files"]:
        lines.append("Изменённые файлы: " + ", ".join(context["changed_files"]))
    return "\n".join(lines)


def answer(assistant, question, project="alaba", settings=None, system=ANSWER_SYSTEM, extra_block=""):
    index = assistant.index(project)
    result = retrieval.retrieve(index, question, settings)
    hits = result["final"]
    context = git_context(assistant.executor, project) if project in ("alaba", "advent") else {"available": False}

    if not hits:
        return {
            "question": question,
            "project": project,
            "retrieval": result,
            "git": context,
            "answer": NO_CONTEXT,
            "sources": [],
            "quotes": [],
            "confidence": "low",
            "refused": True,
        }

    blocks = [_git_block(context)]
    if extra_block:
        blocks.append(extra_block)
    blocks.append("Фрагменты базы знаний:\n" + retrieval.format_context(hits))
    blocks.append(f"Вопрос: {question}")

    payload = chat_json(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(blocks)},
        ],
        model=config.MAIN_MODEL,
        temperature=0.2,
        label="help",
    )
    return {
        "question": question,
        "project": project,
        "retrieval": result,
        "git": context,
        "answer": payload.get("answer", "").strip(),
        "sources": payload.get("sources", []),
        "quotes": validate_quotes(payload, hits),
        "confidence": payload.get("confidence", "medium"),
        "refused": False,
    }
