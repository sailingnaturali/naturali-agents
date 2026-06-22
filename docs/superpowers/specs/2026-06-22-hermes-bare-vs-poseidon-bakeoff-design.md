# Fresh Bare Hermes vs Poseidon — Bake-off

**Date:** 2026-06-22
**Status:** Approved, pre-implementation
**Context:** Hermes is scheduled for decommission (~2026-06-23). Before removing it,
run a controlled comparison between a *fresh, bare* install of the latest upstream
Hermes Agent and our current Poseidon stack, to confirm we're not throwing away a
better tool. The live Hermes install is v0.16.0, 1812 commits behind upstream; the
recently-added "bare install" mode skips heavy non-Python deps (node/browser/ffmpeg).

## Goal

A results doc — table + transcripts + recommendation — answering: *is fresh bare
Hermes meaningfully better than Poseidon for the boat-assistant role?* The expected
default is "no, proceed with decommission," but the comparison must be fair enough
to overturn that if warranted.

## Hard constraint: zero contact with the live system

The live `~/.hermes/` is load-bearing until decommission — it holds Poseidon's live
`.env`, `state.db`, sessions, SOUL.md, and the running `ai.hermes.gateway` +
`com.naturali.poseidon` launchd jobs depend on it. The bake-off must not read or
write it.

- Source clone: `~/src/hermes-fresh/hermes-agent` (latest `NousResearch/hermes-agent`).
- State home: `HERMES_HOME=~/.hermes-fresh`, exported on **every** invocation.
- Invoke the **fresh venv binary directly** — never the live `hermes` wrapper
  (`~/.local/bin/hermes` hardcodes the live venv path).
- **No launchd job** for the fresh install. The live gateway/Poseidon stay running,
  untouched.

## Bare install

1. Clone latest upstream into `~/src/hermes-fresh/hermes-agent`.
2. Verify the exact "bare" flag against the fresh installer's `--help` /
   `setup-hermes.sh` (the local v0.16.0 copy has no bare flag — the feature is in
   the newer code we'll pull; likely a toolset-distribution selection per
   `toolset_distributions.py`).
3. Create a Python 3.11 venv, install the minimal/bare distribution, **skip
   `hermes postinstall`** (that step bootstraps node/browser/ffmpeg).
4. Record install footprint vs the live venv (313M baseline).

## Minimal config (the reconciliation)

A zero-config Hermes cannot answer boat questions or call tools, so answer-quality
and tool-calling would be untestable. Keep the install bare, but inject exactly two
things — **not** a full config/state clone:

- `ANTHROPIC_API_KEY` + model `claude-sonnet-4-6` (matching Poseidon, so we compare
  the *agent*, not the model).
- The same 5 stdio MCP servers (signalk, currents, pilotbook, logbook, club-moorage),
  pointed at the mock vessel `naturalaspi.local:3000`.

This is the leanest config that keeps the comparison fair.

## Prompt suite (against the mock vessel)

Identical prompts to both agents:

1. Currents at Boundary Pass this evening + slack window.
2. Protected anchorage near here for tonight's forecast.
3. Battery state of charge + depth right now.
4. Explain the active alarms.
5. A daily-briefing-style composition.

## Scoring dimensions

| Dimension | What we measure |
|---|---|
| Answer quality | Correctness against the known mock state; voice-readiness of spoken output (per voice conventions — units spelled out, no raw MMSI/coords). |
| Tool-calling reliability | Right MCP reached, tools chained, no hallucinated readings or wrong-tool calls. |
| Latency | Time-to-answer per prompt. |
| Footprint / operability | Install size, dep count; config friction; how each would run as a daemon. |

## Driving Poseidon

To feed Poseidon the same ad-hoc prompts, resolve the cleanest path during
execution — direct naturali-agents agent entry vs an MQTT intent — and **confirm
the chosen path before running the Poseidon side**, so we don't perturb the live
daemon unexpectedly.

## Deliverable

Results doc (table + transcripts + recommendation) committed alongside this spec.

## Cleanup

Sandbox is `~/.hermes-fresh` + `~/src/hermes-fresh`. Both are `rm -rf`-able with
zero residue once the bake-off is recorded.

## Out of scope

- Modifying or upgrading the live Hermes install.
- Any launchd / gateway / MQTT change to the running system.
- Comparing models (both use `claude-sonnet-4-6`).
