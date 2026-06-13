from __future__ import annotations

import json

from poseidon.bench.scoring import Scorecard
from poseidon.bench.report import render_markdown, write_results


def _card():
    return Scorecard(
        model="claude-sonnet-4-6", n=8, correctness=0.875, error_rate=0.0,
        latency_p50=5.6, latency_p95=7.1,
        per_ask=[{"id": "depth", "category": "engineer-direct",
                  "expected": ["mcp__signalk__depth_state"],
                  "observed": ["mcp__signalk__depth_state"], "match": True,
                  "dt_total": 5.6, "is_error": False}],
    )


def test_render_markdown_contains_headline_numbers():
    md = render_markdown(_card(), run_date="2026-06-13")
    assert "claude-sonnet-4-6" in md
    assert "87.5%" in md          # correctness as percent
    assert "5.6" in md            # p50
    assert "depth" in md          # per-ask row


def test_write_results_emits_json_and_md(tmp_path):
    paths = write_results(_card(), out_dir=tmp_path, run_date="2026-06-13")
    data = json.loads(paths["json"].read_text())
    assert data["model"] == "claude-sonnet-4-6"
    assert data["correctness"] == 0.875
    assert paths["md"].read_text().startswith("### Benchmark run")
