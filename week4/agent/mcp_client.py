from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def _normalize(tools):
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema or {},
        }
        for tool in tools
    ]


class McpClient:
    @staticmethod
    async def list_remote_tools(url):
        async with streamablehttp_client(url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                return _normalize(result.tools)
