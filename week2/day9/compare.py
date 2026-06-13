import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "day8"))

from agent8 import Agent as RawAgent     
from agent9 import Agent as CompressingAgent

#python week2\day9\compare.py

SYSTEM = "Ты — ассистент. Отвечай кратко, по-русски, без лишних слов."
FACT_MESSAGES = [
    "Меня зовут Иван, я из Новосибирска. Ответь одним словом.",
    "Бюджет моего проекта — 50 тысяч рублей. Ответь одним словом.",
    "Созвон по проекту — в четверг в 15:00. Ответь одним словом.",
]
CHATTER_MESSAGES = [
    "Придумай короткое название для IT-проекта. Одним словом.",
    "Сколько будет 17 умножить на 23? Одним числом.",
    "Какая столица Франции? Одним словом.",
    "Сколько дней в неделе? Одним числом.",
]
CONTROL_QUESTIONS = [
    "Назови моё имя, город, бюджет проекта и время созвона. Одной строкой.",
    "Процитируй дословно моё самое первое сообщение в этом диалоге.",
]
BALLAST_TOKENS = 2000


def run_same_dialog(agent):
    for text in FACT_MESSAGES:
        agent.ask(text)
    agent.fill(BALLAST_TOKENS)
    for text in CHATTER_MESSAGES:
        agent.ask(text)


def last_question_turn(agent):
    return [t for t in agent.turns if not t.get("compress")][-1]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    here = Path(__file__).parent
    raw_path = here / "compare_raw.json"
    compressed_path = here / "compare_compressed.json"
    raw_path.unlink(missing_ok=True)
    compressed_path.unlink(missing_ok=True)
    raw = RawAgent(system=SYSTEM, history_path=raw_path)
    compressing = CompressingAgent(system=SYSTEM, history_path=compressed_path)

    print("Одинаковый диалог обоим агентам: 3 факта, балласт ~2000 токенов, болтовня...\n")
    run_same_dialog(raw)
    run_same_dialog(compressing)
    compression = compressing.last_compression or compressing.compress()
    print(f"agent9 сжал историю: {compression['removed_messages']} сообщений → summary "
          f"({compression['summary_chars']} символов), вызов {compression['cost_rub']:.4f} ₽")
    print(f"\nSUMMARY agent9: {compressing.summary}\n")

    for question in CONTROL_QUESTIONS:
        print("=" * 80)
        print(f"\nКОНТРОЛЬНЫЙ ВОПРОС: {question}\n")
        for label, agent in (("БЕЗ сжатия (agent8)", raw),
                             ("СО сжатием (agent9)", compressing)):
            answer = agent.ask(question)
            turn = last_question_turn(agent)
            print(f"--- {label} | вход {turn['prompt_tokens']} ток. | ход {turn['cost_rub']:.4f} ₽")
            print(f"    {answer}\n")

    compression_cost = sum(t["cost_rub"] for t in compressing.turns if t.get("compress"))
    print("=" * 80)
    print(f"\nИтого за весь прогон: БЕЗ сжатия {raw.total_spent_rub():.4f} ₽ | "
          f"СО сжатием {compressing.total_spent_rub():.4f} ₽ "
          f"(из них на сжатие {compression_cost:.4f} ₽)")
    raw_path.unlink(missing_ok=True)
    compressed_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
