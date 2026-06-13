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
DETAIL_CHECKS = {
    0: [("бюджет 500 тыс.", ["500"]),
        ("платформа Android", ["android"]),
        ("срок 1 сентября", ["сентябр", "1.09", "01.09"])],
    1: [("цвет #2E7D32", ["2e7d32"]),
        ("оплата ЮKassa", ["kassa", "касс"])],
}
STRATEGY_DESC = {
    "sliding": "Sliding Window — в запрос идут только последние N сообщений, старее окна отбрасывается.",
    "facts": "Sticky Facts — отдельный KV-блок (gpt-4o-mini обновляет после каждой реплики) + последние N сообщений.",
    "branching": "Branching — в запрос идёт ВСЯ история текущей ветки (без обрезки); фишка — ветви диалога.",
}
SEP = "=" * 78
SUB = "-" * 78


def asks_cost(agent):
    return sum(t["cost_rub"] for t in agent.turns)


def asks_prompt_tokens(agent):
    return sum(t["prompt_tokens"] for t in agent.turns if t["kind"] == "ask")


def asks_total_tokens(agent):
    return sum(t["total_tokens"] for t in agent.turns)


def facts_cost(agent):
    return sum(t["cost_rub"] for t in agent.turns if t["kind"] == "facts")


def detail_report(answer, question_index):
    low = answer.lower()
    kept, lost = [], []
    for label, variants in DETAIL_CHECKS[question_index]:
        if any(v in low for v in variants):
            kept.append(label)
        else:
            lost.append(label)
    return kept, lost


def kept_total(answers):
    total = 0
    for index in DETAIL_CHECKS:
        kept, _ = detail_report(answers[index], index)
        total += len(kept)
    return total


def total_details():
    return sum(len(v) for v in DETAIL_CHECKS.values())


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


def print_intro():
    print(SEP)
    print("ДЕНЬ 10 — СРАВНЕНИЕ 3 СТРАТЕГИЙ УПРАВЛЕНИЯ КОНТЕКСТОМ")
    print(SEP)
    print("\nЧТО СРАВНИВАЕМ (одинаковый диалог через каждую стратегию):")
    for name in ("sliding", "facts", "branching"):
        print(f"  • {STRATEGY_DESC[name]}")
    print(f"\nСЦЕНАРИЙ: собираем ТЗ на приложение — {len(SPEC_MESSAGES)} реплик. "
          f"Размер окна N = {WINDOW_N}.")
    print("Важные факты названы в ПЕРВЫХ сообщениях (поэтому к концу диалога")
    print(f"они оказываются ВНЕ окна последних {WINDOW_N} сообщений):")
    for label, _ in DETAIL_CHECKS[0] + DETAIL_CHECKS[1]:
        print(f"  - {label}")
    print("\nЗатем задаём 2 контрольных вопроса про эти ранние факты и смотрим,")
    print("какая стратегия их вспомнит, а какая забудет — и сколько это стоило.\n")


def print_question_block(results, index):
    print(SEP)
    print(f"КОНТРОЛЬНЫЙ ВОПРОС {index + 1}: {CONTROL_QUESTIONS[index]}")
    print(SEP)
    for name in ("sliding", "facts", "branching"):
        _, answers = results[name]
        kept, lost = detail_report(answers[index], index)
        verdict = f"сохранил {len(kept)}/{len(kept) + len(lost)} деталей"
        if lost:
            verdict += f"; ПОТЕРЯЛ: {', '.join(lost)}"
        print(f"\n[{name}] → {verdict}")
        print(f"    {answers[index].strip()}")
    print()


def print_cost_table(results):
    print(SEP)
    print("РАСХОД И ПАМЯТЬ ПО СТРАТЕГИЯМ")
    print(f"(весь прогон: {len(SPEC_MESSAGES)} реплик ТЗ + {len(CONTROL_QUESTIONS)} контрольных вопроса)")
    print(SEP)
    print(f"\n{'стратегия':>10} | {'вход, ток.':>10} | {'все ток.':>9} | {'facts ₽':>8} | "
          f"{'итого ₽':>9} | {'помнит факты':>12}")
    print(SUB)
    for name in ("sliding", "facts", "branching"):
        agent, answers = results[name]
        memory = f"{kept_total(answers)}/{total_details()}"
        print(f"{name:>10} | {asks_prompt_tokens(agent):>10} | {asks_total_tokens(agent):>9} | "
              f"{facts_cost(agent):>8.4f} | {asks_cost(agent):>9.4f} | {memory:>12}")
    print("\n«вход, ток.» — сумма входных токенов всех запросов к главной модели "
          "(чем больше истории шлём, тем выше).")
    print("«facts ₽» — отдельная цена вызовов дешёвой gpt-4o-mini, что ведёт KV (только у facts).")
    print("«помнит факты» — сколько ранних деталей стратегия вспомнила в контрольных ответах.\n")


def print_facts(results):
    print(SUB)
    print("FACTS, накопленные стратегией facts (KV от gpt-4o-mini):")
    print(SUB)
    facts_agent = results["facts"][0]
    for key, value in facts_agent.facts.items():
        print(f"  {key}: {value}")
    print()


def print_conclusions(results):
    print(SEP)
    print("ВЫВОДЫ ПО 4 КРИТЕРИЯМ ТЗ")
    print(SEP)
    cheapest = min(("sliding", "facts", "branching"), key=lambda n: asks_cost(results[n][0]))
    print(f"\n1) КАЧЕСТВО ОТВЕТА:")
    print(f"   sliding — теряет ранние факты (вне окна), честно отвечает «не зафиксировано».")
    print(f"   facts   — отвечает верно, опираясь на компактный KV.")
    print(f"   branching — отвечает верно и подробнее всех (видит всю историю ветки).")
    print(f"\n2) СТАБИЛЬНОСТЬ (не теряет ли детали) — счёт «помнит факты» из таблицы:")
    for name in ("sliding", "facts", "branching"):
        print(f"   {name:>9}: {kept_total(results[name][1])}/{total_details()}")
    print(f"\n3) РАСХОД ТОКЕНОВ/ДЕНЕГ:")
    for name in ("sliding", "facts", "branching"):
        print(f"   {name:>9}: {asks_cost(results[name][0]):.4f} ₽ "
              f"(вход {asks_prompt_tokens(results[name][0])} ток.)")
    print(f"   → дешевле всех: {cheapest}.")
    print(f"\n4) УДОБСТВО ДЛЯ ПОЛЬЗОВАТЕЛЯ:")
    print(f"   sliding   — проще всего, но забывает всё вне окна → плохо для долгого диалога.")
    print(f"   facts     — баланс: помнит ключевое и дёшево, но теряет дословность/нюансы.")
    print(f"   branching — ничего не теряет и даёт ветки под альтернативы, но дороже всех.")
    print()


def print_branching(here):
    print(SEP)
    print("ВЕТВЛЕНИЕ: независимость двух веток от одного checkpoint")
    print(SEP)
    print("\nОбщий старт → checkpoint → от одной точки создаём 2 ветки:")
    print("  ветка 'android' (Kotlin)  и  ветка 'ios' (Swift).")
    print("Затем задаём ОБЕИМ один и тот же вопрос «что мы выбрали в этой ветке?»:\n")
    android_answer, ios_answer = run_branching_independence(here / "compare10_branch.json")
    print(f"[ветка android]\n    {android_answer.strip()}\n")
    print(f"[ветка ios]\n    {ios_answer.strip()}\n")
    print("Каждая ветка помнит только своё решение и не видит решения соседней —")
    print("контексты полностью независимы. Это и есть ветвление диалога.\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    here = Path(__file__).parent
    print_intro()

    results = {}
    for name in ("sliding", "facts", "branching"):
        path = here / f"compare10_{name}.json"
        results[name] = run_strategy(name, path)
        path.unlink(missing_ok=True)

    for index in range(len(CONTROL_QUESTIONS)):
        print_question_block(results, index)
    print_cost_table(results)
    print_facts(results)
    print_conclusions(results)
    print_branching(here)


if __name__ == "__main__":
    main()
