import json
import os
import sys
from pathlib import Path

import requests

HISTORY_PATH = Path(__file__).parent / "history.json"
API_URL = "https://api.proxyapi.ru/openai/v1/chat/completions"
PRICES_RUB_PER_1M = {
    "gpt-5.2": {"input": 531, "output": 4245},
    "gpt-3.5-turbo": {"input": 129, "output": 387},
}
CONTEXT_LIMIT = 10000
FLOOD_MODEL = "gpt-3.5-turbo"
FLOOD_MODEL_WINDOW = 16385
JUNK_WORD = "вода "
JUNK_TOKENS_PER_WORD_GPT52 = 1


class ContextOverflowError(Exception):
    pass


class Agent:
    def __init__(self, model="gpt-5.2", system=None, history_path=HISTORY_PATH,
                 context_limit=CONTEXT_LIMIT):
        self.model = model
        self.system = system
        self.history_path = Path(history_path)
        self.context_limit = context_limit
        self.api_key = os.environ["PROXYAPI_KEY"]
        self.messages = []
        self.history_tokens = 0
        self.turns = []
        self.load()

    def fresh(self):
        self.messages = []
        if self.system:
            self.messages.append({"role": "system", "content": self.system})
        self.history_tokens = 0
        self.turns = []

    def load(self):
        if self.history_path.exists():
            state = json.loads(self.history_path.read_text(encoding="utf-8"))
            self.messages = state["messages"]
            self.history_tokens = state["history_tokens"]
            self.turns = state["turns"]
        else:
            self.fresh()

    def save(self):
        state = {
            "messages": self.messages,
            "history_tokens": self.history_tokens,
            "turns": self.turns,
        }
        self.history_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def reset(self):
        self.fresh()
        self.history_path.unlink(missing_ok=True)

    def cost_rub(self, prompt_tokens, completion_tokens):
        price = PRICES_RUB_PER_1M[self.model]
        return (prompt_tokens * price["input"]
                + completion_tokens * price["output"]) / 1_000_000

    def total_spent_rub(self):
        return sum(turn["cost_rub"] for turn in self.turns)

    def context_fill_percent(self):
        return round(self.history_tokens / self.context_limit * 100)

    def fill(self, target_tokens):
        repeats = max(1, target_tokens // JUNK_TOKENS_PER_WORD_GPT52)
        junk = "Технический балласт для теста контекста, игнорируй его: " + JUNK_WORD * repeats
        self.messages.append({"role": "user", "content": junk})
        self.messages.append({"role": "assistant", "content": "Принято, игнорирую."})
        self.history_tokens += target_tokens
        self.save()

    def ask(self, user_text):
        if self.history_tokens >= self.context_limit:
            raise ContextOverflowError(
                f"Контекст агента переполнен: история {self.history_tokens} токенов "
                f">= лимит {self.context_limit}. Запрос к модели не отправлен. "
                f"Команда 'reset' очистит историю."
            )
        self.messages.append({"role": "user", "content": user_text})
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": self.messages},
        )
        response.raise_for_status()
        data = response.json()
        answer = data["choices"][0]["message"]["content"]
        self.messages.append({"role": "assistant", "content": answer})
        usage = data["usage"]
        self.turns.append({
            "request_tokens": usage["prompt_tokens"] - self.history_tokens,
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "cost_rub": self.cost_rub(usage["prompt_tokens"], usage["completion_tokens"]),
        })
        self.history_tokens = usage["total_tokens"]
        self.save()
        return answer


def flood(api_key):
    junk = "вода " * 20000
    print(f"Шлю {FLOOD_MODEL} одно сообщение из {len(junk)} символов "
          f"(окно модели — {FLOOD_MODEL_WINDOW} токенов)...")
    response = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": FLOOD_MODEL,
              "messages": [{"role": "user", "content": junk}]},
    )
    print(f"HTTP {response.status_code}")
    body = response.json()
    if "error" in body:
        print(f"Ошибка API: {body['error']['message']}")
    else:
        print(f"Модель неожиданно ответила: {body['choices'][0]['message']['content'][:200]}")


def print_turn_stats(agent):
    turn = agent.turns[-1]
    fill = agent.context_fill_percent()
    print(
        f"[токены: запрос {turn['request_tokens']} | "
        f"вход всего {turn['prompt_tokens']} | "
        f"ответ {turn['completion_tokens']} | "
        f"история {agent.history_tokens}/{agent.context_limit} ({fill}%) | "
        f"ход {turn['cost_rub']:.4f} ₽ | всего {agent.total_spent_rub():.4f} ₽]"
    )
    if fill >= 100:
        print("[КОНТЕКСТ ПЕРЕПОЛНЕН: следующий запрос агент не примет]")
    elif fill >= 80:
        print("[ВНИМАНИЕ: контекст почти заполнен]")
    print()


def print_dialog_stats(agent):
    if not agent.turns:
        print("[Ходов ещё не было]\n")
        return
    print(f"{'ход':>3} | {'запрос':>6} | {'вход всего':>10} | {'ответ':>6} | {'история':>8} | {'цена ₽':>8}")
    for number, turn in enumerate(agent.turns, 1):
        print(f"{number:>3} | {turn['request_tokens']:>6} | {turn['prompt_tokens']:>10} | "
              f"{turn['completion_tokens']:>6} | {turn['total_tokens']:>8} | {turn['cost_rub']:>8.4f}")
    print(f"Итого за диалог: {agent.total_spent_rub():.4f} ₽\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    agent = Agent(system=(
        "Ты — вдумчивый специалист широкого профиля. К каждой задаче подходишь с умом: "
        "сначала понимаешь суть вопроса и его контекст, отделяешь главное от второстепенного, "
        "и только потом отвечаешь. "
        "Если в запросе не хватает данных для точного ответа — не угадывай, а назови, "
        "какого факта недостаёт, и задай один уточняющий вопрос. "
        "Отвечай по существу и по-русски: сначала вывод, затем при необходимости короткое обоснование. "
        "Не выдумывай факты; если не уверен — честно скажи об этом. Без воды и лишней вежливости."
    ))
    dialog_replicas = len([m for m in agent.messages if m["role"] != "system"])
    if dialog_replicas:
        print(f"Агент на {agent.model} запущен. Продолжаю прошлый диалог "
              f"({dialog_replicas} реплик, {agent.history_tokens} токенов, "
              f"{agent.context_fill_percent()}% лимита).")
    else:
        print(f"Агент на {agent.model} запущен. Новый диалог.")
    print(f"Лимит контекста: {agent.context_limit} токенов (ручной, для демонстрации).")
    print("Команды: 'stats' — таблица токенов, 'fill N' — дописать в историю ~N токенов "
          f"балласта (локально, бесплатно), 'flood' — переполнить реальное окно {FLOOD_MODEL}, "
          "'reset' — забыть диалог, пустая строка или 'exit' — выход.\n")
    while True:
        user = input("Ты: ").strip()
        if user == "" or user.lower() == "exit":
            break
        if user.lower() == "reset":
            agent.reset()
            print("\n[Память очищена, история удалена]\n")
            continue
        if user.lower() == "stats":
            print()
            print_dialog_stats(agent)
            continue
        if user.lower() == "flood":
            print()
            flood(agent.api_key)
            print()
            continue
        if user.lower().startswith("fill"):
            parts = user.split()
            if len(parts) != 2 or not parts[1].isdigit():
                print("\n[Формат: fill N, например fill 7000]\n")
                continue
            agent.fill(int(parts[1]))
            print(f"\n[Балласт ~{parts[1]} токенов дописан в историю локально, без запроса к API. "
                  f"История ~{agent.history_tokens}/{agent.context_limit} "
                  f"({agent.context_fill_percent()}%). Точная цифра — после следующего хода.]\n")
            continue
        try:
            print(f"\nАгент: {agent.ask(user)}\n")
        except ContextOverflowError as error:
            print(f"\n[ОШИБКА] {error}\n")
            continue
        print_turn_stats(agent)


if __name__ == "__main__":
    main()
