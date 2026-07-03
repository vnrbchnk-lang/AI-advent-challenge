QUESTIONS = [
    {
        "question": "Как работает механика травмы и смерти карты?",
        "expectation": "Показатель до 0 — травма (смерть в конце 2 ходов до паса); два показателя 0 — смерть сразу; травму снимает лечение; в дуэли при силе 0 — смерть без травмы",
        "expected_sources": ["game-rules"],
    },
    {
        "question": "Какой размер колоды и лимиты по редкости карт?",
        "expectation": "25 карт; серебряных максимум 7, золотых 5, бронзовых без ограничения; 4 фракции",
        "expected_sources": ["game-rules"],
    },
    {
        "question": "Какой технологический стек у клиента и бэкенда проекта?",
        "expectation": "Клиент Flutter/Dart (+Flame), бэкенд NestJS/Node/TypeScript, PostgreSQL + Prisma, Redis, WebSocket",
        "expected_sources": ["stack-and-architecture", "readme"],
    },
    {
        "question": "Кто целевая аудитория игры «Личная культура»?",
        "expectation": "Студенты ССУЗ/вузов 16-24 лет, RU-only",
        "expected_sources": ["product-overview", "readme"],
    },
    {
        "question": "Что решили с пушем в GitVerse?",
        "expectation": "Репо переименован в studentlabs/personal_culture_mobile, remote обновлён, запушено; починены права ssh-ключа и core.sshCommand",
        "expected_sources": ["current-tasks"],
    },
    {
        "question": "Какие игровые режимы актуальны после созвона 3 июля?",
        "expectation": "Пересмотр режимов по созвону 03.07.2026: батл/PvP в приоритете, одиночная игра (арена) отложена на MVP+",
        "expected_sources": ["game-rules", "customer-userflow-sync", "product-overview"],
    },
    {
        "question": "Какие ограничения из-за RU-only накладываются на сервисы?",
        "expectation": "Без Google/Apple-сервисов: RuStore (Pay/Push), VK ID, Yandex AppMetrica, Yandex Cloud",
        "expected_sources": ["readme", "product-overview", "stack-and-architecture"],
    },
    {
        "question": "Что означает принцип «сервер-авторитет» в проекте?",
        "expectation": "Валюта, RNG, квизы, исход дуэлей считаются на сервере; клиент не доверенный",
        "expected_sources": ["readme", "stack-and-architecture", "development-conventions"],
    },
    {
        "question": "Что ментор посоветовал про Memory Bank на созвоне 26 июня?",
        "expectation": "Советы ментора по ведению memory bank как ядра знаний агента (созвон 26.06.2026)",
        "expected_sources": ["mentor-ai-weekly", "ai-workflow"],
    },
    {
        "question": "Как устроен pack-opening UX по итогам ресёрча?",
        "expectation": "6 шагов pack-opening (источник N3TWORK) из UX-ресёрча",
        "expected_sources": ["ux-research"],
    },
]


def sources_hit(expected_sources, answer_sources):
    used = " ".join(s["source"] for s in answer_sources)
    return any(marker in used for marker in expected_sources)
