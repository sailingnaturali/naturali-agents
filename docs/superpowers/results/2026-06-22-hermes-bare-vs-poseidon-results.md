# Fresh Hermes vs Poseidon — Bake-off Results

**Date:** 2026-06-22
**Spec:** `docs/superpowers/specs/2026-06-22-hermes-bare-vs-poseidon-bakeoff-design.md`
**Plan:** `docs/superpowers/plans/2026-06-22-hermes-bare-vs-poseidon-bakeoff.md`

> **Correction (this revision):** an earlier draft blamed a Poseidon "capability-routing
> regression" for its low score. That was **wrong.** Root-cause debugging traced every
> position-dependent failure to a `signalk-mcp` connectivity bug (async `httpx` could not
> resolve the `naturalaspi.local` mDNS host on macOS — ConnectTimeout at 5 s on every call).
> Fixing it took Poseidon from **0.38 → 0.85** with no change to its prompt or routing. The
> sections below reflect the corrected understanding.

## TL;DR

Minimal **Hermes Agent v0.17.0** (Blank-Slate baseline + boat MCP stack) vs **Poseidon (`main`)**, model held equal at `claude-sonnet-4-6`, over the 13-ask bench golden set:

| | Correctness | Latency p50 | Latency p95 | Install |
|---|---|---|---|---|
| **Poseidon (post-fix)** | **0.85 (11/13)** | 12.0 s | 20.5 s | — |
| **Hermes (Blank Slate + MCP)** | 0.69 (9/13) | 15.9 s | 38.6 s | 98 MB venv |
| Poseidon (pre-fix, broken `.local`) | 0.38 (5/13) | 9.7 s | 20.2 s | — |

**Headline:** once the `signalk-mcp` `.local` bug is fixed, **Poseidon wins on both correctness (0.85 vs 0.69) and latency (12.0 s vs 15.9 s p50).** Decommissioning Hermes is the right call — and the bake-off paid for itself by surfacing a real production bug.

## What was compared

- **Hermes:** fresh clone of `NousResearch/hermes-agent` @ v0.17.0, installed lean (`pip install -e '.[anthropic,mcp]'`, no `postinstall` → no node/browser/ffmpeg). Configured via the **Blank Slate** preset (everything off: compression, checkpoints, smart routing, memory capture; toolsets = file+terminal only), then opted in to *only* `claude-sonnet-4-6` + the boat MCP servers. Fully sandboxed (`HERMES_HOME=~/.hermes-fresh`, own venv); the live `~/.hermes` was never touched (mtimes verified unchanged).
- **Poseidon:** `main` as shipped, via `python -m poseidon.bench --backend sdk` (production `crew_options()` — real system prompt, tool subsets, routing).
- **Harness:** the existing `poseidon.bench` golden set + `scoring.py` for both. Poseidon runs natively; Hermes runs through a new adapter (`poseidon/bench/hermes_runner.py`) that drives `hermes -z` per ask and normalizes Hermes's `mcp_<server>_<tool>` names into the scorer's `mcp__<server>__<tool>` namespace.

### Fairness controls & deviations
- **Model held equal** (`claude-sonnet-4-6`) — measures the *agent framework*, not the model.
- **"Bare install" reframed:** there's no Hermes bare-install *mode*; the recalled feature is the **Blank Slate** setup preset (runtime config), which is what we used. The lean pip install is a separate footprint axis.
- **signalk endpoint:** Hermes pointed at `192.168.68.60`; Poseidon at `naturalaspi.local` (same host). Pre-fix this was a confound (see below); post-fix both effectively reach the same IP, so the rematch is fair.
- **Server set:** Hermes got 8/9 of Poseidon's MCP servers; `memory`/mnemosyne (localhost-ollama) was omitted — irrelevant to the golden asks.

## Root cause: the `signalk-mcp` `.local` ConnectTimeout

The bench scores **tool selection, not tool success** (`expected_tools ⊆ observed_tools`). That masked the real failure:

- Every failing navigator ask needs the **vessel position first** — the model correctly calls `read_sensor("navigation.position")`, then `currents_near` / `get_tide_heights` / `assess_anchorage` / forecast.
- That position read **ConnectTimeout'd at 5 s** on `naturalaspi.local`. Direct proof (same client, same paths):

  ```
  http://naturalaspi.local:3000   navigation.position   FAIL 5.00s ConnectTimeout (×3)
  http://192.168.68.60:3000       navigation.position   OK   0.00s
  ```

- httpx's async connect offers an IPv6 candidate first; Happy-Eyeballs waits out the full timeout before IPv4 fallback. The system resolver (sync `getaddrinfo`) handles mDNS fine — httpx's async path doesn't.
- Seeing the position read fail, the model concludes *"GPS not responding"* and **aborts before calling the target tool** → the expected tool never appears → scored "fail." Direct/no-position asks (depth, battery, alarms) still "passed" because the model *called* the right tool — even though that call also timed out and was slow (~17 s of retries).
- Hermes only looked more accurate because it ran on the **IP**, so its position reads succeeded. The correctness gap was largely a measurement artifact of the `.local` bug, **not** Hermes routing better.

### The fix
`signalk-mcp` `SignalKClient` now resolves a `.local` host to its IPv4 via the system resolver at construction and connects to the IP (commit `409c596`, TDD; non-`.local` hosts and resolution failures unchanged). Result: position reads succeed in ~10 ms, and Poseidon's score went **0.38 → 0.85** with signalk asks dropping from ~17 s to ~4 s.

### Production impact
Poseidon's daemon runs on **this Mac Studio** against `naturalaspi.local`. Pre-fix, the live assistant would have **failed every position-dependent query** (currents, tides, anchorages, forecasts) — worth confirming the daily briefing wasn't silently degraded. The fix lands the moment the daemon respawns the (locally-sourced) `signalk-mcp`.

## Per-ask head-to-head (post-fix)

```
ask                Poseidon   Hermes    note
depth                 PASS      PASS
battery               PASS      PASS
alarms                PASS      PASS
black-water-tank      PASS      PASS
wind-forecast         PASS      PASS
current-boundary      PASS      PASS
currents-nearby       PASS      PASS
tide-heights          PASS      PASS
anchorage-near        PASS      fail     Hermes routes to club-moorage, not pilotbook
safe-to-anchor        PASS      fail     Hermes burns ~35s on club-moorage tools
where-to-anchor       fail      fail     borderline: model sometimes skips assess_anchorage
can-we-beach          fail      PASS     unusual intent (beaching → tide+depth)
explain-alarm         PASS      fail     golden expects no-tool 'Agent' delegation; Hermes calls signalk
```

Poseidon's 2 remaining misses are genuine tool-selection nuances (borderline/nondeterministic — `safe-to-anchor` uses the same `assess_anchorage` tool and passes), not systemic. Hermes's misses cluster on the anchorage intent (it prefers `club-moorage` over `pilotbook`) and the no-tool `explain-alarm`.

## Latency
Post-fix Poseidon is faster (p50 12.0 s vs 15.9 s; p95 20.5 s vs 38.6 s). Hermes's agent loop makes more calls per ask and its p95 is dragged up by 35–44 s spent mis-routing the anchorage asks.

## Footprint & operability
- Hermes lean venv **98 MB** vs the live install's **313 MB** — Blank Slate + minimal extras is genuinely lean.
- Poseidon already runs as a launchd daemon wired into the MQTT/briefing pipeline; standing Hermes up to parity means its gateway + re-plumbing. No operational reason to switch.

## Threats to validity
- Scorecards are single runs (Poseidon pre-fix varied 0.31–0.46). The post-fix jump is large and structural — every position-gated ask deterministically flipped to calling the right tool — not noise. Repeat runs would tighten the 2 borderline asks; a follow-up.
- `--offpath` over-answering check didn't run (`--offpath` unrecognized in current `main`); moot — the failure mode was under-calling.

## Recommendation
1. **Proceed with the Hermes decommission** — post-fix Poseidon wins on correctness and latency, and Hermes has no operability advantage.
2. **`signalk-mcp` `.local` fix — done** (commit `409c596`); confirm the live daemon picks it up and that the daily briefing wasn't degraded pre-fix.
3. **Poseidon `where-to-anchor` / `can-we-beach`** — minor routing tune (assess_anchorage trigger; beach→tide+depth mapping).
4. **Hermes anchorage routing** (pilotbook vs club-moorage) is moot once Hermes is retired; noted only as a data point.

## Reproduce
```bash
uv run python -m poseidon.bench --backend sdk --model claude-sonnet-4-6   # Poseidon
uv run python -m poseidon.bench.hermes_runner                             # Hermes (sandbox per plan Tasks 1–3)
# scorecards in dev/bench-results/
```
