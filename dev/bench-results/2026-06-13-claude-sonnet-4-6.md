### Benchmark run 2026-06-13 — claude-sonnet-4-6

- Asks: 8 | correctness: 50.0% | error rate: 0.0%
- Warm-hop latency: p50 11.11s | p95 32.28s

| ask | category | expected | observed | match | dt_total (s) |
|-----|----------|----------|----------|-------|--------------|
| depth | engineer-direct | mcp__signalk__depth_state | mcp__signalk__depth_state | ✓ | 3.50 |
| battery | engineer-direct | mcp__signalk__battery_state | mcp__signalk__battery_state | ✓ | 3.90 |
| alarms | engineer-direct | mcp__signalk__get_active_alarms | mcp__signalk__get_active_alarms | ✓ | 7.16 |
| wind-forecast | navigator | mcp__weather__get_marine_forecast | mcp__signalk__read_sensor, mcp__signalk__get_local_time, mcp__weather__get_marine_forecast | ✗ | 15.06 |
| current-boundary | navigator | mcp__currents__get_tidal_gate | mcp__currents__get_tidal_gate | ✓ | 6.25 |
| anchorage-near | navigator | mcp__pilotbook__find_anchorages_near | mcp__pilotbook__find_anchorages_near, mcp__pilotbook__rank_anchorages | ✗ | 40.25 |
| safe-to-anchor | navigator-multi | mcp__pilotbook__find_anchorages_near, mcp__weather__get_marine_forecast | — | ✗ | 17.36 |
| explain-alarm | delegated | Agent | Agent, mcp__signalk__battery_state, mcp__signalk__get_active_alarms | ✗ | 17.47 |
