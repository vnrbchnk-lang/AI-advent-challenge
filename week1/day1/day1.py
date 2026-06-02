import os
import requests

API_KEY = os.environ["PROXYAPI_KEY"]
URL = "https://api.proxyapi.ru/openai/v1/chat/completions"

response = requests.post(
    URL,
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Привет! Назови три факта о Луне."}
        ],
    },
)
response.raise_for_status()

print(response.json()["choices"][0]["message"]["content"])
