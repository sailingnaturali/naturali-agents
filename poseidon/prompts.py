"""poseidon/prompts.py — system/user prompt assembly from repo sources.

SOUL.md is the single persona source (do not duplicate persona text here);
skills/<agent>/body.md are the duty layers (the generated prompts/*.md mirrors
stay hermes-only). Stable-prefix ordering matters for prompt caching: SOUL
first, duties second, nothing volatile (no timestamps) anywhere in here.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]

_SEVERITY = {"nominal": 0, "normal": 1, "alert": 2, "warn": 3,
             "alarm": 4, "emergency": 5}


def _resolve_vessel_name() -> str:
    """Port of scripts/vessel-name.sh: $VESSEL_NAME override, else the active
    vessel profile's name: (infrastructure/vessels/profiles, override with
    $VESSEL_PROFILES_DIR), else "Naturali"."""
    explicit = os.environ.get("VESSEL_NAME")
    if explicit:
        return explicit
    profiles_dir = Path(os.environ.get(
        "VESSEL_PROFILES_DIR",
        str(REPO_ROOT.parent / "infrastructure" / "vessels" / "profiles")))
    try:
        active_text = (profiles_dir / "active.yaml").read_text(encoding="utf-8")
        m = re.search(r"^active:\s*(\S+)", active_text, re.M)
        active = m.group(1).strip("\"'") if m else ""
        if active:
            profile_text = (profiles_dir / f"{active}.yaml").read_text(
                encoding="utf-8")
            m = re.search(r"^name:\s*(.+)$", profile_text, re.M)
            if m:
                name = m.group(1).strip().strip("\"'")
                if name:
                    return name
    except OSError:
        pass
    log.warning("vessel profile unavailable; using fallback vessel name "
                "'Naturali'")
    return "Naturali"


VESSEL_NAME = _resolve_vessel_name()

# hermes-era server tokens -> SDK MCP server names. Tokens can contain
# underscores, so match an explicit alternation (longest first), never a
# generic pattern. "tide" became the currents MCP.
_HERMES_SERVERS = {
    "vessel_knowledge": "vessel-knowledge",
    "pilotbook": "pilotbook",
    "signalk": "signalk",
    "colregs": "colregs",
    "logbook": "logbook",
    "weather": "weather",
    "tide": "currents",
}
_TOOL_PREFIX_RE = re.compile(
    r"\bmcp_(" + "|".join(sorted(_HERMES_SERVERS, key=len, reverse=True)) + r")_")


def _modernize_tool_names(text: str) -> str:
    """Rewrite hermes-era tool names (mcp_<server>_<tool>) to the SDK's
    mcp__<server>__<tool> form at assembly time. body.md files are shared
    with hermes and keep the old names; only the assembled prompt changes.
    Prefix-based so wildcard mentions like `mcp_signalk_*` convert too."""
    return _TOOL_PREFIX_RE.sub(
        lambda m: f"mcp__{_HERMES_SERVERS[m.group(1)]}__", text)


def _read(rel: str) -> str:
    text = (REPO_ROOT / rel).read_text(encoding="utf-8").strip()
    # deploy-soul.sh renders this for hermes; poseidon substitutes at load
    return text.replace("{{VESSEL_NAME}}", VESSEL_NAME)


def crew_system_prompt() -> str:
    return _modernize_tool_names(
        _read("SOUL.md") + "\n\n# Navigator duties\n\n" +
        _read("skills/navigator/body.md"))


def engineer_prompt() -> str:
    return _modernize_tool_names(_read("skills/engineer/body.md"))


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
