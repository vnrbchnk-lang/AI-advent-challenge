import json
import time

from devassist import config

SEED = config.DATA / "tickets.json"
LIVE = config.STORE / "tickets.json"


class TicketError(RuntimeError):
    pass


def _load():
    config.STORE.mkdir(parents=True, exist_ok=True)
    if not LIVE.is_file():
        LIVE.write_text(SEED.read_text(encoding="utf-8"), encoding="utf-8")
    return json.loads(LIVE.read_text(encoding="utf-8"))


def _save(data):
    LIVE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def reset():
    if LIVE.is_file():
        LIVE.unlink()
    return {"reset": True}


def list_tickets(status="", tag=""):
    data = _load()
    tickets = data["tickets"]
    if status:
        tickets = [item for item in tickets if item["status"] == status]
    if tag:
        tickets = [item for item in tickets if tag in item["tags"]]
    short = [
        {"id": item["id"], "user_id": item["user_id"], "status": item["status"],
         "subject": item["subject"], "created": item["created"], "tags": item["tags"]}
        for item in tickets
    ]
    return {"count": len(short), "tickets": short}


def get_ticket(ticket_id=""):
    data = _load()
    for ticket in data["tickets"]:
        if ticket["id"].lower() == ticket_id.strip().lower():
            user = next((item for item in data["users"] if item["id"] == ticket["user_id"]), None)
            return {"ticket": ticket, "user": user}
    raise TicketError(f"тикет {ticket_id} не найден")


def find_user(query=""):
    data = _load()
    needle = query.strip().lower()
    found = [
        user for user in data["users"]
        if needle in user["id"].lower() or needle in user["name"].lower() or needle in user["email"].lower()
    ]
    for user in found:
        user["tickets"] = [item["id"] for item in data["tickets"] if item["user_id"] == user["id"]]
    return {"count": len(found), "users": found}


def add_note(ticket_id="", text=""):
    data = _load()
    for ticket in data["tickets"]:
        if ticket["id"].lower() == ticket_id.strip().lower():
            ticket.setdefault("notes", []).append({
                "at": time.strftime("%Y-%m-%d %H:%M"),
                "author": "ai-support",
                "text": text,
            })
            _save(data)
            return {"ticket_id": ticket["id"], "notes": len(ticket["notes"])}
    raise TicketError(f"тикет {ticket_id} не найден")
