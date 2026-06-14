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
