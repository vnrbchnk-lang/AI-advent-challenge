import json
import time
from statistics import median

from devassist import config

LOG = config.STORE / "metrics.jsonl"


def cost_rub(model, prompt_tokens, completion_tokens):
    price_in, price_out = config.PRICE_RUB_PER_MTOK.get(model, (0.0, 0.0))
    return prompt_tokens / 1e6 * price_in + completion_tokens / 1e6 * price_out


def record(label, model, prompt_tokens, completion_tokens, seconds, ok=True, note=""):
    config.STORE.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "label": label,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "seconds": round(seconds, 2),
        "cost_rub": round(cost_rub(model, prompt_tokens, completion_tokens), 4),
        "ok": ok,
        "note": note,
    }
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load():
    if not LOG.is_file():
        return []
    entries = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def _percentile(values, share):
    if not values:
        return 0.0
    ordered = sorted(values)
    position = min(len(ordered) - 1, int(round(share * (len(ordered) - 1))))
    return ordered[position]


def summary():
    entries = load()
    groups = {}
    for entry in entries:
        groups.setdefault(entry["label"], []).append(entry)
    rows = []
    for label, group in sorted(groups.items()):
        seconds = [item["seconds"] for item in group]
        rows.append({
            "label": label,
            "calls": len(group),
            "fails": sum(1 for item in group if not item["ok"]),
            "p50": round(median(seconds), 2),
            "p95": round(_percentile(seconds, 0.95), 2),
            "tokens": sum(item["prompt_tokens"] + item["completion_tokens"] for item in group),
            "cost_rub": round(sum(item["cost_rub"] for item in group), 3),
        })
    total = {
        "calls": len(entries),
        "fails": sum(1 for item in entries if not item["ok"]),
        "tokens": sum(item["prompt_tokens"] + item["completion_tokens"] for item in entries),
        "cost_rub": round(sum(item["cost_rub"] for item in entries), 3),
    }
    return rows, total
