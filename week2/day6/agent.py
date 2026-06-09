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
    agent = Agent(system=(
        "Ты — вдумчивый специалист широкого профиля. К каждой задаче подходишь с умом: "
        "сначала понимаешь суть вопроса и его контекст, отделяешь главное от второстепенного, "
        "и только потом отвечаешь. "
        "Если в запросе не хватает данных для точного ответа — не угадывай, а назови, "
        "какого факта недостаёт, и задай один уточняющий вопрос. "
        "Отвечай по существу и по-русски: сначала вывод, затем при необходимости короткое обоснование. "
        "Не выдумывай факты; если не уверен — честно скажи об этом. Без воды и лишней вежливости."
    ))
    print(f"Агент на {agent.model} запущен. Пиши вопрос. Выход — пустая строка или 'exit'.\n")
    while True:
        user = input("Ты: ").strip()
        if user == "" or user.lower() == "exit":
            break
        print(f"\nАгент: {agent.ask(user)}\n")


if __name__ == "__main__":
    main()
