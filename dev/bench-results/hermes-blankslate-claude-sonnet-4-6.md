### Benchmark run  — hermes-blankslate-claude-sonnet-4-6

- Asks: 13 | correctness: 61.5% | error rate: 0.0%
- Warm-hop latency: p50 13.77s | p95 36.96s

| ask | category | expected | observed | match | dt_total (s) |
|-----|----------|----------|----------|-------|--------------|
| depth | engineer-direct | mcp__signalk__depth_state | mcp__signalk__depth_state | ✓ | 6.11 |
| battery | engineer-direct | mcp__signalk__battery_state | mcp__signalk__battery_state | ✓ | 7.80 |
| alarms | engineer-direct | mcp__signalk__get_active_alarms | mcp__signalk__get_active_alarms | ✓ | 8.71 |
| black-water-tank | engineer-direct | mcp__signalk__read_sensor | mcp__signalk__list_paths, mcp__signalk__read_sensor | ✓ | 9.84 |
| wind-forecast | navigator | mcp__weather__get_marine_forecast | mcp__signalk__read_sensor, mcp__signalk__get_local_time, mcp__weather__get_marine_forecast | ✓ | 18.26 |
| current-boundary | navigator | mcp__currents__get_gate_current | mcp__currents__get_gate_current | ✓ | 7.46 |
| currents-nearby | navigator | mcp__currents__currents_near | mcp__signalk__read_sensor, mcp__signalk__get_local_time, mcp__currents__currents_near | ✓ | 14.40 |
| tide-heights | navigator | mcp__currents__get_tide_heights | mcp__signalk__read_sensor, mcp__currents__get_tide_heights | ✓ | 11.05 |
| anchorage-near | navigator | mcp__pilotbook__find_anchorages_near | mcp__signalk__read_sensor, mcp__club-moorage__find_moorage_near | ✗ | 13.77 |
| safe-to-anchor | navigator-multi | mcp__pilotbook__assess_anchorage | mcp__signalk__read_sensor, mcp__signalk__get_local_time, mcp__weather__get_marine_forecast, mcp__currents__currents_near, mcp__signalk__depth_state, mcp__club-moorage__find_moorage_near | ✗ | 35.94 |
| where-to-anchor | navigator-multi | mcp__pilotbook__assess_anchorage | mcp__signalk__read_sensor, mcp__signalk__get_local_time, mcp__weather__get_marine_forecast, mcp__club-moorage__find_moorage_near, mcp__club-moorage__rank_moorage | ✗ | 38.50 |
| can-we-beach | navigator-multi | mcp__currents__get_tide_heights, mcp__signalk__depth_state | mcp__signalk__depth_state, mcp__signalk__read_sensor | ✗ | 15.40 |
| explain-alarm | delegated | Agent | mcp__signalk__get_active_alarms, mcp__signalk__battery_state | ✗ | 16.27 |
