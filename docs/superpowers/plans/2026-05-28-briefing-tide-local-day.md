# Briefing Tide Fetch — Local-Day Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `scripts/briefing.py:fetch_tides` query CHS over the navigator's local-day UTC window (America/Vancouver) instead of the UTC day, so today's evening PDT tides are no longer truncated from the briefing.

**Architecture:** Add an injectable `now` parameter to `fetch_tides`. Compute the local-day start/end in `America/Vancouver` via `zoneinfo`, convert those boundaries back to UTC, and use them as the CHS `from`/`to` params. No new dependencies; classification, return shape, and prompt rendering are unchanged.

**Tech Stack:** Python 3.11+, `httpx` (sync), `respx` (test mocks), `zoneinfo` (stdlib).

**Companion spec:** [`../specs/2026-05-28-briefing-tide-local-day.md`](../specs/2026-05-28-briefing-tide-local-day.md). Read it before starting Task 1.

---

## Background — read this first

`scripts/briefing.py` is a once-daily script (run by `bridges/` and/or HA automation) that builds a navigator prompt with today's weather + tides. It fetches tide events directly from CHS IWLS — independent from the `tide-mcp` MCP server, which serves the chat-time navigator surface.

The current query window is one UTC day. The fix is to query the local (America/Vancouver) day window — same single CHS call, just different `from`/`to` bounds.

You only touch:

- `scripts/briefing.py` — replace the inline window computation with a local-day computation; add `now` param to `fetch_tides`.
- `tests/test_briefing.py` — update one existing test (pass deterministic `now`, adjust mock event dates), add two new tests that pin the local-day window behaviour.

You do NOT touch:

- `_classify_tide_events` (still correct for single-call sequences).
- `build_prompt` (timestamp formatting is out of scope).
- `_haversine_km`, `_nearest_tide_station`, `_deg_to_compass` (unrelated).
- Any non-test file outside `scripts/briefing.py`.

## File Structure

```
scripts/briefing.py            modify ~20 lines around fetch_tides
tests/test_briefing.py         modify 1 test, add 2 tests
```

No new files.

## Test conventions used in this repo

- Tests are synchronous (`httpx.get` is sync in briefing.py). No `pytest-asyncio` decorators.
- HTTP mocks use `@respx.mock` decorator + `respx.get(URL).mock(return_value=httpx.Response(...))`.
- The CHS URLs are `https://api-sine.dfo-mpo.gc.ca/api/v1/stations` and `…/stations/{id}/data`.
- Existing tests live in one flat `tests/test_briefing.py` (no class grouping).

Run the test suite with:

```
uv run pytest tests/test_briefing.py -v
```

(The project's existing `pyproject.toml` already has pytest + respx in dev deps.)

---

## Task 1: Add `now` injection and switch to the local-day UTC window

**Files:**
- Modify: `scripts/briefing.py` — add a `DISPLAY_TZ` constant, modify `fetch_tides(lat, lon, now=None)`.
- Modify: `tests/test_briefing.py` — add a new test pinning the CHS query bounds.

- [ ] **Step 1: Add a failing test for the query window**

Append to `tests/test_briefing.py` (after `test_fetch_tides_returns_none_on_failure`, before `test_deg_to_compass`):

```python
@respx.mock
def test_fetch_tides_queries_local_day_utc_window():
    """At 08:00 PDT on 2026-05-21, the CHS window must cover 07:00Z that day
    through 07:00Z the next day — exactly local-today in UTC."""
    respx.get("https://api-sine.dfo-mpo.gc.ca/api/v1/stations").mock(
        return_value=httpx.Response(200, json=[
            {
                "id": "ccc", "officialName": "Tsawwassen", "operating": True,
                "latitude": 49.007, "longitude": -123.129,
                "timeSeries": [{"code": "wlp-hilo"}],
            }
        ])
    )
    data_route = respx.get("https://api-sine.dfo-mpo.gc.ca/api/v1/stations/ccc/data").mock(
        return_value=httpx.Response(200, json=[])
    )

    now = datetime(2026, 5, 21, 15, 0, tzinfo=timezone.utc)  # 08:00 PDT
    briefing.fetch_tides(48.76, -123.05, now=now)

    assert data_route.called
    params = data_route.calls[0].request.url.params
    assert params["from"] == "2026-05-21T07:00:00Z"
    assert params["to"] == "2026-05-22T07:00:00Z"
    assert params["time-series-code"] == "wlp-hilo"
```

This test also requires `datetime` and `timezone` in the test module imports. Verify the top of `tests/test_briefing.py` already imports them (it should — search for `from datetime import`). If not, add `from datetime import datetime, timezone` to the imports.

- [ ] **Step 2: Run the new test and confirm it fails**

Run: `uv run pytest tests/test_briefing.py::test_fetch_tides_queries_local_day_utc_window -v`

Expected: **FAIL**. The most likely failure is `TypeError: fetch_tides() got an unexpected keyword argument 'now'`. (If `fetch_tides` somehow accepts `now` but produces the wrong window, the assertion on `params["from"]` will fail with a UTC-day boundary like `2026-05-21T00:00:00Z`.)

- [ ] **Step 3: Add the imports and constant**

At the top of `scripts/briefing.py`, find the existing `from datetime import datetime, timedelta, timezone` line and add `zoneinfo` immediately after it:

```python
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
```

Then add the timezone constant near the other module-level constants (next to `CHS_DATA_URL`):

```python
DISPLAY_TZ = ZoneInfo("America/Vancouver")
```

- [ ] **Step 4: Rewrite `fetch_tides` to use the local-day window**

Replace the existing `fetch_tides` function (currently `scripts/briefing.py:157-184`) with:

```python
def fetch_tides(lat: float, lon: float, now: datetime | None = None) -> dict | None:
    """Fetch today's tide extrema for the nearest CHS wlp-hilo station.

    `now` is injectable for deterministic tests; defaults to the current UTC time.
    The query window is exactly one *local* day (America/Vancouver), so today's
    evening PDT extrema that land past UTC midnight are still captured. Mirrors
    the window semantics of tide-mcp's `tide_height_events`.
    """
    try:
        sr = httpx.get(CHS_STATIONS_URL, timeout=15)
        sr.raise_for_status()
        station = _nearest_tide_station(lat, lon, sr.json())

        if now is None:
            now = datetime.now(timezone.utc)
        local_now = now.astimezone(DISPLAY_TZ)
        local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        local_end = local_start + timedelta(days=1)
        window_from = local_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        window_to = local_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        dr = httpx.get(
            CHS_DATA_URL.format(station_id=station["id"]),
            params={
                "time-series-code": "wlp-hilo",
                "from": window_from,
                "to": window_to,
            },
            timeout=15,
        )
        dr.raise_for_status()
        events = _classify_tide_events(dr.json())
        distance_km = round(_haversine_km(lat, lon, station["latitude"], station["longitude"]))
        return {
            "station_name": station["officialName"],
            "distance_km": distance_km,
            "events": events,
        }
    except Exception as e:
        log.warning("fetch_tides failed: %s", e)
        return None
```

- [ ] **Step 5: Re-run the new test and confirm it passes**

Run: `uv run pytest tests/test_briefing.py::test_fetch_tides_queries_local_day_utc_window -v`

Expected: **PASS**.

- [ ] **Step 6: Run the full briefing test file to spot fallout**

Run: `uv run pytest tests/test_briefing.py -v`

Expected: One failure — `test_fetch_tides_returns_station_and_events` — because its mock events at `2026-05-21T06:00:00Z` now fall outside the local-day window. Leave this failure for Task 2; do **not** "fix" it by reverting the implementation.

If any other test fails, stop and investigate — that's an unexpected interaction.

- [ ] **Step 7: Commit**

```bash
git add scripts/briefing.py tests/test_briefing.py
git commit -m "fix(briefing): query CHS over local-day UTC window

Today's evening PDT extrema were dropped whenever they landed past UTC
midnight. Compute the local-day (America/Vancouver) bounds and convert
back to UTC for the CHS query, mirroring tide-mcp's tide_height_events
window semantics. fetch_tides now takes an optional now= for tests."
```

---

## Task 2: Repair the existing fetch_tides test

The old `test_fetch_tides_returns_station_and_events` used mock events at `2026-05-21T06:00:00Z`, which is before the local-day start of `2026-05-21T07:00:00Z`. After Task 1, CHS would receive a window that excludes that event. Update the mock to use timestamps fully inside a deterministic local-day window, and pass `now=` so the test isn't time-dependent.

**Files:**
- Modify: `tests/test_briefing.py` — `test_fetch_tides_returns_station_and_events`.

- [ ] **Step 1: Replace the existing test body**

Find `test_fetch_tides_returns_station_and_events` (currently around `tests/test_briefing.py:138-162`). Replace its body with:

```python
@respx.mock
def test_fetch_tides_returns_station_and_events():
    respx.get("https://api-sine.dfo-mpo.gc.ca/api/v1/stations").mock(
        return_value=httpx.Response(200, json=[
            {
                "id": "ccc", "officialName": "Tsawwassen", "operating": True,
                "latitude": 49.007, "longitude": -123.129,
                "timeSeries": [{"code": "wlp-hilo"}],
            }
        ])
    )
    # Events fully inside the 2026-05-21 PDT day (07:00Z → next-day 07:00Z).
    respx.get("https://api-sine.dfo-mpo.gc.ca/api/v1/stations/ccc/data").mock(
        return_value=httpx.Response(200, json=[
            {"eventDate": "2026-05-21T08:30:00Z", "value": 4.76, "qcFlagCode": "1"},
            {"eventDate": "2026-05-21T14:45:00Z", "value": 1.38, "qcFlagCode": "1"},
            {"eventDate": "2026-05-21T20:35:00Z", "value": 3.82, "qcFlagCode": "1"},
            {"eventDate": "2026-05-22T02:50:00Z", "value": 0.58, "qcFlagCode": "1"},
        ])
    )
    now = datetime(2026, 5, 21, 15, 0, tzinfo=timezone.utc)
    result = briefing.fetch_tides(48.76, -123.05, now=now)
    assert result is not None
    assert result["station_name"] == "Tsawwassen"
    assert result["distance_km"] == 28
    assert len(result["events"]) == 4
    assert [e["type"] for e in result["events"]] == ["high", "low", "high", "low"]
    assert result["events"][0]["height_m"] == 4.8
    assert result["events"][3]["time_utc"] == "2026-05-22T02:50:00Z"
```

- [ ] **Step 2: Run the updated test**

Run: `uv run pytest tests/test_briefing.py::test_fetch_tides_returns_station_and_events -v`

Expected: **PASS**.

- [ ] **Step 3: Run the full briefing test file**

Run: `uv run pytest tests/test_briefing.py -v`

Expected: **ALL PASS**. If any test still fails, investigate before moving on.

- [ ] **Step 4: Commit**

```bash
git add tests/test_briefing.py
git commit -m "test(briefing): pass deterministic now to fetch_tides

Mock events were near the UTC-day boundary and ambiguous after the
local-day window switch. Pin now=2026-05-21T15:00Z, move events fully
inside that PDT day (including one past UTC midnight, to exercise the
fix), and assert the full alternation."
```

---

## Task 3: Pin the UTC-midnight regression with an explicit test

The bug we just fixed is "today's evening PDT extremum gets dropped because it lives in tomorrow UTC." Add a focused test that would fail under the *old* behaviour even if Task 2's combined-assertion test happened to be loosened.

**Files:**
- Modify: `tests/test_briefing.py` — add one new test.

- [ ] **Step 1: Add the regression test**

Append to `tests/test_briefing.py` (next to the other `fetch_tides` tests):

```python
@respx.mock
def test_fetch_tides_includes_evening_pdt_event_past_utc_midnight():
    """Regression: with the old UTC-day window, an event at 2026-05-22T03:00Z
    (19:00 PDT on 2026-05-21) was dropped from the 2026-05-21 briefing."""
    respx.get("https://api-sine.dfo-mpo.gc.ca/api/v1/stations").mock(
        return_value=httpx.Response(200, json=[
            {
                "id": "ccc", "officialName": "Tsawwassen", "operating": True,
                "latitude": 49.007, "longitude": -123.129,
                "timeSeries": [{"code": "wlp-hilo"}],
            }
        ])
    )
    respx.get("https://api-sine.dfo-mpo.gc.ca/api/v1/stations/ccc/data").mock(
        return_value=httpx.Response(200, json=[
            {"eventDate": "2026-05-21T10:00:00Z", "value": 4.2, "qcFlagCode": "1"},
            {"eventDate": "2026-05-22T03:00:00Z", "value": 0.9, "qcFlagCode": "1"},
        ])
    )
    now = datetime(2026, 5, 21, 15, 0, tzinfo=timezone.utc)
    result = briefing.fetch_tides(48.76, -123.05, now=now)
    assert result is not None
    times = [e["time_utc"] for e in result["events"]]
    assert "2026-05-22T03:00:00Z" in times, (
        "evening PDT event past UTC midnight must be included in today's briefing"
    )
```

- [ ] **Step 2: Run the new test**

Run: `uv run pytest tests/test_briefing.py::test_fetch_tides_includes_evening_pdt_event_past_utc_midnight -v`

Expected: **PASS**.

- [ ] **Step 3: Run the full briefing test file one more time**

Run: `uv run pytest tests/test_briefing.py -v`

Expected: **ALL PASS** (including the three new/updated tests from Tasks 1–3).

- [ ] **Step 4: Commit**

```bash
git add tests/test_briefing.py
git commit -m "test(briefing): regression test for evening PDT event past UTC midnight"
```

---

## Task 4: Add a parity cross-reference comment

`scripts/briefing.py` is a parallel implementation of CHS height fetching to `tide-mcp`'s `tide_height_events`. They should evolve together. Drop a comment so the next person editing either side knows about the other.

**Files:**
- Modify: `scripts/briefing.py` — one-line comment above `fetch_tides`.

- [ ] **Step 1: Add the comment**

Find the `def fetch_tides(...)` line in `scripts/briefing.py`. Immediately above it (between `_classify_tide_events` and `fetch_tides`), add:

```python
# Parity sibling: tide-mcp/src/tide_mcp/fetch.py:tide_height_events. Keep the
# CHS query-window semantics in sync between the two implementations.
```

- [ ] **Step 2: Verify nothing else changed**

Run: `uv run pytest tests/test_briefing.py -v`

Expected: **ALL PASS**.

- [ ] **Step 3: Commit**

```bash
git add scripts/briefing.py
git commit -m "docs(briefing): note tide-mcp parity sibling on fetch_tides"
```

---

## Final verification

After all four tasks:

- [ ] Run the full test suite (not just `test_briefing.py`):

```
uv run pytest -v
```

Every existing test should still pass. Only `tests/test_briefing.py` has changed.

- [ ] Sanity-check `git log`:

```
git log --oneline -5
```

You should see four new commits (Tasks 1–4) on top of `d0a9589`.

- [ ] Spot-check the prod path. With network access:

```
uv run scripts/briefing.py --dry-run
```

The printed prompt should contain a `TIDES` block whose timestamps span a full PDT day (typically four extrema). If it shows only two or three, double-check the local-day computation in Task 1's Step 4.

## Don't

- Do **not** also filter past events. The briefing intentionally shows the day's full pattern. That filter belongs in `tide-mcp`'s chat surface, not here.
- Do **not** add an HTTP cache. The briefing is a once-daily job.
- Do **not** switch the prompt rendering from `HH:MM UTC` to PDT — out of scope; revisit separately.
- Do **not** introduce `freezegun` or any other time-mocking dependency. The `now=` injection is sufficient and dependency-free.
