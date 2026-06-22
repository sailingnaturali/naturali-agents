"""poseidon/interim.py — deterministic interim-say policy (spec §4).

Phrases are ready-to-speak (SOUL rule: tools/templates return speakable
strings); max two interim says per turn, total, across both kinds.
"""
from __future__ import annotations

STILL_WORKING_AFTER_S = 20.0
STILL_WORKING_PHRASE = "Still working on it."
RECONSIDER_PHRASE = "Let me reconsider that."
NO_HELP_PHRASE = "I can't help with that one yet."
_GENERIC = object()

# Keyed by MCP server prefix ("mcp__<server>") or exact tool name.
_TOPICS: dict[str, str] = {
    "mcp__pilotbook": "the pilot book",
    "mcp__weather": "the forecast",
    "mcp__currents": "the currents",
    "mcp__signalk": "the instruments",
    "mcp__colregs": "the rules of the road",
    "mcp__vessel-knowledge": "the equipment notes",
    "mcp__logbook": "the logbook",
    "mcp__club-moorage": "the outstations",
    "Agent": "with the crew",
}


def _topic(tool_name: str) -> str | object:
    if tool_name.startswith("mcp__"):
        prefix = "__".join(tool_name.split("__")[:2])
        return _TOPICS.get(prefix, _GENERIC)
    return _TOPICS.get(tool_name, _GENERIC)


def phrase_for_tools(tool_names: list[str]) -> str:
    if not tool_names:
        return "Let me look into that."
    topics: list = []
    for name in tool_names:
        t = _topic(name)
        if t not in topics:
            topics.append(t)
    named = [t for t in topics if t is not _GENERIC]
    if not named:
        return "Let me look into that."
    return f"Let me check {' and '.join(named)}."


class InterimPolicy:
    """Per-turn budget: one tool acknowledgment + one still-working, max two."""

    def __init__(self, max_says: int = 2) -> None:
        self._max = max_says
        self._said = 0
        self._acked = False
        self._stilled = False

    def note_tool_use(self, tool_names: list[str]) -> str | None:
        if self._acked or self._said >= self._max:
            return None
        self._acked = True
        self._said += 1
        return phrase_for_tools(tool_names)

    def still_working(self) -> str | None:
        if self._stilled or self._said >= self._max:
            return None
        self._stilled = True
        self._said += 1
        return STILL_WORKING_PHRASE
