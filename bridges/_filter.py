"""Shared Hermes stdout filter for the MQTT bridges.

Hermes in `-Q` mode still leaks operational noise onto stdout: session_id
lines, ⚠ warnings, 🔧 tool-call display, and indented config suggestions.
Piper TTS reads the wrench emoji as "wrench auto repair" — so this filter
runs on both producer paths (`hermes_to_mqtt.py` and `mqtt_to_hermes.py`).
"""

from __future__ import annotations


_NOISE_PREFIXES = ("🔧", "⚠", "session_id:", "session:")
_CONFIG_LABEL_PREFIXES = ("auxiliary:", "compression:", "model:", "threshold:")
_CONFIG_KEYWORDS = ("model", "threshold", "compression")
_CONFIG_SUGGESTION_SUBSTRINGS = ("To make this permanent", "edit config.yaml")


def is_response_line(line: str) -> bool:
    """Return True only for lines that are actual agent response text."""
    s = line.strip()
    if not s:
        return False
    if s.startswith(_NOISE_PREFIXES):
        return False
    if s.startswith(("1.", "2.")) and any(k in s for k in _CONFIG_KEYWORDS):
        return False
    if s.startswith(_CONFIG_LABEL_PREFIXES):
        return False
    if any(sub in s for sub in _CONFIG_SUGGESTION_SUBSTRINGS):
        return False
    return True
