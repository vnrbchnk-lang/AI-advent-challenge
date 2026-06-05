import os
import sys
import time
import requests

sys.stdout.reconfigure(encoding="utf-8")

API_KEY = os.environ["PROXYAPI_KEY"]
URL = "https://api.proxyapi.ru/openai/v1/chat/completions"

# слабая / средняя / сильная
MODELS = ["gpt-3.5-turbo", "gpt-4o", "gpt-5.5"]

# цена за 1М токенов: (вход, выход, валюта)
# gpt-3.5-turbo, gpt-4o — официальный прайс OpenAI (USD)
# gpt-5.5 — новее cutoff, цены OpenAI нет → прайс ProxyAPI (руб.)
PRICES = {
    "gpt-3.5-turbo": (0.50, 1.50, "$"),
    "gpt-4o": (2.50, 10.00, "$"),
    "gpt-5.5": (1520, 9100, "₽"),
}

# Ловушка-подмена: знаменитая загадка, но условие изменено — лодка вмещает ВСЁ
# сразу. Слабая модель шпарит заученную многоходовку не читая; сильная замечает
# подвох и отвечает «за один рейс».
PROMPTS = [
    "Фермеру нужно переправить через реку волка, козу и капусту. "
    "Его лодка вмещает фермера и весь груз одновременно — волка, козу "
    "и капусту за один раз. Как ему переправить всех через реку?",
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
