import json
import logging
import sys
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
