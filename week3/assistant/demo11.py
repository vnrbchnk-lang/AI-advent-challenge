import sys

from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns

from assistant.cli11 import Assistant, SYSTEM_PROMPT
from assistant.memory import build_messages

console = Console()

PROFILE = {
    "имя": "Иван",
    "стек": "Kotlin",
    "архитектура": "только MVI, обязательная ViewModel",
    "запреты": "не использовать Python и RxJava",
}
QUESTION = "Набросай старт сервиса авторизации для нашего проекта."


def answer_with(assistant, use_long_term):
    assistant.memory.short_term = [{"role": "user", "content": QUESTION}]
    messages = build_messages(assistant.memory, SYSTEM_PROMPT,
                              use_long_term=use_long_term, use_working=False)
    answer, usage = assistant.call_api(messages)
    return answer, usage


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    assistant = Assistant()
    assistant.memory.long_term = dict(PROFILE)
    assistant.memory.working = {}

    console.print(Panel(f"Вопрос: [bold]{QUESTION}[/bold]\n\nДолговременная память (профиль): "
                        f"{PROFILE}", title="День 11 — влияние памяти на ответ", border_style="magenta"))

    off_answer, off_usage = answer_with(assistant, use_long_term=False)
    on_answer, on_usage = answer_with(assistant, use_long_term=True)

    off_panel = Panel(off_answer, title="❌ БЕЗ долговременной памяти",
                      border_style="red", subtitle=f"{off_usage['prompt_tokens']} вход. ток.")
    on_panel = Panel(on_answer, title="✅ С долговременной памятью (профиль)",
                     border_style="green", subtitle=f"{on_usage['prompt_tokens']} вход. ток.")
    console.print(Columns([off_panel, on_panel], equal=True, expand=True))
    console.print("[dim]Один и тот же вопрос. Слева профиль не подмешан — модель выбирает "
                  "ходовой вариант (обычно Python). Справа из долговременной памяти "
                  "приходит стек Kotlin/MVI и запреты — ответ другой.[/dim]")


if __name__ == "__main__":
    main()
