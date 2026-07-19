import fnmatch
import re
from pathlib import Path

from devassist import config

SECRET_RULES = [re.compile(pattern) for pattern in config.SECRET_PATTERNS]


def _denied(path, base):
    relative = path.relative_to(base)
    if any(part in config.DENY_DIRS or part.endswith(".egg-info") for part in relative.parts):
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in config.DENY_GLOBS)


def _first_heading(text, fallback):
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def _has_secret(text):
    return any(rule.search(text) for rule in SECRET_RULES)


def collect(project):
    spec = config.PROJECTS[project]
    root = spec["root"]
    documents = []
    skipped = []
    seen = set()
    for kind, base_name, patterns in spec["sources"]:
        base = Path(base_name) if root is None or Path(base_name).is_absolute() else root / base_name
        if not base.exists():
            skipped.append({"path": str(base), "reason": "нет каталога"})
            continue
        for pattern in patterns:
            for path in sorted(base.glob(pattern)):
                if not path.is_file() or path in seen:
                    continue
                seen.add(path)
                anchor = root if root else base
                try:
                    if _denied(path, anchor):
                        continue
                except ValueError:
                    pass
                text = path.read_text(encoding="utf-8", errors="replace")
                if _has_secret(text):
                    skipped.append({"path": str(path), "reason": "похоже на секрет"})
                    continue
                if not text.strip():
                    continue
                if len(text) > config.MAX_FILE_CHARS:
                    text = text[: config.MAX_FILE_CHARS]
                relative = path.relative_to(anchor).as_posix() if anchor in path.parents else path.name
                documents.append({
                    "project": project,
                    "kind": kind,
                    "path": relative,
                    "title": _first_heading(text, path.name) if path.suffix == ".md" else path.name,
                    "text": text,
                    "n_chars": len(text),
                })
    return documents, skipped
