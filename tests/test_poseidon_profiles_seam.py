# tests/test_poseidon_profiles_seam.py
import importlib

from poseidon import alarms, config, profiles


def _reload():
    return importlib.reload(config)


def test_provider_defaults(monkeypatch):
    monkeypatch.delenv("POSEIDON_PROVIDER", raising=False)
    monkeypatch.delenv("POSEIDON_BASE_URL", raising=False)
    cfg = _reload()
    assert cfg.PROVIDER == "sdk"
    assert cfg.BASE_URL == ""


def test_no_base_url_means_no_env_override(monkeypatch):
    monkeypatch.delenv("POSEIDON_BASE_URL", raising=False)
    _reload()
    assert profiles.crew_options().env == {}
    assert alarms._alarm_options("warn").env == {}


def test_subagent_tools_not_globally_disallowed():
    # --disallowedTools is a session-global CLI deny; a subagent's tools= list
    # cannot re-grant a globally-disallowed tool. Delegating to a subagent whose
    # tool is disallowed makes the model report the MCP "not connected".
    opts = profiles.crew_options()
    disallowed = set(opts.disallowed_tools)
    for name, agent in opts.agents.items():
        clashing = [t for t in agent.tools if t in disallowed]
        assert not clashing, f"{name} subagent tools globally disallowed: {clashing}"


def test_base_url_reaches_both_lanes(monkeypatch):
    monkeypatch.setenv("POSEIDON_BASE_URL", "http://localhost:4000")
    _reload()
    try:
        expected = {"ANTHROPIC_BASE_URL": "http://localhost:4000"}
        assert profiles.crew_options().env == expected
        assert alarms._alarm_options("warn").env == expected
    finally:
        monkeypatch.delenv("POSEIDON_BASE_URL")
        _reload()
