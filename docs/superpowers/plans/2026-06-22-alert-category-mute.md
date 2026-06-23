# Alert Category Mute Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the crew mute a *category* of alerts (e.g. whale-zone restricted areas) so the puck stops narrating perpetual-by-geography warnings, without hiding the alert from MQTT/SignalK/the logbook.

**Architecture:** A retained MQTT mute registry (`naturali/mutes/<category>`) holds active mutes with an embedded `expires`. Poseidon subscribes, keeps an in-memory category→expires map, and `AlarmLane` consults an injected `is_muted(path, state)` predicate to skip *narration only*. Mutes are set via a new in-process SDK tool (voice), an HA switch, or the agent proposing the out in its narration. Expiry is authoritative (a past-`expires` mute never suppresses); stale retained slots are cleaned lazily when observed.

**Tech Stack:** Python 3.12, `paho-mqtt` (`paho.mqtt.publish.single`, `paho.mqtt.client`), `claude-agent-sdk` (`tool`, `create_sdk_mcp_server`), `pytest` via the repo `.venv`.

## Global Constraints

- Run tests with `cd ~/src/sailingnaturali/naturali-agents && .venv/bin/python -m pytest`. Python 3.12.
- TDD: failing test first, watch it fail, minimal code, watch it pass, commit. One logical change per commit.
- **Safety rail A — fail toward speaking:** if mute state is missing, unreachable, or malformed, do NOT suppress; narrate. A muting bug must never silence a real alarm.
- **Safety rail B — severity ceiling:** mutes suppress only states in `{"alert", "warn"}`. `alarm` and `emergency` are NEVER muted, even on a muted category's path.
- Voice-output conventions: spoken confirmations are plain prose, units written in full ("until tomorrow", not abbreviations); never speak coordinates, paths, MMSI numbers, or timestamps.
- MQTT auth pattern (copy from `poseidon/daemon.py:94`): `auth = {"username": config.MQTT_USER, "password": config.MQTT_PASSWORD} if config.MQTT_USER else None`.
- Retained-write contract: a mute is set by publishing the JSON envelope with `retain=True`; un-mute is publishing an empty payload (`payload=None`) with `retain=True` to delete the retained slot.
- Commit trailers on every commit:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01FJJcyhP4XTo1GZbxXW7SuM
  ```

## File Structure

- Create `poseidon/mutes.py` — category registry, path→category resolution, `MuteRegistry` (in-memory map + `is_muted`), envelope parse/build, `next_rollover_expires`. The single home for mute *logic* (no I/O).
- Create `poseidon/mute_tool.py` — `apply_mute_request(...)` (logic, takes an injected publish fn) + the `@tool`-wrapped `set_alert_mute` and `create_sdk_mcp_server` wiring (I/O edge).
- Create `tests/test_poseidon_mutes.py` — unit tests for `mutes.py`.
- Create `tests/test_poseidon_mute_tool.py` — unit tests for `apply_mute_request`.
- Modify `poseidon/config.py` — add `MUTES_TOPIC` / `MUTES_TOPIC_PREFIX`.
- Modify `poseidon/alarms.py` — `AlarmLane` gains an injected `is_muted` predicate.
- Modify `poseidon/daemon.py` — subscribe mutes, route to `MuteRegistry`, build `is_muted`, lazy-clean expired slots.
- Modify `poseidon/profiles.py` — register the in-process `mutes` SDK server + allow its tool.
- Modify `poseidon/prompts.py` — `alarm_user_prompt` adds the agent-proposes line for muteable categories.
- Modify `tests/test_poseidon_alarms.py`, `tests/test_poseidon_daemon.py`, `tests/test_poseidon_prompts.py` — extend existing suites.
- Modify `infrastructure` HA config — `switch.mute_whale_zones` (separate repo; final task).

---

### Task 1: Category registry + path→category resolution

**Files:**
- Create: `poseidon/mutes.py`
- Test: `tests/test_poseidon_mutes.py`

**Interfaces:**
- Produces: `ALERT_CATEGORIES: dict[str, list[str]]`; `category_for_path(path: str) -> str | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_poseidon_mutes.py
from poseidon import mutes


def test_restricted_area_path_resolves_to_whale_zones():
    assert mutes.category_for_path(
        "navigation.restrictedArea.e7e2f870-f6b9-5851-819d-8de04be1f97a"
    ) == "whale-zones"


def test_unrelated_path_resolves_to_no_category():
    assert mutes.category_for_path("electrical.batteries.0.voltage") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_poseidon_mutes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'poseidon.mutes'`.

- [ ] **Step 3: Write minimal implementation**

```python
# poseidon/mutes.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_poseidon_mutes.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add poseidon/mutes.py tests/test_poseidon_mutes.py
git commit -m "feat(mutes): category registry + path resolution"
```

---

### Task 2: Rollover-expiry helper + envelope build/parse

**Files:**
- Modify: `poseidon/mutes.py`
- Test: `tests/test_poseidon_mutes.py`

**Interfaces:**
- Consumes: `ALERT_CATEGORIES` (Task 1).
- Produces:
  - `next_rollover_expires(now: datetime, rollover_hour: int) -> str` — ISO-8601 UTC string of the next local `rollover_hour:00` strictly after `now`.
  - `build_mute_envelope(category: str, muted_by: str, now: datetime, rollover_hour: int) -> dict`.
  - `parse_mute_envelope(raw: bytes | dict) -> dict | None` — normalized envelope or `None` if malformed/empty.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_poseidon_mutes.py
import json
from datetime import datetime, timezone


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_poseidon_mutes.py -q`
Expected: FAIL — `AttributeError: module 'poseidon.mutes' has no attribute 'next_rollover_expires'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to poseidon/mutes.py
import json
import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_poseidon_mutes.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add poseidon/mutes.py tests/test_poseidon_mutes.py
git commit -m "feat(mutes): rollover-expiry helper + envelope build/parse"
```

---

### Task 3: `MuteRegistry` with `is_muted` (ceiling + fail-open + expiry)

**Files:**
- Modify: `poseidon/mutes.py`
- Test: `tests/test_poseidon_mutes.py`

**Interfaces:**
- Consumes: `category_for_path`, `parse_mute_envelope` (Tasks 1-2).
- Produces: `MUTEABLE_STATES: set[str]`; `class MuteRegistry` with:
  - `apply(category: str, envelope: dict | None) -> None` — upsert (`envelope` given) or clear (`None`).
  - `is_muted(path: str, state: str, now: datetime | None = None) -> bool`.
  - `expired_categories(now: datetime | None = None) -> list[str]` — categories whose stored `expires` is past (for lazy cleanup).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_poseidon_mutes.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_poseidon_mutes.py -q`
Expected: FAIL — `AttributeError: module 'poseidon.mutes' has no attribute 'MuteRegistry'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to poseidon/mutes.py
MUTEABLE_STATES = {"alert", "warn"}   # ceiling: alarm/emergency never muted


def _parse_dt(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


class MuteRegistry:
    """In-memory category -> expires(datetime) map. Authoritative on expiry."""

    def __init__(self) -> None:
        self._map: dict[str, datetime] = {}

    def apply(self, category: str, envelope: dict | None) -> None:
        if envelope is None:
            self._map.pop(category, None)
            return
        exp = _parse_dt(envelope.get("expires", ""))
        if exp is None:               # malformed expiry -> fail open (no mute)
            self._map.pop(category, None)
            return
        self._map[category] = exp

    def is_muted(self, path: str, state: str, now: datetime | None = None) -> bool:
        if state not in MUTEABLE_STATES:      # safety rail B
            return False
        category = category_for_path(path)
        if category is None:
            return False
        exp = self._map.get(category)
        if exp is None:
            return False
        now = now or datetime.now().astimezone()
        return now < exp                      # past expires -> not muted

    def expired_categories(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now().astimezone()
        return [c for c, exp in self._map.items() if exp <= now]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_poseidon_mutes.py -q`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add poseidon/mutes.py tests/test_poseidon_mutes.py
git commit -m "feat(mutes): MuteRegistry.is_muted with ceiling + fail-open + expiry"
```

---

### Task 4: `AlarmLane` consults an injected `is_muted` predicate

**Files:**
- Modify: `poseidon/alarms.py:32-47`
- Test: `tests/test_poseidon_alarms.py`

**Interfaces:**
- Consumes: a predicate `is_muted(path: str, state: str) -> bool` (default: never muted).
- Produces: `AlarmLane(query_fn=..., is_muted=...)`; `handle()` returns `None` (no narration) when `is_muted(path, state)` is true for an otherwise-narratable alarm.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_poseidon_alarms.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_poseidon_alarms.py -q`
Expected: FAIL — `TypeError: AlarmLane.__init__() got an unexpected keyword argument 'is_muted'`.

- [ ] **Step 3: Write minimal implementation**

In `poseidon/alarms.py`, change the constructor and add the check. Replace lines 32-47:

```python
class AlarmLane:
    def __init__(self, query_fn=query, is_muted=None) -> None:
        self._query = query_fn
        self._is_muted = is_muted or (lambda path, state: False)
        self._seen: dict[str, str] = {}   # path -> timestamp (retained-alert dedup)

    async def handle(self, env: dict, retain: bool = False) -> str | None:
        """Narrate one alarm envelope; returns the spoken text or None.

        ``retain`` marks an MQTT retained delivery — the backlog the broker
        replays whenever we (re)connect, e.g. after a reboot. We reconcile its
        state into ``_seen`` silently and never speak it: an in-memory dedup
        can't survive a restart, so without this every retained alert would be
        re-narrated as if it just happened.
        """
        state = env.get("state")
        path = env.get("path", "")
        ts = env.get("timestamp")
        if state not in _ACTIVE:           # cleared or below warn
            self._seen.pop(path, None)
            return None
        if self._seen.get(path) == ts:     # already seen (live redelivery)
            return None
        self._seen[path] = ts
        if retain:                         # retained replay: seed dedup, stay silent
            return None
        if self._is_muted(path, state):    # category muted: silence voice only
            log.info("alarm suppressed by mute: %s (%s)", path, state)
            return None
```

(Leave the rest of `handle` — the query loop — unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_poseidon_alarms.py -q`
Expected: PASS (7 passed — 5 existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add poseidon/alarms.py tests/test_poseidon_alarms.py
git commit -m "feat(alarms): suppress narration for muted categories (record untouched)"
```

---

### Task 5: Daemon — subscribe mutes, wire `is_muted`, lazy-clean expired slots

**Files:**
- Modify: `poseidon/config.py:28-29` (add topics)
- Modify: `poseidon/daemon.py` (route mutes, build predicate, lazy clean)
- Test: `tests/test_poseidon_daemon.py`

**Interfaces:**
- Consumes: `MuteRegistry`, `parse_mute_envelope`, `category_for_path` (Tasks 1-3).
- Produces: `Poseidon.handle_mute(topic: str, payload: dict) -> None`; `AlarmLane` in `run()` is constructed with `is_muted=registry.is_muted`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_poseidon_daemon.py
from poseidon import mutes


def test_mute_message_updates_registry_and_alarmlane_suppresses():
    # A live mute envelope on the mutes topic must make the alarm lane go quiet
    # for that category's paths, while the alert envelope is unchanged.
    from datetime import datetime, timezone
    reg = mutes.MuteRegistry()
    lane = FakeAlarmLane("x")
    app, published = make_app(alarms=lane)
    app._mutes = reg  # daemon holds the registry (see implementation)
    now = datetime(2026, 6, 22, 20, 40, tzinfo=timezone.utc)
    env = mutes.build_mute_envelope("whale-zones", "voice", now, rollover_hour=6)
    asyncio.run(app.dispatch("naturali/mutes/whale-zones", env))
    assert reg.is_muted("navigation.restrictedArea.abc", "warn", now) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_poseidon_daemon.py::test_mute_message_updates_registry_and_alarmlane_suppresses -q`
Expected: FAIL — `dispatch` routes `naturali/mutes/...` to "unhandled topic" and `reg.is_muted` stays False (no `app._mutes` handling).

- [ ] **Step 3: Write minimal implementation**

In `poseidon/config.py`, after line 28 (`ALERTS_TOPIC = ...`) add:

```python
MUTES_TOPIC = "naturali/mutes/#"
MUTES_TOPIC_PREFIX = "naturali/mutes"
```

In `poseidon/daemon.py`:

Add import near line 26-29:

```python
from poseidon.mutes import MuteRegistry, parse_mute_envelope
```

Give `Poseidon` a registry. In `Poseidon.__init__` (around line 136-142), add a parameter and store it:

```python
    def __init__(self, *, channel: CrewChannel, alarm_lane: AlarmLane,
                 publish_say: Callable[..., None],
                 run_briefing: Callable[[dict | None], None],
                 mutes: MuteRegistry | None = None) -> None:
        self._channel = channel
        self._alarms = alarm_lane
        self._publish = publish_say
        self._briefing = run_briefing
        self._mutes = mutes or MuteRegistry()
```

Route the topic in `dispatch` (around line 144-153) — add a branch before the `else`:

```python
    async def dispatch(self, topic: str, payload: dict, retain: bool = False) -> None:
        if topic.startswith("naturali/alerts/"):
            await self._handle_alert(payload, retain)
        elif topic.startswith("naturali/mutes/"):
            self.handle_mute(topic, payload)
        elif topic == "naturali/intents/ask":
            await self._handle_ask(payload)
        elif topic == "naturali/intents/briefing":
            await asyncio.to_thread(self._briefing,
                                    timing.timing_ctx("briefing", payload))
        else:
            log.warning("unhandled topic: %s", topic)
```

Add the handler method (place after `_handle_alert`):

```python
    def handle_mute(self, topic: str, payload: dict) -> None:
        category = topic.rsplit("/", 1)[-1]
        envelope = parse_mute_envelope(payload) if payload else None
        self._mutes.apply(category, envelope)
        log.info("mute %s: %s", category, "set" if envelope else "cleared")
```

Wire the registry + predicate in `run()` (around line 228-233): construct the registry first, pass `is_muted` into `AlarmLane`, and hand the registry to `Poseidon`:

```python
    mute_registry = MuteRegistry()
    app = Poseidon(
        channel=channel,
        alarm_lane=AlarmLane(is_muted=mute_registry.is_muted),
        publish_say=publish_say,
        run_briefing=run_briefing,
        mutes=mute_registry,
    )
```

Subscribe to the mutes topic in `on_connect` (after line 247 `client.subscribe(config.ALERTS_TOPIC, qos=1)`):

```python
            client.subscribe(config.MUTES_TOPIC, qos=1)
```

In `on_message` (the `else` branch around line 257-263), mutes already route through `dispatch`; pass `retain` as before — `handle_mute` ignores it. No change needed beyond the existing `app.dispatch(msg.topic, payload, retain=msg.retain)` call, which now also covers `naturali/mutes/...`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_poseidon_daemon.py -q`
Expected: PASS (all daemon tests, including the new one).

- [ ] **Step 5: Commit**

```bash
git add poseidon/config.py poseidon/daemon.py tests/test_poseidon_daemon.py
git commit -m "feat(daemon): subscribe mutes topic, wire is_muted into AlarmLane"
```

---

### Task 6: Lazy cleanup of expired retained mute slots

**Files:**
- Modify: `poseidon/daemon.py` (`handle_mute` + a publish helper)
- Test: `tests/test_poseidon_daemon.py`

**Interfaces:**
- Consumes: `MuteRegistry.expired_categories`, `config.MUTES_TOPIC_PREFIX`.
- Produces: `publish_mute_clear(category: str) -> None` (module function, mirrors `publish_say`'s auth); `handle_mute` clears the retained slot when the applied envelope is already expired.

Rationale: rollover re-arm (spec) is realized by *authoritative expiry* (Task 3) plus this lazy cleanup — when a stale mute (e.g. yesterday's) is observed on reconnect, its retained slot is deleted and it never suppresses. This avoids a standing scheduler (the daemon's rollover is otherwise lazy/per-ask). A continuously-running daemon that crosses rollover without reconnect still suppresses nothing post-expiry (Task 3 is authoritative); the slot is tidied on the next mute message or restart.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_poseidon_daemon.py
def test_expired_mute_envelope_clears_its_retained_slot(monkeypatch):
    from datetime import datetime, timezone, timedelta
    cleared = []
    monkeypatch.setattr(daemon, "publish_mute_clear", lambda c: cleared.append(c))
    reg = mutes.MuteRegistry()
    app, _ = make_app()
    app._mutes = reg
    past = datetime.now(timezone.utc) - timedelta(days=1)
    env = mutes.build_mute_envelope("whale-zones", "voice", past, rollover_hour=6)
    asyncio.run(app.dispatch("naturali/mutes/whale-zones", env))
    assert cleared == ["whale-zones"]
    assert reg.is_muted("navigation.restrictedArea.abc", "warn") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_poseidon_daemon.py::test_expired_mute_envelope_clears_its_retained_slot -q`
Expected: FAIL — `AttributeError: module 'poseidon.daemon' has no attribute 'publish_mute_clear'`.

- [ ] **Step 3: Write minimal implementation**

In `poseidon/daemon.py`, add a publish helper next to `publish_say` (after line 103):

```python
def publish_mute_clear(category: str) -> None:
    """Delete a retained mute slot (empty retained payload)."""
    auth = ({"username": config.MQTT_USER, "password": config.MQTT_PASSWORD}
            if config.MQTT_USER else None)
    mqtt_publish.single(f"{config.MUTES_TOPIC_PREFIX}/{category}", payload=None,
                        retain=True, hostname=config.BROKER, port=config.PORT,
                        auth=auth)
```

Extend `handle_mute` to clean expired slots after applying:

```python
    def handle_mute(self, topic: str, payload: dict) -> None:
        category = topic.rsplit("/", 1)[-1]
        envelope = parse_mute_envelope(payload) if payload else None
        self._mutes.apply(category, envelope)
        for expired in self._mutes.expired_categories():
            publish_mute_clear(expired)
            self._mutes.apply(expired, None)
            log.info("cleared expired mute slot: %s", expired)
        log.info("mute %s: %s", category, "set" if envelope else "cleared")
```

Note: `MuteRegistry.apply` already drops a malformed/expired-on-parse envelope, but an envelope whose `expires` is a valid *past* time is stored by `apply` (Task 3 stores any parseable datetime); `expired_categories()` then catches it here. Verify Task 3 stores past datetimes (it does — `apply` only rejects unparseable expiry), so this cleanup path triggers.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_poseidon_daemon.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add poseidon/daemon.py tests/test_poseidon_daemon.py
git commit -m "feat(daemon): lazy-clear expired retained mute slots"
```

---

### Task 7: Voice tool `set_alert_mute` (logic + SDK wiring)

**Files:**
- Create: `poseidon/mute_tool.py`
- Modify: `poseidon/profiles.py:31-39,63-69`
- Test: `tests/test_poseidon_mute_tool.py`

**Interfaces:**
- Consumes: `ALERT_CATEGORIES`, `build_mute_envelope` (Tasks 1-2).
- Produces:
  - `apply_mute_request(category: str, action: str, publish: Callable[[str, dict | None], None], now: datetime, rollover_hour: int) -> str` — validates, publishes (envelope for "mute", `None` for "unmute"), returns a ready-to-speak confirmation. Unknown category or action → spoken rejection, no publish.
  - `mutes_server` — `create_sdk_mcp_server` exposing `set_alert_mute` (tool id `mcp__mutes__set_alert_mute`).

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_poseidon_mute_tool.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'poseidon.mute_tool'`.

- [ ] **Step 3: Write minimal implementation**

```python
# poseidon/mute_tool.py
"""poseidon/mute_tool.py — the in-process voice tool for setting alert mutes.

apply_mute_request holds the logic (testable with an injected publish fn); the
@tool wrapper binds the real MQTT publish + clock. Tool id: mcp__mutes__set_alert_mute.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from claude_agent_sdk import create_sdk_mcp_server, tool

from poseidon import config
from poseidon.mutes import ALERT_CATEGORIES, build_mute_envelope

# Friendly spoken names for categories (units/words, never raw slugs/paths).
_SPOKEN = {"whale-zones": "whale-zone"}


def _spoken(category: str) -> str:
    return _SPOKEN.get(category, category.replace("-", " "))


def apply_mute_request(category: str, action: str,
                       publish: Callable[[str, dict | None], None],
                       now: datetime, rollover_hour: int) -> str:
    """Validate + publish a mute change; return a ready-to-speak confirmation."""
    if category not in ALERT_CATEGORIES:
        return (f"I don't have an alert category called {category.replace('-', ' ')}. "
                "I can mute whale-zone alerts.")
    if action == "mute":
        env = build_mute_envelope(category, "voice", now, rollover_hour)
        publish(category, env)
        return f"{_spoken(category).capitalize()} alerts muted until tomorrow."
    if action == "unmute":
        publish(category, None)
        return f"{_spoken(category).capitalize()} alerts back on."
    return "Tell me whether to mute or unmute, and which alerts."


@tool("set_alert_mute",
      "Mute or unmute a category of alerts (e.g. whale-zone restricted areas). "
      "Use action 'mute' to silence narration until the next day, 'unmute' to "
      "restore it. Categories: whale-zones.",
      {"category": str, "action": str})
async def set_alert_mute(args):
    from poseidon.daemon import publish_mute_clear, publish_mute_set
    def _publish(category: str, env: dict | None) -> None:
        publish_mute_set(category, env) if env else publish_mute_clear(category)
    msg = apply_mute_request(args["category"], args["action"], _publish,
                             datetime.now().astimezone(), config.ROLLOVER_HOUR)
    return {"content": [{"type": "text", "text": msg}]}


mutes_server = create_sdk_mcp_server(name="mutes", version="1.0.0",
                                     tools=[set_alert_mute])
```

Add the companion retained-set publisher to `poseidon/daemon.py` (next to `publish_mute_clear`):

```python
def publish_mute_set(category: str, envelope: dict) -> None:
    """Publish a retained mute envelope."""
    auth = ({"username": config.MQTT_USER, "password": config.MQTT_PASSWORD}
            if config.MQTT_USER else None)
    mqtt_publish.single(f"{config.MUTES_TOPIC_PREFIX}/{category}",
                        payload=json.dumps(envelope), retain=True,
                        hostname=config.BROKER, port=config.PORT, auth=auth)
```

Register the server + allow the tool in `poseidon/profiles.py`. Add to `NAVIGATOR_TOOLS` (line 31-39 list), before `"Agent"`:

```python
    "mcp__mutes__set_alert_mute",
```

In `crew_options()` (line 63-69), merge the in-process server into `mcp_servers`:

```python
def crew_options() -> ClaudeAgentOptions:
    from poseidon.mute_tool import mutes_server
    servers = load_mcp_servers()
    servers["mutes"] = mutes_server
    return ClaudeAgentOptions(
        system_prompt=prompts.crew_system_prompt(),
        model=config.MODEL,
        mcp_servers=servers,
        strict_mcp_config=True,
        allowed_tools=NAVIGATOR_TOOLS + ENGINEER_TOOLS + LOGBOOK_TOOLS,
        tools=NAVIGATOR_TOOLS,
        disallowed_tools=["mcp__vessel-knowledge", "mcp__logbook"],
        # ... rest unchanged ...
```

(Keep the `agents=`, `setting_sources=`, `permission_mode=`, `include_partial_messages=`, `max_turns=` arguments exactly as they are.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_poseidon_mute_tool.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add poseidon/mute_tool.py poseidon/daemon.py poseidon/profiles.py tests/test_poseidon_mute_tool.py
git commit -m "feat(mutes): set_alert_mute voice tool + retained publishers"
```

---

### Task 8: Agent-proposes line in alarm narration

**Files:**
- Modify: `poseidon/prompts.py:116-125` (`alarm_user_prompt`)
- Test: `tests/test_poseidon_prompts.py`

**Interfaces:**
- Consumes: `category_for_path`, `MUTEABLE_STATES` (Tasks 1, 3).
- Produces: `alarm_user_prompt(env)` appends a one-line mute offer when the alarm's path is in a known category and its state is muteable; otherwise unchanged.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_poseidon_prompts.py
from poseidon import prompts


def test_alarm_prompt_offers_mute_for_muteable_category():
    env = {"state": "warn",
           "path": "navigation.restrictedArea.abc",
           "message": "Inside whale closure"}
    q = prompts.alarm_user_prompt(env)
    assert "mute whale" in q.lower()


def test_alarm_prompt_no_mute_offer_for_emergency_or_unknown_path():
    emerg = {"state": "emergency", "path": "navigation.restrictedArea.abc",
             "message": "x"}
    other = {"state": "warn", "path": "electrical.batteries.0.voltage",
             "message": "x"}
    assert "mute" not in prompts.alarm_user_prompt(emerg).lower()
    assert "mute" not in prompts.alarm_user_prompt(other).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_poseidon_prompts.py -q`
Expected: FAIL — the mute offer is absent from `alarm_user_prompt` output.

- [ ] **Step 3: Write minimal implementation**

In `poseidon/prompts.py`, add an import near the top (after line 13):

```python
from poseidon.mutes import MUTEABLE_STATES, category_for_path
```

Replace `alarm_user_prompt` (lines 116-125) with:

```python
def alarm_user_prompt(env: dict) -> str:
    """Seed for one alarm narration (ported from the bridge's alert_query;
    the no-tools alarm lane drops the explain_notification escape hatch)."""
    base = (
        f"ALARM DISPATCH ({env.get('state')}, path {env.get('path')}): "
        f'announce this to the Captain now: "{env.get("message")}". '
        "Speak at most two short sentences: the announcement, plus one action "
        "only if obvious and urgent. Do not report other systems or readings, "
        "and never speak coordinates, paths, MMSI numbers, or timestamps."
    )
    category = category_for_path(env.get("path", ""))
    if category and env.get("state") in MUTEABLE_STATES:
        spoken = category.replace("-", " ")
        base += (f" If the Captain may want quiet on these, you may add: "
                 f"say 'mute {spoken}' and I'll keep quiet about them today.")
    return base
```

Note: the alarm lane's `ALARM_SYSTEM_PROMPT` caps output at two sentences; the offer is a third only when the crew is likely to want it. Keep the offer phrasing within the spoken-budget spirit — one short clause.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_poseidon_prompts.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite + commit**

```bash
.venv/bin/python -m pytest -q
```
Expected: all pass.

```bash
git add poseidon/prompts.py tests/test_poseidon_prompts.py
git commit -m "feat(mutes): alarm narration offers the mute opt-out for muteable categories"
```

---

### Task 9: HA dashboard toggle `switch.mute_whale_zones`

**Files (separate repo `~/src/sailingnaturali/infrastructure`):**
- Modify: `infrastructure/homeassistant/configuration.yaml` (add the MQTT switch under the existing `mqtt:` block).
- Reference: deploy via `infrastructure/scripts/ha-sync.sh` (scps `homeassistant/configuration.yaml` → `root@HA:/config/configuration.yaml` and restarts HA when that file changed).

**Interfaces:**
- Consumes: the retained mute topic contract (`naturali/mutes/whale-zones`; envelope on `mute`, empty payload on `unmute`).

This task is config, not code; it has no pytest cycle. It is gated behind a live broker and HA, so it is the final task and is verified by observation, not unit test.

- [ ] **Step 1: Add the MQTT switch**

In the HA MQTT config (where existing `mqtt:` entities live), add:

```yaml
mqtt:
  switch:
    - name: "Mute whale-zone alerts"
      unique_id: mute_whale_zones
      state_topic: "naturali/mutes/whale-zones"
      command_topic: "naturali/intents/mute"
      payload_on: '{"category":"whale-zones","action":"mute"}'
      payload_off: '{"category":"whale-zones","action":"unmute"}'
      state_on: "whale-zones"           # retained envelope present => on
      state_off: ""                      # empty retained payload => off
      value_template: "{{ value_json.category if value_json is defined else '' }}"
      optimistic: false
      retain: false
```

Note: the switch *commands* go to `naturali/intents/mute` (so HA does not write the full envelope itself — the daemon owns envelope construction). Add a small daemon handler OR an HA automation that republishes. To keep envelope-building in one place, prefer the daemon: see Step 2.

- [ ] **Step 2: Route `naturali/intents/mute` through the daemon**

The daemon already subscribes `naturali/intents/#`. In `poseidon/daemon.py` `dispatch`, add a branch (before the final `else`) that turns an intent into a publish via the same `apply_mute_request` path used by the voice tool:

```python
        elif topic == "naturali/intents/mute":
            from poseidon.mute_tool import apply_mute_request
            from poseidon.daemon import publish_mute_clear, publish_mute_set
            from datetime import datetime

            def _pub(category, env):
                publish_mute_set(category, env) if env else publish_mute_clear(category)
            apply_mute_request(payload.get("category", ""), payload.get("action", ""),
                               _pub, datetime.now().astimezone(), config.ROLLOVER_HOUR)
```

Add a daemon test mirroring Task 5's style asserting an `intents/mute` `{"category":"whale-zones","action":"mute"}` results in a `publish_mute_set` call (monkeypatch the publishers). Place in `tests/test_poseidon_daemon.py`; run `.venv/bin/python -m pytest tests/test_poseidon_daemon.py -q` and expect PASS. Commit:

```bash
git add poseidon/daemon.py tests/test_poseidon_daemon.py
git commit -m "feat(daemon): HA intents/mute routes through apply_mute_request"
```

- [ ] **Step 3: Deploy + verify (live, observational)**

```bash
~/src/sailingnaturali/infrastructure/scripts/ha-sync.sh
```
Then in the HA UI toggle the switch on; confirm a retained envelope appears:
```bash
mosquitto_sub -h 192.168.68.90 -u naturali -P "$MQTT_PASSWORD" -t 'naturali/mutes/#' -v -W 3
```
Expected: `naturali/mutes/whale-zones {"category":"whale-zones",...}`. Toggle off; confirm the retained slot clears (empty payload). Commit the HA config in the infrastructure repo:

```bash
cd ~/src/sailingnaturali/infrastructure
git add homeassistant/configuration.yaml
git commit -m "ha: mute-whale-zones switch (writes via naturali/intents/mute)"
```

---

## Post-implementation verification

- [ ] `cd ~/src/sailingnaturali/naturali-agents && .venv/bin/python -m pytest -q` — all green.
- [ ] Restart the daemon: `launchctl kickstart -k gui/$(id -u)/com.naturali.poseidon`.
- [ ] Live: publish a mute, then confirm a fresh `navigation.restrictedArea` `warn` does NOT reach `naturali/agents/navigator/say` (subscribe to both topics while injecting), while the alert still appears on `naturali/alerts/#`. Unmute and confirm narration returns.
- [ ] Voice: ask the puck "mute whale zones" and confirm the retained envelope is published and the spoken confirmation reads naturally.
