import re

DOC_MAX_CHARS = 1600
SCHEMA_MAX_CHARS = 2600
CODE_WINDOW_LINES = 80
CODE_OVERLAP_LINES = 10

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _split_markdown(text):
    sections = []
    stack = []
    buffer = []

    def flush():
        body = "\n".join(buffer).strip()
        if body:
            sections.append((" / ".join(part for part in stack if part), body))

    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            flush()
            buffer = []
            level = len(match.group(1))
            stack = stack[: level - 1]
            while len(stack) < level - 1:
                stack.append("")
            stack.append(match.group(2).strip())
        else:
            buffer.append(line)
    flush()
    return sections


def _pack(body, limit):
    parts = []
    current = []
    size = 0
    for paragraph in body.split("\n\n"):
        piece = paragraph.strip()
        if not piece:
            continue
        if size + len(piece) > limit and current:
            parts.append("\n\n".join(current))
            current, size = [], 0
        if len(piece) > limit:
            for start in range(0, len(piece), limit):
                parts.append(piece[start: start + limit])
            continue
        current.append(piece)
        size += len(piece) + 2
    if current:
        parts.append("\n\n".join(current))
    return parts


def _doc_chunks(document):
    chunks = []
    for section, body in _split_markdown(document["text"]) or [("", document["text"])]:
        for piece in _pack(body, DOC_MAX_CHARS):
            chunks.append({"section": section, "lines": "", "text": piece})
    return chunks


def _schema_chunks(document):
    text = document["text"]
    if len(text) <= SCHEMA_MAX_CHARS:
        return [{"section": "", "lines": "", "text": text}]
    return [
        {"section": f"часть {number}", "lines": "", "text": text[start: start + SCHEMA_MAX_CHARS]}
        for number, start in enumerate(range(0, len(text), SCHEMA_MAX_CHARS), 1)
    ]


def _code_chunks(document):
    lines = document["text"].splitlines()
    step = CODE_WINDOW_LINES - CODE_OVERLAP_LINES
    chunks = []
    for start in range(0, max(len(lines), 1), step):
        window = lines[start: start + CODE_WINDOW_LINES]
        body = "\n".join(window).strip()
        if not body:
            continue
        first, last = start + 1, start + len(window)
        chunks.append({"section": f"строки {first}-{last}", "lines": f"{first}-{last}", "text": "\n".join(window)})
        if start + CODE_WINDOW_LINES >= len(lines):
            break
    return chunks


def chunk_documents(documents):
    builders = {"doc": _doc_chunks, "schema": _schema_chunks, "code": _code_chunks}
    chunks = []
    for document in documents:
        for piece in builders[document["kind"]](document):
            chunks.append({
                "chunk_id": len(chunks) + 1,
                "project": document["project"],
                "kind": document["kind"],
                "path": document["path"],
                "title": document["title"],
                "section": piece["section"],
                "lines": piece["lines"],
                "text": piece["text"],
                "n_chars": len(piece["text"]),
            })
    return chunks


def embed_input(chunk):
    header = f"{chunk['project']} :: {chunk['path']}"
    if chunk["section"]:
        header += f" :: {chunk['section']}"
    return f"{header}\n{chunk['text']}"
