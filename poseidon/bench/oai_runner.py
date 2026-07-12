"""poseidon.bench.oai_runner — native OpenAI/Ollama flat-agent benchmark runner.

Calls an OpenAI-compatible /chat/completions endpoint over httpx, executing MCP
tools itself via McpToolset (flat: all tools, no subagents). Produces AskResults
the existing scoring/report consume. The pure helpers (parse_choice,
flat_scored_ask) are unit-tested; the async loop is exercised by the live run.
"""
from __future__ import annotations

import contextlib
import json
import time
from dataclasses import replace

import os

import httpx

from poseidon import prompts
from poseidon.bench.golden import Ask, load_golden_asks
from poseidon.bench.oai_tools import create_toolset
from poseidon.bench.scoring import AskResult


def parse_choice(response_json: dict) -> tuple[list[dict], str, str]:
    choice = response_json["choices"][0]
    message = choice.get("message", {})
    tool_calls = message.get("tool_calls") or []
    text = message.get("content") or ""
    return tool_calls, text, choice.get("finish_reason", "")


def flat_scored_ask(ask: Ask) -> Ask:
    """Score a flat-backend run against expected_tools_flat when set (no Agent
    wrapper exists off-SDK), leaving scoring.py untouched."""
    if ask.expected_tools_flat:
        return replace(ask, expected_tools=ask.expected_tools_flat)
    return ask


async def run_ask_openai(http: httpx.AsyncClient, base_url: str, model: str,
                         system_prompt: str, schemas: list[dict], toolset,
                         ask: Ask, max_rounds: int = 10) -> AskResult:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": ask.prompt},
    ]
    observed: dict[str, dict] = {}  # insertion-ordered; first-seen args per tool
    text = ""
    is_error = False
    t0 = time.monotonic()
    try:
        for _ in range(max_rounds):
            resp = await http.post(
                base_url.rstrip("/") + "/chat/completions",
                json={"model": model, "messages": messages, "tools": schemas,
                      "tool_choice": "auto", "stream": False},
            )
            resp.raise_for_status()
            tool_calls, text, _finish = parse_choice(resp.json())
            if not tool_calls:
                break
            messages.append({"role": "assistant", "content": text or None,
                             "tool_calls": tool_calls})
            for tc in tool_calls:
                fn = tc.get("function", {}).get("name", "")
                try:
                    args = json.loads(tc.get("function", {}).get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                observed.setdefault(fn, args)
                result = await toolset.call(fn, args)
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                                 "content": result})
    except Exception as e:
        is_error = True
        text = text or f"ERROR: {e}"
    dt = time.monotonic() - t0
    return AskResult(ask=flat_scored_ask(ask), observed_tools=list(observed),
                     observed_args=list(observed.values()), dt_total=dt,
                     is_error=is_error, text=text)


def auth_headers() -> dict[str, str]:
    """Bearer auth for hosted OpenAI-compatible endpoints; empty for local
    (Ollama ignores auth). Reads OPENAI_API_KEY from the environment, which
    __main__ populates via config.load_env_file."""
    key = os.environ.get("OPENAI_API_KEY", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


async def run_benchmark_openai(model: str, base_url: str, repeat: int = 1,
                               asks: list[Ask] | None = None) -> list[AskResult]:
    asks = asks or load_golden_asks()
    system_prompt = prompts.crew_system_prompt()
    toolset = await create_toolset()
    try:
        schemas = toolset.openai_schemas()
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0),
                                     headers=auth_headers()) as http:
            # Throwaway warm-up: load the model off the clock.
            with contextlib.suppress(Exception):
                await http.post(
                    base_url.rstrip("/") + "/chat/completions",
                    json={"model": model,
                          "messages": [{"role": "user", "content": "Hello."}],
                          "stream": False},
                )
            results: list[AskResult] = []
            for _ in range(repeat):
                for ask in asks:
                    results.append(await run_ask_openai(
                        http, base_url, model, system_prompt, schemas, toolset, ask))
            return results
    finally:
        await toolset.aclose()
