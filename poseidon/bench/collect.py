"""poseidon.bench.collect — reduce a turn's SDK messages to scorable facts.

Duck-typed on purpose (hasattr, not isinstance) so unit tests use trivial fakes
and the reducer does not couple to claude_agent_sdk internals. A content block is
a tool use if it has both .name and .input; a text block if it has .text.
Subagent tool calls are captured from messages carrying a truthy .last_tool_name
(the SDK's TaskProgressMessage), which is more reliable than the subagent's
ToolUseBlocks surfacing as top-level AssistantMessages. Tools are deduped by name
(insertion-ordered; a real ToolUseBlock input wins over the input-less
TaskProgress entry), so a tool seen via both channels counts once.
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
    tools_by_name: dict[str, dict] = {}  # insertion-ordered; dedups by tool name
    texts: list[str] = []
    for message in messages:
        content = getattr(message, "content", None)
        if content is not None:
            for block in content:
                if _is_tool_use(block):
                    # Real input wins; updating an existing key keeps its position.
                    tools_by_name[block.name] = dict(getattr(block, "input", {}) or {})
                elif hasattr(block, "text"):
                    texts.append(block.text)
        elif getattr(message, "last_tool_name", None):
            # Subagent tool call (TaskProgressMessage); no input on this channel.
            tools_by_name.setdefault(message.last_tool_name, {})
        elif hasattr(message, "is_error"):
            obs.is_error = bool(message.is_error)
            obs.usage = getattr(message, "usage", None)
    obs.tools = list(tools_by_name)
    obs.tool_inputs = list(tools_by_name.values())
    obs.text = " ".join(texts).strip()
    return obs
