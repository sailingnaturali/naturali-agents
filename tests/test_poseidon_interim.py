"""Interim-say policy: deterministic phrases, max two says per turn."""
from poseidon.interim import InterimPolicy, phrase_for_tools


def test_phrase_single_tool():
    assert phrase_for_tools(["mcp__pilotbook__search_anchorages"]) == \
        "Let me check the pilot book."


def test_phrase_combines_and_dedupes_servers():
    phrase = phrase_for_tools([
        "mcp__weather__get_marine_forecast",
        "mcp__pilotbook__rank_anchorages",
        "mcp__pilotbook__get_anchorage",
    ])
    assert phrase == "Let me check the forecast and the pilot book."


def test_phrase_subagent_delegation():
    assert phrase_for_tools(["Agent"]) == "Let me check with the crew."


def test_phrase_unknown_tool_generic():
    assert phrase_for_tools(["SomethingNew"]) == "Let me look into that."


def test_phrase_empty_and_multiple_unknowns_generic():
    assert phrase_for_tools([]) == "Let me look into that."
    assert phrase_for_tools(["UnknownA", "UnknownB"]) == "Let me look into that."


def test_phrase_mixed_known_and_unknown_drops_generic():
    assert phrase_for_tools(["mcp__pilotbook__get_anchorage", "UnknownB"]) == \
        "Let me check the pilot book."


def test_policy_first_ack_only_once():
    p = InterimPolicy()
    assert p.note_tool_use(["mcp__signalk__read_sensor"]) == \
        "Let me check the instruments."
    assert p.note_tool_use(["mcp__weather__get_marine_forecast"]) is None


def test_policy_still_working_once_and_budget():
    p = InterimPolicy()
    assert p.note_tool_use(["Agent"]) is not None
    assert p.still_working() == "Still working on it."
    assert p.still_working() is None  # max two says per turn


def test_policy_still_working_without_prior_ack():
    p = InterimPolicy()
    assert p.still_working() == "Still working on it."
    assert p.note_tool_use(["Agent"]) is not None  # second say still allowed
    assert p.note_tool_use(["Agent"]) is None
