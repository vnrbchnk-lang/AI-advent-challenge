import re
from pathlib import Path

from pypdf import PdfReader

ALABA = Path("C:/Alaba")
DOCS = Path(__file__).resolve().parent / "docs"

SOURCES = [
    ("memory-bank", ALABA / ".memory-bank", "*.md"),
    ("readme", ALABA, "README.md"),
    ("raw-txt", ALABA / "raw", "*.txt"),
    ("raw-pdf", ALABA / "raw", "*.pdf"),
]


def _slug(path):
    stem = re.sub(r"[^\w\-]+", "_", path.stem, flags=re.UNICODE).strip("_")
    return stem or "doc"


def _pdf_to_markdown(path):
    reader = PdfReader(str(path))
    parts = [f"# {path.stem}"]
    for number, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if text:
            parts.append(f"## Страница {number}\n\n{text}")
    return "\n\n".join(parts)


def _txt_to_markdown(path):
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return f"# {path.stem}\n\n{text}"


def _first_heading(text, fallback):
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def collect():
    DOCS.mkdir(parents=True, exist_ok=True)
    for old in DOCS.glob("*.md"):
        old.unlink()
    documents = []
    for group, base, pattern in SOURCES:
        for path in sorted(base.rglob(pattern) if group == "memory-bank" else base.glob(pattern)):
            if path.suffix == ".pdf":
                text = _pdf_to_markdown(path)
            elif path.suffix == ".txt":
                text = _txt_to_markdown(path)
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
            name = f"{group}__{_slug(path)}.md"
            (DOCS / name).write_text(text, encoding="utf-8")
            documents.append({
                "file": name,
                "group": group,
                "origin": str(path),
                "title": _first_heading(text, path.stem),
                "n_chars": len(text),
            })
    return documents


def load_documents():
    documents = []
    for path in sorted(DOCS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        group = path.name.split("__", 1)[0]
        documents.append({
            "file": path.name,
            "group": group,
            "title": _first_heading(text, path.stem),
            "text": text,
        })
    return documents
