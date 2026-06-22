"""tests.bench.test_hermes_runner — unit tests for the Hermes session parser
and tool-name normalizer.

Tests are driven by the real captured session fixture so the schema is not
assumed — any mismatch means the parser needs updating.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURE = Path(__file__).parent / "fixtures" / "hermes_session_depth.json"


@pytest.fixture
def depth_session() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# normalize_tool_name
# ---------------------------------------------------------------------------

def test_normalize_already_sdk_form():
    from poseidon.bench.hermes_runner import normalize_tool_name
    assert normalize_tool_name("mcp__signalk__depth_state") == "mcp__signalk__depth_state"


def test_normalize_hermes_signalk_depth():
    """The exact Hermes tool name captured from the fixture."""
    from poseidon.bench.hermes_runner import normalize_tool_name
    assert normalize_tool_name("mcp_signalk_depth_state") == "mcp__signalk__depth_state"


def test_normalize_hermes_signalk_battery():
    from poseidon.bench.hermes_runner import normalize_tool_name
    assert normalize_tool_name("mcp_signalk_battery_state") == "mcp__signalk__battery_state"


def test_normalize_hermes_signalk_get_active_alarms():
    from poseidon.bench.hermes_runner import normalize_tool_name
    assert normalize_tool_name("mcp_signalk_get_active_alarms") == "mcp__signalk__get_active_alarms"


def test_normalize_hermes_currents():
    from poseidon.bench.hermes_runner import normalize_tool_name
    assert normalize_tool_name("mcp_currents_get_tide_heights") == "mcp__currents__get_tide_heights"


def test_normalize_hermes_pilotbook():
    from poseidon.bench.hermes_runner import normalize_tool_name
    assert normalize_tool_name("mcp_pilotbook_find_anchorages_near") == "mcp__pilotbook__find_anchorages_near"


def test_normalize_hermes_weather():
    from poseidon.bench.hermes_runner import normalize_tool_name
    assert normalize_tool_name("mcp_weather_get_marine_forecast") == "mcp__weather__get_marine_forecast"


def test_normalize_hermes_club_moorage():
    """club-moorage server: Hermes uses underscore; scorer uses the original dash."""
    from poseidon.bench.hermes_runner import normalize_tool_name
    assert normalize_tool_name("mcp_club_moorage_find_moorage_near") == "mcp__club-moorage__find_moorage_near"


def test_normalize_hermes_vessel_knowledge():
    """vessel-knowledge server: Hermes uses underscore; scorer uses the original dash."""
    from poseidon.bench.hermes_runner import normalize_tool_name
    assert normalize_tool_name("mcp_vessel_knowledge_get_equipment") == "mcp__vessel-knowledge__get_equipment"


def test_normalize_passthrough_non_mcp():
    from poseidon.bench.hermes_runner import normalize_tool_name
    assert normalize_tool_name("Agent") == "Agent"


# ---------------------------------------------------------------------------
# parse_hermes_session — driven by the real fixture
# ---------------------------------------------------------------------------

def test_parse_extracts_depth_tool(depth_session):
    from poseidon.bench.hermes_runner import parse_hermes_session
    tools, args, text = parse_hermes_session(depth_session)
    assert "mcp__signalk__depth_state" in tools


def test_parse_args_are_list_of_dicts(depth_session):
    from poseidon.bench.hermes_runner import parse_hermes_session
    tools, args, text = parse_hermes_session(depth_session)
    assert isinstance(args, list)
    assert all(isinstance(a, dict) for a in args)


def test_parse_final_text_nonempty(depth_session):
    from poseidon.bench.hermes_runner import parse_hermes_session
    tools, args, text = parse_hermes_session(depth_session)
    assert isinstance(text, str)
    assert len(text) > 0


def test_parse_tool_count_matches_args_count(depth_session):
    from poseidon.bench.hermes_runner import parse_hermes_session
    tools, args, text = parse_hermes_session(depth_session)
    assert len(tools) == len(args)
