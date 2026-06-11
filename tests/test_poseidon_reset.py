"""Crew-conversation reset policy: idle, explicit phrase, daily rollover."""
from datetime import datetime, timedelta, timezone

import pytest

from poseidon.reset import ResetPolicy

TZ = timezone.utc
NOON = datetime(2026, 6, 11, 12, 0, tzinfo=TZ)


def test_no_reset_on_first_turn():
    assert ResetPolicy().should_reset(None, NOON, "wind?") is False


def test_idle_timeout():
    p = ResetPolicy(idle_seconds=1800)
    assert p.should_reset(NOON - timedelta(minutes=29), NOON, "wind?") is False
    assert p.should_reset(NOON - timedelta(minutes=31), NOON, "wind?") is True


def test_explicit_phrase_resets_even_when_fresh():
    p = ResetPolicy()
    assert p.should_reset(NOON - timedelta(minutes=1), NOON,
                          "OK, new topic: anchorages") is True
    assert p.should_reset(None, NOON, "start fresh please") is True


def test_daily_rollover():
    p = ResetPolicy(idle_seconds=999999, rollover_hour=6)
    last_evening = datetime(2026, 6, 10, 22, 0, tzinfo=TZ)
    morning = datetime(2026, 6, 11, 7, 0, tzinfo=TZ)
    assert p.should_reset(last_evening, morning, "wind?") is True
    # same morning, both after rollover: no reset
    later = datetime(2026, 6, 11, 9, 0, tzinfo=TZ)
    assert p.should_reset(morning, later, "wind?") is False
    # pre-dawn ask continues yesterday evening's thread (rollover not crossed)
    predawn = datetime(2026, 6, 11, 5, 0, tzinfo=TZ)
    assert p.should_reset(last_evening, predawn, "wind?") is False


def test_idle_boundary_exactly_30min_keeps_thread():
    p = ResetPolicy(idle_seconds=1800)
    assert p.should_reset(NOON - timedelta(seconds=1800), NOON, "wind?") is False


def test_now_exactly_at_rollover_uses_todays_boundary():
    p = ResetPolicy(idle_seconds=999999, rollover_hour=6)
    at_six = datetime(2026, 6, 11, 6, 0, tzinfo=TZ)
    last_evening = datetime(2026, 6, 10, 22, 0, tzinfo=TZ)
    assert p.should_reset(last_evening, at_six, "wind?") is True


def test_naive_datetime_rejected():
    p = ResetPolicy()
    naive = datetime(2026, 6, 11, 11, 0)
    with pytest.raises(ValueError):
        p.should_reset(naive, NOON, "wind?")
