# Spec: Briefing tide fetch — align to local day

**Date:** 2026-05-28
**Status:** Ready for implementation
**Owner:** Bryan
**Companion plan:** [`../plans/2026-05-28-briefing-tide-local-day.md`](../plans/2026-05-28-briefing-tide-local-day.md)

## Problem

`scripts/briefing.py:fetch_tides` queries CHS IWLS over a UTC-day window (`today 00:00Z → tomorrow 00:00Z`). The navigator's local timezone is `America/Vancouver` (PDT/PST, UTC-7/-8). When the daily briefing renders, tide extrema between today's 17:00 PDT and 24:00 PDT — which fall on *tomorrow* in UTC — are silently dropped from the briefing prompt.

Concretely, for a typical PNW mixed-semidiurnal pattern (HHW → LLW → LHW → HLW spread across ~25h), the briefing reliably truncates the day's last extremum and sometimes the last two whenever it runs before mid-afternoon UTC. That covers every realistic morning-briefing run time.

## Current behaviour

```python
# scripts/briefing.py:163-173 (today)
today = datetime.now(timezone.utc).date()
tomorrow = today + timedelta(days=1)
dr = httpx.get(
    CHS_DATA_URL.format(station_id=station["id"]),
    params={
        "time-series-code": "wlp-hilo",
        "from": f"{today}T00:00:00Z",
        "to": f"{tomorrow}T00:00:00Z",
    },
    timeout=15,
)
```

If "today UTC" is 2026-05-21, the window is `2026-05-21T00:00:00Z → 2026-05-22T00:00:00Z`. An event at 2026-05-22T02:30:00Z (which is 2026-05-21T19:30 PDT — today, locally) is excluded. An event at 2026-05-21T03:00:00Z (which is 2026-05-20T20:00 PDT — *yesterday* locally) is incorrectly included.

## Desired behaviour

The briefing presents the complete set of tide events that fall within today's *local* day in `America/Vancouver`. Query CHS over the UTC window that brackets local-today exactly.

For `now = 2026-05-21T15:00:00Z` (08:00 PDT):

- local-today starts at `2026-05-21T00:00 PDT` = `2026-05-21T07:00:00Z`
- local-today ends at `2026-05-22T00:00 PDT` = `2026-05-22T07:00:00Z`
- CHS query: `from=2026-05-21T07:00:00Z&to=2026-05-22T07:00:00Z`

This captures every extremum the captain will experience on their calendar day regardless of UTC straddling.

## Why this matters

The briefing's purpose is to give the navigator agent a complete picture of *today's* navigational constraints. A truncated tide schedule causes:

- The navigator cannot plan afternoon/evening departures around extrema it has never been told about.
- The captain hears a partial tide list and may misjudge the day's range.
- The failure mode is UTC-offset-dependent — it worsens the further west the vessel sails. Naturali's operating area (BC) sits at exactly the worst latitude band for this bug.

It also brings the briefing into semantic parity with `tide-mcp`'s `get_tide_heights`, which already covers the full local-day window (see the tide-mcp 0.2.0+ fixes to `tide_height_events`).

## Behavioural contract after the fix

| Aspect | Before | After |
|---|---|---|
| Query window | today UTC → tomorrow UTC | local-today PDT → local-tomorrow PDT (expressed in UTC) |
| Events for vessel's evening | dropped if past UTC midnight | always included |
| Events from yesterday-evening PDT | sometimes included | never |
| Number of CHS calls | 1 | 1 (unchanged) |
| `fetch_tides(lat, lon)` signature | `(lat, lon)` | `(lat, lon, now=None)` — `now` injectable for tests, defaults to `datetime.now(timezone.utc)` |
| Return shape | `{station_name, distance_km, events: [...]}` | unchanged |
| Behaviour when CHS fails | returns `None` | unchanged |

## Out of scope

- Switching the prompt's tide timestamps from `HH:MM UTC` to PDT. (`build_prompt:226-228` would change; revisit separately.)
- Filtering past events. The briefing deliberately shows the day's full pattern so the navigator can reason about elapsed *and* upcoming extrema.
- HTTP caching. The briefing is a once-daily job; a cache adds no value.
- Touching `_classify_tide_events`. A single CHS request returns a strictly alternating sequence, so per-call classification is correct without changes.
- Calling `tide-mcp` from `briefing.py` (a clean-up that removes the duplication). Worth doing eventually, but mechanically larger and not required to fix the bug. Track separately.

## Parity with tide-mcp

After this fix, both consumers of CHS height data behave consistently on the window question:

| Surface | Used by | UTC window | Filter past | Cap |
|---|---|---|---|---|
| `tide-mcp:get_tide_heights` | Navigator (chat) | local-day-equivalent (2 UTC days, cached per-day) | yes (`>= now`) | 4 |
| `briefing.py:fetch_tides` | Daily briefing | local-day exact window (1 call) | no | none |

The window math is the same; filter/cap differ because the use cases differ (chat = "what's next?", briefing = "what's the day's pattern?").

## Acceptance criteria

1. With `now = 2026-05-21T15:00:00Z`, `fetch_tides` issues a CHS `data` request whose `from` and `to` params are `2026-05-21T07:00:00Z` and `2026-05-22T07:00:00Z` respectively (PDT — UTC-7).
2. With `now` in a PST window (UTC-8), the same logic produces an 08:00Z–08:00Z window.
3. A mocked CHS response containing events at 2026-05-21T08:00Z (07:00Z is the local-day start; event is in window), 2026-05-21T14:30Z, 2026-05-21T20:45Z, and 2026-05-22T02:30Z is returned in full (all four events) for `now = 2026-05-21T15:00:00Z`.
4. The existing test `test_fetch_tides_returns_station_and_events` continues to pass after being updated to pass a deterministic `now`.
5. All other tests in `tests/test_briefing.py` continue to pass without modification.
6. `fetch_tides(lat, lon)` (no `now` argument) still works in production — defaults to current UTC time.
