import os
import sys
import time
import requests

sys.stdout.reconfigure(encoding="utf-8")

API_KEY = os.environ["PROXYAPI_KEY"]
URL = "https://api.proxyapi.ru/openai/v1/chat/completions"

RUB_PER_USD = 90

MODELS = ["gpt-3.5-turbo", "gpt-4o", "gpt-5.5"]

PRICE_PER_1M_USD = {
    "gpt-3.5-turbo": (0.50, 1.50),
    "gpt-4o": (2.50, 10.00),
    "gpt-5.5": (1520 / RUB_PER_USD, 9100 / RUB_PER_USD),
}

PROMPTS = [
    "У Салли 3 брата. У каждого из её братьев есть 2 сестры. "
    "Сколько сестёр у Салли? Дай число и короткое объяснение.",
]

def ask(model, prompt):
    t = time.perf_counter()
    response = requests.post(
        URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
    )
    response.raise_for_status()
    dt = time.perf_counter() - t
    data = response.json()
    text = data["choices"][0]["message"]["content"]
    usage = data["usage"]
    return text, dt, usage

for prompt in PROMPTS:
    print("ЗАПРОС:", prompt)
    for model in MODELS:
        text, dt, usage = ask(model, prompt)
        price_in, price_out = PRICE_PER_1M_USD[model]
        print(f"\n--- {model} ---")
        print(f"время:     {dt:.2f} c")
        print(f"токены:    {usage['prompt_tokens']} вход + "
              f"{usage['completion_tokens']} выход = {usage['total_tokens']} всего")
        print(f"цена/1М:   ${price_in:.2f} вход / ${price_out:.2f} выход")
        print(f"ответ:     {text}")
