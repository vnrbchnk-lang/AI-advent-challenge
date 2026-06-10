import os
import sys
import requests


class Agent:
    def __init__(self, model="gpt-5.2", system=None):
        self.model = model
        self.system = system
        self.api_key = os.environ["PROXYAPI_KEY"]
        self.url = "https://api.proxyapi.ru/openai/v1/chat/completions"
        self.messages = []
        self.last_usage = None
        self.reset()

    def reset(self):
        self.messages = []
        if self.system:
            self.messages.append({"role": "system", "content": self.system})
        self.last_usage = None

    def ask(self, user_text):
        self.messages.append({"role": "user", "content": user_text})
        response = requests.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": self.messages},
        )
        response.raise_for_status()
        data = response.json()
        answer = data["choices"][0]["message"]["content"]
        self.messages.append({"role": "assistant", "content": answer})
        self.last_usage = data.get("usage")
        return answer


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
    print(f"Агент на {agent.model} запущен. Помнит диалог в рамках сессии.")
    print("Команды: 'reset' — забыть диалог, пустая строка или 'exit' — выход.\n")
    while True:
        user = input("Ты: ").strip()
        if user == "" or user.lower() == "exit":
            break
        if user.lower() == "reset":
            agent.reset()
            print("\n[Память сессии очищена]\n")
            continue
        print(f"\nАгент: {agent.ask(user)}\n")
        usage = agent.last_usage
        if usage:
            print(
                f"[токены: вход {usage['prompt_tokens']}, "
                f"выход {usage['completion_tokens']}, "
                f"всего {usage['total_tokens']} | реплик в памяти: {len(agent.messages)}]\n"
            )


if __name__ == "__main__":
    main()
