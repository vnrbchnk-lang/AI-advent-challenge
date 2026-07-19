import json

from devassist import config
from devassist.llm import complete

AGENT_SYSTEM = (
    "Ты — инженер-ассистент, который работает с файлами проекта сам. Тебе дают ЦЕЛЬ, а не список "
    "шагов: сам решаешь, какие инструменты вызвать и в каком порядке. "
    "Инструменты вида project__* работают с репозиториями, rag_search ищет по документации и коду. "
    "Правила: "
    "1) сначала разберись в фактах — читай, ищи, грепай, не угадывай; "
    "2) любые правки файлов делай ТОЛЬКО в проекте sandbox, живые репозитории защищены и запись в них "
    "будет отклонена; "
    "3) не выдумывай пути и содержимое — если файла нет, скажи об этом; "
    "4) не повторяй один и тот же вызов с теми же аргументами; "
    "5) когда цель достигнута — верни финальный отчёт на русском: что искал, что нашёл "
    "(с путями и строками), что изменил или создал, и что осталось человеку."
)

MAX_TOOL_RESULT_CHARS = 6000


def _shrink(payload):
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return text[:MAX_TOOL_RESULT_CHARS] + "… (результат обрезан)"


def run_goal(assistant, goal, tool_names=None, max_steps=14, on_step=None, extra=""):
    names = tool_names or assistant.registry.names(prefixes=["project__", "rag_search"])
    specs = assistant.registry.specs(names)
    messages = [
        {"role": "system", "content": AGENT_SYSTEM},
        {"role": "user", "content": f"ЦЕЛЬ: {goal}" + (f"\n\nДополнительно: {extra}" if extra else "")},
    ]
    steps = []
    for step in range(max_steps):
        message = complete(messages, model=config.MAIN_MODEL, temperature=0.1,
                           tools=specs, label="task-agent")
        calls = message.get("tool_calls") or []
        messages.append({
            "role": "assistant",
            "content": message.get("content") or "",
            **({"tool_calls": calls} if calls else {}),
        })
        if not calls:
            return {"goal": goal, "answer": (message.get("content") or "").strip(),
                    "steps": steps, "stopped": "готово"}
        for call in calls:
            name = call["function"]["name"]
            try:
                arguments = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            outcome = assistant.executor.safe_call(name, arguments)
            payload = outcome["result"] if outcome["ok"] else {"error": outcome["error"]}
            record = {"step": step + 1, "tool": name, "arguments": arguments,
                      "ok": outcome["ok"],
                      "summary": outcome["error"] if not outcome["ok"] else ""}
            steps.append(record)
            if on_step:
                on_step(record)
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": _shrink(payload),
            })
    return {"goal": goal, "answer": "Достигнут лимит шагов, цель не завершена.",
            "steps": steps, "stopped": "лимит шагов"}
