import time

import numpy as np
import requests

from devassist import config, metrics
from devassist.llm import LLMError, _headers

BATCH = 64
RETRIES = 3
TIMEOUT = 180


def _embed_batch(batch, label):
    last_error = None
    for attempt in range(RETRIES):
        started = time.time()
        try:
            response = requests.post(
                config.EMBED_URL,
                headers=_headers(),
                json={"model": config.EMBED_MODEL, "input": batch},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            last_error = error
            metrics.record(label, config.EMBED_MODEL, 0, 0, time.time() - started, ok=False,
                           note=f"attempt {attempt + 1}: {error}")
            time.sleep(1.5 * (attempt + 1))
            continue
        usage = payload.get("usage") or {}
        metrics.record(label, config.EMBED_MODEL, usage.get("prompt_tokens", 0), 0,
                       time.time() - started)
        ordered = sorted(payload["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in ordered]
    raise LLMError(f"{config.EMBED_MODEL}: {last_error}")


def embed_texts(texts, progress=None, label="embed"):
    cleaned = [text if text.strip() else "пусто" for text in texts]
    vectors = []
    for start in range(0, len(cleaned), BATCH):
        vectors.extend(_embed_batch(cleaned[start: start + BATCH], label))
        if progress:
            progress(min(start + BATCH, len(cleaned)), len(cleaned))
    matrix = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-10)


def embed_one(text, label="embed-query"):
    return embed_texts([text], label=label)[0]
