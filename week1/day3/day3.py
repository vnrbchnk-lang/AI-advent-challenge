import os
import sys
import requests

sys.stdout.reconfigure(encoding="utf-8")

API_KEY = os.environ["PROXYAPI_KEY"]
URL = "https://api.proxyapi.ru/openai/v1/chat/completions"

TASK = "Как попить воду из кружки, у которой нет дна, а верхушка запаяна?"

def ask(messages):
    response = requests.post(
        URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"model": "gpt-5.5", "messages": messages},
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

direct = ask([
    {"role": "user", "content": TASK},
])

step = ask([
    {"role": "user", "content": TASK + "\n\nРешай пошагово, рассуждай по порядку."},
])

crafted_prompt = ask([
    {
        "role": "user",
        "content": (
            "Составь оптимальный промпт для решения задачи ниже. "
            "Верни только текст промпта, без решения.\n\nЗадача: " + TASK
        ),
    },
])
self_prompt = ask([
    {"role": "user", "content": crafted_prompt},
])

experts = ask([
    {
        "role": "system",
        "content": (
            "Реши задачу как совещание трёх экспертов: Аналитик, Инженер, Критик. "
            "Каждый даёт своё решение от первого лица. "
            "В конце выведи строку «Итог:» с общим ответом."
        ),
    },
    {"role": "user", "content": TASK},
])

print("ЗАДАЧА:", TASK)
print()
print("=== 1. ПРЯМОЙ ОТВЕТ ===")
print(direct)
print()
print("=== 2. ПОШАГОВО ===")
print(step)
print()
print("=== 3. МОДЕЛЬ САМА СОСТАВИЛА ПРОМПТ ===")
print("[сгенерированный промпт]")
print(crafted_prompt)
print("[ответ по нему]")
print(self_prompt)
print()
print("=== 4. ГРУППА ЭКСПЕРТОВ ===")
print(experts)
