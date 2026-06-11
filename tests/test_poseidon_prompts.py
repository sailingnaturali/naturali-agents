"""Prompt assembly and agent-profile tool subsets."""
from poseidon import prompts, profiles


def test_crew_system_prompt_layers_soul_then_navigator():
    text = prompts.crew_system_prompt()
    # SOUL persona present — "Captain" appears in the identity section
    assert "Captain" in text
    # SOUL.md header comes before the Navigator duties header we inject
    # (SOUL.md itself mentions "Navigator" in its preamble, so we test
    # section boundaries instead of first-occurrence ordering)
    assert "# SOUL" in text
    assert "# Navigator duties" in text
    assert text.index("# SOUL") < text.index("# Navigator duties")


def test_engineer_prompt_contains_duties():
    assert "Engineer" in prompts.engineer_prompt()


def test_alarm_user_prompt_quotes_message_and_forbids_detail():
    env = {"state": "alarm", "path": "electrical.batteries.0.voltage",
           "message": "Battery voltage critically low"}
    q = prompts.alarm_user_prompt(env)
    assert '"Battery voltage critically low"' in q
    assert "two short sentences" in q
    assert "coordinates" in q
    assert "explain_notification" not in q  # alarm lane has no tools


def test_model_for_state_severity_routing(monkeypatch):
    monkeypatch.setenv("ALARM_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("WARN_MODEL", "")
    assert prompts.model_for_state("emergency") == "claude-opus-4-8"
    assert prompts.model_for_state("warn") is None


def test_profiles_tool_subsets_disjoint_from_engineer_extras():
    assert any(t.startswith("mcp__pilotbook") for t in profiles.NAVIGATOR_TOOLS)
    assert "mcp__vessel-knowledge" in profiles.ENGINEER_TOOLS
    assert "mcp__vessel-knowledge" not in profiles.NAVIGATOR_TOOLS
    assert "Agent" in profiles.NAVIGATOR_TOOLS  # delegation enabled


def test_crew_options_constructs_with_two_subagents():
    """Smoke test: crew_options() builds without error and has engineer + logbook."""
    opts = profiles.crew_options()
    assert opts.agents is not None
    assert "engineer" in opts.agents
    assert "logbook" in opts.agents
