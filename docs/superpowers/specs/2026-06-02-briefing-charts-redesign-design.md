# Daily Briefing — Chart Redesign (wind compass + tide area chart)

Date: 2026-06-02
Status: Approved (design)

## Problem

The briefing's navigation chart overlays wind (knots) and tide (metres) on a
single SVG with a shared y-axis and no axis labels. Knots and metres have no
correlation, so the shared axis is meaningless, and without tick values the
reader can't tell tide height or the time of changes. The chart is decorative,
not informative.

## Goal

Replace the single dual-curve with two purpose-built, self-contained inline
SVGs, laid out side by side (wrapping on narrow screens):

1. A **wind compass** — current direction + speed (direction matters most).
2. A **tide area chart** — the existing line, now filled and with labelled axes.

Approach A (chosen): pure functions in `briefing.py` emitting inline SVG. No JS,
no CDN — the briefing stays a single offline HTML document.

## Components

### Wind compass — `build_wind_compass(direction_deg, speed_kn) -> str`

- Circle with N/E/S/W ticks and labels.
- An arrow drawn from the source bearing toward the centre (meteorological
  convention: wind *from* a bearing, e.g. a NW wind blows from the NW).
- Centre text: speed `8 kn` and cardinal label `NW` (16-point compass rounding).
- Pure function; returns `""` when inputs are missing → compass omitted.

Data: new `fetch_current_wind(lat, lon) -> dict | None` calling Open-Meteo with
`current=wind_speed_10m,wind_direction_10m`, `wind_speed_unit=kn`. Returns
`{"speed_kn": float, "direction_deg": float}` or `None` on failure (offline →
compass omitted gracefully).

### Tide area chart — `build_tide_chart(tide_curve) -> str`

- Same polyline from `fetch_tide_curve` (CHS 15-min `wlp` height series), now
  with a **translucent amber fill** to the chart baseline.
- **Y-axis:** 2–3 height ticks labelled in metres, spanning the day's min/max
  (e.g. `0.2 m` … `3.1 m`), with light horizontal gridlines.
- **X-axis:** time ticks every 6h in **local** time (`00 06 12 18 24`) with light
  vertical gridlines. `time_utc` values are converted UTC→local for labels.
- A subtle vertical **"now"** marker and small dots at the day's hi/lo points.
- Pure function; returns `""` when there is no curve data.

### Layout — template

The `.chart` div becomes a flex row: the compass (fixed ~200px square) on the
left, the tide chart (flex-grow) on the right; `flex-wrap` so it stacks on narrow
screens. Existing dark theme / accent colours (`--teal`, `--amber`) reused.

## Wiring changes (`briefing.py`, `templates/briefing.html.j2`)

- Remove `build_svg_curve` and `fetch_wind_curve` (the hourly wind curve is no
  longer used).
- `main()`: fetch `current_wind = fetch_current_wind(lat, lon)` and
  `tide_curve = fetch_tide_curve(lat, lon)`; build `compass_svg` + `tide_svg`.
- `render_html(briefing, compass_svg="", tide_svg="")` — pass both to the
  template (replacing the single `svg` arg).
- Template: replace `{{ svg|safe }}` with the flex row rendering
  `{{ compass_svg|safe }}` and `{{ tide_svg|safe }}`, each guarded so an empty
  string renders nothing.

## Testing / verification

- Unit: `fetch_current_wind` returns speed+direction for known coords;
  `build_wind_compass` / `build_tide_chart` are pure — assert key SVG elements
  (axis labels, arrow, fill path) for sample inputs and render `""` for empty.
- Integration: regenerate the briefing and verify on HA — compass shows current
  direction/speed, tide chart shows metre/time labels with fill.

## Out of scope (YAGNI)

- Wind vector field over a map (explicitly deferred by the user).
- Wind forecast curve / gust series.
- Interactivity or JS charting libraries.
