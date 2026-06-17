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

> Ключ ProxyAPI должен быть с балансом — запросы платные.

## Запуск агентов (недели 2–3)

Агенты недель 2–3 ставятся как пакеты с глобальной командой. `pip install -e` сам
создаёт команду (`agent6`…`agent11`) в каталоге скриптов pip — отдельная настройка PATH
обычно не нужна, команда работает из любой папки.

```powershell
$env:PROXYAPI_KEY = "<ваш ключ>"

# Неделя 2 (каждый день — свой пакет и своя команда agent6..agent10):
pip install -e week2/day6     # -> команда agent6
pip install -e week2/day10    # -> команда agent10
agent10

# Неделя 3 (единый растущий пакет, команда agent11):
pip install -e week3          # ставит requests, rich, prompt_toolkit + команду agent11
agent11
```

Если каталог скриптов pip не на PATH (команда `agent11` не находится) — запуск модулем:

```powershell
python -m assistant.cli11     # из папки week3
```

Память агентов (история диалога, слои памяти) хранится локально в JSON рядом с кодом и
в репозиторий не коммитится (см. `.gitignore`); свежий клон стартует с пустой памятью.

Подробный контекст проекта и журнал по дням — в [`CLAUDE.md`](CLAUDE.md) и
`JOURNAL-week1/2/3.md`.
