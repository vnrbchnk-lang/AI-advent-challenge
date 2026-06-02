import os
import sys
import requests

API_KEY = os.environ["PROXYAPI_KEY"]
URL = "https://api.proxyapi.ru/openai/v1/chat/completions"

sys.stdout.reconfigure(encoding="utf-8")

messages = [{"role": "system", "content": "Ты — полезный ассистент. Отвечай по-русски."}]

print("Агент запущен. Пиши вопрос. Выход — пустая строка или 'exit'.\n")

while True:
    user = input("Ты: ").strip()
    if user == "" or user.lower() == "exit":
        break

    messages.append({"role": "user", "content": user})
    response = requests.post(
        URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"model": "gpt-4o-mini", "messages": messages},
    )
    response.raise_for_status()

    answer = response.json()["choices"][0]["message"]["content"]
    messages.append({"role": "assistant", "content": answer})
    print(f"\nАгент: {answer}\n")
