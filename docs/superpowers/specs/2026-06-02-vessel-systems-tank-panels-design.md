# Daily Briefing — Vessel Systems Tank Panels

Date: 2026-06-02
Status: Approved (design)

## Problem

The Vessel Systems section is free-form model text, and the values are
**fabricated** — "Black water 72%" / "Battery 68%" are the schema example being
echoed by the structured-output model, not measured. There is no tank sensor on
SignalK today (`/vessels/self/tanks` is empty) and no history of levels over
time. We want a real, visual tank readout that shows current fill, the trend
over time, and an estimate of when a tank reaches its critical level.

## Goal

A **reusable tank panel** (inline SVG, like the wind/tide charts) driven by a
per-tank config, handling both fill directions:

| Tank | Direction | Projection | Guidance |
|------|-----------|------------|----------|
| Black water | fills ↑ | ETA to **full** (100%) | "pump out at <port>" |
| Fresh water | drains ↓ | ETA to **empty** (0%) | "run the water maker / fill soon" |

Wired to real SignalK `tanks.*` data and a recorded history, so it shows live
values + a real projection the moment a sensor is installed. Until then it
renders a clearly-labelled "sample · awaiting sensor" placeholder.

Chosen approaches: storage **A** (new table in the existing logbook SQLite DB),
visual **A** (fill bar + sparkline + projection line + ETA/action label).

## Components (all in `briefing.py`, deterministic)

### TankSpec (config, one per tank)

```
TankSpec:
  key          # SignalK tank type path segment: "blackWater" | "freshWater"
  label        # "Black Water" | "Fresh Water"
  direction    # "fill" (concern = reaching 100%) | "drain" (concern = reaching 0%)
  action       # "pump out" | "run the water maker / fill soon"
```

Module constant `TANKS = [TankSpec(blackWater, fill, …), TankSpec(freshWater, drain, …)]`.

### Data access

- `fetch_tank_level(key) -> float | None` — GET SignalK
  `tanks/<key>` to find the first instance id, then
  `tanks/<key>/<id>/currentLevel` (ratio 0–1 → percent 0–100). `None` when the
  tank/SignalK is absent.
- `record_tank_reading(key, level_pct)` — insert into a new table:
  `tank_readings(id INTEGER PK, tank TEXT, level REAL, timestamp TEXT)` in
  `~/.naturali/briefings.db`. Only called when a real level exists.
- `tank_history(key, limit=30) -> list[(timestamp, level)]` — recent rows for
  the tank, oldest→newest.

### Projection

- `project_threshold(history, direction) -> dict | None` — linear least-squares
  fit of level vs. time over the history. From the slope (%/day):
  - `fill` → time until level reaches 100%.
  - `drain` → time until level reaches 0%.
  Returns `{"eta": datetime, "days": float, "rate_pct_day": float}` or `None`
  when there are <2 readings or the slope is the wrong sign / ~flat (no ETA).

### Visual

- `build_tank_panel(spec, level_pct, history, projection) -> str` — pure SVG:
  - **Fill bar**: current % with a fill colour that reflects concern —
    `fill` tanks go teal→amber→red as they rise; `drain` tanks go teal→amber→red
    as they fall. Percent label on the bar.
  - **Sparkline**: recorded readings over time; a **dashed projection line**
    continuing to the threshold (100% for fill, 0% for drain).
  - **Label line**: `Black Water · ≈ full in 3 days · pump out at Sidney`
    / `Fresh Water · ≈ empty in 2 days · run the water maker`. When <2 readings:
    "collecting trend". When no sensor: "sample · awaiting sensor".
  - Returns "" only if neither a level nor a placeholder should show (always
    renders the placeholder today).

## Wiring

- `main()`: for each `TankSpec`, `level = fetch_tank_level(key)`; if real,
  `record_tank_reading`; `history = tank_history`; `proj = project_threshold`;
  `panel = build_tank_panel(...)`. Collect the panel SVGs.
- `render_html(..., tank_panels=[...])` — pass the list to the template.
- Template: render the tank panels stacked inside the Vessel Systems card,
  above the existing model notes.
- Remove `"Black water 72% — pump out at Sidney."` from `SCHEMA_EXAMPLE` so the
  model stops fabricating a black-water note that duplicates the real panel.

## Today (no sensor) behaviour

`fetch_tank_level` returns `None` → `build_tank_panel` renders a muted
placeholder bar at a sample level with a "sample · awaiting sensor" label and a
synthetic trend, so the layout is visible and review-able. No rows are written
to `tank_readings` until a real level exists, so the projection stays honest.

## Testing

- Unit: `project_threshold` returns a sane ETA for a known rising/falling series
  and `None` for <2 points / wrong-direction slope. `build_tank_panel` is pure —
  assert bar width ∝ level, presence of projection line + label, and the
  placeholder path. `record_tank_reading`/`tank_history` round-trip via a temp DB.
- Integration: regenerate the briefing; Vessel Systems shows the black-water and
  fresh-water panels in "awaiting sensor" state. (Real-data path verified when a
  SignalK tank sensor exists.)

## Out of scope (YAGNI)

- Tanks beyond black + fresh water (grey water, fuel) — config is generic so they
  drop in later.
- A separate high-frequency poller — daily briefing-run snapshots only for now.
- Fixing the rest of the fabricated Vessel Systems / battery (separate effort).
- Non-linear / usage-pattern projection — a linear fit is the first-order
  estimate.
