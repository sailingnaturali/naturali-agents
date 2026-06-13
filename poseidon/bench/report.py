"""poseidon.bench.report — scorecard → JSON + markdown, written to a results dir.

render_markdown() returns the exact block to paste under ADR 0002 § Benchmark
results. write_results() persists <date>-<model>.json and .md under out_dir
(default dev/bench-results/).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from poseidon.bench.scoring import Scorecard

_DEFAULT_OUT = Path(__file__).resolve().parents[2] / "dev" / "bench-results"


def render_markdown(card: Scorecard, run_date: str) -> str:
    lines = [
        f"### Benchmark run {run_date} — {card.model}",
        "",
        f"- Asks: {card.n} | correctness: {card.correctness * 100:.1f}% | "
        f"error rate: {card.error_rate * 100:.1f}%",
        f"- Warm-hop latency: p50 {card.latency_p50:.2f}s | p95 {card.latency_p95:.2f}s",
        "",
        "| ask | category | expected | observed | match | dt_total (s) |",
        "|-----|----------|----------|----------|-------|--------------|",
    ]
    for row in card.per_ask:
        lines.append(
            f"| {row['id']} | {row['category']} | "
            f"{', '.join(row['expected'])} | {', '.join(row['observed']) or '—'} | "
            f"{'✓' if row['match'] else '✗'} | {row['dt_total']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def write_results(card: Scorecard, out_dir: Path | None = None,
                  run_date: str = "") -> dict[str, Path]:
    out_dir = Path(out_dir or _DEFAULT_OUT)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_model = card.model.replace("/", "_").replace(":", "_")
    stem = f"{run_date}-{safe_model}" if run_date else safe_model
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(asdict(card), indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(card, run_date), encoding="utf-8")
    return {"json": json_path, "md": md_path}
