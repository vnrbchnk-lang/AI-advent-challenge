import copy
import json
import os
import sys
from pathlib import Path

import requests

HISTORY_PATH = Path(__file__).parent / "history.json"
API_URL = "https://api.proxyapi.ru/openai/v1/chat/completions"
PRICES_RUB_PER_1M = {
    "gpt-5.2": {"input": 531, "output": 4245},
    "gpt-4o-mini": {"input": 39, "output": 155},
}
MAIN_MODEL = "gpt-5.2"
FACTS_MODEL = "gpt-4o-mini"
WINDOW_N = 6
STRATEGIES = ("sliding", "facts", "branching")
FACTS_SYSTEM = (
    "Ты ведёшь компактную память о задаче в виде JSON ключ-значение. "
    "Тебе дают текущие факты и новое сообщение пользователя. "
    "Верни ОБНОВЛЁННЫЙ JSON-объект целиком: добавь или уточни важные данные "
    "(цель, ограничения, предпочтения, решения, договорённости, числа, сроки, имена). "
    "Не выдумывай то, чего нет в сообщениях. Ключи и значения — короткие строки на русском. "
    "Ответ — ТОЛЬКО JSON-объект, без markdown и пояснений."
)


class Agent:
    def __init__(self, model=MAIN_MODEL, system=None, history_path=HISTORY_PATH,
                 window_n=WINDOW_N, strategy="sliding"):
        self.model = model
        self.system = system
        self.history_path = Path(history_path)
        self.window_n = window_n
        self.strategy = strategy
        self.api_key = os.environ["PROXYAPI_KEY"]
        self.branches = {"main": []}
        self.current_branch = "main"
        self.checkpoint = None
        self.facts = {}
        self.history_tokens = 0
        self.turns = []
        self.load()

    @property
    def messages(self):
        return self.branches[self.current_branch]

    def fresh(self):
        self.branches = {"main": []}
        self.current_branch = "main"
        self.checkpoint = None
        self.facts = {}
        self.history_tokens = 0
        self.turns = []

    def load(self):
        if self.history_path.exists():
            state = json.loads(self.history_path.read_text(encoding="utf-8"))
            self.strategy = state["strategy"]
            self.window_n = state["window_n"]
            self.branches = state["branches"]
            self.current_branch = state["current_branch"]
            self.checkpoint = state["checkpoint"]
            self.facts = state["facts"]
            self.history_tokens = state["history_tokens"]
            self.turns = state["turns"]
        else:
            self.fresh()

    def save(self):
        state = {
            "strategy": self.strategy,
            "window_n": self.window_n,
            "branches": self.branches,
            "current_branch": self.current_branch,
            "checkpoint": self.checkpoint,
            "facts": self.facts,
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

    def cost_rub(self, model, prompt_tokens, completion_tokens):
        price = PRICES_RUB_PER_1M[model]
        return (prompt_tokens * price["input"]
                + completion_tokens * price["output"]) / 1_000_000

    def total_spent_rub(self):
        return sum(turn["cost_rub"] for turn in self.turns)

    def call_api(self, model, messages):
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": model, "messages": messages},
        )
        response.raise_for_status()
        return response.json()

    def build_request_messages(self):
        prefix = []
        if self.system:
            prefix.append({"role": "system", "content": self.system})
        if self.strategy == "branching":
            return prefix + self.messages
        if self.strategy == "facts" and self.facts:
            prefix.append({
                "role": "system",
                "content": "Известные факты о задаче (ключ → значение): "
                           + json.dumps(self.facts, ensure_ascii=False),
            })
        return prefix + self.messages[-self.window_n:]

    def log_turn(self, kind, model, usage):
        self.turns.append({
            "kind": kind,
            "strategy": self.strategy,
            "model": model,
            "branch": self.current_branch,
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "cost_rub": self.cost_rub(model, usage["prompt_tokens"], usage["completion_tokens"]),
        })

    def update_facts(self, user_text):
        request = ("Текущие факты (JSON):\n" + json.dumps(self.facts, ensure_ascii=False)
                   + "\n\nНовое сообщение пользователя:\n" + user_text
                   + "\n\nВерни обновлённый JSON-объект целиком.")
        data = self.call_api(FACTS_MODEL, [
            {"role": "system", "content": FACTS_SYSTEM},
            {"role": "user", "content": request},
        ])
        raw = data["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[raw.find("{"):raw.rfind("}") + 1]
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                self.facts = {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            pass
        self.log_turn("facts", FACTS_MODEL, data["usage"])

    def ask(self, user_text):
        self.messages.append({"role": "user", "content": user_text})
        if self.strategy == "facts":
            self.update_facts(user_text)
        data = self.call_api(self.model, self.build_request_messages())
        answer = data["choices"][0]["message"]["content"]
        self.messages.append({"role": "assistant", "content": answer})
        self.log_turn("ask", self.model, data["usage"])
        self.history_tokens = data["usage"]["total_tokens"]
        self.save()
        return answer

    def set_strategy(self, name):
        if name not in STRATEGIES:
            return False
        self.strategy = name
        self.save()
        return True

    def make_checkpoint(self):
        self.checkpoint = copy.deepcopy(self.messages)
        self.save()
        return len(self.checkpoint)

    def branch(self, name):
        source = self.checkpoint if self.checkpoint is not None else self.messages
        self.branches[name] = copy.deepcopy(source)
        self.current_branch = name
        self.save()

    def switch(self, name):
        if name not in self.branches:
            return False
        self.current_branch = name
        self.history_tokens = 0
        self.save()
        return True


def print_turn_stats(agent):
    asks = [t for t in agent.turns if t["kind"] == "ask"]
    last = asks[-1]
    line = (f"[{last['strategy']} | ветка {last['branch']} | модель {last['model']} | "
            f"вход {last['prompt_tokens']} ток. | ответ {last['completion_tokens']} | "
            f"ход {last['cost_rub']:.4f} ₽")
    facts_turns = [t for t in agent.turns if t["kind"] == "facts"]
    if agent.strategy == "facts" and facts_turns:
        line += f" | facts-вызов {facts_turns[-1]['cost_rub']:.4f} ₽ ({len(agent.facts)} фактов)"
    line += f" | всего {agent.total_spent_rub():.4f} ₽]"
    print(line)
    print()


def print_dialog_stats(agent):
    if not agent.turns:
        print("[Ходов ещё не было]\n")
        return
    print(f"{'#':>3} | {'тип':>6} | {'стратегия':>9} | {'ветка':>8} | {'модель':>11} | "
          f"{'вход':>6} | {'ответ':>6} | {'цена ₽':>8}")
    for number, turn in enumerate(agent.turns, 1):
        print(f"{number:>3} | {turn['kind']:>6} | {turn['strategy']:>9} | {turn['branch']:>8} | "
              f"{turn['model']:>11} | {turn['prompt_tokens']:>6} | {turn['completion_tokens']:>6} | "
              f"{turn['cost_rub']:>8.4f}")
    print(f"Итого за диалог: {agent.total_spent_rub():.4f} ₽\n")


def print_facts(agent):
    if not agent.facts:
        print("\n[Facts пусто — стратегия facts ещё не накопила данных]\n")
        return
    print("\n[Facts (ключ → значение):]")
    for key, value in agent.facts.items():
        print(f"  {key}: {value}")
    print()


def print_branches(agent):
    print("\n[Ветки диалога:]")
    for name, msgs in agent.branches.items():
        mark = " ← текущая" if name == agent.current_branch else ""
        print(f"  {name}: {len(msgs)} сообщений{mark}")
    checkpoint_info = f"{len(agent.checkpoint)} сообщений" if agent.checkpoint is not None else "нет"
    print(f"  checkpoint: {checkpoint_info}\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    agent = Agent(system=(
        "Ты — вдумчивый аналитик, помогаешь пользователю собрать техническое задание. "
        "Уточняешь детали, фиксируешь требования, опираешься на ранее сказанное. "
        "Если не хватает данных — задаёшь один уточняющий вопрос, не выдумываешь. "
        "Отвечай по существу и по-русски, кратко."
    ))
    print(f"Агент на {agent.model} запущен. Стратегия: {agent.strategy}, окно N={agent.window_n}.")
    print("Стратегии: sliding (последние N), facts (KV + последние N, экстрактор "
          f"{FACTS_MODEL}), branching (ветки, полная история).")
    print("Команды: 'strategy sliding|facts|branching' — сменить стратегию, 'window N' — размер окна, "
          "'facts' — показать KV, 'checkpoint' — точка ветвления, 'branch <имя>' — ветка от точки, "
          "'switch <имя>' — переключить ветку, 'branches' — список веток, 'stats' — таблица, "
          "'reset' — сброс, пустая строка или 'exit' — выход.\n")
    while True:
        user = input(f"[{agent.strategy}/{agent.current_branch}] Ты: ").strip()
        if user == "" or user.lower() == "exit":
            break
        command = user.lower()
        if command == "reset":
            agent.reset()
            print("\n[Память очищена, история удалена]\n")
            continue
        if command == "stats":
            print()
            print_dialog_stats(agent)
            continue
        if command == "facts":
            print_facts(agent)
            continue
        if command == "branches":
            print_branches(agent)
            continue
        if command == "checkpoint":
            count = agent.make_checkpoint()
            print(f"\n[Checkpoint сохранён на {count} сообщениях. "
                  f"'branch <имя>' создаст ветку от этой точки.]\n")
            continue
        if command.startswith("strategy"):
            parts = user.split()
            if len(parts) == 2 and agent.set_strategy(parts[1].lower()):
                print(f"\n[Стратегия → {agent.strategy}]\n")
            else:
                print(f"\n[Формат: strategy {'|'.join(STRATEGIES)}]\n")
            continue
        if command.startswith("window"):
            parts = user.split()
            if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) > 0:
                agent.window_n = int(parts[1])
                agent.save()
                print(f"\n[Окно N → {agent.window_n}]\n")
            else:
                print("\n[Формат: window N, например window 4]\n")
            continue
        if command.startswith("branch "):
            name = user.split(maxsplit=1)[1].strip()
            agent.branch(name)
            origin = "checkpoint" if agent.checkpoint is not None else "текущей точки"
            print(f"\n[Ветка '{name}' создана от {origin} ({len(agent.messages)} сообщений), "
                  f"переключился на неё]\n")
            continue
        if command.startswith("switch "):
            name = user.split(maxsplit=1)[1].strip()
            if agent.switch(name):
                print(f"\n[Переключился на ветку '{name}' ({len(agent.messages)} сообщений)]\n")
            else:
                print(f"\n[Ветки '{name}' нет. 'branches' — список.]\n")
            continue
        print(f"\nАгент: {agent.ask(user)}\n")
        print_turn_stats(agent)


if __name__ == "__main__":
    main()
