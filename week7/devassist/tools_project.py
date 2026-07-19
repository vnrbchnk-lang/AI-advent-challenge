import fnmatch
import re
import subprocess
from pathlib import Path

from devassist import config

PROJECT_ROOTS = {
    "alaba": config.ALABA_ROOT,
    "advent": config.ADVENT_ROOT,
    "sandbox": config.SANDBOX / "alaba",
}
WRITABLE_PROJECTS = {"sandbox"}
MAX_DIFF_CHARS = 60_000
MAX_READ_LINES = 400


class ToolError(RuntimeError):
    pass


def root_of(project):
    if project not in PROJECT_ROOTS:
        raise ToolError(f"неизвестный проект '{project}', доступны: {', '.join(PROJECT_ROOTS)}")
    root = PROJECT_ROOTS[project]
    if not root.exists():
        raise ToolError(f"каталог проекта не найден: {root}")
    return root


def _safe_path(project, relative):
    root = root_of(project)
    target = (root / relative).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise ToolError(f"путь вне проекта запрещён: {relative}")
    return target


def _git(project, *args, check=True):
    root = root_of(project)
    result = subprocess.run(
        ["git", "--no-pager", *args],
        cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, timeout=60,
    )
    if check and result.returncode != 0:
        raise ToolError(f"git {' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def git_branch(project="alaba"):
    branch = _git(project, "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = _git(project, "rev-parse", "--short", "HEAD").strip()
    subject = _git(project, "log", "-1", "--pretty=%s").strip()
    dirty = bool(_git(project, "status", "--porcelain").strip())
    return {"project": project, "branch": branch, "head": head, "last_commit": subject, "dirty": dirty}


def git_status(project="alaba"):
    entries = []
    for line in _git(project, "status", "--porcelain").splitlines():
        if line.strip():
            entries.append({"status": line[:2].strip(), "path": line[3:].strip()})
    return {"project": project, "changed": len(entries), "files": entries}


def git_log(project="alaba", days=7, limit=40):
    output = _git(project, "log", f"--since={int(days)}.days", f"-{int(limit)}",
                  "--pretty=%h|%ad|%an|%s", "--date=short")
    commits = []
    for line in output.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append({"hash": parts[0], "date": parts[1], "author": parts[2], "subject": parts[3]})
    return {"project": project, "days": days, "count": len(commits), "commits": commits}


def git_diff(project="alaba", base="", head="", max_chars=MAX_DIFF_CHARS, fallback=True):
    if base and head:
        args = ["diff", f"{base}...{head}"]
    elif base:
        args = ["diff", base]
    else:
        args = ["diff", "HEAD"]
    diff = _git(project, *args)
    label = " ".join(args[1:]) or "HEAD"
    if not diff.strip() and not base and fallback:
        diff = _git(project, "show", "HEAD", "--pretty=format:%h %s")
        label = "HEAD (последний коммит, незакоммиченных правок нет)"
    names = re.findall(r"^\+\+\+ b/(.+)$", diff, flags=re.MULTILINE)
    truncated = len(diff) > max_chars
    return {
        "project": project,
        "range": label,
        "files": sorted(set(names)),
        "truncated": truncated,
        "diff": diff[:max_chars],
    }


def list_files(project="alaba", pattern="**/*", limit=200):
    root = root_of(project)
    found = []
    for path in sorted(root.glob(pattern)):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in config.DENY_DIRS for part in relative.parts):
            continue
        if any(fnmatch.fnmatch(path.name, deny) for deny in config.DENY_GLOBS):
            continue
        found.append({"path": relative.as_posix(), "size": path.stat().st_size})
        if len(found) >= limit:
            break
    return {"project": project, "pattern": pattern, "count": len(found), "files": found}


def read_file(project="alaba", path="README.md", start=1, end=0):
    target = _safe_path(project, path)
    if not target.is_file():
        raise ToolError(f"файл не найден: {path}")
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, int(start))
    end = int(end) if end else min(len(lines), start + MAX_READ_LINES - 1)
    end = min(end, len(lines), start + MAX_READ_LINES - 1)
    body = "\n".join(f"{number}: {lines[number - 1]}" for number in range(start, end + 1))
    return {"project": project, "path": path, "start": start, "end": end,
            "total_lines": len(lines), "content": body}


def grep(project="alaba", pattern="TODO", glob="**/*", limit=60, ignore_case=True):
    root = root_of(project)
    flags = re.IGNORECASE if ignore_case else 0
    try:
        rule = re.compile(pattern, flags)
    except re.error as error:
        raise ToolError(f"плохое регулярное выражение: {error}")
    matches = []
    for path in sorted(root.glob(glob)):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in config.DENY_DIRS for part in relative.parts):
            continue
        if any(fnmatch.fnmatch(path.name, deny) for deny in config.DENY_GLOBS):
            continue
        if path.stat().st_size > config.MAX_FILE_CHARS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if rule.search(line):
                matches.append({"path": relative.as_posix(), "line": number, "text": line.strip()[:200]})
                if len(matches) >= limit:
                    return {"project": project, "pattern": pattern, "count": len(matches),
                            "truncated": True, "matches": matches}
    return {"project": project, "pattern": pattern, "count": len(matches),
            "truncated": False, "matches": matches}


def _guard_write(project):
    if project not in WRITABLE_PROJECTS:
        raise ToolError(
            f"запись в проект '{project}' запрещена: это живой репозиторий. "
            f"Разрешена запись только в {', '.join(WRITABLE_PROJECTS)}"
        )


def write_file(project="sandbox", path="", content=""):
    _guard_write(project)
    target = _safe_path(project, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.is_file()
    target.write_text(content, encoding="utf-8")
    return {"project": project, "path": path, "created": not existed, "n_chars": len(content)}


def replace_in_file(project="sandbox", path="", old="", new=""):
    _guard_write(project)
    target = _safe_path(project, path)
    if not target.is_file():
        raise ToolError(f"файл не найден: {path}")
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise ToolError("исходный фрагмент не найден в файле")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    return {"project": project, "path": path, "replaced": True}


def sandbox_prepare(reset=False):
    target = config.SANDBOX / "alaba"
    config.SANDBOX.mkdir(parents=True, exist_ok=True)
    if target.exists() and reset:
        _git("sandbox", "reset", "--hard", "HEAD")
        _git("sandbox", "clean", "-fd")
        return {"path": str(target), "action": "reset"}
    if target.exists():
        return {"path": str(target), "action": "exists"}
    result = subprocess.run(
        ["git", "clone", "--depth", "50", str(config.ALABA_ROOT), str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise ToolError(f"git clone: {result.stderr.strip()}")
    return {"path": str(target), "action": "cloned"}


def sandbox_diff():
    _git("sandbox", "add", "-N", ".")
    return git_diff("sandbox", fallback=False)
