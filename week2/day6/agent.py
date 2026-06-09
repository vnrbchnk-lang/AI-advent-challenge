import os
import sys
import requests


class Agent:
    def __init__(self, model="gpt-5.2", system=None):
        self.model = model
        self.system = system
        self.api_key = os.environ["PROXYAPI_KEY"]
        self.url = "https://api.proxyapi.ru/openai/v1/chat/completions"

    def ask(self, user_text):
        messages = []
        if self.system:
            messages.append({"role": "system", "content": self.system})
        messages.append({"role": "user", "content": user_text})
        response = requests.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages},
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    agent = Agent(system="Ты — полезный ассистент. Отвечай по-русски, кратко и по делу.")
    print(f"Агент на {agent.model} запущен. Пиши вопрос. Выход — пустая строка или 'exit'.\n")
    while True:
        user = input("Ты: ").strip()
        if user == "" or user.lower() == "exit":
            break
        print(f"\nАгент: {agent.ask(user)}\n")


if __name__ == "__main__":
    main()
