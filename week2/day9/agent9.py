import json
import os
import sys
from pathlib import Path

import requests

HISTORY_PATH = Path(__file__).parent / "history.json"
API_URL = "https://api.proxyapi.ru/openai/v1/chat/completions"
PRICES_RUB_PER_1M = {
    "gpt-5.2": {"input": 531, "output": 4245},
}
CONTEXT_LIMIT = 10000
KEEP_LAST_MESSAGES = 6
COMPRESS_EVERY_MESSAGES = 10
JUNK_WORD = "вода "
SUMMARIZER_SYSTEM = (
    "Ты сжимаешь историю диалога в краткое summary. Сохрани имена, факты, числа, "
    "принятые решения и открытые вопросы. Убери всё остальное. Пиши плотным текстом без воды."
)


class ContextOverflowError(Exception):
    pass


class Agent:
    def __init__(self, model="gpt-5.2", system=None, history_path=HISTORY_PATH,
                 context_limit=CONTEXT_LIMIT, keep_last=KEEP_LAST_MESSAGES,
                 compress_every=COMPRESS_EVERY_MESSAGES):
        self.model = model
        self.system = system
        self.history_path = Path(history_path)
        self.context_limit = context_limit
        self.keep_last = keep_last
        self.compress_every = compress_every
        self.api_key = os.environ["PROXYAPI_KEY"]
        self.messages = []
        self.summary = ""
        self.history_tokens = 0
        self.turns = []
        self.last_compression = None
        self.load()

    def fresh(self):
        self.messages = []
        self.summary = ""
        self.history_tokens = 0
        self.turns = []
        self.last_compression = None

    def load(self):
        if self.history_path.exists():
            state = json.loads(self.history_path.read_text(encoding="utf-8"))
            self.messages = state["messages"]
            self.summary = state["summary"]
            self.history_tokens = state["history_tokens"]
            self.turns = state["turns"]
        else:
            self.fresh()

    def save(self):
        state = {
            "messages": self.messages,
            "summary": self.summary,
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

    def request_messages(self):
        prefix = []
        if self.system:
            prefix.append({"role": "system", "content": self.system})
        if self.summary:
            prefix.append({
                "role": "system",
                "content": "Краткое содержание более раннего диалога "
                           "(автоматически сжато, полной истории у тебя нет): " + self.summary,
            })
        return prefix + self.messages

    def estimate_history_tokens(self):
        chars = len(self.summary) + sum(len(m["content"]) for m in self.messages)
        return chars // 3

    def call_api(self, messages):
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages},
        )
        response.raise_for_status()
        return response.json()

    def compress(self):
        archive = self.messages[:-self.keep_last]
        if not archive:
            return None
        chunk = "\n".join(f"{m['role']}: {m['content']}" for m in archive)
        request = ""
        if self.summary:
            request += f"Старое summary:\n{self.summary}\n\n"
        request += f"Новые сообщения диалога:\n{chunk}\n\nВерни обновлённое summary целиком."
        data = self.call_api([
            {"role": "system", "content": SUMMARIZER_SYSTEM},
            {"role": "user", "content": request},
        ])
        self.summary = data["choices"][0]["message"]["content"]
        usage = data["usage"]
        cost = self.cost_rub(usage["prompt_tokens"], usage["completion_tokens"])
        self.turns.append({
            "compress": True,
            "request_tokens": usage["prompt_tokens"],
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "cost_rub": cost,
        })
        self.messages = self.messages[-self.keep_last:]
        self.history_tokens = self.estimate_history_tokens()
        self.last_compression = {
            "removed_messages": len(archive),
            "summary_chars": len(self.summary),
            "cost_rub": cost,
        }
        self.save()
        return self.last_compression

    def ask(self, user_text):
        if self.history_tokens >= self.context_limit:
            raise ContextOverflowError(
                f"Контекст агента переполнен: история {self.history_tokens} токенов "
                f">= лимит {self.context_limit}. Запрос к модели не отправлен. "
                f"Команда 'reset' очистит историю."
            )
        self.last_compression = None
        self.messages.append({"role": "user", "content": user_text})
        data = self.call_api(self.request_messages())
        answer = data["choices"][0]["message"]["content"]
        self.messages.append({"role": "assistant", "content": answer})
        usage = data["usage"]
        self.turns.append({
            "compress": False,
            "request_tokens": max(0, usage["prompt_tokens"] - self.history_tokens),
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "cost_rub": self.cost_rub(usage["prompt_tokens"], usage["completion_tokens"]),
        })
        self.history_tokens = usage["total_tokens"]
        if len(self.messages) - self.keep_last >= self.compress_every:
            self.compress()
        self.save()
        return answer

    def fill(self, target_tokens):
        junk = ("Технический балласт для теста контекста, игнорируй его: "
                + JUNK_WORD * max(1, target_tokens))
        self.messages.append({"role": "user", "content": junk})
        self.messages.append({"role": "assistant", "content": "Принято, игнорирую."})
        self.history_tokens += target_tokens
        self.save()


def print_turn_stats(agent):
    turn = [t for t in agent.turns if not t["compress"]][-1]
    fill = agent.context_fill_percent()
    print(
        f"[токены: запрос {turn['request_tokens']} | "
        f"вход всего {turn['prompt_tokens']} | "
        f"ответ {turn['completion_tokens']} | "
        f"история {agent.history_tokens}/{agent.context_limit} ({fill}%) | "
        f"ход {turn['cost_rub']:.4f} ₽ | всего {agent.total_spent_rub():.4f} ₽]"
    )
    if agent.last_compression:
        compression = agent.last_compression
        print(f"[СЖАТИЕ: {compression['removed_messages']} старых сообщений заменены summary "
              f"({compression['summary_chars']} символов); вызов стоил {compression['cost_rub']:.4f} ₽; "
              f"история теперь ~{agent.history_tokens} токенов]")
    elif fill >= 100:
        print("[КОНТЕКСТ ПЕРЕПОЛНЕН: следующий запрос агент не примет]")
    elif fill >= 80:
        print("[ВНИМАНИЕ: контекст почти заполнен]")
    print()


def print_dialog_stats(agent):
    if not agent.turns:
        print("[Ходов ещё не было]\n")
        return
    print(f"{'ход':>3} | {'тип':>6} | {'запрос':>6} | {'вход всего':>10} | {'ответ':>6} | {'история':>8} | {'цена ₽':>8}")
    for number, turn in enumerate(agent.turns, 1):
        kind = "сжатие" if turn["compress"] else "вопрос"
        print(f"{number:>3} | {kind:>6} | {turn['request_tokens']:>6} | {turn['prompt_tokens']:>10} | "
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
    if agent.messages or agent.summary:
        print(f"Агент на {agent.model} запущен. Продолжаю прошлый диалог: "
              f"{len(agent.messages)} живых сообщений, summary "
              f"{'есть (' + str(len(agent.summary)) + ' символов)' if agent.summary else 'нет'}, "
              f"~{agent.history_tokens} токенов ({agent.context_fill_percent()}% лимита).")
    else:
        print(f"Агент на {agent.model} запущен. Новый диалог.")
    print(f"Сжатие истории: храню последние {agent.keep_last} сообщений как есть, "
          f"при {agent.compress_every}+ сообщениях сверх того — заменяю их summary.")
    print(f"Лимит контекста: {agent.context_limit} токенов (ручной, для демонстрации).")
    print("Команды: 'stats' — таблица токенов, 'summary' — показать текущее summary, "
          "'compress' — сжать принудительно, 'fill N' — дописать ~N токенов балласта "
          "(локально, бесплатно), 'reset' — забыть диалог, пустая строка или 'exit' — выход.\n")
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
        if user.lower() == "summary":
            print(f"\n[Summary: {agent.summary if agent.summary else 'пока нет — сжатие ещё не запускалось'}]\n")
            continue
        if user.lower() == "compress":
            compression = agent.compress()
            if compression:
                print(f"\n[СЖАТИЕ: {compression['removed_messages']} сообщений заменены summary "
                      f"({compression['summary_chars']} символов); вызов стоил {compression['cost_rub']:.4f} ₽; "
                      f"история теперь ~{agent.history_tokens} токенов]\n")
            else:
                print(f"\n[Сжимать нечего: живых сообщений {len(agent.messages)}, "
                      f"храню последние {agent.keep_last} как есть]\n")
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
