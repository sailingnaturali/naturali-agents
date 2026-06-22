"""poseidon/fallback.py — pure helpers for fallback-on-stray (capability-memory spec §1).

No I/O, no SDK, no Mnemosyne — just the stray test and retry-prompt construction, so the
decision logic is unit-testable in isolation from engine.py.
"""
from __future__ import annotations

_NO_ROUTE = "NO_ROUTE"


def is_no_route(answer: str) -> bool:
    """True only when the agent self-declared a stray (exact marker, surrounding space ok)."""
    return answer.strip() == _NO_ROUTE


def build_retry_prompt(original_query: str, facts: list[str]) -> str | None:
    """Prepend recalled capability facts to the original query for one retry.
    Returns None when there are no facts (nothing to add → no retry)."""
    if not facts:
        return None
    bullets = "\n".join(f"- {f}" for f in facts)
    return (
        "These crew capabilities may help you choose a tool or subagent:\n"
        f"{bullets}\n\n"
        f"Using them, answer the original request: {original_query}"
    )
