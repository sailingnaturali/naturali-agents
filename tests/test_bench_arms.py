"""Checks for the MCP-vs-CLI arm experiment.

The load-bearing bits: each arm really does hand the agent a different tool
surface, the SignalK URL is resolved late (not baked at import), and token
accounting survives the trip from SDK usage dict to scorecard.
"""
from __future__ import annotations

import pytest

from poseidon.bench import arms
from poseidon.bench.golden import Ask
from poseidon.bench.scoring import AskResult, _tokens, build_scorecard


def _ask(id="a"):
    return Ask(id=id, category="c", prompt="p", expected_tools=("T",), multi_tool=False)


def _result(usage, cost=0.01):
    return AskResult(ask=_ask(), observed_tools=["T"], observed_args=[{}],
                     dt_total=1.0, is_error=False, usage=usage, cost_usd=cost)


@pytest.mark.parametrize("arm,expected_tools", [
    ("mcp", ["mcp__signalk"]),
    ("curl-cold", ["Bash"]),
    ("curl-warm", ["Bash"]),
    ("cli", ["Bash"]),
])
def test_each_arm_exposes_its_own_tool_surface(arm, expected_tools):
    opts = arms.build_options(arm)
    assert opts.tools == expected_tools
    # Only the mcp arm may spawn an MCP server; the Bash arms must not, or the
    # comparison silently measures both surfaces at once.
    assert bool(opts.mcp_servers) is (arm == "mcp")


def test_arms_share_one_persona_so_only_delivery_differs():
    prompts = {a: arms.build_options(a).system_prompt for a in arms.ARMS}
    for text in prompts.values():
        assert text.startswith(arms.PERSONA)
    assert len(set(prompts.values())) == len(arms.ARMS)


def test_curl_warm_carries_knowledge_that_cold_does_not():
    cold = arms.build_options("curl-cold").system_prompt
    warm = arms.build_options("curl-warm").system_prompt
    assert "1.94384" in warm and "1.94384" not in cold      # unit conversion
    assert "belowKeel" in warm and "belowKeel" not in cold   # path cheatsheet
    assert len(warm) > len(cold)


def test_signalk_url_resolves_late_not_at_import(monkeypatch):
    monkeypatch.setenv("SIGNALK_URL", "http://elsewhere:9999")
    assert arms.signalk_url() == "http://elsewhere:9999"
    assert "http://elsewhere:9999" in arms.build_options("curl-warm").system_prompt


def test_tokens_flatten_missing_usage_to_zeros():
    assert _tokens(None) == {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}


def test_scorecard_carries_arm_and_token_means():
    results = [
        _result({"input_tokens": 10, "output_tokens": 100,
                 "cache_read_input_tokens": 1000}, cost=0.02),
        _result({"input_tokens": 30, "output_tokens": 200,
                 "cache_read_input_tokens": 3000}, cost=0.04),
    ]
    card = build_scorecard(model="m", results=results, arm="cli")
    assert card.arm == "cli"
    assert card.tokens_in_mean == 20.0
    assert card.tokens_out_mean == 150.0
    assert card.cache_read_mean == 2000.0
    assert card.cost_usd_total == pytest.approx(0.06)
    assert card.per_ask[0]["tokens"]["cache_read"] == 1000


def test_cost_is_differenced_not_cumulative():
    """ResultMessage.total_cost_usd accumulates over a session; the runner must
    difference it so per-ask cost and the run total are not triangular sums."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    from poseidon.bench import runner

    cumulative = [0.05, 0.11, 0.20]          # session totals after each ask
    asks = [_ask("a"), _ask("b"), _ask("c")]

    async def fake_run_one(client, ask):
        idx = [a.id for a in asks].index(ask.id)
        return AskResult(ask=ask, observed_tools=[], observed_args=[],
                         dt_total=1.0, is_error=False, cost_usd=cumulative[idx])

    async def no_messages():
        return
        yield          # noqa: unreachable — makes this an async generator

    client = AsyncMock()
    client.receive_response = lambda: no_messages()
    with patch.object(runner, "_run_one", new=fake_run_one), \
         patch.object(runner, "build_options"), \
         patch.object(runner, "ClaudeSDKClient", return_value=client):
        results = asyncio.run(runner.run_benchmark("m", asks=asks, arm="cli"))

    assert [round(r.cost_usd, 2) for r in results] == [0.05, 0.06, 0.09]
    assert round(sum(r.cost_usd for r in results), 2) == 0.20   # == session total
