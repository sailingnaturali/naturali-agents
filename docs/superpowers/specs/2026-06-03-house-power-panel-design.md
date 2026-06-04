# Daily Briefing — House Power Panel

Date: 2026-06-03
Status: Approved (design)

## Problem

The battery line in the briefing is **fabricated** — `"Battery 68% — full range
available."` is the schema example echoed by the model (`briefing.py`, advisories),
not measured. SignalK exposes no electrical data today (`self` has only
`design / name / navigation / uuid`). We want a real house-power readout that
shows state of charge, whether we're charging or discharging and how fast, and
how long until the bank is full/empty.

## Goal

A **house power panel** (inline SVG, in the Vessel Systems card, above the tank
panels), wired to SignalK `electrical.*` and showing a placeholder until a
battery monitor exists:

- **State of charge** as a bar (low = bad).
- **Net power flow** — current (A), power (W), charging/discharging, voltage.
- **Time remaining** — to empty (discharging) or full (charging), from the
  *instantaneous* rate (battery use is cyclic; a trend fit would be misleading).
- A compact **SoC trend** mini-chart (last 7 days) for the charge/discharge cycle.

Chosen approaches: time-remaining from **instantaneous current** (or SignalK
`capacity.timeRemaining`); reuse the `tank_readings` table for SoC history; a
**dedicated** `build_house_power_panel` sharing the bar/colour/date helpers.

## Components (all in `briefing.py`, deterministic)

### Data access

- `fetch_house_power() -> dict | None` — read the first `electrical.batteries.<id>`:
  - `soc_pct` ← `capacity.stateOfCharge.value` × 100 (or `stateOfCharge.value`).
  - `voltage` ← `voltage.value` (V).
  - `current_a` ← `current.value` (A; SignalK sign: + into battery = charging).
  - `power_w` ← `power.value` if present, else `voltage × current_a`.
  - `time_remaining_s` ← `capacity.timeRemaining.value` if present (else None).
  Returns `None` when no battery / SignalK unreachable.
- `record_soc_reading(soc_pct)` — insert into the existing `tank_readings`
  table with `tank = "houseBattery"` (the column is a free identifier).
- `house_soc_history(limit=30)` — `tank_history("houseBattery")`.

### Time remaining

- `house_time_remaining(data) -> dict | None` — prefer `time_remaining_s`
  (discharging case from SignalK). Otherwise compute from instantaneous current:
  - charging (`current_a > 0`): hours to 100% = remaining Ah ÷ current.
  - discharging (`current_a < 0`): hours to 0% = present Ah ÷ |current|.
  Needs a capacity (Ah) — from SignalK `capacity.nominal` (Joules→Ah via voltage)
  when available, else a configured default (`HOUSE_BANK_AH`, env-overridable).
  Returns `{"hours": float, "state": "charging"|"discharging", "target": "full"|"empty"}`
  or `None` when current ≈ 0 (idle) or data is missing.

### Visual — `build_house_power_panel(data, history, placeholder=False) -> str`

Pure SVG, ~720×130:
- Header `HOUSE POWER` (left) + `SoC %` big (right), coloured by level
  (`_tank_color("drain", soc)` — teal→amber→red as it drops).
- **SoC bar**: width ∝ soc, same colour.
- **Flow row** (text): `⚡ {±I} A · {±P} W · {charging|discharging} · {V} V`.
  When idle (≈0 A): "float / idle".
- **Time-remaining**: `≈ empty in 14 h` / `≈ full in 3 h` (hours, or days if >48 h);
  omitted when idle.
- **SoC trend** mini-chart (last 7 days): framed 0–100% with a "now" marker and
  the recorded SoC line. **No** projection line (instantaneous ETA lives in the
  text). "" history → just the bar + flow.

## Wiring

- `main()`: `hp = fetch_house_power()`; if real, `record_soc_reading(hp["soc_pct"])`;
  `hist = house_soc_history()`; build the panel (placeholder when `hp is None`).
  Pass it to `render_html` and render it first in the Vessel Systems card.
- Remove `"Battery 68% — full range available."` from `SCHEMA_EXAMPLE` so the
  model stops fabricating a battery advisory.

## Today (no sensor) behaviour

`fetch_house_power` returns `None` → render a synthetic placeholder: SoC ~68%,
−4.2 A discharging, ~14 h to empty, a 7-day SoC cycle, labelled
"sample · awaiting sensor". No rows recorded until real data exists.

## Testing

- Unit: `house_time_remaining` returns sane hours + state for charging and
  discharging inputs, `None` when idle; `build_house_power_panel` is pure —
  assert bar width ∝ soc, flow text sign, time-remaining text, and the
  placeholder path. SoC history reuses `tank_readings` (temp-DB round-trip).
- Integration: regenerate the briefing; Vessel Systems shows the house-power
  panel in "awaiting sensor" state above the tanks. (Real path verified when a
  battery monitor feeds `electrical.*`.)

## Out of scope (YAGNI)

- Sources breakdown (solar / alternator / shore in watts) — the "full dashboard"
  option; revisit later.
- Multiple battery banks — first instance only for now.
- Voltage/health trend charts — SoC trend only.
