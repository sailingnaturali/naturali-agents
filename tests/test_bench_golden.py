from __future__ import annotations

from poseidon.bench.golden import Ask, load_golden_asks


def test_load_golden_asks_returns_asks():
    asks = load_golden_asks()
    assert len(asks) >= 6
    assert all(isinstance(a, Ask) for a in asks)


def test_ask_ids_are_unique():
    asks = load_golden_asks()
    ids = [a.id for a in asks]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


def test_every_ask_has_nonempty_expected_tools():
    for a in load_golden_asks():
        assert a.expected_tools, f"{a.id} has no expected_tools"
        assert all(t.startswith(("mcp__", "Agent")) for t in a.expected_tools)


def test_single_tool_asks_expect_exactly_one_tool():
    for a in load_golden_asks():
        if not a.multi_tool:
            assert len(a.expected_tools) == 1, f"{a.id} not single-tool"


def test_explain_alarm_has_flat_expectation():
    by_id = {a.id: a for a in load_golden_asks()}
    assert by_id["explain-alarm"].expected_tools_flat == ("mcp__signalk__get_active_alarms",)


def test_expected_tools_flat_defaults_empty():
    by_id = {a.id: a for a in load_golden_asks()}
    assert by_id["depth"].expected_tools_flat == ()
