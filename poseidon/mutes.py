"""poseidon/mutes.py — category alert-mute logic (no I/O).

Category-level acknowledgment: a retained MQTT envelope per muted category
silences NARRATION only (the alert still reaches MQTT/SignalK/logbook). Two
safety rails live here: mutes never apply to alarm/emergency (ceiling), and any
ambiguity fails toward speaking. See docs/superpowers/specs/
2026-06-22-alert-category-mute-design.md.
"""
from __future__ import annotations

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
