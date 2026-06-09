import json
import logging
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "bridges"))

import mqtt_to_hermes as b


def test_parse_t_ha_accepts_numbers_only():
    assert b._parse_t_ha({"t_ha": 1749500000.25}) == 1749500000.25
    assert b._parse_t_ha({"t_ha": 1749500000}) == 1749500000.0
    assert b._parse_t_ha({"t_ha": "garbage"}) is None
    assert b._parse_t_ha({}) is None
    assert b._parse_t_ha({"t_ha": True}) is None
    assert b._parse_t_ha({"t_ha": False}) is None


def test_build_record_full_ask_shape():
    rec = b.build_record(
        "ask", "a1b2c3", "2026-06-09T14:02:11-07:00",
        t_ha=100.0, t_receive_wall=100.41,
        dt_hermes=11.832901, dt_publish=0.0512, dt_total=12.29,
        query_chars=32, response_chars=118, rc=0, model=None,
    )
    assert rec == {
        "trace_id": "a1b2c3", "ts": "2026-06-09T14:02:11-07:00", "kind": "ask",
        "dt_transport": 0.41, "dt_hermes": 11.833, "dt_publish": 0.051,
        "dt_total": 12.29, "query_chars": 32, "response_chars": 118,
        "rc": 0, "model": None,
    }


def test_build_record_missing_t_ha_gives_null_transport():
    rec = b.build_record("alert", "x", "ts", t_ha=None, t_receive_wall=100.0, rc=0)
    assert rec["dt_transport"] is None


def test_build_record_negative_skew_recorded_as_is():
    rec = b.build_record("ask", "x", "ts", t_ha=100.5, t_receive_wall=100.0, rc=0)
    assert rec["dt_transport"] == -0.5


def test_append_timing_record_appends_jsonl(tmp_path, monkeypatch):
    path = tmp_path / "logs" / "voice-timing.jsonl"  # dir doesn't exist yet
    monkeypatch.setattr(b, "TIMING_PATH", str(path))
    b.append_timing_record({"trace_id": "a", "kind": "ask"})
    b.append_timing_record({"trace_id": "b", "kind": "alert"})
    lines = path.read_text().splitlines()
    assert [json.loads(l)["trace_id"] for l in lines] == ["a", "b"]


def test_append_timing_record_never_raises(tmp_path, monkeypatch, caplog):
    # A *file* where the parent dir should be → makedirs/open fails.
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    monkeypatch.setattr(b, "TIMING_PATH", str(blocker / "voice-timing.jsonl"))
    with caplog.at_level(logging.WARNING):
        b.append_timing_record({"trace_id": "a"})  # must not raise
    assert "timing record" in caplog.text


def test_append_timing_record_nan_warns_instead_of_corrupting(tmp_path, monkeypatch, caplog):
    path = tmp_path / "voice-timing.jsonl"
    monkeypatch.setattr(b, "TIMING_PATH", str(path))
    with caplog.at_level(logging.WARNING):
        b.append_timing_record({"trace_id": "a", "dt_total": float("nan")})  # must not raise
    assert "timing record" in caplog.text
    assert path.stat().st_size == 0  # file created but empty due to exception


class FakeCompleted:
    def __init__(self, stdout="Wind is 12 knots, Captain.", returncode=0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def _instrument(monkeypatch, tmp_path, run=None):
    """Patch timing path, subprocess.run, and MQTT publish; return (path, published)."""
    path = tmp_path / "voice-timing.jsonl"
    monkeypatch.setattr(b, "TIMING_PATH", str(path))
    monkeypatch.setattr(
        b.subprocess, "run", run or (lambda cmd, **kw: FakeCompleted())
    )
    published = []
    monkeypatch.setattr(
        b.publish, "single", lambda *a, **kw: published.append((a, kw))
    )
    return path, published


def test_ask_dispatch_writes_full_record(tmp_path, monkeypatch):
    path, published = _instrument(monkeypatch, tmp_path)
    b._dispatch("naturali/intents/ask",
                {"text": "what's the wind?", "t_ha": time.time() - 0.5})
    rec = json.loads(path.read_text().splitlines()[0])
    assert rec["kind"] == "ask"
    assert 0.0 < rec["dt_transport"] < 5.0
    assert rec["rc"] == 0
    assert rec["query_chars"] == len("what's the wind?")
    assert rec["response_chars"] == len("Wind is 12 knots, Captain.")
    assert rec["dt_total"] >= rec["dt_hermes"] >= 0.0
    assert rec["model"] is None
    assert len(rec["trace_id"]) == 6
    assert len(published) == 1


def test_say_payload_unchanged_by_timing(tmp_path, monkeypatch):
    _, published = _instrument(monkeypatch, tmp_path)
    b._dispatch("naturali/intents/ask", {"text": "hi", "t_ha": time.time()})
    payload = json.loads(published[0][1]["payload"])
    assert set(payload) == {"agent", "text"}  # no timing leakage into TTS path


def test_hermes_timeout_still_writes_record(tmp_path, monkeypatch):
    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 60)
    path, published = _instrument(monkeypatch, tmp_path, run=boom)
    b._dispatch("naturali/intents/ask", {"text": "hi", "t_ha": time.time()})
    rec = json.loads(path.read_text().splitlines()[0])
    assert rec["rc"] == "timeout"
    assert rec["response_chars"] == 0
    assert published == []


def test_nonzero_exit_still_writes_record(tmp_path, monkeypatch):
    path, published = _instrument(
        monkeypatch, tmp_path, run=lambda cmd, **kw: FakeCompleted(returncode=3)
    )
    b._dispatch("naturali/intents/ask", {"text": "hi"})
    rec = json.loads(path.read_text().splitlines()[0])
    assert rec["rc"] == 3
    assert rec["dt_transport"] is None  # no t_ha in payload
    assert published == []


def test_alert_dispatch_records_kind_and_model(tmp_path, monkeypatch):
    monkeypatch.setenv("ALARM_MODEL", "claude")
    path, published = _instrument(monkeypatch, tmp_path)
    b._ALERT_SEEN.clear()
    b._dispatch("naturali/alerts/electrical",
                {"path": "electrical.batteries.0", "state": "alarm",
                 "message": "Battery voltage critical.", "timestamp": "t1"})
    rec = json.loads(path.read_text().splitlines()[0])
    assert rec["kind"] == "alert"
    assert rec["dt_transport"] is None  # alert envelopes carry no t_ha
    assert rec["model"] == "claude"
    assert len(published) == 1
