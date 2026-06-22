"""poseidon.bench.offpath — measure capability-memory fallback on off-golden asks.

Runs the off-path ask set with the fallback ON or OFF and reports answer-rate (tool-set
match, NO_ROUTE = miss). The golden set stays the no-regression canary (run separately via
`python -m poseidon.bench`). ON re-queries once with recalled capability facts when the
first turn returns NO_ROUTE.
"""
from __future__ import annotations

import time

from claude_agent_sdk import ClaudeSDKClient

from poseidon import capability, fallback
from poseidon.bench.collect import collect_turn
from poseidon.bench.golden import Ask, load_offpath_asks
from poseidon.bench.scoring import AskResult, score_ask
from poseidon.profiles import crew_options


def answer_rate(results: list[AskResult]) -> float:
    if not results:
        return 0.0
    hits = sum(1 for r in results
               if not r.is_error
               and not fallback.is_no_route(r.text)
               and score_ask(r.ask, r.observed_tools, r.observed_args))
    return hits / len(results)


async def _run_one(client: ClaudeSDKClient, ask: Ask, use_fallback: bool) -> AskResult:
    t0 = time.monotonic()
    await client.query(ask.prompt)
    obs = collect_turn([m async for m in client.receive_response()])
    if use_fallback and not obs.is_error and fallback.is_no_route(obs.text):
        facts = capability.recall_capabilities(ask.prompt)
        retry = fallback.build_retry_prompt(ask.prompt, facts)
        if retry is not None:
            await client.query(retry)
            obs = collect_turn([m async for m in client.receive_response()])
    return AskResult(ask=ask, observed_tools=obs.tools, observed_args=obs.tool_inputs,
                     dt_total=time.monotonic() - t0, is_error=obs.is_error, text=obs.text)


async def run_offpath(model: str, use_fallback: bool) -> list[AskResult]:
    options = crew_options()
    options.model = model
    client = ClaudeSDKClient(options=options)
    await client.connect()
    try:
        await client.query("Hello.")
        async for _ in client.receive_response():
            pass
        return [await _run_one(client, ask, use_fallback) for ask in load_offpath_asks()]
    finally:
        await client.disconnect()
