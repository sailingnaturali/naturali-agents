from __future__ import annotations

import pytest

from poseidon.bench.golden import Ask
from poseidon.bench.scoring import (
    AskResult,
    Scorecard,
    percentile,
    score_ask,
    build_scorecard,
)


def _ask(id, tools, multi=False, args=None):
    return Ask(id=id, category="c", prompt="p", expected_tools=tuple(tools),
               multi_tool=multi, expected_args=args or {})


def test_score_ask_exact_set_match_passes():
    a = _ask("depth", ["mcp__signalk__depth_state"])
    assert score_ask(a, observed_tools=["mcp__signalk__depth_state"]) is True


def test_score_ask_order_tolerant_for_multi():
    a = _ask("x", ["A", "B"], multi=True)
    assert score_ask(a, observed_tools=["B", "A"]) is True


def test_score_ask_extra_tool_allowed():
    a = _ask("depth", ["mcp__signalk__depth_state"])
    assert score_ask(a, observed_tools=["mcp__signalk__depth_state", "mcp__weather__x"]) is True


def test_score_ask_recall_with_helpers():
    a = _ask("wind", ["mcp__weather__get_marine_forecast"])
    observed = ["mcp__signalk__read_sensor", "mcp__weather__get_marine_forecast",
                "mcp__signalk__get_local_time"]
    assert score_ask(a, observed_tools=observed) is True


def test_score_ask_missing_tool_fails():
    a = _ask("x", ["A", "B"], multi=True)
    assert score_ask(a, observed_tools=["A"]) is False


def test_score_ask_arg_subset_checked_when_present():
    a = _ask("g", ["mcp__currents__get_gate_current"], args={"mcp__currents__get_gate_current": {"gate": "boundary_pass"}})
    ok = score_ask(a, observed_tools=["mcp__currents__get_gate_current"],
                   observed_args=[{"gate": "boundary_pass", "extra": 1}])
    bad = score_ask(a, observed_tools=["mcp__currents__get_gate_current"],
                    observed_args=[{"gate": "active_pass"}])
    assert ok is True and bad is False


def test_percentile_p50_p95():
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(data, 50) == 3.0
    assert percentile(data, 95) == pytest.approx(4.8)


def test_build_scorecard_aggregates():
    a1 = _ask("depth", ["mcp__signalk__depth_state"])
    a2 = _ask("wind", ["mcp__weather__get_marine_forecast"])
    results = [
        AskResult(ask=a1, observed_tools=["mcp__signalk__depth_state"],
                  observed_args=[{}], dt_total=2.0, is_error=False),
        AskResult(ask=a2, observed_tools=["mcp__weather__get_marine_forecast"],
                  observed_args=[{}], dt_total=4.0, is_error=False),
    ]
    card = build_scorecard(model="claude-sonnet-4-6", results=results)
    assert isinstance(card, Scorecard)
    assert card.correctness == 1.0
    assert card.error_rate == 0.0
    assert card.latency_p50 == 3.0
    assert card.n == 2
