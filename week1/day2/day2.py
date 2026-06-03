import os
import requests

API_KEY = os.environ["PROXYAPI_KEY"]
URL = "https://api.proxyapi.ru/openai/v1/chat/completions"

QUESTION = "Назови 3 фактов про баскетбол."

def ask(payload):
    response = requests.post(
        URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=payload,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

free = ask({
    "model": "gpt-4o-mini",
    "messages": [
        {"role": "user", "content": QUESTION}
    ],
})

controlled = ask({
    "model": "gpt-4o-mini",
    "messages": [
        {
            "role": "system",
            "content": (
                "Отвечай строго нумерованным списком из трёх пунктов, "
                "каждый факт — одна короткая строка не длиннее 10 слов. "
                "Без вступления и заключения. "
                "После последнего пункта на новой строке напиши слово КОНЕЦ."
            ),
        },
        {"role": "user", "content": QUESTION},
    ],
    "max_tokens": 100,
    "stop": ["КОНЕЦ"],
})

print("=== БЕЗ ОГРАНИЧЕНИЙ ===")
print(free)
print()
print("=== С ОГРАНИЧЕНИЯМИ (формат + длина + stop) ===")
print(controlled)
