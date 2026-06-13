import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent10 import Agent

SYSTEM = (
    "Ты — вдумчивый аналитик, помогаешь собрать техническое задание. "
    "Опираешься на ранее сказанное, не выдумываешь. Отвечай кратко, по-русски."
)
WINDOW_N = 4
SPEC_MESSAGES = [
    "Делаем мобильное приложение доставки еды. Бюджет проекта — 500 тысяч рублей.",
    "Срок — 3 месяца, релиз строго к 1 сентября.",
    "Платформа только Android, минимальная версия — Android 9.",
    "Оплата через ЮKassa, наличные не поддерживаем.",
    "Фирменный цвет — зелёный #2E7D32, интерфейс в тёмной теме.",
    "Нужен экран каталога ресторанов с фильтрами по типу кухни.",
    "Добавь избранное и историю заказов пользователя.",
    "Push-уведомления о статусе заказа обязательны.",
    "Нужна поддержка промокодов на скидку.",
    "Авторизация по номеру телефона через СМС-код.",
    "На главном экране — карта с адресами ресторанов.",
    "Раздел отзывов и рейтинга ресторанов с оценкой по пятибалльной шкале.",
]
CONTROL_QUESTIONS = [
    "Напомни точно: какой бюджет, какой срок релиза и на какой платформе делаем проект?",
    "Какой фирменный цвет и способ оплаты мы выбрали?",
]


def asks_cost(agent):
    return sum(t["cost_rub"] for t in agent.turns)


def asks_prompt_tokens(agent):
    return sum(t["prompt_tokens"] for t in agent.turns if t["kind"] == "ask")


def facts_cost(agent):
    return sum(t["cost_rub"] for t in agent.turns if t["kind"] == "facts")


def run_strategy(name, history_path):
    history_path.unlink(missing_ok=True)
    agent = Agent(system=SYSTEM, history_path=history_path, window_n=WINDOW_N, strategy=name)
    for text in SPEC_MESSAGES:
        agent.ask(text)
    answers = []
    for question in CONTROL_QUESTIONS:
        answers.append(agent.ask(question))
    return agent, answers


def run_branching_independence(history_path):
    history_path.unlink(missing_ok=True)
    agent = Agent(system=SYSTEM, history_path=history_path, strategy="branching")
    agent.ask("Делаем мобильное приложение, помоги выбрать стек разработки.")
    agent.make_checkpoint()
    agent.branch("android")
    agent.ask("Решение зафиксировано: платформа — только Android, язык Kotlin.")
    agent.branch("ios")
    agent.ask("Решение зафиксировано: платформа — только iOS, язык Swift.")
    question = "Какую платформу и язык мы выбрали в этой ветке? Ответь одной строкой."
    agent.switch("android")
    android_answer = agent.ask(question)
    agent.switch("ios")
    ios_answer = agent.ask(question)
    history_path.unlink(missing_ok=True)
    return android_answer, ios_answer


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    here = Path(__file__).parent
    print(f"Сценарий сбора ТЗ: {len(SPEC_MESSAGES)} реплик, окно N={WINDOW_N} "
          f"(важные факты — в первых сообщениях, вне окна).\n")

    results = {}
    for name in ("sliding", "facts", "branching"):
        path = here / f"compare10_{name}.json"
        agent, answers = run_strategy(name, path)
        results[name] = (agent, answers)
        path.unlink(missing_ok=True)

    for index, question in enumerate(CONTROL_QUESTIONS):
        print("=" * 80)
        print(f"\nКОНТРОЛЬНЫЙ ВОПРОС: {question}\n")
        for name in ("sliding", "facts", "branching"):
            agent, answers = results[name]
            print(f"--- {name}")
            print(f"    {answers[index]}\n")

    print("=" * 80)
    print("\nРАСХОД ЗА ВЕСЬ ПРОГОН (12 реплик ТЗ + 2 контрольных):\n")
    print(f"{'стратегия':>10} | {'вход всего, ток.':>16} | {'facts-вызовы ₽':>14} | {'итого ₽':>9}")
    for name in ("sliding", "facts", "branching"):
        agent, _ = results[name]
        print(f"{name:>10} | {asks_prompt_tokens(agent):>16} | "
              f"{facts_cost(agent):>14.4f} | {asks_cost(agent):>9.4f}")

    print("\nFacts, накопленные стратегией facts (gpt-4o-mini):")
    facts_agent = results["facts"][0]
    for key, value in facts_agent.facts.items():
        print(f"  {key}: {value}")
    print()

    print("=" * 80)
    print("\nВЕТВЛЕНИЕ: независимость двух веток от одного checkpoint\n")
    print("Общий старт → checkpoint → ветка 'android' (Kotlin) и ветка 'ios' (Swift), "
          "затем обеим один и тот же вопрос:\n")
    android_path = here / "compare10_branch.json"
    android_answer, ios_answer = run_branching_independence(android_path)
    print(f"--- ветка android\n    {android_answer}\n")
    print(f"--- ветка ios\n    {ios_answer}\n")
    print("Ветки расходятся от общей точки и не видят решений друг друга — "
          "контексты независимы.\n")


if __name__ == "__main__":
    main()
