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


def test_alert_query_is_a_voice_seed_not_a_data_dump():
    # The response goes straight to TTS unprompted: the seed carries the
    # ready-to-speak message and demands brevity. Raw coordinates and
    # timestamps stay OUT so the model can't read them aloud (2026-06-06:
    # the old "gather wind, current, depth" seed had the puck reciting
    # battery status after a DSC drill).
    env = {"path": "dsc.distress", "state": "emergency",
           "message": "DSC distress alert: unidentified vessel, flooding, "
                      "5.1 nautical miles west. Monitor channel 16.",
           "timestamp": "2026-06-05T18:22:10Z",
           "position": {"latitude": 48.76, "longitude": -123.05}}
    q = b.alert_query(env)
    assert "emergency" in q and "dsc.distress" in q
    assert env["message"] in q
    assert "48.76" not in q and "-123.05" not in q
    assert "2026-06-05" not in q
    assert "two" in q.lower()  # the brevity contract is part of the seed


def test_handle_alert_invokes_hermes_once_then_dedups(monkeypatch):
    calls = []
    monkeypatch.setattr(b, "_run_hermes", lambda q, model=None, timing=None: calls.append((q, model)))
    b._ALERT_SEEN.clear()
    env = {"path": "mob.1", "state": "emergency", "message": "MOB",
           "timestamp": "t1", "position": {"latitude": 48.76, "longitude": -123.05}}
    b.handle_alert(env)
    b.handle_alert(env)  # retained redelivery, same timestamp
    assert len(calls) == 1
    assert calls[0][1] == (b.os.environ.get("ALARM_MODEL") or None)


def test_handle_alert_skips_cleared_and_below_warn(monkeypatch):
    calls = []
    monkeypatch.setattr(b, "_run_hermes", lambda q, model=None, timing=None: calls.append(q))
    b._ALERT_SEEN.clear()
    b.handle_alert({"path": "x", "state": "normal", "timestamp": "t"})
    b.handle_alert({"path": "y", "state": "alert", "timestamp": "t"})
    assert calls == []


def test_new_timestamp_reinvokes(monkeypatch):
    calls = []
    monkeypatch.setattr(b, "_run_hermes", lambda q, model=None, timing=None: calls.append(q))
    b._ALERT_SEEN.clear()
    b.handle_alert({"path": "mob.1", "state": "emergency", "timestamp": "t1"})
    b.handle_alert({"path": "mob.1", "state": "emergency", "timestamp": "t2"})
    assert len(calls) == 2


import json
import types


def _fake_hermes_ok(*args, **kwargs):
    return "Wind is 12 knots northwest.", 0


def test_ask_reply_echoes_trace_id(monkeypatch):
    published = []
    monkeypatch.setattr(b, "_invoke_hermes", _fake_hermes_ok)
    monkeypatch.setattr(
        b.publish, "single",
        lambda topic, payload=None, **kw: published.append((topic, json.loads(payload))))
    b._run_hermes("what's the wind?", trace_id="ha17654321")
    assert len(published) == 1
    topic, say = published[0]
    assert topic == b.SAY_TOPIC
    assert say["trace_id"] == "ha17654321"
    assert say["text"] == "Wind is 12 knots northwest."


def test_say_omits_trace_id_when_absent(monkeypatch):
    # Alarm/briefing-style says must NOT carry trace_id — its absence is the
    # discriminator the HA announce automation keys on.
    published = []
    monkeypatch.setattr(b, "_invoke_hermes", _fake_hermes_ok)
    monkeypatch.setattr(
        b.publish, "single",
        lambda topic, payload=None, **kw: published.append(json.loads(payload)))
    b._run_hermes("ALARM DISPATCH: announce this")
    assert len(published) == 1
    assert "trace_id" not in published[0]


def test_dispatch_ask_passes_trace_id(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        b, "_run_hermes",
        lambda q, model=None, timing=None, trace_id=None: seen.update(tid=trace_id))
    b._dispatch("naturali/intents/ask", {"text": "hi", "trace_id": "abc123"})
    assert seen["tid"] == "abc123"


def test_dispatch_ask_without_trace_id_passes_none(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        b, "_run_hermes",
        lambda q, model=None, timing=None, trace_id=None: seen.update(tid=trace_id))
    b._dispatch("naturali/intents/ask", {"text": "hi"})
    assert seen["tid"] is None
