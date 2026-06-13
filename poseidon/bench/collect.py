"""poseidon.bench.collect — reduce a turn's SDK messages to scorable facts.

Duck-typed on purpose (hasattr, not isinstance) so unit tests use trivial fakes
and the reducer does not couple to claude_agent_sdk internals. A block is a tool
use if it has both .name and .input; a text block if it has .text.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TurnObservation:
    tools: list[str] = field(default_factory=list)
    tool_inputs: list[dict] = field(default_factory=list)
    text: str = ""
    is_error: bool = False
    usage: dict | None = None


def _is_tool_use(block) -> bool:
    return hasattr(block, "name") and hasattr(block, "input")


def collect_turn(messages) -> TurnObservation:
    obs = TurnObservation()
    texts: list[str] = []
    for message in messages:
        content = getattr(message, "content", None)
        if content is not None:
            for block in content:
                if _is_tool_use(block):
                    obs.tools.append(block.name)
                    obs.tool_inputs.append(dict(getattr(block, "input", {}) or {}))
                elif hasattr(block, "text"):
                    texts.append(block.text)
        elif hasattr(message, "is_error"):
            obs.is_error = bool(message.is_error)
            obs.usage = getattr(message, "usage", None)
    obs.text = " ".join(texts).strip()
    return obs
