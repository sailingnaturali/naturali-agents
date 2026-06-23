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
    def __init__(self, query_fn=query, is_muted=None) -> None:
        self._query = query_fn
        self._is_muted = is_muted or (lambda path, state: False)
        self._seen: dict[str, str] = {}   # path -> timestamp (retained-alert dedup)

    async def handle(self, env: dict, retain: bool = False) -> str | None:
        """Narrate one alarm envelope; returns the spoken text or None.

        ``retain`` marks an MQTT retained delivery — the backlog the broker
        replays whenever we (re)connect, e.g. after a reboot. We reconcile its
        state into ``_seen`` silently and never speak it: an in-memory dedup
        can't survive a restart, so without this every retained alert would be
        re-narrated as if it just happened.
        """
        state = env.get("state")
        path = env.get("path", "")
        ts = env.get("timestamp")
        if state not in _ACTIVE:           # cleared or below warn
            self._seen.pop(path, None)
            return None
        if self._seen.get(path) == ts:     # already seen (live redelivery)
            return None
        self._seen[path] = ts
        if retain:                         # retained replay: seed dedup, stay silent
            return None
        try:
            muted = self._is_muted(path, state)
        except Exception:                  # fail toward speaking (safety rail A)
            log.exception("mute check failed; narrating alarm")
            muted = False
        if muted:                          # category muted: silence voice only
            log.info("alarm suppressed by mute: %s (%s)", path, state)
            return None

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
