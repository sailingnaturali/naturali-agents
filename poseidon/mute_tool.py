"""poseidon/mute_tool.py — the in-process voice tool for setting alert mutes.

apply_mute_request holds the logic (testable with an injected publish fn); the
@tool wrapper binds the real MQTT publish + clock. Tool id: mcp__mutes__set_alert_mute.
"""
from __future__ import annotations

from datetime import datetime

from claude_agent_sdk import create_sdk_mcp_server, tool

from poseidon import config
from poseidon.mutes import apply_mute_request


@tool("set_alert_mute",
      "Mute or unmute a category of alerts (e.g. whale-zone restricted areas). "
      "Use action 'mute' to silence narration until the next day, 'unmute' to "
      "restore it. Categories: whale-zones.",
      {"category": str, "action": str})
async def set_alert_mute(args):
    from poseidon.daemon import publish_mute_clear, publish_mute_set

    def _publish(category: str, env: dict | None) -> None:
        publish_mute_set(category, env) if env is not None else publish_mute_clear(category)

    msg = apply_mute_request(args["category"], args["action"], _publish,
                             datetime.now().astimezone(), config.ROLLOVER_HOUR)
    return {"content": [{"type": "text", "text": msg}]}


mutes_server = create_sdk_mcp_server(name="mutes", version="1.0.0",
                                     tools=[set_alert_mute])
