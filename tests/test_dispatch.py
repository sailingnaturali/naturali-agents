import sys
from pathlib import Path

# The bridge lives in bridges/, not scripts/ (conftest only adds scripts/).
sys.path.insert(0, str(Path(__file__).parent.parent / "bridges"))

import mqtt_to_hermes as b


def test_model_for_state_routes_by_severity(monkeypatch):
    monkeypatch.setenv("ALARM_MODEL", "anthropic/claude-sonnet-4")
    monkeypatch.setenv("WARN_MODEL", "")
    assert b.model_for_state("emergency") == "anthropic/claude-sonnet-4"
    assert b.model_for_state("alarm") == "anthropic/claude-sonnet-4"
    assert b.model_for_state("warn") is None  # empty -> config default


def test_alert_query_includes_context():
    env = {"path": "mob.1", "state": "emergency", "message": "MOB",
           "timestamp": "2026-06-05T18:22:10Z",
           "position": {"latitude": 48.76, "longitude": -123.05}}
    q = b.alert_query(env)
    assert "emergency" in q and "mob.1" in q and "MOB" in q
    assert "48.76" in q and "-123.05" in q


def test_handle_alert_invokes_hermes_once_then_dedups(monkeypatch):
    calls = []
    monkeypatch.setattr(b, "_run_hermes", lambda q, model=None: calls.append((q, model)))
    b._ALERT_SEEN.clear()
    env = {"path": "mob.1", "state": "emergency", "message": "MOB",
           "timestamp": "t1", "position": {"latitude": 48.76, "longitude": -123.05}}
    b.handle_alert(env)
    b.handle_alert(env)  # retained redelivery, same timestamp
    assert len(calls) == 1
    assert calls[0][1] == (b.os.environ.get("ALARM_MODEL") or None)


def test_handle_alert_skips_cleared_and_below_warn(monkeypatch):
    calls = []
    monkeypatch.setattr(b, "_run_hermes", lambda q, model=None: calls.append(q))
    b._ALERT_SEEN.clear()
    b.handle_alert({"path": "x", "state": "normal", "timestamp": "t"})
    b.handle_alert({"path": "y", "state": "alert", "timestamp": "t"})
    assert calls == []


def test_new_timestamp_reinvokes(monkeypatch):
    calls = []
    monkeypatch.setattr(b, "_run_hermes", lambda q, model=None: calls.append(q))
    b._ALERT_SEEN.clear()
    b.handle_alert({"path": "mob.1", "state": "emergency", "timestamp": "t1"})
    b.handle_alert({"path": "mob.1", "state": "emergency", "timestamp": "t2"})
    assert len(calls) == 2
