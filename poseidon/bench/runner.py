"""poseidon.bench.runner — live runner over one warm SDK session.

Reuses the production crew_options() (real system prompt, tool subsets,
subagents) and overrides only the model, so the benchmark measures the agent as
shipped. One throwaway warm-up ask absorbs connect/cold-cache cost; every scored
ask is therefore warm. Engine swap = pass a different model id (Sonnet/Fable via
the Anthropic API; an OSS model needs ANTHROPIC_BASE_URL pointed at a compatible
gateway — a Phase-1 extension, not exercised here).
"""
from __future__ import annotations

import time

from claude_agent_sdk import ClaudeSDKClient

from poseidon.bench.collect import collect_turn
from poseidon.bench.golden import Ask, load_golden_asks
from poseidon.bench.scoring import AskResult
from poseidon.profiles import crew_options


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
    )


async def run_benchmark(model: str, repeat: int = 1,
                        asks: list[Ask] | None = None) -> list[AskResult]:
    asks = asks or load_golden_asks()
    options = crew_options()
    options.model = model
    client = ClaudeSDKClient(options=options)
    await client.connect()
    try:
        # Throwaway warm-up: pay connect/cold-cache cost off the clock.
        await client.query("Hello.")
        async for _ in client.receive_response():
            pass

        results: list[AskResult] = []
        for _ in range(repeat):
            for ask in asks:
                results.append(await _run_one(client, ask))
        return results
    finally:
        await client.disconnect()
