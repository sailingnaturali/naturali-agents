from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from poseidon.bench.oai_tools import split_tool_name, to_openai_schema


@dataclass
class FakeMcpTool:
    name: str
    description: str = ""
    inputSchema: dict = field(default_factory=dict)


def test_to_openai_schema_builds_prefixed_function():
    tool = FakeMcpTool(name="depth_state", description="Depth below transducer",
                       inputSchema={"type": "object", "properties": {}})
    schema = to_openai_schema("signalk", tool)
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "mcp__signalk__depth_state"
    assert schema["function"]["description"] == "Depth below transducer"
    assert schema["function"]["parameters"] == {"type": "object", "properties": {}}


def test_to_openai_schema_defaults_empty_params():
    schema = to_openai_schema("weather", FakeMcpTool(name="get_marine_forecast"))
    assert schema["function"]["parameters"] == {"type": "object", "properties": {}}
    assert schema["function"]["description"] == ""


def test_split_tool_name_happy():
    assert split_tool_name("mcp__signalk__get_local_time") == ("signalk", "get_local_time")


def test_split_tool_name_rejects_non_mcp():
    with pytest.raises(ValueError):
        split_tool_name("Agent")
