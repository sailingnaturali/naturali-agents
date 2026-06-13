"""poseidon.bench.golden — the fixed golden ask corpus + loader.

v1 targets the Navigator-root-direct safety/nav core (signalk/weather/currents/
pilotbook), where the expected tool surfaces at the top level. Delegated asks
(Engineer/Logbook subagents) expect the top-level "Agent" delegation tool;
capturing subagent-internal tool calls is a v2 follow-up requiring live SDK
verification that receive_response() surfaces subagent tool_use blocks.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_GOLDEN_JSON = Path(__file__).with_name("golden_asks.json")


@dataclass(frozen=True)
class Ask:
    id: str
    category: str
    prompt: str
    expected_tools: tuple[str, ...]
    multi_tool: bool
    expected_args: dict = field(default_factory=dict)


def load_golden_asks(path: Path | None = None) -> list[Ask]:
    raw = json.loads((path or _GOLDEN_JSON).read_text(encoding="utf-8"))
    return [
        Ask(
            id=row["id"],
            category=row["category"],
            prompt=row["prompt"],
            expected_tools=tuple(row["expected_tools"]),
            multi_tool=bool(row.get("multi_tool", False)),
            expected_args=row.get("expected_args", {}),
        )
        for row in raw
    ]
