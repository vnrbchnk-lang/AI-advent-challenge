import json
from pathlib import Path

STORE_DIR = Path(__file__).parent / "store"
STATE_PATH = STORE_DIR / "state.json"

STAGES = ["planning", "execution", "validation", "done"]

TRANSITIONS = {
    "planning": ["execution"],
    "execution": ["validation", "planning"],
    "validation": ["done", "execution"],
    "done": [],
}

EXPECTED = {
    "planning": "составить план и утвердить его (/approve-plan → execution)",
    "execution": "выполнять утверждённый план; не перескакивать в done",
    "validation": "проверить результат на инварианты",
    "done": "задача завершена",
}

EMPTY = {"task": None, "stage": "planning", "step": 0, "plan": None, "results": []}


class TaskState:
    def __init__(self, ephemeral=False):
        self.ephemeral = ephemeral
        if ephemeral:
            self.data = dict(EMPTY)
            return
        STORE_DIR.mkdir(exist_ok=True)
        self.data = self._load()

    def _load(self):
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return dict(EMPTY)

    def _save(self):
        if self.ephemeral:
            return
        STATE_PATH.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def active(self):
        return self.data["task"] is not None

    @property
    def stage(self):
        return self.data["stage"]

    def allowed(self):
        return TRANSITIONS[self.data["stage"]]

    def start(self, name):
        self.data = dict(EMPTY)
        self.data["task"] = name
        self.data["results"] = []
        self._save()

    def set_plan(self, text):
        self.data["plan"] = text
        self._save()

    def add_result(self, text):
        self.data["results"].append(text)
        self._save()

    def transition(self, target):
        current = self.data["stage"]
        if target not in STAGES:
            return False, f"нет такой стадии: {target}. Доступны: {', '.join(STAGES)}"
        if target not in TRANSITIONS[current]:
            allowed = ", ".join(TRANSITIONS[current]) or "—"
            return False, f"переход {current} → {target} запрещён. Из {current} можно только в: {allowed}"
        if target == "execution" and not self.data["plan"]:
            return False, "нельзя в execution без утверждённого плана (сначала /plan <текст>)"
        self.data["stage"] = target
        self.data["step"] += 1
        self._save()
        return True, f"стадия: {current} → {target}"

    def reset(self):
        self.data = dict(EMPTY)
        self._save()

    def as_prompt(self):
        if not self.active:
            return ""
        return ("Состояние задачи (task state machine) — работай строго в рамках текущей стадии, "
                "не перескакивай этапы:\n"
                f"- задача: {self.data['task']}\n"
                f"- стадия: {self.data['stage']} (шаг {self.data['step']})\n"
                f"- ожидаемое действие: {EXPECTED[self.data['stage']]}\n"
                f"- утверждённый план: {self.data['plan'] or '—'}")
