from poseidon.bench.golden import load_offpath_asks
from poseidon.bench.offpath import answer_rate
from poseidon.bench.scoring import AskResult


def test_offpath_asks_load():
    asks = load_offpath_asks()
    assert len(asks) >= 12
    assert all(a.expected_tools for a in asks)


def test_answer_rate_counts_tool_matches_only():
    asks = load_offpath_asks()
    a = asks[0]
    hit = AskResult(ask=a, observed_tools=list(a.expected_tools), observed_args=[],
                    dt_total=1.0, is_error=False, text="done")
    miss = AskResult(ask=a, observed_tools=[], observed_args=[],
                     dt_total=1.0, is_error=False, text="NO_ROUTE")
    assert answer_rate([hit]) == 1.0
    assert answer_rate([miss]) == 0.0
