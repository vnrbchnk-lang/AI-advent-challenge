import os
import sys
import requests

sys.stdout.reconfigure(encoding="utf-8")

API_KEY = os.environ["PROXYAPI_KEY"]
URL = "https://api.proxyapi.ru/openai/v1/chat/completions"

TASK = (
    "Придумай название и слоган для баскетбольной команды "
    "и придумай тактику для неё, чтобы она всегда побеждала соперников."
)

TEMPERATURES = [0, 0.7, 1.2]
RUNS = 1

def ask(temperature):
    response = requests.post(
        URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={
            "model": "gpt-5.2",
            "messages": [{"role": "user", "content": TASK}],
            "temperature": temperature,
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

print("ЗАПРОС:", TASK)
for temp in TEMPERATURES:
    print()
    print(f"========== temperature = {temp} ==========")
    for i in range(1, RUNS + 1):
        print(f"--- прогон {i} ---")
        print(ask(temp))
        print()
