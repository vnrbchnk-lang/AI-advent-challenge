import json
import time

import numpy as np

from devassist import chunking, config, embedder


class VectorIndex:
    def __init__(self, name, chunks, matrix, built_at=None, model=None):
        self.name = name
        self.chunks = chunks
        self.matrix = matrix
        self.built_at = built_at or time.strftime("%Y-%m-%d %H:%M:%S")
        self.model = model or config.EMBED_MODEL

    @classmethod
    def build(cls, name, chunks, progress=None):
        texts = [chunking.embed_input(chunk) for chunk in chunks]
        matrix = embedder.embed_texts(texts, progress=progress, label=f"embed-index:{name}")
        return cls(name, chunks, matrix)

    @staticmethod
    def paths(name):
        return config.STORE / f"index-{name}.json", config.STORE / f"index-{name}.npz"

    @classmethod
    def exists(cls, name):
        meta_path, matrix_path = cls.paths(name)
        return meta_path.is_file() and matrix_path.is_file()

    def save(self):
        config.STORE.mkdir(parents=True, exist_ok=True)
        meta_path, matrix_path = self.paths(self.name)
        meta_path.write_text(json.dumps({
            "name": self.name,
            "model": self.model,
            "built_at": self.built_at,
            "dim": int(self.matrix.shape[1]),
            "chunks": self.chunks,
        }, ensure_ascii=False), encoding="utf-8")
        np.savez_compressed(matrix_path, matrix=self.matrix.astype(np.float16))
        return meta_path

    @classmethod
    def load(cls, name):
        meta_path, matrix_path = cls.paths(name)
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        matrix = np.load(matrix_path)["matrix"].astype(np.float32)
        return cls(name, payload["chunks"], matrix, payload["built_at"], payload["model"])

    def stats(self):
        by_kind = {}
        for chunk in self.chunks:
            by_kind[chunk["kind"]] = by_kind.get(chunk["kind"], 0) + 1
        files = {chunk["path"] for chunk in self.chunks}
        return {
            "name": self.name,
            "chunks": len(self.chunks),
            "files": len(files),
            "by_kind": by_kind,
            "built_at": self.built_at,
            "model": self.model,
            "dim": int(self.matrix.shape[1]),
        }

    def search(self, query_vector, top_n=20, kinds=None, path_prefix=None):
        scores = self.matrix @ query_vector
        order = np.argsort(scores)[::-1]
        hits = []
        for position in order:
            chunk = self.chunks[position]
            if kinds and chunk["kind"] not in kinds:
                continue
            if path_prefix and not chunk["path"].startswith(path_prefix):
                continue
            hits.append((float(scores[position]), chunk))
            if len(hits) >= top_n:
                break
        return hits


def build_project(name, progress=None, on_documents=None):
    from devassist import corpus

    documents, skipped = corpus.collect(name)
    if on_documents:
        on_documents(documents, skipped)
    chunks = chunking.chunk_documents(documents)
    index = VectorIndex.build(name, chunks, progress=progress)
    index.save()
    return index, documents, skipped
