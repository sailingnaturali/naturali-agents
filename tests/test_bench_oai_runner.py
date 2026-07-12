from __future__ import annotations

from poseidon.bench import oai_runner
from poseidon.bench.golden import Ask
from poseidon.bench.oai_runner import flat_scored_ask, parse_choice


def _resp(message: dict, finish_reason: str = "stop") -> dict:
    return {"choices": [{"message": message, "finish_reason": finish_reason}]}


def test_parse_choice_with_tool_calls():
    tc = [{"id": "c1", "function": {"name": "mcp__signalk__depth_state", "arguments": "{}"}}]
    tool_calls, text, finish = parse_choice(_resp({"role": "assistant", "content": None,
                                                   "tool_calls": tc}, "tool_calls"))
    assert tool_calls == tc
    assert text == ""
    assert finish == "tool_calls"


def test_parse_choice_final_text():
    tool_calls, text, finish = parse_choice(_resp({"role": "assistant", "content": "Twelve metres."}))
    assert tool_calls == []
    assert text == "Twelve metres."
    assert finish == "stop"


def test_flat_scored_ask_substitutes_when_flat_present():
    ask = Ask(id="explain-alarm", category="delegated", prompt="p",
              expected_tools=("Agent",), multi_tool=False,
              expected_tools_flat=("mcp__signalk__get_active_alarms",))
    scored = flat_scored_ask(ask)
    assert scored.expected_tools == ("mcp__signalk__get_active_alarms",)


def test_flat_scored_ask_unchanged_without_flat():
    ask = Ask(id="depth", category="engineer-direct", prompt="p",
              expected_tools=("mcp__signalk__depth_state",), multi_tool=False)
    assert flat_scored_ask(ask) is ask


def test_auth_headers_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-123")
    assert oai_runner.auth_headers() == {"Authorization": "Bearer test-key-123"}


def test_auth_headers_absent_without_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert oai_runner.auth_headers() == {}
