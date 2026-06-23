### Benchmark run 2026-06-22 — claude-sonnet-4-6

- Asks: 39 | correctness: 48.7% | error rate: 0.0%
- Warm-hop latency: p50 3.65s | p95 11.56s

| ask | category | expected | observed | match | dt_total (s) |
|-----|----------|----------|----------|-------|--------------|
| depth | engineer-direct | mcp__signalk__depth_state | mcp__signalk__depth_state | ✓ | 5.30 |
| battery | engineer-direct | mcp__signalk__battery_state | mcp__signalk__battery_state | ✓ | 3.81 |
| alarms | engineer-direct | mcp__signalk__get_active_alarms | mcp__signalk__get_active_alarms | ✓ | 4.32 |
| black-water-tank | engineer-direct | mcp__signalk__read_sensor | mcp__signalk__list_paths, mcp__signalk__read_sensor | ✓ | 7.36 |
| wind-forecast | navigator | mcp__weather__get_marine_forecast | mcp__signalk__read_sensor, mcp__signalk__get_local_time, mcp__weather__get_marine_forecast | ✓ | 16.24 |
| current-boundary | navigator | mcp__currents__get_gate_current | mcp__currents__get_gate_current | ✓ | 10.11 |
| currents-nearby | navigator | mcp__currents__currents_near | mcp__currents__currents_near | ✓ | 6.78 |
| tide-heights | navigator | mcp__currents__get_tide_heights | mcp__currents__get_tide_heights | ✓ | 9.72 |
| anchorage-near | navigator | mcp__pilotbook__find_anchorages_near | mcp__pilotbook__find_anchorages_near | ✓ | 5.84 |
| safe-to-anchor | navigator-multi | mcp__pilotbook__assess_anchorage | mcp__pilotbook__assess_anchorage | ✓ | 8.15 |
| where-to-anchor | navigator-multi | mcp__pilotbook__assess_anchorage | — | ✗ | 3.65 |
| can-we-beach | navigator-multi | mcp__currents__get_tide_heights, mcp__signalk__depth_state | — | ✗ | 11.32 |
| explain-alarm | delegated | Agent | Agent, mcp__signalk__battery_state | ✓ | 13.79 |
| depth | engineer-direct | mcp__signalk__depth_state | mcp__signalk__depth_state | ✓ | 3.49 |
| battery | engineer-direct | mcp__signalk__battery_state | mcp__signalk__battery_state | ✓ | 3.56 |
| alarms | engineer-direct | mcp__signalk__get_active_alarms | mcp__signalk__get_active_alarms | ✓ | 3.31 |
| black-water-tank | engineer-direct | mcp__signalk__read_sensor | mcp__signalk__read_sensor | ✓ | 4.05 |
| wind-forecast | navigator | mcp__weather__get_marine_forecast | — | ✗ | 8.67 |
| current-boundary | navigator | mcp__currents__get_gate_current | — | ✗ | 7.18 |
| currents-nearby | navigator | mcp__currents__currents_near | — | ✗ | 3.62 |
| tide-heights | navigator | mcp__currents__get_tide_heights | — | ✗ | 5.06 |
| anchorage-near | navigator | mcp__pilotbook__find_anchorages_near | — | ✗ | 2.92 |
| safe-to-anchor | navigator-multi | mcp__pilotbook__assess_anchorage | — | ✗ | 3.30 |
| where-to-anchor | navigator-multi | mcp__pilotbook__assess_anchorage | — | ✗ | 3.04 |
| can-we-beach | navigator-multi | mcp__currents__get_tide_heights, mcp__signalk__depth_state | — | ✗ | 3.09 |
| explain-alarm | delegated | Agent | — | ✗ | 2.74 |
| depth | engineer-direct | mcp__signalk__depth_state | mcp__signalk__depth_state | ✓ | 3.41 |
| battery | engineer-direct | mcp__signalk__battery_state | mcp__signalk__battery_state | ✓ | 3.13 |
| alarms | engineer-direct | mcp__signalk__get_active_alarms | mcp__signalk__get_active_alarms | ✓ | 3.25 |
| black-water-tank | engineer-direct | mcp__signalk__read_sensor | mcp__signalk__read_sensor | ✓ | 4.19 |
| wind-forecast | navigator | mcp__weather__get_marine_forecast | — | ✗ | 5.14 |
| current-boundary | navigator | mcp__currents__get_gate_current | — | ✗ | 2.00 |
| currents-nearby | navigator | mcp__currents__currents_near | — | ✗ | 2.22 |
| tide-heights | navigator | mcp__currents__get_tide_heights | — | ✗ | 2.38 |
| anchorage-near | navigator | mcp__pilotbook__find_anchorages_near | — | ✗ | 1.87 |
| safe-to-anchor | navigator-multi | mcp__pilotbook__assess_anchorage | — | ✗ | 2.59 |
| where-to-anchor | navigator-multi | mcp__pilotbook__assess_anchorage | — | ✗ | 1.63 |
| can-we-beach | navigator-multi | mcp__currents__get_tide_heights, mcp__signalk__depth_state | — | ✗ | 4.82 |
| explain-alarm | delegated | Agent | — | ✗ | 2.51 |
