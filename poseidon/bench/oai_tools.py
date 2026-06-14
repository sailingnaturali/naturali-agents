"""poseidon.bench.oai_tools — MCP servers adapted to OpenAI tools.

For the native OpenAI/Ollama benchmark backend: connect the same stdio MCP
servers the SDK uses (mcp_servers.json), expose their tools as OpenAI function
schemas named mcp__<server>__<tool>, and dispatch tool calls back to the right
server. The pure helpers (to_openai_schema, split_tool_name) are unit-tested; the
async McpToolset is exercised by the live benchmark run.
"""
from __future__ import annotations

from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from poseidon.profiles import load_mcp_servers


def to_openai_schema(server: str, mcp_tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": f"mcp__{server}__{mcp_tool.name}",
            "description": getattr(mcp_tool, "description", "") or "",
            "parameters": getattr(mcp_tool, "inputSchema", None)
            or {"type": "object", "properties": {}},
        },
    }


def split_tool_name(name: str) -> tuple[str, str]:
    if not name.startswith("mcp__") or name.count("__") < 2:
        raise ValueError(f"not an mcp tool name: {name!r}")
    _, server, tool = name.split("__", 2)
    return server, tool


class McpToolset:
    """Live MCP connections for the OpenAI backend. Build via create_toolset();
    use within a single asyncio task; call aclose() to tear down."""

    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self._index: dict[str, tuple[ClientSession, object]] = {}  # full name -> (session, tool)

    async def _add_server(self, server: str, cfg: dict) -> None:
        params = StdioServerParameters(
            command=cfg["command"], args=cfg.get("args", []), env=cfg.get("env"))
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        for tool in (await session.list_tools()).tools:
            self._index[f"mcp__{server}__{tool.name}"] = (session, tool)

    def openai_schemas(self) -> list[dict]:
        return [to_openai_schema(split_tool_name(name)[0], tool)
                for name, (_session, tool) in self._index.items()]

    async def call(self, name: str, arguments: dict) -> str:
        entry = self._index.get(name)
        if entry is None:
            return f"ERROR: unknown tool {name}"
        session, _tool = entry
        try:
            result = await session.call_tool(split_tool_name(name)[1], arguments)
        except Exception as e:  # tool errors must not kill the loop
            return f"ERROR: {e}"
        return "".join(getattr(b, "text", "") for b in (result.content or []))

    async def aclose(self) -> None:
        await self._stack.aclose()


async def create_toolset(servers: dict | None = None) -> McpToolset:
    servers = servers if servers is not None else load_mcp_servers()
    toolset = McpToolset()
    try:
        for server, cfg in servers.items():
            await toolset._add_server(server, cfg)
    except Exception:
        await toolset.aclose()
        raise
    return toolset
