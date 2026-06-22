# Fresh Hermes vs Poseidon — Bake-off Results

**Date:** 2026-06-22
**Spec:** `docs/superpowers/specs/2026-06-22-hermes-bare-vs-poseidon-bakeoff-design.md`
**Plan:** `docs/superpowers/plans/2026-06-22-hermes-bare-vs-poseidon-bakeoff.md`

## TL;DR

Comparing a fresh, minimal **Hermes Agent v0.17.0** (Blank-Slate baseline + the boat MCP stack) against **Poseidon (`main`)**, model held equal at `claude-sonnet-4-6`, over the 13-ask bench golden set:

| | Correctness | Latency p50 | Latency p95 | Install |
|---|---|---|---|---|
| **Poseidon (main)** | **0.38** (5/13) — range 0.31–0.46 over 3 runs | 9.7 s | 20.2 s | — |
| **Hermes (Blank Slate + MCP)** | **0.69** (9/13) | 15.9 s | 38.6 s | 98 MB venv |

**Headline:** a minimal out-of-the-box Hermes routes tools *more accurately* than Poseidon right now (0.69 vs 0.38), but is ~2× slower per ask.

**This is not "keep Hermes."** The gap is mostly **Poseidon regressing**, not Hermes excelling: Poseidon's capability router (recently merged to `main`) fails to call the right tool — or any tool — on 6/13 boat intents. The same code runs the live daemon. So:

1. **Decommissioning Hermes remains the right call** — it offers no operational advantage (2× slower, heavier daemon story, the "win" is Poseidon being temporarily broken, not Hermes being better).
2. **Higher priority than the bake-off:** Poseidon's tool routing has regressed on currents/tide/anchorage intents. **Fix before trusting the live assistant.** The golden set is the regression detector.

## What was compared

- **Hermes:** fresh clone of `NousResearch/hermes-agent` @ v0.17.0, installed lean (`pip install -e '.[anthropic,mcp]'`, no `postinstall` → no node/browser/ffmpeg). Configured via the **Blank Slate** preset (everything off: compression, checkpoints, smart routing, memory capture; toolsets = file+terminal only), then opted in to *only* `claude-sonnet-4-6` + the boat MCP servers. Fully sandboxed (`HERMES_HOME=~/.hermes-fresh`, own venv); the live `~/.hermes` was never touched (mtimes verified unchanged across the run).
- **Poseidon:** `main` as shipped, via `python -m poseidon.bench --backend sdk` (production `crew_options()` — real system prompt, tool subsets, routing).
- **Harness:** the existing `poseidon.bench` golden set + `scoring.py` for both. Poseidon runs natively; Hermes runs through a new adapter (`poseidon/bench/hermes_runner.py`) that drives `hermes -z` per ask and normalizes Hermes's `mcp_<server>_<tool>` names into the scorer's `mcp__<server>__<tool>` namespace.

### Fairness controls & deviations
- **Model held equal** (`claude-sonnet-4-6`) — this measures the *agent framework*, not the model.
- **"Bare install" reframed:** there is no Hermes bare-install *mode*; the user-recalled feature is the **Blank Slate** setup preset (runtime config), which is what we used. The lean pip install is a separate footprint axis.
- **signalk URL asymmetry (decision A(a)):** Hermes points at `192.168.68.60`; Poseidon uses `naturalaspi.local` (same host). Python async `httpx` can't resolve mDNS `.local` on macOS, so signalk-mcp times out for a cold process — Poseidon tolerates it slowly (signalk asks ~10–24 s), Hermes on the IP is fast. **This *helps* Poseidon's latency**, so the "Hermes is 2× slower" finding is conservative.
- **Server set:** Hermes got 8/9 of Poseidon's MCP servers; the `memory`/mnemosyne (localhost-ollama) server was omitted — irrelevant to the golden asks.

## Per-ask head-to-head

```
ask                Poseidon   Hermes    note
depth                 PASS      PASS
battery               PASS      PASS
alarms                PASS      PASS
black-water-tank      fail      PASS     Poseidon called list_paths; Hermes read_sensor (right)
wind-forecast         fail      PASS     Poseidon called signalk read_sensor; Hermes weather (right)
current-boundary      PASS      PASS
currents-nearby       fail      PASS     Poseidon called signalk read_sensor; Hermes currents_near (right)
tide-heights          fail      PASS     Poseidon called NO tool; Hermes get_tide_heights (right)
anchorage-near        fail      fail     both miss: Poseidon no tool; Hermes routed to club-moorage
safe-to-anchor        fail      fail     both miss; Hermes burned ~35 s on club-moorage tools
where-to-anchor       fail      fail     both miss; Hermes burned ~44 s on club-moorage tools
can-we-beach          fail      PASS     Poseidon called NO tool; Hermes signalk+currents (right)
explain-alarm         PASS      fail     golden expects no-tool 'Agent' reasoning; Hermes called signalk
```

### Analysis
- **Direct sensor/data asks** (depth, battery, alarms, currents, tides, tank): Hermes reliably picks the correct MCP tool. Poseidon's router frequently substitutes a generic `signalk__read_sensor`/`list_paths`, or calls **no tool at all** (tide-heights, can-we-beach bail in ~2–5 s with `obs=[]`).
- **Anchorage asks** (`assess_anchorage` / `find_anchorages_near`): **both fail.** Poseidon doesn't call a tool; Hermes *over-works* — it routes to **club-moorage** instead of **pilotbook** and spends 18–44 s doing it. Worth checking pilotbook's tool descriptions vs club-moorage's (the intent is genuinely ambiguous to both agents).
- **explain-alarm:** the golden set expects pure-reasoning/`Agent` delegation (no tool). Poseidon delegates (passes); Hermes calls signalk tools instead (scored fail, though arguably reasonable behavior — a golden-set quirk).
- **Latency:** Hermes is ~2× slower (p50 15.9 s vs 9.7 s; p95 38.6 s vs 20.2 s) *despite* its signalk speed advantage. The slow anchorage asks (35–44 s of mis-routed tool calls) inflate its p95. Hermes's agent loop simply makes more calls / larger reasoning per ask.

## The Poseidon routing regression (most actionable finding)

The golden set's expected tools all exist in the current MCP servers (verified), and signalk is reachable — so the 6 Poseidon misses are a **routing regression**, not a stale instrument or infra. Pattern: currents/tide/anchorage/beach intents either get `obs=[]` (no tool, ~2–5 s bail) or a generic `signalk__read_sensor` substitution; `wind-forecast` once mis-routed to `mnemosyne_recall`. This lines up with the capability-routing work merged into `main`. **The live daemon runs this code**, so real users would hit the same walls on those intents. Recommend treating the golden set as a routing-regression gate and fixing before relying on the assistant.

## Threats to validity
- **Single Hermes run vs a 3-run Poseidon band** (0.31–0.46). LLM nondeterminism is real, but the Hermes wins are *structural and explainable* (it calls `currents_near`/`get_tide_heights`/`weather` where Poseidon calls the wrong tool or none) rather than noise. Repeat runs (`--repeat`) would tighten the numbers — a follow-up.
- Blank-Slate Hermes lacks Poseidon's memory/smart-routing; in this test those features appear to **hurt** Poseidon (mis-selection), not help.
- The `--offpath` over-answering check didn't run (`--offpath` is unrecognized in current `main`); moot here since the failure mode is *under*-calling, not over-answering.

## Footprint & operability
- Hermes lean venv **98 MB** vs the live install's **313 MB** — Blank Slate + minimal extras is genuinely lean.
- Operability: Poseidon already runs as a launchd daemon wired into the MQTT/briefing pipeline; standing Hermes up to parity would mean its gateway + re-plumbing. No operational reason to switch.

## Recommendation
1. **Proceed with the Hermes decommission.** No correctness/latency/operability advantage that survives fixing Poseidon.
2. **Fix Poseidon's tool routing** (currents/tide/anchorage intents calling wrong/no tool) — higher impact than this bake-off; the live assistant shares it.
3. **Investigate the anchorage intent** (pilotbook `assess_anchorage` vs club-moorage) — both agents mis-route it.
4. File the **signalk-mcp `.local` async-DNS bug** (5 s `httpx` timeout vs mDNS resolution delay; resolve-to-IP at startup or raise the timeout).

## Reproduce
```bash
# Poseidon baseline:
uv run python -m poseidon.bench --backend sdk --model claude-sonnet-4-6
# Hermes (sandbox must be configured — see plan Tasks 1–3):
uv run python -m poseidon.bench.hermes_runner
# Scorecards land in dev/bench-results/
```
