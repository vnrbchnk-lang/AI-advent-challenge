import time

from devassist import config
from devassist.llm import chat_json

STATUS_SYSTEM = (
    "Ты готовишь еженедельный статус для заказчика проекта. Заказчик не программист: пишешь по-русски, "
    "деловым, но человеческим языком, без жаргона и без списка коммитов дословно. Опираешься ТОЛЬКО на "
    "предоставленные данные: коммиты за период, файл текущих задач и записи созвонов. Ничего не "
    "додумываешь и не обещаешь сроков, которых нет в данных. "
    'Формат — строго JSON: {"headline": "одно предложение о главном за неделю", '
    '"done": ["что сделано, по-человечески"], "in_progress": ["что в работе"], '
    '"risks": ["риски и блокеры"], "questions": ["вопросы к заказчику"], '
    '"next": ["план на следующую неделю"]}. '
    "В каждом списке 2-5 пунктов, пункт — одна строка."
)


def gather(assistant, project="alaba", days=7, transcripts=2):
    executor = assistant.executor
    log = executor.call("project__git_log", {"project": project, "days": days, "limit": 60})
    sources = {"commits": log["count"]}

    tasks_text = ""
    tasks = executor.safe_call("project__read_file", {
        "project": project, "path": ".memory-bank/tasks/current-tasks.md", "start": 1, "end": 220})
    if tasks["ok"]:
        tasks_text = tasks["result"]["content"]
        sources["tasks_file"] = ".memory-bank/tasks/current-tasks.md"

    notes = []
    listed = executor.safe_call("project__list_files", {
        "project": project, "pattern": ".memory-bank/transcripts/*.md", "limit": 50})
    if listed["ok"]:
        recent = sorted(item["path"] for item in listed["result"]["files"])[-transcripts:]
        for path in recent:
            piece = executor.safe_call("project__read_file", {
                "project": project, "path": path, "start": 1, "end": 120})
            if piece["ok"]:
                notes.append({"path": path, "content": piece["result"]["content"]})
        sources["transcripts"] = [item["path"] for item in notes]

    return {"log": log, "tasks": tasks_text, "notes": notes, "sources": sources, "days": days}


def draft(assistant, project="alaba", days=7):
    data = gather(assistant, project, days)
    commits = "\n".join(
        f"- {item['date']} {item['hash']} {item['subject']}" for item in data["log"]["commits"]
    ) or "коммитов за период нет"
    notes = "\n\n".join(f"Созвон {item['path']}:\n{item['content'][:4000]}" for item in data["notes"])
    user_block = (
        f"Проект: {config.PROJECTS[project]['title']}\n"
        f"Период: последние {days} дней\n\n"
        f"Коммиты за период ({data['log']['count']} шт.):\n{commits}\n\n"
        f"Файл текущих задач:\n{data['tasks'][:6000] or 'недоступен'}\n\n"
        f"Записи созвонов:\n{notes[:6000] or 'нет'}"
    )
    payload = chat_json(
        [{"role": "system", "content": STATUS_SYSTEM}, {"role": "user", "content": user_block}],
        model=config.MAIN_MODEL,
        temperature=0.3,
        label="status",
    )
    payload["sources"] = data["sources"]
    payload["days"] = days
    payload["project"] = project
    payload["generated_at"] = time.strftime("%Y-%m-%d %H:%M")
    return payload


def to_markdown(payload):
    lines = [
        f"# Статус проекта за {payload['days']} дней",
        "",
        f"Дата: {payload['generated_at']}",
        "",
        payload.get("headline", ""),
        "",
    ]
    blocks = [
        ("Сделано", "done"),
        ("В работе", "in_progress"),
        ("Риски и блокеры", "risks"),
        ("Вопросы к заказчику", "questions"),
        ("План на следующую неделю", "next"),
    ]
    for title, key in blocks:
        items = payload.get(key) or []
        if not items:
            continue
        lines.append(f"## {title}")
        lines.extend(f"- {item}" for item in items)
        lines.append("")
    sources = payload.get("sources", {})
    lines.append("---")
    lines.append(
        f"Черновик собран автоматически из данных проекта: коммитов {sources.get('commits', 0)}, "
        f"файл задач {sources.get('tasks_file', 'нет')}, созвоны: "
        f"{', '.join(sources.get('transcripts', [])) or 'нет'}. Перед отправкой проверяет человек."
    )
    return "\n".join(lines)


def save(payload, text):
    config.OUT.mkdir(parents=True, exist_ok=True)
    path = config.OUT / f"status-{time.strftime('%Y-%m-%d')}.md"
    path.write_text(text, encoding="utf-8")
    return path
