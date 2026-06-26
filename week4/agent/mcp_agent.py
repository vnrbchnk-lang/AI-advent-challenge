import asyncio
import json
import os
import sys
import threading

import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

API_URL = "https://api.proxyapi.ru/openai/v1/chat/completions"
MAIN_MODEL = "gpt-4.1"

ASK_SYSTEM = (
    "Ты — агент с набором MCP-инструментов (поиск в Википедии, получение статьи, суммаризация, "
    "сохранение в файл, напоминания). Выполни цель пользователя: вызывай инструменты по необходимости "
    "и опирайся на их результаты, передавая данные от одного к другому. Когда цель достигнута — дай "
    "краткий итог на русском."
)


def _server_params():
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "agent.server.app"],
        env=dict(os.environ),
    )


class McpAgent:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()
        self._session = None
        self._tools = []
        self._ready = threading.Event()
        self._stop = None

    def connect(self, timeout=30):
        asyncio.run_coroutine_threadsafe(self._serve(), self._loop)
        if not self._ready.wait(timeout=timeout):
            raise TimeoutError("MCP-сервер не ответил за отведённое время")

    async def _serve(self):
        self._stop = asyncio.Event()
        async with stdio_client(_server_params()) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                self._tools = [
                    {
                        "name": tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
                    }
                    for tool in result.tools
                ]
                self._session = session
                self._ready.set()
                await self._stop.wait()

    def list_tools(self):
        return self._tools

    def _extract(self, result):
        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        return None

    def call_tool(self, name, arguments):
        future = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments), self._loop
        )
        return self._extract(future.result(timeout=120))

    def run_pipeline(self, query):
        stages = []
        search = self.call_tool("wiki_search", {"query": query, "limit": 5})
        results = search.get("results", []) if isinstance(search, dict) else []
        stages.append(("search", f"найдено результатов: {len(results)}"))
        if not results:
            return stages, None
        title = results[0]["title"]
        fetched = self.call_tool("wiki_fetch", {"title": title})
        extract = fetched.get("extract", "")
        stages.append(("wiki_fetch", f"статья «{title}», символов: {len(extract)}"))
        summarized = self.call_tool("summarize", {"text": extract})
        summary = summarized.get("summary", "")
        stages.append(("summarize", f"саммари символов: {len(summary)}"))
        saved = self.call_tool("save_to_file", {"name": title, "content": summary})
        path = saved.get("path", "")
        stages.append(("save_to_file", path))
        return stages, {"title": title, "summary": summary, "path": path}

    def _openai_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in self._tools
        ]

    def ask(self, goal, max_steps=6):
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
                name = call["function"]["name"]
                arguments = json.loads(call["function"]["arguments"] or "{}")
                output = self.call_tool(name, arguments)
                transcript.append({"tool": name, "arguments": arguments, "output": output})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(output, ensure_ascii=False),
                })
        return transcript, "(достигнут лимит шагов)"

    def close(self):
        if self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
