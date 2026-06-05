import os
import sys
import time
import requests

sys.stdout.reconfigure(encoding="utf-8")

API_KEY = os.environ["PROXYAPI_KEY"]
URL = "https://api.proxyapi.ru/openai/v1/chat/completions"

MODELS = ["gpt-3.5-turbo", "gpt-4o", "gpt-5.5"]

PRICES = {
    "gpt-3.5-turbo": (0.50, 1.50, "$"),
    "gpt-4o": (2.50, 10.00, "$"),
    "gpt-5.5": (1520, 9100, "₽"),
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
    price_in, price_out, currency = PRICES[model]
    cost = usage["prompt_tokens"] / 1e6 * price_in + usage["completion_tokens"] / 1e6 * price_out
    return text, dt, usage, cost, currency, price_in, price_out

for prompt in PROMPTS:
    print("\n" + "=" * 70)
    print("ЗАПРОС:", prompt)
    print("=" * 70)
    for model in MODELS:
        text, dt, usage, cost, currency, price_in, price_out = ask(model, prompt)
        print(f"\n--- {model} ---")
        print(f"время:     {dt:.2f} c")
        print(f"токены:    {usage['prompt_tokens']} вход + "
              f"{usage['completion_tokens']} выход = {usage['total_tokens']} всего")
        print(f"цена/1М:   {price_in} вход / {price_out} выход {currency}")
        print(f"стоимость: {cost:.4f} {currency}")
        print(f"ответ:     {text}")
