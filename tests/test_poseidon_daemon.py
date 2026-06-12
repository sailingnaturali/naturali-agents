"""Daemon routing: ask/alert/briefing lanes and say payload contract."""
import asyncio
import importlib
import json

import pytest

from poseidon import daemon, timing as timing_mod
from poseidon.engine import TurnResult


@pytest.fixture(autouse=True)
def _isolated_timing(tmp_path, monkeypatch):
    monkeypatch.setattr(timing_mod, "TIMING_PATH", str(tmp_path / "t.jsonl"))


class FakeChannel:
    def __init__(self, result):
        self.result = result
        self.asks = []

    async def ask(self, text, on_interim):
        self.asks.append(text)
        on_interim("Let me check the instruments.")
        return self.result


class FakeAlarmLane:
    def __init__(self, narration="Battery alarm."):
        self.narration = narration
        self.envs = []

    async def handle(self, env):
        self.envs.append(env)
        return self.narration


def make_app(channel=None, alarms=None):
    published = []

    def fake_publish(text, trace_id=None, interim=False):
        published.append({"text": text, "trace_id": trace_id,
                          "interim": interim})

    app = daemon.Poseidon(
        channel=channel or FakeChannel(TurnResult("ok", 0, 1.0, None)),
        alarm_lane=alarms or FakeAlarmLane(),
        publish_say=fake_publish,
        run_briefing=lambda timing: None,
    )
    return app, published


def test_ask_publishes_interim_without_trace_and_final_with():
    ch = FakeChannel(TurnResult("Wind is 12 knots.", 0, 1.2, 0.4))
    app, published = make_app(channel=ch)
    asyncio.run(app.dispatch("naturali/intents/ask",
                             {"text": "wind?", "trace_id": "t1", "t_ha": 1.0}))
    # interim publishing is fire-and-forget; assert content, not ordering.
    # interim=True: HA's broadcast automation must skip these (a puck announce
    # mid-voice-session kills the session — found live 2026-06-11).
    assert {"text": "Let me check the instruments.",
            "trace_id": None, "interim": True} in published
    assert {"text": "Wind is 12 knots.", "trace_id": "t1",
            "interim": False} in published


def test_ask_timeout_publishes_nothing_final():
    ch = FakeChannel(TurnResult("", "timeout", 60.0, None))
    app, published = make_app(channel=ch)
    asyncio.run(app.dispatch("naturali/intents/ask", {"text": "slow?"}))
    finals = [p for p in published if p["text"] != "Let me check the instruments."]
    assert finals == []   # HA's 75s fallback is the backstop


def test_ask_rc1_publishes_failure_say_with_trace():
    # spec §6: hard failures publish a failure say so HA's wait resolves
    # instead of dangling to the 75 s fallback
    ch = FakeChannel(TurnResult("", 1, 2.0, None))
    app, published = make_app(channel=ch)
    asyncio.run(app.dispatch("naturali/intents/ask",
                             {"text": "broken?", "trace_id": "t9"}))
    assert {"text": "Sorry Captain, something went wrong answering that.",
            "trace_id": "t9", "interim": False} in published


def test_empty_ask_ignored():
    app, published = make_app()
    asyncio.run(app.dispatch("naturali/intents/ask", {"text": "  "}))
    assert published == []


def test_alert_routes_to_alarm_lane_and_speaks_unsolicited():
    lane = FakeAlarmLane("Battery alarm. Check the charger.")
    app, published = make_app(alarms=lane)
    asyncio.run(app.dispatch("naturali/alerts/electrical",
                             {"state": "alarm", "path": "p", "message": "m",
                              "timestamp": "T"}))
    assert lane.envs and published == [
        {"text": "Battery alarm. Check the charger.", "trace_id": None,
         "interim": False}]


def test_unknown_topic_logged_not_crashed():
    app, published = make_app()
    asyncio.run(app.dispatch("naturali/other", {}))
    assert published == []


def test_payload_decode_fallback():
    assert daemon.decode_payload(b'{"text": "hi"}') == {"text": "hi"}
    assert daemon.decode_payload(b"plain words") == {"text": "plain words"}


def test_payload_decode_wraps_non_dict_json():
    assert daemon.decode_payload(b"42") == {"text": "42"}


def test_strip_markdown_removes_speech_hostile_markers():
    out = daemon._strip_markdown("**16.4 knots** and `raw`\n## Header\n- item")
    assert out == "16.4 knots and raw\nHeader\nitem"
    # collapse runs of blank lines; keep italic content
    assert daemon._strip_markdown("a\n\n\n\nb") == "a\n\nb"
    assert daemon._strip_markdown("*calm* seas") == "calm seas"


def test_run_env_reload_applies_mqtt_creds(monkeypatch, tmp_path):
    """config constants must re-freeze after the env file loads."""
    from poseidon import config
    envfile = tmp_path / ".env"
    envfile.write_text("MQTT_USER=naturali\nMQTT_PASSWORD=pw\n")
    monkeypatch.delenv("MQTT_USER", raising=False)
    monkeypatch.delenv("MQTT_PASSWORD", raising=False)
    config.load_env_file(str(envfile))
    cfg = importlib.reload(config)
    assert cfg.MQTT_USER == "naturali" and cfg.MQTT_PASSWORD == "pw"
    # cleanup: reload once more after monkeypatch-managed env teardown happens
    # is not possible here; explicitly delete and reload to restore defaults
    monkeypatch.delenv("MQTT_USER", raising=False)
    monkeypatch.delenv("MQTT_PASSWORD", raising=False)
    importlib.reload(config)


def test_speech_normalization_units_and_tables():
    text = ("Wind **13 kn** from the NW, seas 0.5 m.\n"
            "| Name | Dist |\n|---|---|\n| Clam Bay | 4.2 nm |\n"
            "Course 305°T, bearing 120°M, then 90°.")
    out = daemon._normalize_speech(daemon._strip_markdown(text))
    assert "13 knots" in out and "kn " not in out
    assert "4.2 nautical miles" in out
    assert "305 degrees true" in out and "120 degrees magnetic" in out
    assert "90 degrees" in out
    assert "|" not in out and "---" not in out
