import json
from pathlib import Path

STORE_DIR = Path(__file__).parent / "store"
PROFILE_PATH = STORE_DIR / "profile.json"

FIELDS = {
    "стиль": "формальный / дружеский / краткий — тон ответа",
    "формат": "списки / проза / код-first — как оформлять",
    "уровень": "junior / middle / senior — глубина объяснений",
    "роль": "кто пользователь и зачем ему агент",
}


class Profile:
    def __init__(self):
        STORE_DIR.mkdir(exist_ok=True)
        self.data = self._load()

    def _load(self):
        if PROFILE_PATH.exists():
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        return {}

    def _save(self):
        PROFILE_PATH.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def set(self, key, value):
        self.data[key] = value
        self._save()

    def unset(self, key):
        existed = key in self.data
        self.data.pop(key, None)
        self._save()
        return existed

    def clear(self):
        self.data = {}
        self._save()

    def as_prompt(self):
        if not self.data:
            return ""
        lines = "\n".join(f"- {k}: {v}" for k, v in self.data.items())
        return ("Профиль пользователя (персонализация) — подстраивай стиль, формат и "
                "глубину ответа под него, даже если в самом вопросе об этом не просят:\n" + lines)
