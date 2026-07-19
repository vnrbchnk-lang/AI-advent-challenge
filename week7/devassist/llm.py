import json
import os
import time

import requests

from devassist import config, metrics

RETRIES = 3
TIMEOUT = 240


class LLMError(RuntimeError):
    pass


def _headers():
    api_key = os.environ.get("PROXYAPI_KEY")
    if not api_key:
        raise LLMError("PROXYAPI_KEY не задан в переменных окружения")
    return {"Authorization": f"Bearer {api_key}"}


def complete(messages, model=None, temperature=0.3, json_mode=False, tools=None,
             label="chat", max_tokens=None, fallback=True):
    model = model or config.MAIN_MODEL
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if max_tokens:
        payload["max_tokens"] = max_tokens

    last_error = None
    for attempt in range(RETRIES):
        started = time.time()
        try:
            response = requests.post(config.CHAT_URL, headers=_headers(), json=payload, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as error:
            last_error = error
            metrics.record(label, model, 0, 0, time.time() - started, ok=False,
                           note=f"attempt {attempt + 1}: {error}")
            time.sleep(1.5 * (attempt + 1))
            continue
        usage = data.get("usage") or {}
        metrics.record(label, model, usage.get("prompt_tokens", 0),
                       usage.get("completion_tokens", 0), time.time() - started)
        return data["choices"][0]["message"]

    if fallback and model != config.CHEAP_MODEL:
        return complete(messages, model=config.CHEAP_MODEL, temperature=temperature,
                        json_mode=json_mode, tools=tools, label=f"{label}:fallback",
                        max_tokens=max_tokens, fallback=False)
    raise LLMError(f"{model}: {last_error}")


def chat(messages, **kwargs):
    return (complete(messages, **kwargs).get("content") or "").strip()


def chat_json(messages, **kwargs):
    kwargs["json_mode"] = True
    raw = chat(messages, **kwargs)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
        raise
