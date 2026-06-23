# Alert Category Mute ("acknowledge completely") — Design

**Date:** 2026-06-22
**Status:** Approved (design); implementation pending
**Component:** `naturali-agents` (Poseidon), with coupled HA dashboard config in `infrastructure`

## Problem

Some alert categories are perpetually active by geography, not by exception.
The Southern Resident Killer Whale (SRKW) 400 m approach-prohibition zones
(raised by the ProtectedSeas restricted-areas plugin as
`navigation.restrictedArea.<uuid>`) cover practically all navigable water in
the Salish Sea. The plugin clears and re-raises the `warn` notification on each
re-evaluation, so every cycle is a genuinely new edge with a fresh timestamp —
the per-`(path, timestamp)` dedup in `AlarmLane` cannot catch it, and the puck
re-narrates the same nuisance indefinitely.

The alert chain has no notion of "the crew has seen this and it's fine — stop
narrating it." This is a missing acknowledgment/suppression layer, not a tuning
problem. (Repositioning the mock vessel out of the closure is a band-aid; the
real vessel will face the same geography.)

## Requirements (settled in brainstorming)

| Dimension | Decision |
|-----------|----------|
| **Scope** | Category-level — mute a *class* (e.g. "whale zones"), applying to every polygon present and future, keyed by notification path-prefix. Not per-instance. |
| **Lifetime** | Auto-expires at the daily/trip rollover boundary (the same boundary the crew channel already resets on). The category quietly re-arms; the crew re-acks if still irrelevant. |
| **Triggers** | Three paths, all writing the same shared state: (1) voice to the puck, (2) agent proposes → crew confirms, (3) HA dashboard toggle. |
| **Semantics** | Silence the **voice only**. The alert still reaches MQTT, SignalK, and the logbook — a silent system is not a blind one. Suppression happens at the narration layer so the record is untouched by construction. |

## Architecture (Option 1: MQTT mute registry + Poseidon-side suppression)

Chosen over (2) acknowledging at the SignalK source — which would blind any
MQTT-based dashboard, needs write tokens, and gets clobbered by the ProtectedSeas
plugin re-raising — and (3) a standalone alert-policy sidecar, which is a whole
new daemon for what is naturally Poseidon's job (it owns narration).

### Components

**1. Mute registry — MQTT retained, topic `naturali/mutes/<category>`**

One retained JSON envelope per muted category:

```json
{
  "category": "whale-zones",
  "paths": ["navigation.restrictedArea"],
  "muted_by": "voice",
  "created": "2026-06-22T20:40:00Z",
  "expires": "2026-06-23T13:00:00Z"
}
```

- `expires` is set to the next rollover boundary at creation time.
- **Un-mute** = publish an empty (zero-length) retained payload to the topic,
  which deletes the retained slot. (Same mechanism used to clear a stale
  `dsc.distress` retained message.)
- Retained ⇒ HA and Poseidon both receive current state on (re)connect, and it
  survives a restart.

**2. Category registry — static config in Poseidon**

Maps a friendly slug to the path-prefixes it covers:

```python
ALERT_CATEGORIES = {"whale-zones": ["navigation.restrictedArea"]}
```

Used to (a) resolve an incoming alert path to its category for the suppression
check, and (b) validate a mute request's category name. v1 ships exactly one
entry; adding categories later is a one-line edit.

**3. Suppression — in `AlarmLane`, narration-only**

- The daemon subscribes `naturali/mutes/#` and maintains an in-memory
  `{category: expires}` map. Retained replay on connect **seeds** this map
  (desired — mutes are durable *state*, unlike alarm events).
- The daemon injects an `is_muted(path, state) -> bool` predicate into
  `AlarmLane` (constructor dependency, default `lambda p, s: False`). This keeps
  `AlarmLane` unit-testable with a fake predicate and keeps the live mute map +
  category registry owned by the daemon.
- `AlarmLane.handle()` gains one check alongside the existing dedup/cleared
  logic: if `is_muted(path, state)` → return `None` (no voice), and log
  `suppressed by mute` + a timing record. The MQTT alert envelope and SignalK
  notification are never modified.

### Data flow

```
SET MUTE   voice tool / HA toggle / agent  ──publish retained──▶ naturali/mutes/whale-zones
                                                                        │
                                                              Poseidon updates in-memory map

ALERT      bridge ──▶ naturali/alerts/navigation.restrictedArea.<uuid> ──▶ Poseidon dispatch
                                                                        │
                                              AlarmLane: resolve path→category (whale-zones)
                                                 muted & not expired & state ≤ ceiling?
                                                     yes → return None (no voice), log suppressed
                                                     no  → narrate
                                              (MQTT + SignalK + logbook unchanged either way)

RE-ARM     at rollover_hour, Poseidon clears expired retained mute slots → next alert narrates
```

### Triggers

- **Voice:** new agent tool `set_alert_mute(category: str, action: "mute"|"unmute")`
  in the crew channel. "mute whale zones" / "unmute whale zones" / "acknowledge
  that" → publishes (or clears) the retained envelope and returns a
  ready-to-speak confirmation (e.g. "Whale-zone alerts muted until tomorrow.").
  The prompt teaches the agent to resolve "that"/"the whale alert" to the
  category slug.
- **Agent proposes:** the alarm-narration prompt offers the out inline
  (e.g. "…whale-zone closures cover most of this area — say 'mute whale zones'
  and I'll keep quiet about them today"). No separate frequency detector in v1;
  the crew then uses the voice trigger.
- **HA toggle:** an MQTT switch `switch.mute_whale_zones` bound to the mute
  topic (command publishes the envelope / empty payload; state reads the
  retained topic). Reflects current mute state; good for pre-departure setup.
  This is an `infrastructure` / ha-sync surface.

### Expiry / re-arm

- `expires` is authoritative: Poseidon treats a mute whose `expires` is in the
  past as inactive, regardless of whether the retained slot was cleared.
- At its own `rollover_hour`, Poseidon clears retained mute slots whose `expires`
  has passed (publishes empty retained), tidying the registry. Hooks into the
  existing crew-channel rollover logic — one place owns rollover.

## Safety decisions (explicitly approved)

**A. Fail toward *speaking*.** If mute state is missing, unreachable, or
malformed, do **not** suppress — narrate the alert. A bug in muting must never
silence a real alarm. This is the deliberate opposite of the retained-replay
fix's fail-direction (which stays silent on replay): there, a stuck retained
message was noise; here, an un-narrated alarm is a hazard.

**B. Severity ceiling — mutes never silence the serious stuff.** A category mute
suppresses only `warn` and `alert`. `alarm` and `emergency` on a muted path
**always narrate**. Muting "whale zones" (a `warn`) silences the nuisance, but
were anything on that path to escalate to alarm/emergency, the crew still hears
it. This prevents a blanket mute from ever hiding a mayday-class event.

## Error handling

- Malformed mute envelope (bad JSON, missing `expires`) → ignored (no mute),
  logged. (Fail-open per A.)
- Unknown category in a mute request → tool rejects with a spoken error; no
  retained write.
- Clock/expiry parse failure → treat as not muted (fail-open).

## Testing (TDD)

`AlarmLane` (fake `is_muted` predicate + fake query):
- muted category, `warn` → returns `None`, no narration query issued
- muted category, `emergency` → narrates (ceiling B)
- muted category, `alarm` → narrates (ceiling B)
- unmuted category, `warn` → narrates
- expired mute → narrates (fail toward speech / authoritative expiry)
- malformed/absent mute state → narrates (fail-open A)

Mute registry / category resolution (pure functions):
- path `navigation.restrictedArea.<uuid>` resolves to `whale-zones`
- unrelated path resolves to no category (never suppressed)
- `expires` in future → active; in past → inactive; missing → inactive

Daemon plumbing:
- a `naturali/mutes/...` message updates the in-memory map
- retained mute replay on connect seeds the map (and does **not** narrate)
- rollover clears expired retained mute slots

Agent tool:
- `set_alert_mute("whale-zones", "mute")` publishes a retained envelope with a
  rollover `expires` and returns a speakable confirmation
- `"unmute"` publishes an empty retained payload
- unknown category → spoken rejection, no publish

## Out of scope (v1 / YAGNI)

- Per-instance acknowledgment (we chose category scope).
- Categories beyond `whale-zones` (registry is extensible; ship one).
- A re-firing frequency detector for the agent-proposes path (folded into the
  narration prompt).
- Generalized/auto-generated HA switches (one hand-written switch for v1).
- Configurable per-category severity ceiling (hard-coded warn/alert in v1).

## Coupled surfaces to update with the implementation

- `naturali-agents`: `AlarmLane`, daemon mute subscription + rollover clear,
  category registry config, the `set_alert_mute` agent tool, the
  alarm-narration prompt (agent-proposes line), SOUL/tool docs.
- `infrastructure`: HA `switch.mute_whale_zones` (configuration.yaml / MQTT),
  pushed via `ha-sync.sh`; a note in pi5-signalk or agent docs.
