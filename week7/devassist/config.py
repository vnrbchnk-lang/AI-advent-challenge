import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
WEEK7 = PACKAGE.parent
STORE = PACKAGE / "store"
DATA = WEEK7 / "data"
OUT = WEEK7 / "out"
SANDBOX = WEEK7 / "sandbox"

ADVENT_ROOT = Path(os.environ.get("ADVENT_ROOT", WEEK7.parent))
ALABA_ROOT = Path(os.environ.get("ALABA_ROOT", "C:/Alaba"))

API_BASE = "https://api.proxyapi.ru/openai/v1"
CHAT_URL = f"{API_BASE}/chat/completions"
EMBED_URL = f"{API_BASE}/embeddings"

MAIN_MODEL = "gpt-4.1"
CHEAP_MODEL = "gpt-4o-mini"
EMBED_MODEL = "text-embedding-3-small"

PRICE_RUB_PER_MTOK = {
    "gpt-4.1": (516.0, 2062.0),
    "gpt-4o-mini": (39.0, 155.0),
    "text-embedding-3-small": (5.16, 0.0),
}

DENY_DIRS = {
    ".git", "node_modules", "build", "dist", ".dart_tool", ".idea", ".vscode",
    "__pycache__", ".venv", "venv", "coverage", ".figtmp", "logs", "store", "sandbox",
}
DENY_GLOBS = [".env*", "*.lock", "package-lock.json", "*.freezed.dart", "*.g.dart", "*.min.js"]

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9_\-]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*[\"'][^\"'\s]{16,}[\"']",
]

MAX_FILE_CHARS = 120_000

PROJECTS = {
    "alaba": {
        "title": "Личная культура (Flutter + NestJS)",
        "root": ALABA_ROOT,
        "sources": [
            ("doc", ".", ["README.md", "AGENTS.md"]),
            ("doc", ".memory-bank", ["**/*.md"]),
            ("doc", "content", ["README.md"]),
            ("schema", "server/prisma", ["schema.prisma", "migrations/**/*.sql"]),
            ("schema", "shared/generated", ["*.json"]),
            ("schema", "content", ["*.schema.json"]),
            ("code", "server/src", ["**/*.ts"]),
            ("code", "shared/src", ["**/*.ts"]),
            ("code", "app/lib", ["**/*.dart"]),
        ],
    },
    "advent": {
        "title": "AI Advent Challenge (недели 1-7)",
        "root": ADVENT_ROOT,
        "sources": [
            ("doc", ".", ["CLAUDE.md", "README.md", "JOURNAL-week*.md"]),
            ("code", "week1", ["**/*.py"]),
            ("code", "week2", ["**/*.py"]),
            ("code", "week3", ["**/*.py"]),
            ("code", "week4", ["**/*.py"]),
            ("code", "week5", ["**/*.py"]),
            ("code", "week6", ["**/*.py"]),
            ("code", "week7", ["**/*.py"]),
        ],
    },
    "support": {
        "title": "База поддержки пользователей",
        "root": None,
        "sources": [
            ("doc", str(DATA), ["faq.md"]),
            ("doc", str(ALABA_ROOT / ".memory-bank" / "product-overview"), ["*.md"]),
        ],
    },
}

PUBLIC_INDEXES = {"advent"}
