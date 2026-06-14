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
