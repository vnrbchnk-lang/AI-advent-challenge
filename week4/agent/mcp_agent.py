import asyncio
import json
import os
import sys
import threading
from contextlib import AsyncExitStack

import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

API_URL = "https://api.proxyapi.ru/openai/v1/chat/completions"
MAIN_MODEL = "gpt-4.1"
DEEPWIKI_URL = "https://mcp.deepwiki.com/mcp"
NAMESPACE_SEP = "__"
CONNECT_TIMEOUT = 25

SERVERS = [
    {"name": "wiki", "transport": "stdio", "module": "agent.server.wiki_app",
     "title": "Википедия — поиск и статьи"},
    {"name": "pipeline", "transport": "stdio", "module": "agent.server.pipeline_app",
     "title": "Обработка — суммаризация и сохранение"},
    {"name": "scheduler", "transport": "stdio", "module": "agent.server.scheduler_app",
     "title": "Планировщик — напоминания 24/7"},
    {"name": "deepwiki", "transport": "http", "url": DEEPWIKI_URL,
     "title": "DeepWiki — вики GitHub-репозиториев"},
]

ASK_SYSTEM = (
    "Ты — агент-оркестратор с инструментами от НЕСКОЛЬКИХ MCP-серверов: "
    "wiki (поиск и статьи Википедии), pipeline (суммаризация и сохранение в файл), "
    "scheduler (напоминания), deepwiki (вики GitHub-репозиториев). "
    "Имя инструмента имеет вид server__tool. Выполни цель пользователя: выбирай нужные "
    "инструменты с разных серверов, вызывай их по порядку и передавай данные от одного "
    "к другому. Когда цель достигнута — дай краткий итог на русском."
)


def _stdio_params(module):
    return StdioServerParameters(command=sys.executable, args=["-m", module], env=dict(os.environ))


class McpAgent:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()
        self._sessions = {}
        self._tools = []
        self._servers = []
        self._ready = threading.Event()
        self._stop = None

    def connect(self, timeout=90):
        asyncio.run_coroutine_threadsafe(self._serve(), self._loop)
        if not self._ready.wait(timeout=timeout):
            raise TimeoutError("MCP-серверы не ответили за отведённое время")

    async def _open(self, stack, spec):
        if spec["transport"] == "stdio":
            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(_stdio_params(spec["module"]))
            )
        else:
            read_stream, write_stream, _ = await stack.enter_async_context(
                streamablehttp_client(spec["url"])
            )
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        result = await session.list_tools()
        return session, result.tools

    async def _serve(self):
        self._stop = asyncio.Event()
        async with AsyncExitStack() as stack:
            for spec in SERVERS:
                status = {
                    "name": spec["name"],
                    "transport": spec["transport"],
                    "title": spec["title"],
                    "ok": False,
                    "tools": 0,
                    "error": "",
                }
                try:
                    session, tools = await asyncio.wait_for(
                        self._open(stack, spec), timeout=CONNECT_TIMEOUT
                    )
                    self._sessions[spec["name"]] = session
                    for tool in tools:
                        self._tools.append({
                            "server": spec["name"],
                            "name": tool.name,
                            "qualified": spec["name"] + NAMESPACE_SEP + tool.name,
                            "description": tool.description or "",
                            "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
                        })
                    status["ok"] = True
                    status["tools"] = len(tools)
                except Exception as error:
                    status["error"] = f"{type(error).__name__}: {error}"
                self._servers.append(status)
            self._ready.set()
            await self._stop.wait()

    def list_tools(self):
        return self._tools

    def servers(self):
        return self._servers

    def tools_for(self, server):
        return [tool for tool in self._tools if tool["server"] == server]

    def _extract(self, result):
        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        return None

    def call_tool(self, server, name, arguments):
        session = self._sessions.get(server)
        if session is None:
            raise RuntimeError(f"Сервер '{server}' не подключён")
        future = asyncio.run_coroutine_threadsafe(
            session.call_tool(name, arguments), self._loop
        )
        return self._extract(future.result(timeout=120))

    def run_flow(self, topic):
        stages = []
        search = self.call_tool("wiki", "wiki_search", {"query": topic, "limit": 5})
        results = search.get("results", []) if isinstance(search, dict) else []
        stages.append(("wiki", "wiki_search", f"найдено статей: {len(results)}"))
        if not results:
            return stages, None
        title = results[0]["title"]
        fetched = self.call_tool("wiki", "wiki_fetch", {"title": title})
        extract = fetched.get("extract", "") if isinstance(fetched, dict) else ""
        stages.append(("wiki", "wiki_fetch", f"статья «{title}», символов: {len(extract)}"))
        summarized = self.call_tool("pipeline", "summarize", {"text": extract})
        summary = summarized.get("summary", "") if isinstance(summarized, dict) else ""
        stages.append(("pipeline", "summarize", f"саммари символов: {len(summary)}"))
        saved = self.call_tool("pipeline", "save_to_file", {"name": title, "content": summary})
        path = saved.get("path", "") if isinstance(saved, dict) else ""
        stages.append(("pipeline", "save_to_file", path))
        reminder = self.call_tool(
            "scheduler", "remind_add",
            {"text": f"Проверить саммари «{title}»", "run_at": "+60"},
        )
        rid = reminder.get("id") if isinstance(reminder, dict) else None
        run_at = reminder.get("run_at", "") if isinstance(reminder, dict) else ""
        stages.append(("scheduler", "remind_add", f"напоминание #{rid} на {run_at}"))
        return stages, {"title": title, "summary": summary, "path": path}

    def run_research(self, repo):
        stages = []
        structure = self.call_tool("deepwiki", "read_wiki_structure", {"repoName": repo})
        struct_text = structure if isinstance(structure, str) else json.dumps(structure, ensure_ascii=False)
        stages.append(("deepwiki", "read_wiki_structure", f"структура вики, символов: {len(struct_text)}"))
        question = f"Кратко: что такое репозиторий {repo} и для чего он нужен?"
        answer = self.call_tool("deepwiki", "ask_question", {"repoName": repo, "question": question})
        answer_text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
        stages.append(("deepwiki", "ask_question", f"ответ получен, символов: {len(answer_text)}"))
        summarized = self.call_tool("pipeline", "summarize", {"text": answer_text})
        summary = summarized.get("summary", "") if isinstance(summarized, dict) else ""
        stages.append(("pipeline", "summarize", f"саммари символов: {len(summary)}"))
        name = repo.replace("/", "_")
        saved = self.call_tool("pipeline", "save_to_file", {"name": name, "content": summary})
        path = saved.get("path", "") if isinstance(saved, dict) else ""
        stages.append(("pipeline", "save_to_file", path))
        reminder = self.call_tool(
            "scheduler", "remind_add",
            {"text": f"Изучить репозиторий {repo}", "run_at": "+60"},
        )
        rid = reminder.get("id") if isinstance(reminder, dict) else None
        run_at = reminder.get("run_at", "") if isinstance(reminder, dict) else ""
        stages.append(("scheduler", "remind_add", f"напоминание #{rid} на {run_at}"))
        return stages, {"repo": repo, "summary": summary, "path": path}

    def _openai_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["qualified"],
                    "description": f"[сервер {tool['server']}] {tool['description']}",
                    "parameters": tool["input_schema"],
                },
            }
            for tool in self._tools
        ]

    def ask(self, goal, max_steps=8):
        api_key = os.environ["PROXYAPI_KEY"]
        headers = {"Authorization": f"Bearer {api_key}"}
        tools = self._openai_tools()
        messages = [
            {"role": "system", "content": ASK_SYSTEM},
            {"role": "user", "content": goal},
        ]
        transcript = []
        for _ in range(max_steps):
            response = requests.post(
                API_URL,
                headers=headers,
                json={"model": MAIN_MODEL, "messages": messages, "tools": tools, "tool_choice": "auto"},
                timeout=120,
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            messages.append(message)
            calls = message.get("tool_calls")
            if not calls:
                return transcript, message.get("content", "")
            for call in calls:
                qualified = call["function"]["name"]
                server, _, name = qualified.partition(NAMESPACE_SEP)
                arguments = json.loads(call["function"]["arguments"] or "{}")
                output = self.call_tool(server, name, arguments)
                transcript.append({"server": server, "tool": name, "arguments": arguments, "output": output})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(output, ensure_ascii=False),
                })
        return transcript, "(достигнут лимит шагов)"

    def close(self):
        if self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
