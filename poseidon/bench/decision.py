"""poseidon.bench.decision — ADR-0002 swap rule.

A candidate replaces the incumbent primary only if ALL hold:
  1. faster on p50 warm hop,
  2. correctness >= incumbent - eps,
  3. session-stable (zero error rate).
Returns a Verdict with a human reason naming the first failing condition.
"""
from __future__ import annotations

from dataclasses import dataclass

from poseidon.bench.scoring import Scorecard


@dataclass
class Verdict:
    swap: bool
    reason: str


def compare(incumbent: Scorecard, candidate: Scorecard, eps: float = 0.05) -> Verdict:
    if candidate.error_rate > 0:
        return Verdict(False, f"candidate not session-stable "
                              f"(error_rate={candidate.error_rate:.2f})")
    if candidate.latency_p50 >= incumbent.latency_p50:
        return Verdict(False, f"candidate not faster "
                              f"(p50 {candidate.latency_p50:.2f}s vs "
                              f"incumbent {incumbent.latency_p50:.2f}s)")
    if candidate.correctness < incumbent.correctness - eps:
        return Verdict(False, f"candidate correctness below tolerance "
                              f"({candidate.correctness:.2f} < "
                              f"{incumbent.correctness:.2f} - {eps})")
    return Verdict(True, f"{candidate.model} is faster "
                         f"({candidate.latency_p50:.2f}s vs "
                         f"{incumbent.latency_p50:.2f}s) and within correctness "
                         f"tolerance — replaces {incumbent.model}")
