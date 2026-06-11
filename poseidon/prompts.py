"""poseidon/prompts.py — system/user prompt assembly from repo sources.

SOUL.md is the single persona source (do not duplicate persona text here);
skills/<agent>/body.md are the duty layers (the generated prompts/*.md mirrors
stay hermes-only). Stable-prefix ordering matters for prompt caching: SOUL
first, duties second, nothing volatile (no timestamps) anywhere in here.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_SEVERITY = {"nominal": 0, "normal": 1, "alert": 2, "warn": 3,
             "alarm": 4, "emergency": 5}


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8").strip()


def crew_system_prompt() -> str:
    return _read("SOUL.md") + "\n\n# Navigator duties\n\n" + \
        _read("skills/navigator/body.md")


def engineer_prompt() -> str:
    return _read("skills/engineer/body.md")


LOGBOOK_PROMPT = """You are the ship's Logbook keeper. You record sea-day
events, mark notable moments, and answer questions about past entries using
the logbook tools. Keep spoken answers to one or two sentences; dates and
times in the vessel's local time."""


ALARM_SYSTEM_PROMPT = """You are the ship's Engineer announcing an alarm to
the Captain over the cabin speaker. Speak plainly and calmly. Two short
sentences maximum: the announcement, plus one action only if obvious and
urgent. Never speak coordinates, paths, MMSI numbers, or timestamps."""


def alarm_user_prompt(env: dict) -> str:
    """Seed for one alarm narration (ported from the bridge's alert_query;
    the no-tools alarm lane drops the explain_notification escape hatch)."""
    return (
        f"ALARM DISPATCH ({env.get('state')}, path {env.get('path')}): "
        f'announce this to the Captain now: "{env.get("message")}". '
        "Speak at most two short sentences: the announcement, plus one action "
        "only if obvious and urgent. Do not report other systems or readings, "
        "and never speak coordinates, paths, MMSI numbers, or timestamps."
    )


def model_for_state(state: str) -> str | None:
    """Severity-routed model override (port of the bridge's model_for_state)."""
    alarm_model = os.environ.get("ALARM_MODEL", "")
    warn_model = os.environ.get("WARN_MODEL", "")
    if _SEVERITY.get(state, 0) >= _SEVERITY["alarm"]:
        return alarm_model or None
    return warn_model or None
