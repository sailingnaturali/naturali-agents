"""poseidon/mutes_mcp.py — standalone stdio MCP server for alert mutes.

Replaces the in-process SDK tool (create_sdk_mcp_server) so the mutes tool is
runtime-independent like the rest of the fleet. Server name "mutes" + tool
name "set_alert_mute" preserve the SDK tool id mcp__mutes__set_alert_mute
that the Navigator profile allows.

Run: python -m poseidon.mutes_mcp  (see mcp_servers.json — spawned by the
agent runtime with the daemon's environment; also loads POSEIDON_ENV itself
so it works when spawned by other MCP clients).
"""
from __future__ import annotations

import importlib
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from poseidon import config
from poseidon.mutes import apply_mute_request

mcp = FastMCP("mutes")


def set_alert_mute(category: str, action: str) -> str:
    """Mute or unmute a category of alerts (e.g. whale-zone restricted areas).
    Use action 'mute' to silence narration until the next day, 'unmute' to
    restore it. Categories: whale-zones."""
    from poseidon import mute_publish

    def _publish(cat: str, env: dict | None) -> None:
        (mute_publish.publish_mute_set(cat, env) if env is not None
         else mute_publish.publish_mute_clear(cat))

    return apply_mute_request(category, action, _publish,
                              datetime.now().astimezone(), config.ROLLOVER_HOUR)


mcp.tool()(set_alert_mute)


def main() -> None:
    # Same env dance as daemon.run(): constants freeze at import, so load the
    # env file then re-read config. reload() mutates the existing module object,
    # so the `config` reference above sees the new values.
    config.load_env_file(config.ENV_FILE)
    importlib.reload(config)
    mcp.run()   # stdio transport


if __name__ == "__main__":
    main()
