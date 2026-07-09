import sys
import time
from pathlib import Path

from local import localllm

WEEK5 = Path(__file__).resolve().parent.parent.parent / "week5"


def _ensure_rag_path():
    if str(WEEK5) not in sys.path:
        sys.path.insert(0, str(WEEK5))


_ensure_rag_path()

from rag.index import VectorIndex
from rag.retrieval import retrieve, DEFAULTS
from rag.rag import _context_block, answer_rag


LOCAL_RAG_SYSTEM = (
    "Ты ассистент по базе знаний проекта «Личная культура» (хакатон). Отвечай ТОЛЬКО на основе "
    "приложенных фрагментов базы, по-русски, 2-6 предложений. Ничего не выдумывай сверх фрагментов. "
    "Если во фрагментах нет ответа — так и скажи."
)


def load_index(strategy="structural"):
    if VectorIndex.exists(strategy):
        return VectorIndex.load(strategy)
    return None


def _sources(final_hits):
    return [
        {"chunk_id": chunk["chunk_id"], "source": chunk["source"],
         "title": chunk["title"], "section": chunk["section"]}
        for _, chunk in final_hits
    ]


def answer_local(question, index, settings=None, model=localllm.CHAT_MODEL,
                 temperature=0.3, num_ctx=None, num_predict=None):
    result = retrieve(index, question, settings)
    if not result["final"]:
        return {"status": "no_context", "answer": "В базе нет релевантного контекста.",
                "sources": [], "stats": None, "retrieval": result}
    context = _context_block(result["final"])
    messages = [
        {"role": "system", "content": LOCAL_RAG_SYSTEM},
        {"role": "user", "content": f"Фрагменты базы:\n{context}\n\nВопрос: {question}"},
    ]
    text, stats = localllm.chat(messages, model=model, temperature=temperature,
                                num_ctx=num_ctx, num_predict=num_predict)
    return {"status": "ok", "answer": text, "sources": _sources(result["final"]),
            "stats": stats, "retrieval": result}


def compare(question, index, settings=None):
    local_result = answer_local(question, index, settings)
    started = time.time()
    cloud_result = answer_rag(question, index, settings)
    cloud_result["seconds"] = round(time.time() - started, 2)
    return local_result, cloud_result
