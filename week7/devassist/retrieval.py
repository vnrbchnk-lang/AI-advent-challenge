from devassist import config, embedder
from devassist.llm import chat_json

DEFAULTS = {
    "threshold": 0.35,
    "top_n": 30,
    "top_k": 6,
    "rerank": False,
    "rerank_min": 4,
    "kinds": None,
    "path_prefix": None,
}

RERANK_SYSTEM = (
    "Ты оцениваешь релевантность фрагментов кода и документации вопросу разработчика. "
    "Для каждого фрагмента поставь целую оценку 0-10: 10 — прямо отвечает на вопрос, 0 — не по теме. "
    'Верни строго JSON вида {"scores": {"1": 7, "2": 0}} по номерам фрагментов.'
)


def _rerank(question, hits, minimum):
    numbered = "\n\n".join(
        f"[{position}] {chunk['path']} :: {chunk['section']}\n{chunk['text'][:700]}"
        for position, (_, chunk) in enumerate(hits, 1)
    )
    payload = chat_json(
        [
            {"role": "system", "content": RERANK_SYSTEM},
            {"role": "user", "content": f"Вопрос: {question}\n\nФрагменты:\n{numbered}"},
        ],
        model=config.CHEAP_MODEL,
        temperature=0,
        label="rerank",
    )
    scores = {int(key): float(value) for key, value in payload.get("scores", {}).items()}
    kept, dropped = [], []
    for position, (score, chunk) in enumerate(hits, 1):
        if scores.get(position, 0) >= minimum:
            kept.append((scores.get(position, 0), score, chunk))
        else:
            dropped.append((score, chunk))
    kept.sort(key=lambda item: item[0], reverse=True)
    return [(score, chunk) for _, score, chunk in kept], dropped, scores


def retrieve(index, question, settings=None):
    settings = {**DEFAULTS, **(settings or {})}
    vector = embedder.embed_one(question)
    raw = index.search(vector, settings["top_n"], settings["kinds"], settings["path_prefix"])
    passed = [(score, chunk) for score, chunk in raw if score >= settings["threshold"]]
    dropped_threshold = [(score, chunk) for score, chunk in raw if score < settings["threshold"]]
    dropped_rerank, llm_scores = [], {}
    if settings["rerank"] and passed:
        passed, dropped_rerank, llm_scores = _rerank(question, passed[: settings["top_n"]], settings["rerank_min"])
    return {
        "question": question,
        "settings": settings,
        "raw": raw,
        "final": passed[: settings["top_k"]],
        "dropped_threshold": dropped_threshold,
        "dropped_rerank": dropped_rerank,
        "llm_scores": llm_scores,
        "best_score": raw[0][0] if raw else 0.0,
    }


def label(chunk):
    parts = [chunk["path"]]
    if chunk["section"]:
        parts.append(chunk["section"])
    return " :: ".join(parts)


def format_context(hits):
    blocks = []
    for position, (score, chunk) in enumerate(hits, 1):
        blocks.append(f"[{position}] {label(chunk)} (близость {score:.2f})\n{chunk['text']}")
    return "\n\n---\n\n".join(blocks)
