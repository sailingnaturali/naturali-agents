# Bosun — Nightly Fleet-Maintenance Orchestrator

**Date:** 2026-06-12
**Status:** Approved design, pre-implementation
**Home:** `naturali-agents/bosun/`
**Host:** `studio.local` (the scheduled-job host)

## Purpose

Each night, autonomously survey every repo in the `sailingnaturali` GitHub org for
maintenance problems (broken CI, registry-publication gaps, stale cross-references,
open-issue backlog), fix the bounded/mechanical classes with real TDD changes opened
as PRs, and hand the rest to Bryan as a single consolidated morning report. Bosun
**never merges anything** — its output is PRs plus a decision queue.

The name: a bosun (boatswain) is the ship's officer responsible for maintenance of
the vessel and its equipment. This is the maintenance crew chief for the software fleet.

## Design principles

- **Two-phase, fan-out only where needed.** A cheap deterministic pass collects signals
  from all repos with zero LLM cost; LLM subagents are spawned *only* for repos that have
  an actionable problem. We do not spawn ~24 agents blindly.
- **Bounded fix scope.** Subagents write fix PRs for exactly two problem classes:
  real CI defects and stale cross-reference drift. Everything else is reported, not fixed.
- **Never auto-merge.** The worst case for an over-eager fix is a PR that sits unmerged.
  This makes the "pause and ask before merging published/boat code" requirement structural
  rather than a runtime gate: nothing merges, so there is nothing to gate.
- **Idempotent.** Stable per-problem branch names mean a re-run updates an existing PR
  instead of opening a duplicate.
- **Isolated.** Each subagent works in its own git worktree; it cannot clobber Bryan's
  working tree or another subagent's.

## Scope

### Fix + open PR (subagent acts)
- **Real CI defects** — a CI failure whose root cause is an actual code/test defect the
  subagent can confidently fix via TDD (failing test first, then fix).
- **Stale cross-reference drift** — references to renamed/retired things, seeded from a
  configurable token map (e.g. `tide-mcp` → `currents-mcp`, retired `localhost:3000`
  mac-dev rig → `naturalaspi.local:3000`). The collector greps for these; the subagent
  confirms and fixes.

### Report only (no PR)
- **Open issues** — read, categorize/label, summarize. Never fix-PR'd (unbounded; would
  burn budget and generate noise PRs on feature requests).
- **Registry-publication gaps** — latest git tag / `package.json` version not live on npm
  (and, secondarily, SignalK plugin-registry presence). Reported because the fix is usually
  a release-process action, not a code change.
- **Transient CI failures** — root cause classified as `network` / `cache` / `auth` /
  `flaky`. Reported with the diagnosis; not fixed.
- **CI defects the subagent can't confidently fix** — reported with root cause.

## Architecture

```
                 ┌─────────────────────────────────────────────────┐
   launchd       │  Phase 1: COLLECT  (deterministic, no LLM)       │
 com.naturali    │  enumerate org repos → clone/fetch cache         │
   .bosun        │  per repo: CI status, registry state,            │
  (pmset wake    │            open issues, stale-token grep         │
   ~03:00)  ───▶ │  → fleet-state.json  (repos w/ no problem dropped)│
                 └───────────────────────┬─────────────────────────┘
                                         │ flagged repos only
                 ┌───────────────────────▼─────────────────────────┐
                 │  Phase 2: TRIAGE & FIX  (LLM, concurrency-capped) │
                 │  per flagged repo:                                │
                 │    git worktree add  →  claude -p <task contract> │
                 │    systematic-debugging → classify CI failure     │
                 │    real-defect / stale-ref → TDD fix → PR         │
                 │      on stable branch  bosun/<class>-<slug>       │
                 │    writes bosun-result.json                       │
                 │  Semaphore(4), per-repo wall-clock timeout        │
                 └───────────────────────┬─────────────────────────┘
                                         │ collect all results
                 ┌───────────────────────▼─────────────────────────┐
                 │  Phase 3: CONSOLIDATE & DELIVER                   │
                 │  aggregate → Jinja → bosun.html + .md             │
                 │  scp HTML → root@192.168.68.90:/config/www/       │
                 │            bosun.html  (:8123/local/bosun.html)   │
                 └─────────────────────────────────────────────────┘
```

### Phase 1 — Collect (deterministic)
A pure-Python collector. For each org repo (via `gh repo list sailingnaturali`):
- **Clone/fetch** into a cache dir (`~/.bosun/repos/<name>`); not every repo is cloned on
  every machine, so Bosun owns its clones. Shallow fetch for speed.
- **CI status** — `gh run list --repo <r> --branch <default> --limit 1` → conclusion.
  Repos with no workflows are skipped (not actionable).
- **Registry state** — for publishable repos: `npm view <pkg> version` vs latest git tag /
  `package.json` version. Secondary: SignalK plugin-registry presence (report-only nicety).
- **Open issues** — `gh issue list` → count, titles, labels.
- **Stale-token grep** — grep each clone for the configured stale-token map; hits become
  actionable stale-reference candidates.

Output: `fleet-state.json`. Any repo with no actionable problem is dropped here and never
gets an agent.

### Phase 2 — Triage & fix (LLM, selective)
For each flagged repo, concurrency-capped (default `Semaphore(4)`):
- `git worktree add` a branch off the repo's default branch in the cache clone.
- Spawn `claude -p` as an asyncio subprocess with a **task-contract prompt** (see below) and
  a per-repo wall-clock timeout. The subagent inherits the full Claude Code toolset —
  Bash, `gh`, Edit, and the **test-driven-development** + **systematic-debugging** skills.
- The subagent:
  1. Root-causes any CI failure with systematic-debugging; classifies it.
  2. For `real-defect` and `stale-reference` only: writes a **failing test first**, then the
     fix, on stable branch `bosun/<class>-<slug>`. If that branch already has an open PR,
     it updates it rather than opening a new one.
  3. Pushes and opens a PR with a clear body (problem, root cause, fix, test).
  4. Writes `bosun-result.json` (schema below) to the worktree.
- The orchestrator parses `bosun-result.json`; on timeout/crash it records a `skip` with the
  partial signals so the repo still appears in the report.
- Worktree is removed after the result is collected.

`claude -p` itself is not unit-tested (it's the LLM); the **prompt/contract and the
result-parsing** are tested against fixture `bosun-result.json` files.

### Phase 3 — Consolidate & deliver
Aggregate every `bosun-result.json` + the Phase-1 state into one report (Jinja, mirroring
`briefing.py`). Render `bosun.html` and a markdown twin, then `scp -o BatchMode=yes` the
HTML to `root@192.168.68.90:/config/www/bosun.html` (viewable at `:8123/local/bosun.html`).
Standalone from the 06:00 vessel briefing — different audience (Bryan-the-developer, not
Bryan-the-skipper).

Report sections:
1. **Header** — run timestamp, repos scanned, repos flagged, PRs opened, items needing decision.
2. **Auto-fixed** — table of PRs opened: repo, class, PR link, **risk flag** (🔴 published-npm
   or boat-deployed — "review before merge"; ⚪ low-risk).
3. **Needs your decision** — registry gaps, transient CI failures + root cause, open-issue
   triage summary, any fix the subagent declined.
4. **Errors / skips** — repos where collection or the subagent failed (with partial signals).

## Key data contracts

**`bosun-result.json`** (written per subagent):
```json
{
  "repo": "currents-mcp",
  "signals": { "ci": "...", "registry": "...", "issues": [...], "stale_refs": [...] },
  "classifications": [{ "problem": "ci_failure", "class": "real-defect", "confidence": "high" }],
  "actions": [{ "type": "pr_opened", "url": "...", "branch": "bosun/real-defect-...",
               "class": "real-defect", "files_changed": ["..."], "risk_tier": "published" }],
  "needs_decision": [{ "kind": "registry_gap", "summary": "...", "detail": "..." }],
  "notes": "..."
}
```

**Risk classification** (config-driven, used only for the report flag, never to gate merge —
because nothing merges):
- `published` — `@sailingnaturali/*` MCP servers and the `signalk-*` plugins / `vault-search`
  (anything released to npm).
- `boat-deployed` — `signalk-*` plugins (run on the Pi), `naturali-agents`, `infrastructure`.
- `low-risk` — everything else (docs, vaults, web, engineering, claude-skills, journey-data).

A repo can be both `published` and `boat-deployed`; either flags it 🔴 in the report.

## Module layout

```
naturali-agents/bosun/
  __init__.py
  __main__.py           # entrypoint: run the nightly pipeline
  config.py             # org name, repo risk-tier map, stale-token map, concurrency,
                        # timeout, cache/paths, HA scp target
  collect.py            # Phase 1: deterministic signal collection → FleetState
  classify.py           # actionable filtering + risk tiers
  fanout.py             # Phase 2: worktrees, Semaphore, claude -p subprocess, result parse
  prompts.py            # subagent task-contract prompt template
  report.py             # Phase 3: Jinja aggregation → HTML + markdown
  deliver.py            # scp to HA Green (BatchMode, mirrors briefing.py)
  templates/bosun.html.j2
naturali-agents/tests/bosun/
  test_collect.py       # mocked gh/npm → fleet-state
  test_classify.py      # risk tiers + actionable filter
  test_stale_tokens.py  # token scanner over fixture repos
  test_fanout.py        # semaphore/timeout/idempotency with a fake subagent command
  test_report.py        # snapshot of Jinja output from a fixture aggregate
  fixtures/...
```

Infrastructure (added in the `infrastructure` repo during implementation):
- `com.naturali.bosun.plist` — launchd agent on `studio.local`.
- `pmset` repeat wake at ~03:00 so the Mac is awake for the run, finishing before the 06:00
  briefing (mirrors the existing 05:58 briefing wake).

## Safety properties
- Phase 1 is fully read-only.
- Subagents run in isolated worktrees — no clobbering Bryan's tree or each other.
- Stable branch names → idempotent, no duplicate-PR storms across nightly runs.
- Bosun never merges; published/boat PRs are explicitly 🔴-flagged in the report.
- Bounded fan-out: a configurable cap on repos fanned out per night; per-repo timeout;
  concurrency semaphore — runaway token cost is bounded.

## Testing strategy (TDD)
Every unit below gets a failing test first:
- `collect` — mocked `gh`/`npm` responses produce the expected `fleet-state.json`; repos with
  no problems are dropped.
- `classify` — risk tiers and the actionable/non-actionable split.
- `stale_tokens` — scanner finds seeded tokens in fixture repos, ignores clean ones.
- `fanout` — Semaphore caps concurrency; timeout yields a `skip`; an existing `bosun/<slug>`
  branch updates rather than duplicates; malformed `bosun-result.json` is handled.
- `report` — snapshot test of the rendered report from a fixture aggregate, including the
  🔴 risk flag for published/boat repos.

The LLM subagent is not unit-tested; its prompt contract and result-parsing are.

## Open implementation details (decide during planning)
- `claude -p` model + any turn/budget flags.
- Exact stale-token map seed list (beyond `tide-mcp`→`currents-mcp`, `localhost:3000`).
- Whether registry check also asserts SignalK plugin-registry presence or only npm.
- ntfy/Signal "run finished" ping in addition to the HA dashboard (deferred; not in v1).
