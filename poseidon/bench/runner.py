"""poseidon.bench.runner — live runner over one warm SDK session.

Reuses the production crew_options() (real system prompt, tool subsets,
subagents) and overrides only the model, so the benchmark measures the agent as
shipped. One throwaway warm-up ask absorbs connect/cold-cache cost; every scored
ask is therefore warm. Engine swap = pass a different model id (Sonnet/Fable via
the Anthropic API; an OSS model needs ANTHROPIC_BASE_URL pointed at a compatible
gateway — a Phase-1 extension, not exercised here).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from claude_agent_sdk import ClaudeSDKClient

from poseidon.bench.arms import build_options, signalk_url
from poseidon.bench.collect import collect_turn
from poseidon.bench.golden import Ask, load_golden_asks
from poseidon.bench.scoring import AskResult
from poseidon.profiles import crew_options


def _fetch_truth(ask: Ask) -> str:
    """Read the ask's answer straight off SignalK, next to the agent's turn.

    Deliberately a raw urllib GET, not signalk-mcp's client: the whole point is
    an independent reading the arms cannot influence. Values are time-varying
    (battery cycles with the sun, tanks fill), so truth is captured per ask
    rather than once per run.
    """
    if not ask.truth_path:
        return ""
    url = f"{signalk_url()}/signalk/v1/api/vessels/self/{ask.truth_path.replace('.', '/')}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:   # noqa: S310 — fixed host
            raw = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return f"<truth unavailable: {exc}>"
    value = raw.get("value", raw) if isinstance(raw, dict) else raw
    return json.dumps(value, default=str)[:400]


async def _run_one(client: ClaudeSDKClient, ask: Ask) -> AskResult:
    t0 = time.monotonic()
    await client.query(ask.prompt)
    messages = [m async for m in client.receive_response()]
    dt = time.monotonic() - t0
    obs = collect_turn(messages)
    return AskResult(
        ask=ask,
        observed_tools=obs.tools,
        observed_args=obs.tool_inputs,
        dt_total=dt,
        is_error=obs.is_error,
        text=obs.text,
        usage=obs.usage,
        cost_usd=obs.cost_usd,
        truth=_fetch_truth(ask),
    )


async def run_benchmark(model: str, repeat: int = 1,
                        asks: list[Ask] | None = None,
                        arm: str | None = None) -> list[AskResult]:
    """arm=None keeps the original ADR-0002 behaviour (full production crew
    options, all MCP servers). Passing an arm switches to the isolated
    single-agent tool-surface comparison in arms.py."""
    asks = asks or load_golden_asks()
    options = build_options(arm) if arm else crew_options()
    options.model = model
    client = ClaudeSDKClient(options=options)
    await client.connect()
    try:
        # Throwaway warm-up: pay connect/cold-cache cost off the clock.
        await client.query("Hello.")
        async for _ in client.receive_response():
            pass

        results: list[AskResult] = []
        # ResultMessage.total_cost_usd is CUMULATIVE for the session, not the
        # turn — summing it raw gives a triangular over-count. Difference it.
        prev_cost = 0.0
        for _ in range(repeat):
            for ask in asks:
                result = await _run_one(client, ask)
                result.cost_usd, prev_cost = max(result.cost_usd - prev_cost, 0.0), result.cost_usd
                results.append(result)
        return results
    finally:
        await client.disconnect()
