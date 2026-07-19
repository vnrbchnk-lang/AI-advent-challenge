from devassist import qa

SUPPORT_SYSTEM = (
    "Ты — первая линия поддержки пользователей мобильной игры. Отвечаешь пользователю на русском, "
    "коротко и по-человечески, без канцелярита. Опираешься ТОЛЬКО на фрагменты базы поддержки (FAQ и "
    "описание продукта) и на данные тикета: переписку, серверные логи, устройство и версию приложения. "
    "Обязательно учитывай контекст тикета: если логи объясняют причину — назови её; если версия "
    "приложения устарела — скажи про обновление. Ничего не выдумывай: нет данных — честно скажи и "
    "передай инженерам. "
    'Формат ответа — строго JSON: {"answer": "текст ответа пользователю", "sources": [номера фрагментов], '
    '"quotes": [{"source": номер, "quote": "дословная подстрока фрагмента"}], '
    '"confidence": "high|medium|low"}. '
    "Цитата — непрерывная дословная подстрока фрагмента, до 200 символов, без многоточий."
)


def _ticket_block(payload):
    ticket = payload["ticket"]
    user = payload.get("user") or {}
    lines = [
        f"Тикет {ticket['id']} ({ticket['status']}, создан {ticket['created']}): {ticket['subject']}",
        f"Теги: {', '.join(ticket['tags']) or 'нет'}",
        "",
        "Пользователь:",
        f"  {user.get('name', '?')} ({user.get('id', '?')}, {user.get('email', '?')})",
        f"  устройство: {user.get('device', '?')}, версия приложения: {user.get('app_version', '?')}",
        f"  баланс: {user.get('balance', '?')} монет, карт: {user.get('cards', '?')}, колод: {user.get('decks', '?')}",
        "",
        "Переписка:",
    ]
    for message in ticket["messages"]:
        lines.append(f"  [{message['at']}] {message['from']}: {message['text']}")
    lines.append("")
    lines.append("Серверные логи по инциденту:")
    if ticket["logs"]:
        lines.extend(f"  {line}" for line in ticket["logs"])
    else:
        lines.append("  логов нет")
    for note in ticket.get("notes", []):
        lines.append(f"Заметка [{note['at']}] {note['author']}: {note['text']}")
    return "\n".join(lines)


def _query_from_ticket(ticket, question):
    if question:
        return question
    user_messages = [item["text"] for item in ticket["messages"] if item["from"] == "user"]
    return f"{ticket['subject']}. {user_messages[-1] if user_messages else ''}"


def answer_ticket(assistant, ticket_id, question=""):
    payload = assistant.executor.call("tickets__get_ticket", {"ticket_id": ticket_id})
    ticket = payload["ticket"]
    result = qa.answer(
        assistant,
        _query_from_ticket(ticket, question),
        project="support",
        settings={"top_k": 6},
        system=SUPPORT_SYSTEM,
        extra_block=_ticket_block(payload),
    )
    result["ticket"] = payload
    result["escalate"] = result["refused"] or result["confidence"] == "low"
    return result


def answer_general(assistant, question):
    result = qa.answer(
        assistant, question, project="support", settings={"top_k": 6},
        system=SUPPORT_SYSTEM,
        extra_block="Тикет не указан: отвечаем на общий вопрос о продукте.",
    )
    result["ticket"] = None
    result["escalate"] = result["refused"] or result["confidence"] == "low"
    return result


def note_text(result):
    ticket = result["ticket"]["ticket"]["id"] if result["ticket"] else "общий вопрос"
    head = f"ИИ-поддержка ответила по тикету {ticket}, уверенность {result['confidence']}."
    if result["escalate"]:
        head = f"ИИ-поддержка не смогла ответить по тикету {ticket}, нужна инженерная проверка."
    return f"{head} Ответ: {result['answer'][:600]}"
