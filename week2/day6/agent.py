import os
import sys
import requests


class GeminiAgent:
    def __init__(self, model="gemini-2.5-pro", system=None):
        self.model = model
        self.system = system
        self.api_key = os.environ["PROXYAPI_KEY"]
        self.url = f"https://api.proxyapi.ru/google/v1beta/models/{model}:generateContent"

    def ask(self, user_text):
        payload = {"contents": [{"parts": [{"text": user_text}]}]}
        if self.system:
            payload["systemInstruction"] = {"parts": [{"text": self.system}]}
        response = requests.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    agent = GeminiAgent(system="Ты — полезный ассистент. Отвечай по-русски, кратко и по делу.")
    print(f"Агент на {agent.model} запущен. Пиши вопрос. Выход — пустая строка или 'exit'.\n")
    while True:
        user = input("Ты: ").strip()
        if user == "" or user.lower() == "exit":
            break
        print(f"\nАгент: {agent.ask(user)}\n")


if __name__ == "__main__":
    main()
