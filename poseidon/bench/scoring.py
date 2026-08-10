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
    usage: dict | None = None
    cost_usd: float = 0.0            # this turn alone (differenced by the runner)
    cost_usd_session: float = 0.0    # cumulative session cost as the SDK reported it
    truth: str = ""          # live SignalK value at ask time, for hand-grading


def _tokens(usage: dict | None) -> dict:
    """Flatten an SDK usage dict. Cache reads are counted separately because a
    warm session bills most of its input at the cache rate — lumping them in
    would hide exactly the cost this experiment is about (schemas resident in
    every turn's prompt)."""
    u = usage or {}
    return {
        "input": int(u.get("input_tokens", 0) or 0),
        "output": int(u.get("output_tokens", 0) or 0),
        "cache_read": int(u.get("cache_read_input_tokens", 0) or 0),
        "cache_write": int(u.get("cache_creation_input_tokens", 0) or 0),
    }


@dataclass
class Scorecard:
    model: str
    n: int
    correctness: float          # fraction of asks with a tool-set match
    error_rate: float
    latency_p50: float
    latency_p95: float
    per_ask: list[dict] = field(default_factory=list)
    # Arm experiment (MCP vs CLI): defaulted so old scorecard JSON still loads
    # through Scorecard(**data) in __main__._load_baseline.
    arm: str = ""
    # --- per turn (means over asks): what one ask costs ---
    tokens_in_mean: float = 0.0
    tokens_out_mean: float = 0.0
    cache_read_mean: float = 0.0
    cache_write_mean: float = 0.0
    cost_usd_mean: float = 0.0
    # --- per session (totals over the run): what holding a conversation costs ---
    # The two views answer different questions, and the fleet-vs-arm gap only
    # shows up in the session one — a resident tool schema is billed on every
    # turn, so its cost scales with conversation length, not with ask count.
    tokens_in_total: int = 0
    tokens_out_total: int = 0
    cache_read_total: int = 0
    cache_write_total: int = 0
    cost_usd_total: float = 0.0      # sum of per-turn costs
    cost_usd_session: float = 0.0    # final cumulative figure the SDK reported


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


def build_scorecard(model: str, results: list[AskResult], arm: str = "") -> Scorecard:
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
            "tokens": _tokens(r.usage),
            "cost_usd": round(r.cost_usd, 6),
            "cost_usd_session": round(r.cost_usd_session, 6),
            "answer": r.text,
            "truth": r.truth,
        }
        for r in results
    ]
    toks = [_tokens(r.usage) for r in results]
    total = lambda key: sum(t[key] for t in toks)                       # noqa: E731
    mean = lambda key: (total(key) / len(toks)) if toks else 0.0        # noqa: E731
    return Scorecard(
        model=model,
        n=n,
        correctness=(passes / n) if n else 0.0,
        error_rate=(errors / n) if n else 0.0,
        latency_p50=round(percentile(latencies, 50), 3),
        latency_p95=round(percentile(latencies, 95), 3),
        per_ask=per_ask,
        arm=arm,
        tokens_in_mean=round(mean("input"), 1),
        tokens_out_mean=round(mean("output"), 1),
        cache_read_mean=round(mean("cache_read"), 1),
        cache_write_mean=round(mean("cache_write"), 1),
        cost_usd_mean=round((sum(r.cost_usd for r in results) / n) if n else 0.0, 6),
        tokens_in_total=total("input"),
        tokens_out_total=total("output"),
        cache_read_total=total("cache_read"),
        cache_write_total=total("cache_write"),
        cost_usd_total=round(sum(r.cost_usd for r in results), 6),
        cost_usd_session=round(max((r.cost_usd_session for r in results), default=0.0), 6),
    )
