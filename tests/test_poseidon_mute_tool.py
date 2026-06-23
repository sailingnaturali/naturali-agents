# tests/test_poseidon_mute_tool.py
from datetime import datetime, timezone

from poseidon import mute_tool

NOW = datetime(2026, 6, 22, 20, 40, tzinfo=timezone.utc)


def test_mute_publishes_retained_envelope_and_confirms():
    sent = []
    msg = mute_tool.apply_mute_request(
        "whale-zones", "mute", lambda topic_cat, env: sent.append((topic_cat, env)),
        NOW, rollover_hour=6)
    assert sent and sent[0][0] == "whale-zones"
    assert sent[0][1]["category"] == "whale-zones"        # envelope, not None
    assert "whale" in msg.lower() and "mute" in msg.lower()
    assert ":" not in msg                                  # no raw timestamps spoken


def test_unmute_publishes_clear():
    sent = []
    msg = mute_tool.apply_mute_request(
        "whale-zones", "unmute", lambda cat, env: sent.append((cat, env)),
        NOW, rollover_hour=6)
    assert sent == [("whale-zones", None)]
    assert "whale" in msg.lower()


def test_unknown_category_rejects_without_publishing():
    sent = []
    msg = mute_tool.apply_mute_request(
        "kraken", "mute", lambda cat, env: sent.append((cat, env)),
        NOW, rollover_hour=6)
    assert sent == []
    assert "don't" in msg.lower() or "no" in msg.lower() or "unknown" in msg.lower()
