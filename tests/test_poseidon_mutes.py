import json
from datetime import datetime, timedelta, timezone

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
    assert parsed.tzinfo is not None
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


def _reg_with(category, now, rollover_hour=6):
    reg = mutes.MuteRegistry()
    reg.apply(category, mutes.build_mute_envelope(category, "voice", now, rollover_hour))
    return reg


def test_muted_warn_is_muted_but_emergency_and_alarm_are_not():
    now = datetime(2026, 6, 22, 20, 40, tzinfo=timezone.utc)
    reg = _reg_with("whale-zones", now)
    path = "navigation.restrictedArea.abc"
    assert reg.is_muted(path, "warn", now) is True
    assert reg.is_muted(path, "alert", now) is True
    assert reg.is_muted(path, "alarm", now) is False       # ceiling B
    assert reg.is_muted(path, "emergency", now) is False    # ceiling B


def test_unmuted_or_unknown_path_is_not_muted():
    now = datetime(2026, 6, 22, 20, 40, tzinfo=timezone.utc)
    reg = _reg_with("whale-zones", now)
    assert reg.is_muted("electrical.batteries.0.voltage", "warn", now) is False
    reg.apply("whale-zones", None)  # clear
    assert reg.is_muted("navigation.restrictedArea.abc", "warn", now) is False


def test_expired_mute_does_not_suppress_and_is_reported():
    now = datetime(2026, 6, 22, 20, 40, tzinfo=timezone.utc)
    reg = _reg_with("whale-zones", now)
    later = now + timedelta(days=2)
    assert reg.is_muted("navigation.restrictedArea.abc", "warn", later) is False
    assert reg.expired_categories(later) == ["whale-zones"]
    assert reg.expired_categories(now) == []


def test_malformed_expires_fails_open():
    reg = mutes.MuteRegistry()
    reg.apply("whale-zones", {"category": "whale-zones", "expires": "not-a-date"})
    now = datetime(2026, 6, 22, 20, 40, tzinfo=timezone.utc)
    assert reg.is_muted("navigation.restrictedArea.abc", "warn", now) is False


def test_naive_expires_is_rejected_and_fails_open():
    # A timezone-naive expiry is ambiguous -> no mute (alarm still speaks), no crash.
    reg = mutes.MuteRegistry()
    reg.apply("whale-zones", {"category": "whale-zones", "expires": "2026-06-23T06:00:00"})
    now = datetime(2026, 6, 22, 20, 40, tzinfo=timezone.utc)
    assert reg.is_muted("navigation.restrictedArea.abc", "warn", now) is False


def test_is_muted_default_now_does_not_raise():
    # now=None default path must work and not raise on a freshly-muted category.
    now = datetime.now(timezone.utc)
    reg = mutes.MuteRegistry()
    reg.apply("whale-zones", mutes.build_mute_envelope("whale-zones", "voice", now, 6))
    assert reg.is_muted("navigation.restrictedArea.abc", "warn") is True
