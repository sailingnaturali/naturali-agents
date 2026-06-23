import json
from datetime import datetime, timezone

from poseidon import mutes


def test_restricted_area_path_resolves_to_whale_zones():
    assert mutes.category_for_path(
        "navigation.restrictedArea.e7e2f870-f6b9-5851-819d-8de04be1f97a"
    ) == "whale-zones"


def test_unrelated_path_resolves_to_no_category():
    assert mutes.category_for_path("electrical.batteries.0.voltage") is None


def test_next_rollover_is_strictly_after_now():
    now = datetime(2026, 6, 22, 20, 40, tzinfo=timezone.utc)
    exp = mutes.next_rollover_expires(now, rollover_hour=6)
    parsed = datetime.fromisoformat(exp)
    assert parsed > now
    assert parsed.astimezone().hour == 6


def test_build_envelope_has_category_paths_and_future_expiry():
    now = datetime(2026, 6, 22, 20, 40, tzinfo=timezone.utc)
    env = mutes.build_mute_envelope("whale-zones", "voice", now, rollover_hour=6)
    assert env["category"] == "whale-zones"
    assert env["paths"] == ["navigation.restrictedArea"]
    assert env["muted_by"] == "voice"
    assert datetime.fromisoformat(env["expires"]) > now


def test_parse_envelope_round_trips_and_rejects_garbage():
    now = datetime(2026, 6, 22, 20, 40, tzinfo=timezone.utc)
    env = mutes.build_mute_envelope("whale-zones", "voice", now, rollover_hour=6)
    assert mutes.parse_mute_envelope(json.dumps(env).encode()) == env
    assert mutes.parse_mute_envelope(b"") is None
    assert mutes.parse_mute_envelope(b"not json") is None
    assert mutes.parse_mute_envelope({"category": "x"}) is None  # no expires
