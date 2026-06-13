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

Подробный контекст проекта и журнал по дням — в [`CLAUDE.md`](CLAUDE.md).
