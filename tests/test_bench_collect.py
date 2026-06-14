from __future__ import annotations

from dataclasses import dataclass, field

from poseidon.bench.collect import TurnObservation, collect_turn


# Minimal duck-typed fakes mirroring the SDK message shapes.
@dataclass
class FakeToolUse:
    name: str
    input: dict = field(default_factory=dict)


@dataclass
class FakeText:
    text: str


@dataclass
class FakeAssistant:
    content: list


@dataclass
class FakeResult:
    is_error: bool = False
    usage: dict | None = None


@dataclass
class FakeTaskProgress:
    last_tool_name: str


def test_collects_tool_names_and_inputs_in_order():
    messages = [
        FakeAssistant(content=[FakeToolUse(name="mcp__signalk__depth_state", input={"x": 1})]),
        FakeAssistant(content=[FakeText(text="Twelve metres.")]),
        FakeResult(is_error=False, usage={"input_tokens": 100}),
    ]
    obs = collect_turn(messages)
    assert isinstance(obs, TurnObservation)
    assert obs.tools == ["mcp__signalk__depth_state"]
    assert obs.tool_inputs == [{"x": 1}]
    assert obs.text == "Twelve metres."
    assert obs.is_error is False
    assert obs.usage == {"input_tokens": 100}


def test_multiple_tools_preserve_order():
    messages = [
        FakeAssistant(content=[
            FakeToolUse(name="mcp__pilotbook__find_anchorages_near"),
            FakeToolUse(name="mcp__weather__get_marine_forecast"),
        ]),
        FakeResult(is_error=False),
    ]
    obs = collect_turn(messages)
    assert obs.tools == [
        "mcp__pilotbook__find_anchorages_near",
        "mcp__weather__get_marine_forecast",
    ]


def test_error_result_sets_flag():
    obs = collect_turn([FakeResult(is_error=True)])
    assert obs.is_error is True
    assert obs.tools == []
    assert obs.text == ""


def test_text_blocks_join_with_space():
    messages = [FakeAssistant(content=[FakeText(text="One."), FakeText(text="Two.")])]
    obs = collect_turn(messages)
    assert obs.text == "One. Two."


def test_empty_messages_returns_default_observation():
    obs = collect_turn([])
    assert obs.tools == []
    assert obs.tool_inputs == []
    assert obs.text == ""
    assert obs.is_error is False
    assert obs.usage is None


def test_captures_subagent_tool_from_task_progress():
    messages = [
        FakeTaskProgress(last_tool_name="mcp__signalk__get_active_alarms"),
        FakeResult(is_error=False),
    ]
    obs = collect_turn(messages)
    assert obs.tools == ["mcp__signalk__get_active_alarms"]


def test_dedups_task_progress_and_tool_use():
    messages = [
        FakeTaskProgress(last_tool_name="X"),
        FakeAssistant(content=[FakeToolUse(name="X", input={"a": 1})]),
        FakeResult(is_error=False),
    ]
    obs = collect_turn(messages)
    assert obs.tools == ["X"]
    assert obs.tool_inputs == [{"a": 1}]  # real input preferred, position kept


def test_agent_wrapper_and_subagent_tool_both_present():
    messages = [
        FakeAssistant(content=[FakeToolUse(name="Agent")]),
        FakeTaskProgress(last_tool_name="mcp__signalk__battery_state"),
        FakeResult(is_error=False),
    ]
    obs = collect_turn(messages)
    assert obs.tools == ["Agent", "mcp__signalk__battery_state"]


def test_dedups_repeated_task_progress_same_tool():
    messages = [
        FakeTaskProgress(last_tool_name="mcp__signalk__battery_state"),
        FakeTaskProgress(last_tool_name="mcp__signalk__battery_state"),
        FakeResult(is_error=False),
    ]
    obs = collect_turn(messages)
    assert obs.tools == ["mcp__signalk__battery_state"]
