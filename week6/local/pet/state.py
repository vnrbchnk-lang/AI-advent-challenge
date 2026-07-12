import json
import threading
import time
from pathlib import Path

STORE = Path(__file__).parent / "store"
PET_FILE = STORE / "pet.json"

FULLNESS_DECAY_PER_MIN = 0.9
ENERGY_REGEN_PER_MIN = 0.6
FEED_GAIN = 9.0
TALK_ENERGY_COST = 3.0
STUFFED_LEVEL = 96.0

DEFAULT = {
    "name": "Пиксель",
    "born": None,
    "fullness": 65.0,
    "energy": 80.0,
    "feeds": 0,
    "last_tick": None,
}

_lock = threading.Lock()


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def _load():
    if PET_FILE.exists():
        data = json.loads(PET_FILE.read_text(encoding="utf-8"))
        merged = dict(DEFAULT)
        merged.update(data)
        return merged
    born = time.time()
    fresh = dict(DEFAULT)
    fresh["born"] = born
    fresh["last_tick"] = born
    return fresh


def _save(pet):
    STORE.mkdir(parents=True, exist_ok=True)
    PET_FILE.write_text(json.dumps(pet, ensure_ascii=False, indent=2), encoding="utf-8")


def _tick(pet, now):
    last = pet.get("last_tick") or now
    minutes = max(0.0, (now - last) / 60.0)
    pet["fullness"] = _clamp(pet["fullness"] - FULLNESS_DECAY_PER_MIN * minutes)
    pet["energy"] = _clamp(pet["energy"] + ENERGY_REGEN_PER_MIN * minutes)
    pet["last_tick"] = now
    return pet


def mood(pet):
    if pet["fullness"] < 18:
        return "голодный"
    if pet["energy"] < 18:
        return "сонный"
    if pet["fullness"] > STUFFED_LEVEL:
        return "объелся"
    if pet["fullness"] > 55 and pet["energy"] > 45:
        return "довольный"
    return "спокойный"


def age_hours(pet):
    born = pet.get("born") or time.time()
    return round((time.time() - born) / 3600.0, 1)


def snapshot():
    with _lock:
        pet = _tick(_load(), time.time())
        return {
            "name": pet["name"],
            "fullness": round(pet["fullness"]),
            "energy": round(pet["energy"]),
            "feeds": pet["feeds"],
            "mood": mood(pet),
            "age_hours": age_hours(pet),
        }


def feed_and_talk():
    with _lock:
        pet = _tick(_load(), time.time())
        stuffed = pet["fullness"] > STUFFED_LEVEL
        if not stuffed:
            pet["fullness"] = _clamp(pet["fullness"] + FEED_GAIN)
        pet["energy"] = _clamp(pet["energy"] - TALK_ENERGY_COST)
        pet["feeds"] += 1
        _save(pet)
        return {
            "name": pet["name"],
            "fullness": round(pet["fullness"]),
            "energy": round(pet["energy"]),
            "feeds": pet["feeds"],
            "mood": mood(pet),
            "age_hours": age_hours(pet),
            "stuffed": stuffed,
        }
