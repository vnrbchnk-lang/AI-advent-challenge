import json
from pathlib import Path

STORE_DIR = Path(__file__).parent / "store"
SHORT_TERM_PATH = STORE_DIR / "short_term.json"
WORKING_PATH = STORE_DIR / "working.json"
LONG_TERM_PATH = STORE_DIR / "long_term.json"

WINDOW_N = 8

LAYER_TITLES = {
    "short_term": "Краткосрочная (текущий диалог)",
    "working": "Рабочая (данные текущей задачи)",
    "long_term": "Долговременная (профиль, решения, знания)",
}


class MemoryLayers:
    def __init__(self):
        STORE_DIR.mkdir(exist_ok=True)
        self.short_term = self._load(SHORT_TERM_PATH, [])
        self.working = self._load(WORKING_PATH, {})
        self.long_term = self._load(LONG_TERM_PATH, {})

    def _load(self, path, default):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return default

    def _save(self, path, data):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_all(self):
        self._save(SHORT_TERM_PATH, self.short_term)
        self._save(WORKING_PATH, self.working)
        self._save(LONG_TERM_PATH, self.long_term)

    def add_dialog(self, role, content):
        self.short_term.append({"role": role, "content": content})
        self._save(SHORT_TERM_PATH, self.short_term)

    def remember(self, key, value):
        self.long_term[key] = value
        self._save(LONG_TERM_PATH, self.long_term)

    def set_task(self, key, value):
        self.working[key] = value
        self._save(WORKING_PATH, self.working)

    def forget(self, key):
        existed = key in self.long_term
        self.long_term.pop(key, None)
        self._save(LONG_TERM_PATH, self.long_term)
        return existed

    def clear_working(self):
        self.working = {}
        self._save(WORKING_PATH, self.working)

    def clear_dialog(self):
        self.short_term = []
        self._save(SHORT_TERM_PATH, self.short_term)

    def reset(self):
        self.short_term = []
        self.working = {}
        self.long_term = {}
        self.save_all()

    def next_note_key(self):
        return f"факт_{len(self.long_term) + 1}"


def build_messages(memory, system, use_long_term=True, use_working=True, window_n=WINDOW_N):
    messages = [{"role": "system", "content": system}]
    if use_long_term and memory.long_term:
        messages.append({
            "role": "system",
            "content": "Долговременная память (профиль, решения, знания) — "
                       "учитывай как постоянные факты о пользователе и проекте: "
                       + json.dumps(memory.long_term, ensure_ascii=False),
        })
    if use_working and memory.working:
        messages.append({
            "role": "system",
            "content": "Рабочая память (данные текущей задачи) — "
                       "это контекст того, что делаем прямо сейчас: "
                       + json.dumps(memory.working, ensure_ascii=False),
        })
    messages += memory.short_term[-window_n:]
    return messages
