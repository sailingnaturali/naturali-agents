#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Summarize voice-pipeline timing records (voice-timing.jsonl).

Usage:
    uv run scripts/timing_report.py [path]

Default path: ~/Library/Logs/naturali/voice-timing.jsonl
Prints per-kind p50/p95/max for each dt_* hop, the worst dispatches by
dt_total, and a clock-skew flag (negative dt_transport count). Output is
pasted into the Phase 0 retro / runtime ADR.
"""

from __future__ import annotations

import json
import math
import os
import sys

DEFAULT_PATH = os.path.expanduser("~/Library/Logs/naturali/voice-timing.jsonl")
DT_FIELDS = ("dt_transport", "dt_hermes", "dt_first_say", "dt_publish",
             "dt_total", "dt_subprocess")


def load_records(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a torn write; the rest of the file is fine
    return records


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile; None for an empty list."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, math.ceil(p / 100 * len(s)) - 1)
    return s[k]


def summarize(records: list[dict]) -> dict:
    """{kind: {dt_field: {n, p50, p95, max}}} — None values excluded."""
    grouped: dict[str, dict[str, list[float]]] = {}
    for rec in records:
        kind = rec.get("kind", "?")
        for field in DT_FIELDS:
            value = rec.get(field)
            if isinstance(value, (int, float)):
                grouped.setdefault(kind, {}).setdefault(field, []).append(value)
    return {
        kind: {
            field: {
                "n": len(vals),
                "p50": percentile(vals, 50),
                "p95": percentile(vals, 95),
                "max": max(vals),
            }
            for field, vals in fields.items()
        }
        for kind, fields in grouped.items()
    }


def count_negative_transport(records: list[dict]) -> int:
    return sum(
        1 for r in records
        if isinstance(r.get("dt_transport"), (int, float)) and r["dt_transport"] < 0
    )


def worst(records: list[dict], n: int = 5) -> list[dict]:
    timed = [r for r in records if isinstance(r.get("dt_total"), (int, float))]
    return sorted(timed, key=lambda r: r["dt_total"], reverse=True)[:n]


def render(records: list[dict]) -> str:
    lines = [f"voice-timing report — {len(records)} records", ""]
    summary = summarize(records)
    for kind in sorted(summary):
        lines.append(f"[{kind}]")
        lines.append(f"  {'hop':<14}{'n':>4}{'p50':>9}{'p95':>9}{'max':>9}")
        for field in DT_FIELDS:
            if field not in summary[kind]:
                continue
            s = summary[kind][field]
            lines.append(
                f"  {field:<14}{s['n']:>4}{s['p50']:>9.2f}{s['p95']:>9.2f}{s['max']:>9.2f}"
            )
        lines.append("")
    lines.append("worst by dt_total:")
    for r in worst(records):
        lines.append(
            f"  {r.get('trace_id')}  {r.get('ts', '?')}  kind={r.get('kind')}"
            f"  dt_total={r.get('dt_total')}  rc={r.get('rc')}"
        )
    negatives = count_negative_transport(records)
    lines.append("")
    lines.append(
        f"negative dt_transport records (HA↔Studio clock skew): {negatives}"
    )
    return "\n".join(lines)


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    if not os.path.exists(path):
        sys.exit(f"no timing file at {path}")
    records = load_records(path)
    if not records:
        sys.exit("timing file is empty")
    print(render(records))


if __name__ == "__main__":
    main()
