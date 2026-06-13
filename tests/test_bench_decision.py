from __future__ import annotations

from poseidon.bench.scoring import Scorecard
from poseidon.bench.decision import compare, Verdict


def _card(model, correctness, p50, error_rate=0.0):
    return Scorecard(model=model, n=8, correctness=correctness, error_rate=error_rate,
                     latency_p50=p50, latency_p95=p50 + 1)


def test_faster_and_as_accurate_swaps():
    base = _card("sonnet", 1.0, 6.0)
    cand = _card("oss-14b", 1.0, 4.0)
    v = compare(base, cand, eps=0.05)
    assert isinstance(v, Verdict)
    assert v.swap is True


def test_faster_but_less_accurate_beyond_eps_holds():
    base = _card("sonnet", 1.0, 6.0)
    cand = _card("oss-14b", 0.80, 4.0)
    v = compare(base, cand, eps=0.05)
    assert v.swap is False
    assert "correctness" in v.reason


def test_within_eps_correctness_ok():
    base = _card("sonnet", 1.0, 6.0)
    cand = _card("oss-14b", 0.96, 4.0)
    assert compare(base, cand, eps=0.05).swap is True


def test_slower_holds_even_if_more_accurate():
    base = _card("sonnet", 0.9, 4.0)
    cand = _card("oss-14b", 1.0, 5.0)
    v = compare(base, cand, eps=0.05)
    assert v.swap is False
    assert "faster" in v.reason


def test_candidate_with_errors_holds():
    base = _card("sonnet", 1.0, 6.0)
    cand = _card("oss-14b", 1.0, 4.0, error_rate=0.1)
    v = compare(base, cand, eps=0.05)
    assert v.swap is False
    assert "stable" in v.reason
