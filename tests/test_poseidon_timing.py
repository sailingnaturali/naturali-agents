"""poseidon.timing record schema and fail-safe writer."""
import json

from poseidon import timing


def test_build_record_core_fields():
    rec = timing.build_record(
        "ask", "abc123", "2026-06-11T10:00:00-07:00",
        t_ha=100.0, t_receive_wall=100.5,
        dt_hermes=4.2, dt_first_say=1.234567, dt_publish=0.01,
        dt_total=4.5, query_chars=10, response_chars=40, rc=0,
        model="claude-sonnet-4-6",
    )
    assert rec["trace_id"] == "abc123"
    assert rec["dt_transport"] == 0.5
    assert rec["dt_first_say"] == 1.235  # floats rounded to 3 decimals
    assert rec["rc"] == 0


def test_t_ha_rejects_bool_and_garbage():
    assert timing._parse_t_ha({"t_ha": True}) is None
    assert timing._parse_t_ha({"t_ha": "soon"}) is None
    assert timing._parse_t_ha({"t_ha": 12.5}) == 12.5
    assert timing._parse_t_ha({}) is None


def test_append_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(timing, "TIMING_PATH", str(tmp_path / "x" / "t.jsonl"))
    timing.append_timing_record({"trace_id": "a", "ts": "t", "kind": "ask"})
    line = (tmp_path / "x" / "t.jsonl").read_text().strip()
    assert json.loads(line)["kind"] == "ask"
    # unserializable record must warn-and-continue, not raise
    timing.append_timing_record({"bad": float("nan")})


def test_timing_ctx_shape():
    ctx = timing.timing_ctx("alert", {"t_ha": 5.0})
    assert ctx["kind"] == "alert" and len(ctx["trace_id"]) == 6
    assert ctx["t_ha"] == 5.0 and "t_mono" in ctx and "t_wall" in ctx
