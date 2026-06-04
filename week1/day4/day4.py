import os
import sys
import requests

sys.stdout.reconfigure(encoding="utf-8")

API_KEY = os.environ["PROXYAPI_KEY"]
URL = "https://api.proxyapi.ru/openai/v1/chat/completions"

TASKS = {
    "КРЕАТИВ": "Продолжи одним предложением: Я открыл холодильник, а там...",
    "ФАКТ": "В каком году основан город Казань? Ответь одним предложением.",
}

TEMPERATURES = [0, 0.7, 1.2]

def ask(task, temperature):
    response = requests.post(
        URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={
            "model": "gpt-5.2",
            "messages": [{"role": "user", "content": task}],
            "temperature": temperature,
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

for label, task in TASKS.items():
    print(f"################## {label} ##################")
    print("ЗАПРОС:", task)
    for temp in TEMPERATURES:
        print()
        print(f"========== temperature = {temp} ==========")
        print(ask(task, temp))
    print()
