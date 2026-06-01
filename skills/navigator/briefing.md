## Daily briefing

When asked to generate the daily briefing, external weather and tide data will be provided in the prompt. Your job:

1. Call `mcp_signalk_get_local_time` first — use for all time references
2. Call `mcp_signalk_read_sensor` for current position, wind, SOG, depth, pressure
3. Call `mcp_signalk_battery_state` for charge level
4. Call `mcp_signalk_get_route` for the planned route (if set)
5. Synthesize all data into a briefing — surface only what is actionable

### Section ownership — each piece of data appears exactly once

| Data | Field |
|------|-------|
| Forecast weather (wind, swell, pressure) | `weather.rows` + `weather.analysis` |
| Onboard wind + pressure (with sailing interpretation) | `weather.rows` + `weather.analysis` |
| Tides, passage timing, route | `navigation` |
| Battery (only if actionable) | `navigation.analysis` |
| Tanks, watermaker, mechanical | `vessel_systems.notes` |

Battery and pressure are NEVER repeated in `vessel_systems` if already covered above.

### Format: structured rows for data, prose for analysis

Put raw numbers in the structured `rows` / `tide_rows` arrays, and keep the `analysis` fields to 1–2 sentences. Do not embed raw numbers in the analysis prose — the numbers live in the rows.

Example weather rows (these become `weather.rows`):
```json
[ { "source": "Forecast", "wind": "5 kn North", "pressure": "1015 hPa steady" },
  { "source": "Onboard",  "wind": "16 kn",       "pressure": "1002 hPa" } ]
```

### Pressure intelligence

Interpret the ONBOARD pressure reading for sailing conditions. Do not compare onboard vs forecast and suggest sensor calibration — real local pressure routinely diverges from regional forecasts, especially in the islands.

Use this scale for onboard absolute pressure:
- >1013 hPa: high pressure, settled conditions
- 1005–1013 hPa: neutral — no mention unless falling
- <1005 hPa: low pressure area — note "watch for deteriorating conditions and squalls"
- <995 hPa: significant low — flag, advise shelter plan

Use this scale for pressure trend (onboard reading vs 6 hours ago if available):
- Falling >3 hPa/6h: mention "pressure falling — possible frontal approach"
- Falling >6 hPa/6h: flag exposed anchorage risk explicitly

When both forecast and onboard pressure are available, report both in the table. Analysis prose uses the ONBOARD reading only.

**When to recommend monitoring:** When onboard pressure is low or diverges significantly from forecast, close the analysis with a specific recheck instruction. Use this logic:

- Onboard <1005 hPa **or** >8 hPa below regional forecast → "Recommend a pressure check in 30 minutes. If it has fallen more than 1 hPa, revisit your shelter plan before [next decision point on the route]."
- Onboard 1005–1010 hPa **or** 3–8 hPa below forecast → "Worth checking pressure again in an hour."
- Normal/stable → no monitoring suggestion needed.

The goal is to give the captain a specific time and a decision trigger — not a vague "monitor conditions."

### Wind intelligence

Do not compare onboard wind to forecast wind. Forecasts are regional; onboard wind is local reality. Report forecast and onboard independently in the weather table. Analysis is based on the onboard reading.

### Battery intelligence

- >60%: full range available — mention only as one line in Navigation, never in Vessel Systems
- 30–60%: plan a charge stop — mention in Navigation
- <30%: do not depart on a long passage — flag in Navigation
- Battery data does not appear in ## Vessel Systems unless it is the primary concern

### Other intelligence rules

- Full freshwater tank → no mention. 40% freshwater with no watermaker run planned → mention.
- Black water >70% → always mention in Vessel Systems with nearest pump-out suggestion.

### Output contract — structured fields

Respond with valid JSON only — no preamble, no explanation, just the JSON object. Do **not** emit markdown prose; populate the structured fields below. The briefing script renders these into the on-screen HTML and a logbook archive.

```json
{
  "briefing": {
    "header": { "date": "...", "position": "...", "destination": "..." },
    "weather": {
      "rows": [ { "source": "Forecast", "wind": "5 kn N", "pressure": "1015 steady" },
                { "source": "Onboard",  "wind": "16 kn",    "pressure": "1002" } ],
      "analysis": "1–2 sentences interpreting the ONBOARD reading."
    },
    "navigation": {
      "tide_rows": [ { "type": "High", "time": "12:38", "height": "3.8 m" } ],
      "departure": "Departure-time recommendation tied to tides/route.",
      "analysis": "Passage timing, tidal gates, battery range if actionable."
    },
    "vessel_systems": { "notes": [ "Actionable note, e.g. 'Black water 72% — pump out at Ganges.'" ] },
    "advisories": [ { "level": "info|caution|warning", "text": "..." } ]
  },
  "tts_extract": "Good morning. [weather headline]. [departure note]. [one priority advisory if any]."
}
```

Field mapping for the rules above:
- Forecast/onboard wind + pressure rows → `weather.rows`; the sailing interpretation → `weather.analysis`.
- Tides, passage timing, route, and actionable battery → `navigation` (table rows + `analysis`/`departure`).
- Tanks, watermaker, mechanical → `vessel_systems.notes`.
- The pressure/wind **recheck and shelter triggers** (the specific time + decision trigger) → an entry in `advisories` with the appropriate `level` (`caution` for a recheck, `warning` for shelter-plan risk). Routine/settled conditions → omit the advisory entirely.
- Section ownership still holds: each datum appears in exactly one place. Only include what is actionable; leave a field's list empty (`[]`) when there is nothing to say.

`tts_extract` must be 75 words or fewer. No markdown in `tts_extract`.
