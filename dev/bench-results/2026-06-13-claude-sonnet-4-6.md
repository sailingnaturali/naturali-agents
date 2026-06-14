### Benchmark run 2026-06-13 — claude-sonnet-4-6

- Asks: 8 | correctness: 87.5% | error rate: 0.0%
- Warm-hop latency: p50 9.39s | p95 30.00s

| ask | category | expected | observed | match | dt_total (s) |
|-----|----------|----------|----------|-------|--------------|
| depth | engineer-direct | mcp__signalk__depth_state | mcp__signalk__depth_state | ✓ | 3.63 |
| battery | engineer-direct | mcp__signalk__battery_state | mcp__signalk__battery_state | ✓ | 3.35 |
| alarms | engineer-direct | mcp__signalk__get_active_alarms | mcp__signalk__get_active_alarms | ✓ | 5.41 |
| wind-forecast | navigator | mcp__weather__get_marine_forecast | mcp__signalk__read_sensor, mcp__signalk__get_local_time, mcp__weather__get_marine_forecast | ✓ | 13.38 |
| current-boundary | navigator | mcp__currents__get_tidal_gate | mcp__currents__get_tidal_gate | ✓ | 4.78 |
| anchorage-near | navigator | mcp__pilotbook__find_anchorages_near | mcp__pilotbook__find_anchorages_near, mcp__pilotbook__rank_anchorages | ✓ | 37.58 |
| safe-to-anchor | navigator-multi | mcp__pilotbook__find_anchorages_near, mcp__weather__get_marine_forecast | — | ✗ | 15.91 |
| explain-alarm | delegated | Agent | Agent | ✓ | 15.42 |
