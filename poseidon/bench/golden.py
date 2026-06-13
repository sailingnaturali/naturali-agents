"""poseidon.bench.golden — the fixed golden ask corpus + loader.

Targets the Navigator-root-direct safety/nav core (signalk/weather/currents/
pilotbook). Subagent (Engineer/Logbook) tool calls DO surface in the top-level
receive_response() stream and are captured by the collector, so delegated asks
are annotated with the underlying tool that reliably appears (e.g. explain-alarm
→ get_active_alarms), not the "Agent" delegation wrapper. Scoring is recall/
subset, so any extra helper tools the model adds do not fail an ask.
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
