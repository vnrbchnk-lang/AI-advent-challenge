import time

import requests

OLLAMA_URL = "http://localhost:11434"
CHAT_MODEL = "qwen2.5:7b-instruct"
Q8_MODEL = "qwen2.5:7b-instruct-q8_0"


def is_available():
    try:
        requests.get(f"{OLLAMA_URL}/api/version", timeout=3)
        return True
    except requests.RequestException:
        return False


def list_models():
    response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
    response.raise_for_status()
    models = []
    for entry in response.json().get("models", []):
        models.append({
            "name": entry["name"],
            "size_gb": round(entry.get("size", 0) / 1e9, 2),
            "family": entry.get("details", {}).get("family", ""),
            "params": entry.get("details", {}).get("parameter_size", ""),
            "quant": entry.get("details", {}).get("quantization_level", ""),
        })
    return sorted(models, key=lambda m: m["name"])


def running_models():
    response = requests.get(f"{OLLAMA_URL}/api/ps", timeout=10)
    response.raise_for_status()
    loaded = []
    for entry in response.json().get("models", []):
        total = entry.get("size", 0)
        vram = entry.get("size_vram", 0)
        loaded.append({
            "name": entry["name"],
            "size_gb": round(total / 1e9, 2),
            "vram_gb": round(vram / 1e9, 2),
            "cpu_gb": round((total - vram) / 1e9, 2),
        })
    return loaded


def _options(temperature, num_ctx, num_predict):
    options = {"temperature": temperature}
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    if num_predict is not None:
        options["num_predict"] = num_predict
    return options


def _stats(payload, wall_seconds):
    eval_count = payload.get("eval_count", 0)
    eval_ns = payload.get("eval_duration", 0) or 1
    return {
        "seconds": round(wall_seconds, 2),
        "tokens": eval_count,
        "tok_per_s": round(eval_count / (eval_ns / 1e9), 1),
        "prompt_tokens": payload.get("prompt_eval_count", 0),
        "load_seconds": round(payload.get("load_duration", 0) / 1e9, 2),
        "model": payload.get("model", ""),
    }


def chat(messages, model=CHAT_MODEL, temperature=0.3, num_ctx=None, num_predict=None):
    started = time.time()
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": _options(temperature, num_ctx, num_predict),
        },
        timeout=600,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload["message"]["content"].strip()
    return text, _stats(payload, time.time() - started)


def unload(model):
    try:
        requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": model, "keep_alive": 0}, timeout=30)
    except requests.RequestException:
        pass


def ask(prompt, model=CHAT_MODEL, temperature=0.3, num_ctx=None, num_predict=None):
    return chat([{"role": "user", "content": prompt}], model, temperature, num_ctx, num_predict)
