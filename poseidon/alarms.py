"""poseidon/alarms.py — one-shot alarm narration lane (spec §5).

No tools, no conversation history, never queued behind a crew-channel turn.
Dedup and severity-routing ported from the bridge (handle_alert).
"""
from __future__ import annotations

import logging

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

from poseidon import config, prompts

log = logging.getLogger(__name__)

_ACTIVE = {"warn", "alarm", "emergency"}


def _alarm_options(state: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=prompts.ALARM_SYSTEM_PROMPT,
        model=prompts.model_for_state(state) or config.MODEL,
        mcp_servers={},
        strict_mcp_config=True,
        allowed_tools=[],
        setting_sources=[],
        permission_mode="bypassPermissions",
        max_turns=1,
    )


class AlarmLane:
    def __init__(self, query_fn=query) -> None:
        self._query = query_fn
        self._seen: dict[str, str] = {}   # path -> timestamp (retained-alert dedup)

    async def handle(self, env: dict) -> str | None:
        """Narrate one alarm envelope; returns the spoken text or None."""
        state = env.get("state")
        path = env.get("path", "")
        ts = env.get("timestamp")
        if state not in _ACTIVE:           # cleared or below warn
            self._seen.pop(path, None)
            return None
        if self._seen.get(path) == ts:     # retained redelivery
            return None
        self._seen[path] = ts

        parts: list[str] = []
        try:
            async for message in self._query(prompt=prompts.alarm_user_prompt(env),
                                             options=_alarm_options(state)):
                if isinstance(message, AssistantMessage):
                    parts.extend(b.text for b in message.content
                                 if isinstance(b, TextBlock))
        except Exception:
            log.exception("alarm narration failed; speaking raw message")
            return str(env.get("message") or "Alarm received.")
        return " ".join(parts).strip() or str(env.get("message") or "")
