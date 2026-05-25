# naturali-agents

Hermes Agent configs and prompts for the Naturali boat agent system.

Part of the [Naturali](https://sailingnaturali.com) open-source boat agent stack.

## Agents

| Agent | Status | Role |
|-------|--------|------|
| Navigator | Phase 0 | Routing, weather, conditions, battery-aware passage planning |
| Engineer | Phase 0.5 | Vessel systems, anomaly detection, vessel knowledge RAG |
| Logbook | Phase 0.5 | Sea-day capture, end-of-day summaries, USCG/TC form export |

## Phase 0 scope

Navigator only. Hermes loaded with the `signalk-mcp` MCP server. Single-prompt agent, no subagents.

## Architecture

```
Hermes Agent (Mac Studio)
    ├── SOUL.md                  ← shared persona (loaded first for every agent)
    ├── prompts/navigator.md     ← per-agent responsibilities + tool surface
    ├── bridges/
    │   ├── hermes_to_mqtt.py   ← pipe Hermes responses → MQTT → HA TTS
    │   └── mqtt_to_hermes.py   ← MQTT intents (HA voice) → Hermes tool calls
    └── mcp_servers:
        ├── signalk-mcp          ← live marine data (github.com/sailingnaturali/signalk-mcp)
        ├── logbook-mcp          ← marked moments, sea logs (github.com/sailingnaturali/logbook-mcp)
        └── tide-mcp             ← tidal-gate slack windows (github.com/sailingnaturali/tide-mcp)
```

Full interface contract — MQTT topics/payloads, env vars, MCP tool surface, persona composition — in [SPEC.md](SPEC.md).

## Related repos

- [`signalk-mcp`](https://github.com/sailingnaturali/signalk-mcp) — MCP server for SignalK data
- [`logbook-mcp`](https://github.com/sailingnaturali/logbook-mcp) — MCP server for sea-day logging
- [`tide-mcp`](https://github.com/sailingnaturali/tide-mcp) — MCP server for tidal-gate slack windows (CHS + NOAA)
- [`infrastructure`](https://github.com/sailingnaturali/infrastructure) — private; Pi 5 + network configs

## License

MIT.
