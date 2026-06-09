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
