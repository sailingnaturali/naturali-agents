> **EXPERIMENT, not a baseline.** Captured on the shelved `feat/capability-memory`
> branch with the `NO_ROUTE` prompt addendum active in `crew_options()`. This run scored
> 30.8% vs the clean `main` baseline's 46.2% (`2026-06-22-claude-sonnet-4-6.md`) — a 2/13
> difference that is **within single-run variance** for Sonnet (one run each, latency p95
> also swung 8→19s), so whether the addendum affected golden routing is **inconclusive**
> from this data. What is clear from the per-ask detail: the misses are
> `read_sensor`-substitution and empty/delegated observations, **not** `NO_ROUTE` misfires.
> See `planning/docs/superpowers/specs/2026-06-22-capability-memory-routing-design.md`.

### Benchmark run 2026-06-22 — claude-sonnet-4-6 (capability-fallback experiment)

- Asks: 13 | correctness: 30.8% | error rate: 0.0%
- Warm-hop latency: p50 8.46s | p95 10.13s

| ask | category | expected | observed | match | dt_total (s) |
|-----|----------|----------|----------|-------|--------------|
| depth | engineer-direct | mcp__signalk__depth_state | mcp__signalk__depth_state | ✓ | 8.46 |
| battery | engineer-direct | mcp__signalk__battery_state | mcp__signalk__battery_state | ✓ | 9.61 |
| alarms | engineer-direct | mcp__signalk__get_active_alarms | mcp__signalk__get_active_alarms | ✓ | 8.49 |
| black-water-tank | engineer-direct | mcp__signalk__read_sensor | — | ✗ | 5.79 |
| wind-forecast | navigator | mcp__weather__get_marine_forecast | mcp__signalk__read_sensor | ✗ | 10.69 |
| current-boundary | navigator | mcp__currents__get_gate_current | mcp__currents__get_gate_current | ✓ | 9.34 |
| currents-nearby | navigator | mcp__currents__currents_near | mcp__signalk__read_sensor | ✗ | 9.18 |
| tide-heights | navigator | mcp__currents__get_tide_heights | mcp__signalk__read_sensor | ✗ | 9.76 |
| anchorage-near | navigator | mcp__pilotbook__find_anchorages_near | — | ✗ | 2.64 |
| safe-to-anchor | navigator-multi | mcp__pilotbook__assess_anchorage | — | ✗ | 2.57 |
| where-to-anchor | navigator-multi | mcp__pilotbook__assess_anchorage | — | ✗ | 7.38 |
| can-we-beach | navigator-multi | mcp__currents__get_tide_heights, mcp__signalk__depth_state | — | ✗ | 2.02 |
| explain-alarm | delegated | Agent | — | ✗ | 1.23 |
