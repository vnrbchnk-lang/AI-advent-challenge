import json

from rag.llm import chat, MAIN_MODEL
from rag.retrieval import retrieve

NO_RAG_SYSTEM = (
    "Ты ассистент разработчика. Отвечай на вопрос кратко, на русском. "
    "Если не знаешь точного ответа про конкретный проект — отвечай из общих знаний."
)

RAG_SYSTEM = (
    "Ты ассистент по базе знаний проекта «Личная культура» (хакатон). Отвечай ТОЛЬКО на основе "
    "приложенных фрагментов базы. Ничего не выдумывай сверх них. Каждый факт бери из фрагментов. "
    "Верни строго JSON:\n"
    '{"answer": "ответ на русском, 2-6 предложений", '
    '"sources": [{"chunk_id": "...", "reason": "что взято из этого фрагмента"}], '
    '"quotes": [{"chunk_id": "...", "text": "дословная цитата из фрагмента, 1-2 предложения"}]}\n'
    "В sources и quotes указывай только реально использованные chunk_id из приложенных. "
    "Цитаты копируй ДОСЛОВНО, символ в символ."
)

REFUSAL = (
    "В базе знаний нет достаточно релевантного ответа на этот вопрос. "
    "Уточни формулировку или спроси о том, что описано в документах проекта."
)


def _context_block(final_hits):
    return "\n\n".join(
        f"=== chunk_id: {chunk['chunk_id']}\n"
        f"документ: {chunk['title']} | секция: {chunk['section']} | файл: {chunk['source']}\n"
        f"{chunk['text']}"
        for _, chunk in final_hits
    )


def answer_no_rag(question):
    return chat(
        [{"role": "system", "content": NO_RAG_SYSTEM}, {"role": "user", "content": question}],
        model=MAIN_MODEL,
    )


def _validate_quotes(quotes, chunks_by_id):
    validated = []
    for quote in quotes:
        chunk = chunks_by_id.get(quote.get("chunk_id"))
        text = (quote.get("text") or "").strip()
        normalized_chunk = " ".join(chunk["text"].split()) if chunk else ""
        ok = bool(text) and " ".join(text.split()) in normalized_chunk
        validated.append({**quote, "verified": ok})
    return validated


def generate_answer(question, result, history_messages=None):
    if not result["final"]:
        return {"status": "no_context", "answer": REFUSAL, "sources": [], "quotes": [],
                "retrieval": result}
    context = _context_block(result["final"])
    messages = [{"role": "system", "content": RAG_SYSTEM}]
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": f"Фрагменты базы:\n{context}\n\nВопрос: {question}"})
    raw = chat(messages, model=MAIN_MODEL, json_mode=True)
    payload = json.loads(raw)
    chunks_by_id = {chunk["chunk_id"]: chunk for _, chunk in result["final"]}
    sources = []
    for source in payload.get("sources", []):
        chunk = chunks_by_id.get(source.get("chunk_id"))
        if chunk:
            sources.append({
                "chunk_id": chunk["chunk_id"],
                "source": chunk["source"],
                "title": chunk["title"],
                "section": chunk["section"],
                "reason": source.get("reason", ""),
            })
    quotes = _validate_quotes(payload.get("quotes", []), chunks_by_id)
    return {
        "status": "ok",
        "answer": payload.get("answer", ""),
        "sources": sources,
        "quotes": quotes,
        "retrieval": result,
    }


def answer_rag(question, index, settings=None, history_text="", history_messages=None):
    result = retrieve(index, question, settings, history_text)
    return generate_answer(question, result, history_messages)
