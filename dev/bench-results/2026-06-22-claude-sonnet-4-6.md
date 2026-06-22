### Benchmark run 2026-06-22 — claude-sonnet-4-6

- Asks: 13 | correctness: 46.2% | error rate: 0.0%
- Warm-hop latency: p50 8.89s | p95 19.21s

| ask | category | expected | observed | match | dt_total (s) |
|-----|----------|----------|----------|-------|--------------|
| depth | engineer-direct | mcp__signalk__depth_state | mcp__signalk__depth_state, mcp__signalk__read_sensor | ✓ | 19.06 |
| battery | engineer-direct | mcp__signalk__battery_state | mcp__signalk__battery_state | ✓ | 9.18 |
| alarms | engineer-direct | mcp__signalk__get_active_alarms | mcp__signalk__get_active_alarms | ✓ | 8.89 |
| black-water-tank | engineer-direct | mcp__signalk__read_sensor | mcp__signalk__read_sensor | ✓ | 19.14 |
| wind-forecast | navigator | mcp__weather__get_marine_forecast | mcp__memory__mnemosyne_recall | ✗ | 10.70 |
| current-boundary | navigator | mcp__currents__get_gate_current | mcp__currents__get_gate_current | ✓ | 13.50 |
| currents-nearby | navigator | mcp__currents__currents_near | — | ✗ | 2.99 |
| tide-heights | navigator | mcp__currents__get_tide_heights | — | ✗ | 1.96 |
| anchorage-near | navigator | mcp__pilotbook__find_anchorages_near | — | ✗ | 1.60 |
| safe-to-anchor | navigator-multi | mcp__pilotbook__assess_anchorage | — | ✗ | 2.24 |
| where-to-anchor | navigator-multi | mcp__pilotbook__assess_anchorage | — | ✗ | 1.67 |
| can-we-beach | navigator-multi | mcp__currents__get_tide_heights, mcp__signalk__depth_state | — | ✗ | 2.25 |
| explain-alarm | delegated | Agent | Agent, mcp__signalk__battery_state | ✓ | 19.31 |
