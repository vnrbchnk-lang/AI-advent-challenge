import argparse
import json
import os
import sys

from devassist import config, retrieval, subagents
from devassist.assistant import DevAssistant
from devassist.llm import chat_json

SEVERITY_ORDER = {"критично": 0, "важно": 1, "мелочь": 2}

COMMON_RULES = (
    "Ты ревьюишь pull request. Тебе дан diff и фрагменты документации и кода этого же проекта, "
    "найденные семантическим поиском. Опирайся на них: правила проекта важнее общих практик. "
    "Не выдумывай строки и файлы, которых нет в diff. Пустой результат — нормальный ответ. "
    'Верни строго JSON: {"findings": [{"severity": "критично|важно|мелочь", "file": "путь", '
    '"line": "строка или диапазон из diff", "title": "суть в одной строке", '
    '"detail": "почему это проблема", "fix": "что сделать", "source": "на какой фрагмент опираешься"}]}'
)

DIMENSIONS = [
    {
        "key": "bugs",
        "title": "Потенциальные баги",
        "system": COMMON_RULES + " Твоя специализация — ошибки: краши, None и пустые значения, "
                                 "неверные условия и границы, off-by-one, опасные значения по умолчанию, "
                                 "необработанные исключения, утечки ресурсов, гонки. "
                                 "Отдельно проверь работу с внешними API: существуют ли указанные имена "
                                 "моделей, верны ли адреса эндпоинтов и параметры запроса — сверяй с тем, "
                                 "как это же API вызывается в других файлах проекта во фрагментах.",
        "query": "вызов внешнего API, имена моделей и эндпоинты, обработка ошибок, граничные случаи",
    },
    {
        "key": "architecture",
        "title": "Архитектурные проблемы",
        "system": COMMON_RULES + " Твоя специализация — архитектура: нарушение слоёв и границ модулей, "
                                 "дублирование существующего кода, неудачные абстракции, связанность, "
                                 "несоответствие принятой в проекте структуре.",
        "query": "архитектура проекта, структура модулей, принципы разработки",
    },
    {
        "key": "conventions",
        "title": "Конвенции и правила проекта",
        "system": COMMON_RULES + " Твоя специализация — писаные правила этого репозитория. "
                                 "Действуй так: выпиши для себя КАЖДОЕ правило, которое видишь во фрагментах "
                                 "(нумерованные ограничения, конвенции, запреты), и проверь diff на нарушение "
                                 "каждого из них по очереди. Нарушено — обязательно замечание, в поле source "
                                 "процитируй само правило. Общие практики, которых нет во фрагментах, не "
                                 "выдумывай.",
        "query": "ограничения для агента, правила и конвенции разработки, требования к коду и оформлению",
    },
]


def _context_for(assistant, project, diff_payload, dimension_query, per_file=3):
    chunks = {}
    queries = [dimension_query] + diff_payload["files"][:8]
    for query in queries:
        try:
            result = retrieval.retrieve(assistant.index(project), query, {"top_k": per_file})
        except Exception:
            continue
        for score, chunk in result["final"]:
            chunks.setdefault(retrieval.label(chunk), (score, chunk))
    ordered = sorted(chunks.values(), key=lambda item: item[0], reverse=True)[:10]
    return retrieval.format_context(ordered), [retrieval.label(chunk) for _, chunk in ordered]


def _run_dimension(assistant, project, diff_payload, dimension):
    context, sources = _context_for(assistant, project, diff_payload, dimension["query"])
    user_block = (
        f"Проект: {config.PROJECTS[project]['title']}\n"
        f"Диапазон: {diff_payload['range']}\n"
        f"Изменённые файлы: {', '.join(diff_payload['files']) or 'нет'}\n\n"
        f"Фрагменты документации и кода проекта:\n{context}\n\n"
        f"Diff:\n{diff_payload['diff']}"
    )
    payload = chat_json(
        [
            {"role": "system", "content": dimension["system"]},
            {"role": "user", "content": user_block},
        ],
        model=config.MAIN_MODEL,
        temperature=0.1,
        label=f"review:{dimension['key']}",
    )
    findings = []
    for item in payload.get("findings", []):
        item["dimension"] = dimension["title"]
        findings.append(item)
    return {"dimension": dimension, "findings": findings, "sources": sources}


def review(assistant, project="advent", base="", head="", dimensions=None):
    diff_payload = assistant.executor.call(
        "project__git_diff", {"project": project, "base": base, "head": head})
    if not diff_payload["diff"].strip():
        return {"project": project, "diff": diff_payload, "findings": [], "parts": [],
                "empty": True}

    chosen = dimensions or DIMENSIONS
    outcomes = subagents.fan_out(
        chosen, lambda dimension: _run_dimension(assistant, project, diff_payload, dimension))

    findings, parts = [], []
    for outcome in outcomes:
        if outcome["ok"]:
            parts.append(outcome["result"])
            findings.extend(outcome["result"]["findings"])
        else:
            parts.append({"dimension": outcome["job"], "findings": [], "error": outcome["error"],
                          "sources": []})
    findings.sort(key=lambda item: SEVERITY_ORDER.get(item.get("severity", "мелочь"), 3))
    return {"project": project, "diff": diff_payload, "findings": findings, "parts": parts,
            "empty": False}


def to_markdown(result):
    diff_payload = result["diff"]
    lines = ["## AI-ревью изменений", ""]
    lines.append(f"Проект: `{result['project']}` · диапазон: `{diff_payload['range']}` · "
                 f"файлов изменено: {len(diff_payload['files'])}")
    lines.append("")
    if result["empty"]:
        lines.append("Изменений не найдено — ревьюить нечего.")
        return "\n".join(lines)
    if not result["findings"]:
        lines.append("Замечаний нет: три субагента (баги, архитектура, конвенции) не нашли проблем.")
    for part in result["parts"]:
        title = part["dimension"]["title"] if isinstance(part["dimension"], dict) else str(part["dimension"])
        lines.append(f"### {title}")
        if part.get("error"):
            lines.append(f"Субагент не отработал: {part['error']}")
            lines.append("")
            continue
        items = part["findings"]
        if not items:
            lines.append("Замечаний нет.")
        for item in items:
            lines.append(f"- **{item.get('severity', 'мелочь')}** · `{item.get('file', '?')}`"
                         f"{(':' + str(item['line'])) if item.get('line') else ''} — {item.get('title', '')}")
            if item.get("detail"):
                lines.append(f"  - Почему: {item['detail']}")
            if item.get("fix"):
                lines.append(f"  - Что сделать: {item['fix']}")
            if item.get("source"):
                lines.append(f"  - Основание: {item['source']}")
        lines.append("")
    used = sorted({source for part in result["parts"] for source in part.get("sources", [])})
    if used:
        lines.append("<details><summary>Контекст из RAG</summary>")
        lines.append("")
        for source in used:
            lines.append(f"- `{source}`")
        lines.append("")
        lines.append("</details>")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="AI-ревью diff с использованием RAG и MCP")
    parser.add_argument("--project", default="advent")
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="")
    parser.add_argument("--out", default="")
    arguments = parser.parse_args()

    assistant = DevAssistant(servers=["project"])
    statuses = assistant.start()
    if not any(status["connected"] for status in statuses):
        print("MCP-сервер проекта не поднялся: " + json.dumps(statuses, ensure_ascii=False),
              file=sys.stderr)
        return 1
    if not assistant.has_index(arguments.project):
        from devassist import index as index_module
        index_module.build_project(arguments.project)

    result = review(assistant, arguments.project, arguments.base, arguments.head)
    text = to_markdown(result)
    assistant.stop()

    if arguments.out:
        with open(arguments.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
