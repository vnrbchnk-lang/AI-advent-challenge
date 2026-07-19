import asyncio
import json
import os
import sys
import threading
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVERS = {
    "project": {
        "module": "devassist.servers.project_app",
        "title": "Проект: git, файлы, поиск по коду",
    },
    "tickets": {
        "module": "devassist.servers.tickets_app",
        "title": "Поддержка: тикеты и пользователи",
    },
}

CONNECT_TIMEOUT = 45
CALL_TIMEOUT = 120


class McpError(RuntimeError):
    pass


class McpBridge:
    def __init__(self, servers=None):
        self.names = list(servers or SERVERS)
        self.loop = None
        self.thread = None
        self.sessions = {}
        self.tools = {}
        self.errors = {}
        self._ready = threading.Event()
        self._stop = None

    def start(self):
        if self.thread:
            return self.status()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._ready.wait(timeout=CONNECT_TIMEOUT * len(self.names) + 10)
        return self.status()

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._serve())
        finally:
            self.loop.close()

    async def _open(self, stack, name):
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", SERVERS[name]["module"]],
            env=dict(os.environ),
        )
        read_stream, write_stream = await stack.enter_async_context(stdio_client(parameters))
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT)
        listed = await asyncio.wait_for(session.list_tools(), timeout=CONNECT_TIMEOUT)
        return session, listed

    async def _serve(self):
        self._stop = asyncio.Event()
        async with AsyncExitStack() as stack:
            for name in self.names:
                try:
                    session, listed = await self._open(stack, name)
                    self.sessions[name] = session
                    self.tools[name] = [
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
                        }
                        for tool in listed.tools
                    ]
                except Exception as error:
                    self.errors[name] = f"{type(error).__name__}: {error}"
            self._ready.set()
            await self._stop.wait()

    def status(self):
        return [
            {
                "server": name,
                "title": SERVERS[name]["title"],
                "connected": name in self.sessions,
                "tools": len(self.tools.get(name, [])),
                "error": self.errors.get(name, ""),
            }
            for name in self.names
        ]

    async def _call(self, server, name, arguments):
        result = await asyncio.wait_for(
            self.sessions[server].call_tool(name, arguments), timeout=CALL_TIMEOUT)
        texts = [getattr(item, "text", "") for item in (result.content or [])]
        joined = "\n".join(part for part in texts if part)
        if getattr(result, "isError", False):
            raise McpError(joined or f"{server}.{name}: ошибка вызова")
        structured = getattr(result, "structuredContent", None)
        if structured:
            return structured
        try:
            return json.loads(joined)
        except (json.JSONDecodeError, TypeError):
            return {"text": joined}

    def call(self, server, name, arguments=None):
        if server not in self.sessions:
            raise McpError(f"сервер '{server}' не подключён: {self.errors.get(server, 'нет сессии')}")
        future = asyncio.run_coroutine_threadsafe(
            self._call(server, name, arguments or {}), self.loop)
        return future.result(timeout=CALL_TIMEOUT + 15)

    def stop(self):
        if self.loop and self._stop:
            self.loop.call_soon_threadsafe(self._stop.set)
        if self.thread:
            self.thread.join(timeout=10)
        self.thread = None
