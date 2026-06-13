"""poseidon.bench.scoring — per-ask correctness + scorecard aggregation.

Tool-call correctness (ADR 0002 §Benchmark): every expected tool must appear in
the observed tools (recall/subset, order-tolerant); extra/helper tool calls are
allowed and do not fail the ask — efficiency is the latency metric's job.
When an ask declares expected_args for a tool, the observed input for that tool
must be a superset of the expected key/values. Latency uses p50/p95 over
dt_total; the cold warm-up ask is excluded upstream by the runner, so every
AskResult here is a warm measurement.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from poseidon.bench.golden import Ask


@dataclass
class AskResult:
    ask: Ask
    observed_tools: list[str]
    observed_args: list[dict]
    dt_total: float
    is_error: bool
    text: str = ""


@dataclass
class Scorecard:
    model: str
    n: int
    correctness: float          # fraction of asks with a tool-set match
    error_rate: float
    latency_p50: float
    latency_p95: float
    per_ask: list[dict] = field(default_factory=list)


def score_ask(ask: Ask, observed_tools: list[str],
              observed_args: list[dict] | None = None) -> bool:
    if not set(ask.expected_tools).issubset(set(observed_tools)):
        return False
    if not ask.expected_args:
        return True
    observed_args = observed_args or []
    by_tool: dict[str, dict] = {}
    for name, args in zip(observed_tools, observed_args):
        by_tool.setdefault(name, args or {})
    for tool, expected in ask.expected_args.items():
        got = by_tool.get(tool, {})
        if any(got.get(k) != v for k, v in expected.items()):
            return False
    return True


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (p / 100) * (len(ordered) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def build_scorecard(model: str, results: list[AskResult]) -> Scorecard:
    n = len(results)
    passes = sum(
        1 for r in results
        if not r.is_error and score_ask(r.ask, r.observed_tools, r.observed_args)
    )
    errors = sum(1 for r in results if r.is_error)
    latencies = [r.dt_total for r in results if not r.is_error]
    per_ask = [
        {
            "id": r.ask.id,
            "category": r.ask.category,
            "expected": list(r.ask.expected_tools),
            "observed": r.observed_tools,
            "match": (not r.is_error) and score_ask(r.ask, r.observed_tools, r.observed_args),
            "dt_total": round(r.dt_total, 3),
            "is_error": r.is_error,
        }
        for r in results
    ]
    return Scorecard(
        model=model,
        n=n,
        correctness=(passes / n) if n else 0.0,
        error_rate=(errors / n) if n else 0.0,
        latency_p50=round(percentile(latencies, 50), 3),
        latency_p95=round(percentile(latencies, 95), 3),
        per_ask=per_ask,
    )
