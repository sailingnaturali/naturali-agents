"""Alarm lane: one-shot no-tools narration with dedup and fail-open."""
import asyncio

from claude_agent_sdk import AssistantMessage, TextBlock

from poseidon.alarms import AlarmLane

ENV = {"state": "alarm", "path": "electrical.batteries.0.voltage",
       "message": "Battery voltage critically low", "timestamp": "T1"}


def fake_query_returning(text):
    calls = []

    async def fake_query(*, prompt, options):
        calls.append((prompt, options))
        yield AssistantMessage(content=[TextBlock(text=text)], model="test")

    return fake_query, calls


def test_active_alarm_narrated_once_per_timestamp():
    fq, calls = fake_query_returning("Battery alarm. Check the charger.")
    lane = AlarmLane(query_fn=fq)
    out1 = asyncio.run(lane.handle(dict(ENV)))
    out2 = asyncio.run(lane.handle(dict(ENV)))          # same (path, ts): dedup
    out3 = asyncio.run(lane.handle({**ENV, "timestamp": "T2"}))
    assert out1 == "Battery alarm. Check the charger."
    assert out2 is None and out3 is not None
    assert len(calls) == 2


def test_retained_replay_seeds_dedup_without_narrating():
    # On (re)connect the broker replays retained alert envelopes. These must be
    # reconciled silently — never spoken — but still seed the dedup state so the
    # matching live publish stays quiet and only a genuinely new event narrates.
    fq, calls = fake_query_returning("Battery alarm. Check the charger.")
    lane = AlarmLane(query_fn=fq)
    out_retained = asyncio.run(lane.handle(dict(ENV), retain=True))
    assert out_retained is None
    assert len(calls) == 0                               # nothing spoken on replay
    # live publish of the same event (same path+ts) stays deduped
    assert asyncio.run(lane.handle(dict(ENV))) is None
    # a genuinely new event (new ts) still narrates
    assert asyncio.run(lane.handle({**ENV, "timestamp": "T2"})) is not None
    assert len(calls) == 1


def test_retained_cleared_replay_drops_dedup_silently():
    # A retained 'cleared' envelope on reconnect must not resurrect a stale alarm
    # and must leave dedup empty so the next live active event narrates.
    fq, calls = fake_query_returning("x")
    lane = AlarmLane(query_fn=fq)
    asyncio.run(lane.handle(dict(ENV)))                  # active, narrated
    assert asyncio.run(lane.handle({**ENV, "state": "normal"}, retain=True)) is None
    assert asyncio.run(lane.handle(dict(ENV))) is not None
    assert len(calls) == 2


def test_cleared_alarm_ignored_and_clears_dedup():
    fq, calls = fake_query_returning("x")
    lane = AlarmLane(query_fn=fq)
    asyncio.run(lane.handle(dict(ENV)))
    assert asyncio.run(lane.handle({**ENV, "state": "normal"})) is None
    # after clearing, the same timestamp may fire again
    assert asyncio.run(lane.handle(dict(ENV))) is not None
    assert len(calls) == 2


def test_options_are_minimal_no_tools():
    fq, calls = fake_query_returning("x")
    lane = AlarmLane(query_fn=fq)
    asyncio.run(lane.handle(dict(ENV)))
    _, options = calls[0]
    assert options.allowed_tools == []
    assert options.mcp_servers in ({}, None)


def test_muted_path_is_not_narrated():
    fq, calls = fake_query_returning("Whale zone warning.")
    lane = AlarmLane(query_fn=fq, is_muted=lambda path, state: True)
    out = asyncio.run(lane.handle({**ENV, "state": "warn"}))
    assert out is None
    assert len(calls) == 0


def test_unmuted_path_still_narrates_with_predicate_present():
    fq, calls = fake_query_returning("Battery alarm.")
    lane = AlarmLane(query_fn=fq, is_muted=lambda path, state: False)
    out = asyncio.run(lane.handle(dict(ENV)))
    assert out == "Battery alarm."
    assert len(calls) == 1
