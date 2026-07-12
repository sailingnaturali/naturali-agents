# naturali-agents

Hermes agent configs, prompts, and tooling for the Naturali boat agent system.

Part of the [Naturali](https://sailingnaturali.com) open-source boat agent stack.

## Agents

| Agent | Status | Role |
|-------|--------|------|
| Navigator | Phase 0 | Routing, weather, tides, anchorages, battery-aware passage planning |
| Engineer | Phase 0.5 | Vessel systems, anomaly detection, vessel knowledge RAG |
| Logbook | Phase 0.5 | Sea-day capture, end-of-day summaries, USCG/TC form export |

Phase 0 ships **Navigator only** — a single skill loaded with the marine MCP
servers below. The skill answers ad-hoc questions via the Poseidon daemon and
generates a scheduled daily briefing.

## What's here

```
SOUL.md                       ← shared persona, loaded first for every agent
poseidon/                     ← Poseidon daemon (Claude Agent SDK) — owns all MQTT lanes
skills/navigator/             ← Navigator skill, built from parts
  ├── frontmatter.yaml         ← skill metadata
  ├── body.md                  ← responsibilities + tool surface
  └── briefing.md              ← daily-briefing instructions
prompts/navigator.md          ← committed mirror of body.md (regenerated, never hand-edited)
scripts/
  ├── briefing.py              ← daily briefing generator (tides → Navigator → HA/TTS/logbook)
  ├── deploy-navigator.sh      ← assemble SKILL.md from skills/navigator/ + deploy to Hermes
  └── git-hooks/               ← pre-commit hook that keeps the deployed skill in sync
dev/
  ├── mock-signalk.py          ← mock SignalK REST server for local dev
  └── nmea-stream.py           ← NMEA 0183 TCP stream for a real SignalK instance
tests/                        ← pytest suite (briefing logic, respx-mocked HTTP)
```

The runtime `SKILL.md` is machine-local and not committed. `skills/navigator/` is the
single source of truth; `scripts/deploy-navigator.sh` assembles it
(`frontmatter.yaml` + `body.md` + `briefing.md`) into the Hermes skills tree and
regenerates the committed `prompts/navigator.md` mirror so the documented prompt can
never drift from what runs.

## Architecture

```
Home Assistant (Pi 5)        Mac Studio                      data sources
  voice intent  ──MQTT──▶  poseidon/daemon.py  ─────────▶  Claude Agent SDK
                            (com.naturali.poseidon)              │
  daily cron    ────────▶  scripts/briefing.py ─────────────────┤
                                                                  ▼
                                                        MCP servers:
                                                          signalk-mcp   ──▶ SignalK
                                                          logbook-mcp   ──▶ signalk-logbook (Pi)
                                                          currents-mcp  ──▶ CHS + NOAA
                                                          weather-mcp   ──▶ Open-Meteo / NDBC / Stormglass
                                                          pilotbook-mcp ──▶ anchorage vault
                                                              │
  Piper TTS    ◀──MQTT──   poseidon/daemon.py  ◀──────────────┘
```

Poseidon (`com.naturali.poseidon`, launchd on Mac Studio) owns all MQTT lanes since
2026-06-11. The retired `mqtt-bridge` service (`com.naturali.mqtt-bridge`) has been
removed.

Full interface contract — MQTT topics/payloads, env vars, MCP tool surface, persona
composition — in [SPEC.md](SPEC.md).

## Daily briefing

`scripts/briefing.py` generates the morning briefing. It fetches the nearest CHS tide
station for the vessel's position, hands a formatted data block to the Navigator skill
via `hermes` (which calls weather-mcp itself for wind/swell/buoys and SignalK for live
vessel state), then routes the synthesized briefing to three places: Home Assistant
Lovelace (REST), Nabu/Piper voice (MQTT), and the logbook (SQLite).

Run it from the CLI with [`uv`](https://docs.astral.sh/uv/) — the script declares its own
dependencies inline (PEP 723), so no separate install is needed:

```bash
# Full run: fetch tides, invoke Navigator, publish to HA + TTS + logbook
uv run scripts/briefing.py

# Dry run: fetch data and print the prompt that would go to the Navigator,
# without invoking hermes or publishing anything
uv run scripts/briefing.py --dry-run
```

Configuration is read from `~/.hermes/.env` (or the process environment) — `SIGNALK_URL`,
`HA_URL` / `HOMEASSISTANT_TOKEN`, `MQTT_BROKER` / `MQTT_PORT` / `MQTT_USER` / `MQTT_PASSWORD`,
and `BRIEFING_DB_PATH`. See [`.env.example`](.env.example). Each publish step degrades
independently: a failed HA post or MQTT publish is logged and the run continues.

On the Mac Studio the full run is wired to a daily launchd/cron schedule; `--dry-run` is
the right way to iterate on prompt and data shaping locally.

## Development

Local development needs no boat. Start the mock SignalK server, then talk to the skill:

```bash
python dev/mock-signalk.py            # serves Boundary Pass scenario on :8765
export SIGNALK_URL=http://localhost:8765
# poseidon (see Poseidon runtime) — Poseidon is the ask/alarm agent
```

Edit the Navigator skill in `skills/navigator/`, then deploy it to the Hermes runtime:

```bash
scripts/deploy-navigator.sh           # rebuild SKILL.md + regenerate prompts/navigator.md
```

Install the git hooks once per clone so commits that touch the skill auto-rebuild and
keep `prompts/navigator.md` in sync:

```bash
scripts/git-hooks/install.sh
```

Run the test suite:

```bash
uv run pytest
```

## Related repos

- [`signalk-mcp`](https://github.com/sailingnaturali/signalk-mcp) — live marine data from SignalK
- [`logbook-mcp`](https://github.com/sailingnaturali/logbook-mcp) — sea-day logging and marked moments
- [`currents-mcp`](https://github.com/sailingnaturali/currents-mcp) — currents and tidal-gate slack windows, tide heights (CHS + NOAA)
- [`weather-mcp`](https://github.com/sailingnaturali/weather-mcp) — marine forecast, NDBC buoys, Stormglass premium
- [`pilotbook-mcp`](https://github.com/sailingnaturali/pilotbook-mcp) — pilot-book anchorages and overnight-comfort ranking
- [`infrastructure`](https://github.com/sailingnaturali/infrastructure) — private; Pi 5 + network configs

## License

MIT.
