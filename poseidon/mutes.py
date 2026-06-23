"""poseidon/mutes.py — category alert-mute logic (no I/O).

Category-level acknowledgment: a retained MQTT envelope per muted category
silences NARRATION only (the alert still reaches MQTT/SignalK/logbook). Two
safety rails live here: mutes never apply to alarm/emergency (ceiling), and any
ambiguity fails toward speaking. See docs/superpowers/specs/
2026-06-22-alert-category-mute-design.md.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# Friendly category slug -> notification path-prefixes it covers. A path is in
# the category if it equals a prefix or starts with "<prefix>.".
ALERT_CATEGORIES: dict[str, list[str]] = {
    "whale-zones": ["navigation.restrictedArea"],
}


def category_for_path(path: str) -> str | None:
    for category, prefixes in ALERT_CATEGORIES.items():
        for prefix in prefixes:
            if path == prefix or path.startswith(prefix + "."):
                return category
    return None


def next_rollover_expires(now: datetime, rollover_hour: int) -> str:
    """ISO-8601 of the next local rollover_hour:00 strictly after now."""
    local = now.astimezone()
    candidate = local.replace(hour=rollover_hour, minute=0, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.isoformat()


def build_mute_envelope(category: str, muted_by: str, now: datetime,
                        rollover_hour: int) -> dict:
    return {
        "category": category,
        "paths": list(ALERT_CATEGORIES.get(category, [])),
        "muted_by": muted_by,
        "created": now.astimezone().isoformat(),
        "expires": next_rollover_expires(now, rollover_hour),
    }


def parse_mute_envelope(raw: bytes | dict) -> dict | None:
    """Normalize a retained mute payload; None for empty/malformed (fail-open)."""
    try:
        obj = raw if isinstance(raw, dict) else json.loads(raw.decode())
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return None
    if not isinstance(obj, dict):
        return None
    if not obj.get("category") or not obj.get("expires"):
        return None
    return obj
