import requests

API_URL = "https://api.proxyapi.ru/openai/v1/chat/completions"
MEMBER_MODEL = "gpt-4o-mini"
ORCHESTRATOR_MODEL = "gpt-4.1"

COUNCIL_ROLES = [
    ("Архитектор", "структура решения, слои, границы модулей, как это масштабируется"),
    ("Безопасность", "данные, доступ, секреты, валидация ввода, поверхность атаки"),
    ("Производительность", "сложность, узкие места, нагрузка, расход ресурсов"),
    ("Прагматик", "сроки и простота: минимальное решение без оверинжиниринга, что выкинуть"),
    ("Критик", "слабые места в задаче и в чужих подходах: что сломается, чего не хватает"),
]

MEMBER_SYSTEM = (
    "Ты — участник совета агентов, роль «{role}». Твоя зона ответственности: {brief}. "
    "Дают задачу и инварианты проекта. Дай короткое мнение (2-4 предложения) строго со своей позиции: "
    "что предлагаешь и на что обратить внимание. Не пиши за другие роли, не пересказывай задачу. "
    "Учитывай инварианты — не предлагай того, что их нарушает."
)

ORCHESTRATOR_SYSTEM = (
    "Ты — оркестратор совета агентов. Ты знаешь исходный запрос пользователя, его профиль и инварианты "
    "проекта. Тебе дают мнения нескольких агентов-специалистов, каждый со своей роли. Сведи их в единый "
    "план из 3-6 пунктов. Если мнения конфликтуют — выбери весомейшее и объясни выбор одной строкой. "
    "Если предложение нарушает инвариант — ОТКЛОНИ его и прямо напиши возражение и причину. "
    "Формат ответа строго такой:\nВОЗРАЖЕНИЯ: <список или «нет»>\nПЛАН:\n1. ...\n2. ..."
)


def _call(api_key, model, messages):
    response = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": messages},
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"], data["usage"]


def _accumulate(total, usage):
    total["prompt_tokens"] += usage["prompt_tokens"]
    total["completion_tokens"] += usage["completion_tokens"]


def run_council(api_key, task, invariant_items, profile_text="", roles=COUNCIL_ROLES):
    rules = "\n".join(f"{i + 1}. {it['rule']}" for i, it in enumerate(invariant_items)) or "—"
    opinions = []
    member_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    for role, brief in roles:
        text, usage = _call(api_key, MEMBER_MODEL, [
            {"role": "system", "content": MEMBER_SYSTEM.format(role=role, brief=brief)},
            {"role": "user", "content": f"ЗАДАЧА:\n{task}\n\nИНВАРИАНТЫ:\n{rules}"},
        ])
        opinions.append({"role": role, "text": text.strip()})
        _accumulate(member_usage, usage)

    joined = "\n\n".join(f"[{o['role']}]\n{o['text']}" for o in opinions)
    profile_block = f"\n\nПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:\n{profile_text}" if profile_text else ""
    orch_user = (f"ЗАПРОС ПОЛЬЗОВАТЕЛЯ:\n{task}\n\nИНВАРИАНТЫ:\n{rules}{profile_block}\n\n"
                 f"МНЕНИЯ АГЕНТОВ:\n{joined}")
    synthesis, orch_usage = _call(api_key, ORCHESTRATOR_MODEL, [
        {"role": "system", "content": ORCHESTRATOR_SYSTEM},
        {"role": "user", "content": orch_user},
    ])
    return opinions, synthesis.strip(), member_usage, orch_usage
