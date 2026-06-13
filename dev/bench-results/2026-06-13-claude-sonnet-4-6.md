### Benchmark run 2026-06-13 — claude-sonnet-4-6

- Asks: 8 | correctness: 75.0% | error rate: 0.0%
- Warm-hop latency: p50 8.77s | p95 30.71s

| ask | category | expected | observed | match | dt_total (s) |
|-----|----------|----------|----------|-------|--------------|
| depth | engineer-direct | mcp__signalk__depth_state | mcp__signalk__depth_state | ✓ | 4.54 |
| battery | engineer-direct | mcp__signalk__battery_state | mcp__signalk__battery_state | ✓ | 4.83 |
| alarms | engineer-direct | mcp__signalk__get_active_alarms | mcp__signalk__get_active_alarms | ✓ | 5.94 |
| wind-forecast | navigator | mcp__weather__get_marine_forecast | mcp__signalk__read_sensor, mcp__signalk__get_local_time, mcp__weather__get_marine_forecast | ✓ | 10.91 |
| current-boundary | navigator | mcp__currents__get_tidal_gate | mcp__currents__get_tidal_gate | ✓ | 6.62 |
| anchorage-near | navigator | mcp__pilotbook__find_anchorages_near | mcp__pilotbook__find_anchorages_near, mcp__pilotbook__rank_anchorages | ✓ | 36.41 |
| safe-to-anchor | navigator-multi | mcp__pilotbook__find_anchorages_near, mcp__weather__get_marine_forecast | — | ✗ | 18.38 |
| explain-alarm | delegated | mcp__signalk__get_active_alarms | Agent | ✗ | 20.14 |
