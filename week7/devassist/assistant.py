from devassist import config, retrieval
from devassist.executor import Executor
from devassist.index import VectorIndex
from devassist.mcp_bridge import McpBridge
from devassist.registry import Registry

RAG_SCHEMA = {
    "type": "object",
    "properties": {
        "project": {
            "type": "string",
            "enum": list(config.PROJECTS),
            "description": "База знаний: alaba — код и документация проекта, advent — репозиторий челленджа, support — FAQ поддержки",
        },
        "query": {"type": "string", "description": "Поисковый запрос своими словами"},
        "kinds": {
            "type": "array",
            "items": {"type": "string", "enum": ["doc", "schema", "code"]},
            "description": "Чем ограничить поиск: doc — документация, schema — схемы данных и API, code — исходники",
        },
        "top_k": {"type": "integer", "description": "Сколько фрагментов вернуть, 1-10"},
    },
    "required": ["project", "query"],
}


class DevAssistant:
    def __init__(self, servers=None, confirm=None):
        self.bridge = McpBridge(servers)
        self.registry = Registry()
        self.executor = Executor(self.registry, self.bridge, confirm=confirm)
        self._indexes = {}

    def start(self):
        statuses = self.bridge.start()
        self.registry.add_from_bridge(self.bridge)
        self.registry.add_local(
            "rag_search",
            "Семантический поиск по проиндексированной документации, схемам и коду проекта. "
            "Возвращает фрагменты с путём файла и близостью к запросу.",
            RAG_SCHEMA,
            self.rag_search,
        )
        return statuses

    def stop(self):
        self.bridge.stop()

    def index(self, name):
        if name not in self._indexes:
            if not VectorIndex.exists(name):
                raise FileNotFoundError(
                    f"индекс '{name}' не построен — выполни /index {name}")
            self._indexes[name] = VectorIndex.load(name)
        return self._indexes[name]

    def has_index(self, name):
        return VectorIndex.exists(name)

    def rag_search(self, project="alaba", query="", kinds=None, top_k=5):
        result = retrieval.retrieve(self.index(project), query, {
            "kinds": kinds,
            "top_k": max(1, min(int(top_k or 5), 10)),
        })
        return {
            "project": project,
            "query": query,
            "count": len(result["final"]),
            "results": [
                {
                    "source": retrieval.label(chunk),
                    "score": round(score, 3),
                    "kind": chunk["kind"],
                    "text": chunk["text"][:1500],
                }
                for score, chunk in result["final"]
            ],
        }
