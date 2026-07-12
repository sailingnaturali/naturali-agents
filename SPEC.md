# SPEC

Operational contract for the Naturali agent stack. Code in this repo MUST match this spec; mismatches are bugs.

Persona and voice live in [SOUL.md](SOUL.md); per-agent responsibilities live in `prompts/*.md`. This file is interface-only.

## Components

```
Home Assistant (Pi 5)        Mac Studio                      data sources
  voice intent  ──MQTT──▶  poseidon/daemon.py  ─────────▶  Claude Agent SDK
                            (com.naturali.poseidon)              │
  daily cron    ────────▶  scripts/briefing.py ─────────────────┤
                                                                  ▼
                                                        MCP servers:
                                                          signalk-mcp   ──▶ SignalK
                                                          logbook-mcp   ──▶ signalk-logbook (Pi)
                                                              │
  Piper TTS    ◀──MQTT──   poseidon/daemon.py  ◀──────────────┘
```

## MQTT contract

Broker: Mosquitto on `naturalaspi.local:1883` by default. Authenticated brokers supported via `MQTT_USER` / `MQTT_PASSWORD`.

### Topics

| Topic                              | Direction | Producer            | Consumer             |
|------------------------------------|-----------|---------------------|----------------------|
| `naturali/intents/ask`             | HA → Mac  | HA voice automation | `poseidon/daemon.py` |
| `naturali/intents/mark_moment`     | HA → Mac  | HA voice automation | `poseidon/daemon.py` |
| `naturali/agents/{agent}/say`      | Mac → HA  | `poseidon/daemon.py` | HA Piper TTS        |

`{agent}` is one of `navigator`, `engineer`, `logbook`. Phase 0 ships `navigator` only.

### Payload schemas

**Intent (HA → Mac), all `naturali/intents/*` topics:**
```json
{ "text": "string — utterance or argument" }
```
A non-JSON payload is treated as `{"text": <raw decoded payload>}`. Missing or empty `text` is allowed only for `mark_moment`.

**Say (Mac → HA), `naturali/agents/{agent}/say`:**
```json
{ "agent": "navigator", "text": "string — already TTS-ready" }
```
`text` MUST NOT contain Hermes operational lines (session_id, tool-call markers, config suggestions). The daemon strips markdown and normalizes units for speech via `poseidon/daemon.py:_strip_markdown()` and `_normalize_speech()`.

QoS 0, no retain.

## Environment variables

Poseidon daemon reads these. Defaults match the Phase 0 deployment.

| Var               | Default                       | Used by                 | Meaning                                                  |
|-------------------|-------------------------------|-------------------------|----------------------------------------------------------|
| `MQTT_BROKER`     | `naturalaspi.local`      | `poseidon/daemon.py`   | Mosquitto host                                           |
| `MQTT_PORT`       | `1883`                        | `poseidon/daemon.py`   | Mosquitto port                                           |
| `MQTT_USER`       | unset                         | `poseidon/daemon.py`   | optional broker auth username                            |
| `MQTT_PASSWORD`   | unset                         | `poseidon/daemon.py`   | optional broker auth password                            |
| `AGENT_NAME`      | `navigator`                   | `poseidon/daemon.py`   | short name; used in topic path and `say` payload         |

## Tool surface — signalk-mcp

Source: <https://github.com/sailingnaturali/signalk-mcp>.

Every read tool returns `{ value, display, timestamp }` where:
- `value` is raw SI (per SignalK spec): m/s, radians, K, Pa, ratio, m.
- `display` is the human-readable pre-converted string with units. Agents MUST report `display`; never re-convert from `value`.
- `timestamp` is ISO-8601 UTC.

`display` unit conventions (signalk-mcp is the source of truth for these strings):

| Reading           | Example                        | Notes                                                     |
|-------------------|--------------------------------|-----------------------------------------------------------|
| wind speed        | `"16.5 knots"`                 |                                                           |
| wind angle        | `"315.0° (North-West wind)"`   | Absolute compass bearing. See "wind angle" below.         |
| heading / COG     | `"135.0° (South-East)"`        | True. Magnetic variant suffixed `M` when reporting magnetic. |
| depth             | `"38.0 m"`                     |                                                           |
| pressure          | `"1010.0 hPa"`                 |                                                           |
| temperature       | `"13.0°C"`                     |                                                           |
| humidity          | `"78%"`                        |                                                           |
| position          | (no `display`; use `value`)    | `{latitude, longitude}` decimal degrees.                  |
| local time        | `"11:54 PDT"`                  | From `get_local_time`; timezone derived from GPS.         |

**Wind angle.** SignalK's `environment.wind.angleTrueWater` is *relative to bow* in radians. signalk-mcp normalizes this to an absolute compass bearing (degrees true) using current `headingTrue` before formatting `display`. The mock SignalK server in `dev/mock-signalk.py` already pre-encodes its wind angle in absolute terms to match this contract — when integrating against a real SignalK server, the conversion MUST happen in signalk-mcp.

### Read tools

- `mcp_signalk_read_sensor(path: str)` — read any SignalK path. Returns `{ value, display, timestamp }`.
- `mcp_signalk_get_route()` — returns the active planned route: `{ name, waypoints: [{lat, lon, name?}, ...] }` plus `startTime` (UTC ISO-8601).
- `mcp_signalk_battery_state(bank: str = "house")` — returns `{ stateOfCharge: 0..1, voltage: V, current: A, display }`. Negative current is discharge.
- `mcp_signalk_get_local_time()` — current time at vessel position. Returns `{ value: ISO-8601 with offset, display: "HH:MM TZ" }`.

### Paths used by Phase 0

```
navigation.position
navigation.speedOverGround
navigation.courseOverGroundTrue
navigation.headingTrue
navigation.speedThroughWater
navigation.magneticVariation
environment.wind.speedTrue
environment.wind.angleTrueWater
environment.wind.speedApparent
environment.depth.belowKeel
environment.outside.pressure
environment.outside.temperature
environment.outside.humidity
```

## Tool surface — logbook-mcp

Source: <https://github.com/sailingnaturali/logbook-mcp>.

- `mcp_logbook_mark_moment(text: str, position?: {latitude, longitude})` — append an entry via signalk-logbook on the Pi; the plugin snapshots position/speed/wind/barometer from live SignalK. Returns `{ id, entry_display, timestamp, time_display, position, position_display }`. `time_display` is vessel-local; stored timestamps are UTC. `position` only overrides the GPS fix.
- `mcp_logbook_read_entries(date?: YYYY-MM-DD)` — a day's entries (default today, vessel-local). Returns `{ date, count, entries[] }`.

## Time

- **Stored data** (logbook entries, mock timestamps, route `startTime`) is UTC ISO-8601.
- **Spoken / displayed conversational time** is local to the vessel's current GPS position, via `mcp_signalk_get_local_time()`.

This split is intentional and not a contradiction.

## Persona composition

Poseidon loads each agent with two prompt sources concatenated, SOUL first:

```
<SOUL.md>

<prompts/{agent}.md>
```

SOUL is identity and style. The per-agent prompt adds responsibilities, available tools, and domain context. If they conflict, the per-agent prompt wins for operational rules; SOUL wins for voice.

## Phases

| Phase | Agent(s)              | New surface                                                         |
|-------|-----------------------|---------------------------------------------------------------------|
| 0     | Navigator             | signalk-mcp read paths above; MQTT bridges; Piper TTS               |
| 0.5   | + Engineer + Logbook  | logbook-mcp full surface; engineer anomaly detection; vessel RAG    |
| 1     | escalation to Claude  | Mac Studio decides locally; out-of-depth queries route to Claude    |

## Non-goals

- Real-time SignalK WebSocket delta subscription (mock and bridges are request/response).
- Multi-vessel deployments.
- Persistence of conversation history across Hermes invocations.
