# AI Advent Challenge #8

Учебный марафон по работе с LLM и ИИ-агентами (курс mobiledeveloper.tech).
Здесь — ежедневные задания: минимальный Python-код, обращающийся к облачной LLM по REST.

## Стек

- **LLM API:** [ProxyAPI.ru](https://proxyapi.ru) (OpenAI-совместимый формат), эндпоинт
  `https://api.proxyapi.ru/openai/v1/chat/completions`.
- **Язык:** Python + `requests`.
- **Ключ:** переменная окружения `PROXYAPI_KEY` (в код/репозиторий не коммитится).

## Запуск

```powershell
$env:PROXYAPI_KEY = "<ваш ключ>"
$env:PYTHONIOENCODING = "utf-8"   # Windows: чтобы кириллица не была кракозябрами
python week1/day1/day1.py
```

## Задания

| День | Тема | Файл |
|------|------|------|
| 1 | Первый запрос к LLM через API | `week1/day1/day1.py` |
| 2 | Контроль формата ответа (формат + длина + stop) | `week1/day2/day2.py` |
| 3 | Разные способы рассуждения (прямой / пошагово / самопромпт / эксперты) | `week1/day3/day3.py` |
| 4 | Температура (0 / 0.7 / 1.2) — точность, креативность, разнообразие | `week1/day4/day4.py` |

`chat.py` — простой консольный чат-агент с памятью диалога (вспомогательный).

Подробный контекст проекта и журнал по дням — в [`CLAUDE.md`](CLAUDE.md).
