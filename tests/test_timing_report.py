import json

import timing_report as tr


def _recs():
    return [
        {"trace_id": "a", "kind": "ask", "dt_transport": 0.4, "dt_hermes": 10.0,
         "dt_publish": 0.05, "dt_total": 10.5, "rc": 0},
        {"trace_id": "b", "kind": "ask", "dt_transport": -0.2, "dt_hermes": 20.0,
         "dt_publish": 0.05, "dt_total": 20.3, "rc": 0},
        {"trace_id": "c", "kind": "ask", "dt_transport": None, "dt_hermes": 12.0,
         "dt_publish": 0.04, "dt_total": 12.1, "rc": "timeout"},
        {"trace_id": "d", "kind": "briefing", "dt_transport": 0.3,
         "dt_subprocess": 95.0, "rc": 0},
    ]


def test_percentile_nearest_rank():
    vals = list(range(1, 11))  # 1..10
    assert tr.percentile(vals, 50) == 5
    assert tr.percentile(vals, 95) == 10
    assert tr.percentile([7], 50) == 7
    assert tr.percentile([], 50) is None


def test_summarize_groups_by_kind_and_field():
    s = tr.summarize(_recs())
    assert s["ask"]["dt_hermes"]["n"] == 3
    assert s["ask"]["dt_hermes"]["max"] == 20.0
    assert s["briefing"]["dt_subprocess"]["p50"] == 95.0
    assert "dt_transport" in s["ask"]  # None values excluded from stats
    assert s["ask"]["dt_transport"]["n"] == 2


def test_negative_transport_flagged():
    assert tr.count_negative_transport(_recs()) == 1


def test_worst_returns_top_n_by_dt_total():
    worst = tr.worst(_recs(), n=2)
    assert [w["trace_id"] for w in worst] == ["b", "c"]


def test_load_records_skips_malformed_lines(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps(_recs()[0]) + "\nnot json\n")
    assert len(tr.load_records(str(p))) == 1


def test_render_mentions_kinds_and_percentiles():
    out = tr.render(_recs())
    assert "ask" in out and "briefing" in out
    assert "p95" in out
    assert "negative dt_transport" in out
