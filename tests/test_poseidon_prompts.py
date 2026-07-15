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


def test_prompts_have_no_unsubstituted_placeholders():
    # {{VESSEL_NAME}} must be substituted at assembly time (deploy-soul.sh
    # only renders the hermes copy; poseidon reads the repo sources raw).
    assert "{{" not in prompts.crew_system_prompt()
    assert "{{" not in prompts.engineer_prompt()


def test_resolve_vessel_name_env_override(monkeypatch):
    monkeypatch.setenv("VESSEL_NAME", "Test Boat")
    assert prompts._resolve_vessel_name() == "Test Boat"


def test_resolve_vessel_name_from_active_profile(tmp_path, monkeypatch):
    monkeypatch.delenv("VESSEL_NAME", raising=False)
    (tmp_path / "active.yaml").write_text("active: wind-chaser\n")
    (tmp_path / "wind-chaser.yaml").write_text('name: "Wind Chaser"\n')
    monkeypatch.setenv("VESSEL_PROFILES_DIR", str(tmp_path))
    assert prompts._resolve_vessel_name() == "Wind Chaser"


def test_resolve_vessel_name_falls_back_when_profiles_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("VESSEL_NAME", raising=False)
    monkeypatch.setenv("VESSEL_PROFILES_DIR", str(tmp_path / "nope"))
    assert prompts._resolve_vessel_name() == "Naturali"


def test_modernize_tool_names_maps_hermes_servers():
    src = ("call `mcp_signalk_read_sensor(path)` then "
           "`mcp_vessel_knowledge_explain_notification(path, state)`; "
           "gates via `mcp_tide_plan_passage`; the `mcp_signalk_*` tools; "
           "log with `mcp_logbook_mark_moment(text)`")
    out = prompts._modernize_tool_names(src)
    assert "mcp__signalk__read_sensor" in out
    assert "mcp__vessel-knowledge__explain_notification" in out
    assert "mcp__currents__plan_passage" in out
    assert "mcp__signalk__*" in out          # wildcard prefix form too
    assert "mcp__logbook__mark_moment" in out
    assert "mcp_signalk_" not in out and "mcp_vessel_knowledge_" not in out
    assert "mcp_tide_" not in out


def test_engineer_prompt_tool_names_modernized():
    text = prompts.engineer_prompt()
    assert "mcp__vessel-knowledge__explain_notification" in text
    assert "mcp__signalk__read_sensor" in text
    assert "mcp_vessel_knowledge_" not in text
    assert "mcp_signalk_" not in text


def test_crew_prompt_tool_names_modernized():
    text = prompts.crew_system_prompt()
    assert "mcp__currents__plan_passage" in text
    assert "mcp__weather__get_marine_forecast" in text
    for stale in ("mcp_tide_", "mcp_signalk_", "mcp_weather_",
                  "mcp_pilotbook_", "mcp_logbook_"):
        assert stale not in text, stale


def test_alarm_user_prompt_quotes_message_and_forbids_detail():
    env = {"state": "alarm", "path": "electrical.batteries.0.voltage",
           "message": "Battery voltage critically low"}
    q = prompts.alarm_user_prompt(env)
    assert '"Battery voltage critically low"' in q
    assert "two short sentences" in q
    assert "coordinates" in q
    assert "explain_notification" not in q  # alarm lane has no tools


def test_model_for_state_severity_routing(monkeypatch):
    monkeypatch.setenv("ALARM_MODEL", "test-alarm-model")
    monkeypatch.setenv("WARN_MODEL", "")
    assert prompts.model_for_state("emergency") == "test-alarm-model"
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
    # mcp_servers must be a dict (not a Path) with all expected server keys
    assert isinstance(opts.mcp_servers, dict)
    expected_servers = {
        "signalk", "logbook", "currents", "weather",
        "pilotbook", "colregs", "vessel-knowledge", "club-moorage", "memory",
        "mutes",  # in-process SDK server (set_alert_mute voice tool)
    }
    assert expected_servers == set(opts.mcp_servers.keys())
    # Soft scoping: no global deny, else it strips the same tools from the
    # Engineer/Logbook subagents (a global --disallowedTools can't be re-granted).
    assert opts.disallowed_tools == []


def test_load_mcp_servers_expands_home_paths():
    cfg = profiles.load_mcp_servers()

    def walk(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        elif isinstance(obj, str):
            assert not obj.startswith("~"), obj

    walk(cfg)
    # paths come back absolute for this user, not literal-tilde
    assert cfg["signalk"]["command"].startswith("/")


def test_alarm_prompt_offers_mute_for_muteable_category():
    env = {"state": "warn",
           "path": "navigation.restrictedArea.abc",
           "message": "Inside whale closure"}
    q = prompts.alarm_user_prompt(env)
    assert "mute whale" in q.lower()


def test_alarm_prompt_no_mute_offer_for_emergency_or_unknown_path():
    emerg = {"state": "emergency", "path": "navigation.restrictedArea.abc",
             "message": "x"}
    other = {"state": "warn", "path": "electrical.batteries.0.voltage",
             "message": "x"}
    assert "mute" not in prompts.alarm_user_prompt(emerg).lower()
    assert "mute" not in prompts.alarm_user_prompt(other).lower()


def test_modernize_tool_names_is_public():
    from poseidon.prompts import modernize_tool_names
    out = modernize_tool_names("Call `mcp_weather_get_marine_forecast` with lat=1")
    assert "mcp__weather__get_marine_forecast" in out
