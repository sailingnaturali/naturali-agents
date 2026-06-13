# Benchmark Scoring Calibration (v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recalibrate the ADR-0002 benchmark's correctness scoring from exact set-equality to recall/subset, re-annotate one golden ask, correct the docs, and refresh the recorded Sonnet 4.6 baseline.

**Architecture:** A one-line semantic change in `score_ask` (subset instead of set-equality), a single golden-annotation edit, docstring/ADR corrections, and a live re-baseline. The collector and the rest of the harness are unchanged (the spike confirmed they're correct). Spec: `docs/superpowers/specs/2026-06-13-bench-scoring-calibration-design.md`.

**Tech Stack:** Python 3.11+, pytest, `uv`. No new dependencies.

---

## File Structure

- Modify: `naturali-agents/poseidon/bench/scoring.py` (`score_ask` rule + docstring)
- Modify: `naturali-agents/tests/test_bench_scoring.py` (invert one test, add one)
- Modify: `naturali-agents/poseidon/bench/golden_asks.json` (`explain-alarm` expected_tools)
- Modify: `naturali-agents/poseidon/bench/golden.py` (docstring correction)
- Modify: `planning/docs/adr/0002-model-strategy.md` (Reading-baseline note + scorecard, Task 4)
- Regenerate: `naturali-agents/dev/bench-results/2026-06-13-claude-sonnet-4-6.{json,md}` (Task 4 re-run)

All `uv`/`pytest`/`git` commands for Tasks 1–3 run from `~/src/sailingnaturali/naturali-agents`.

---

## Task 1: Recall/subset scoring

**Files:**
- Modify: `poseidon/bench/scoring.py`
- Test: `tests/test_bench_scoring.py`

- [ ] **Step 1: Update the tests to the new semantics (TDD — change tests first)**

In `tests/test_bench_scoring.py`, REPLACE the function `test_score_ask_extra_tool_fails` (which currently asserts an extra tool fails) with these two functions:

```python
def test_score_ask_extra_tool_allowed():
    a = _ask("depth", ["mcp__signalk__depth_state"])
    assert score_ask(a, observed_tools=["mcp__signalk__depth_state", "mcp__weather__x"]) is True


def test_score_ask_recall_with_helpers():
    a = _ask("wind", ["mcp__weather__get_marine_forecast"])
    observed = ["mcp__signalk__read_sensor", "mcp__weather__get_marine_forecast",
                "mcp__signalk__get_local_time"]
    assert score_ask(a, observed_tools=observed) is True
```

Leave `test_score_ask_exact_set_match_passes`, `test_score_ask_order_tolerant_for_multi`,
`test_score_ask_missing_tool_fails`, `test_score_ask_arg_subset_checked_when_present`,
`test_percentile_p50_p95`, and `test_build_scorecard_aggregates` unchanged.

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `uv run pytest tests/test_bench_scoring.py -v`
Expected: FAIL — `test_score_ask_extra_tool_allowed` and `test_score_ask_recall_with_helpers` fail (current set-equality returns `False` when extra tools are present). The other tests still pass.

- [ ] **Step 3: Change the scoring rule**

In `poseidon/bench/scoring.py`, inside `score_ask`, change the first check from set-equality to subset:

Replace:
```python
    if set(observed_tools) != set(ask.expected_tools):
        return False
```
with:
```python
    if not set(ask.expected_tools).issubset(set(observed_tools)):
        return False
```

- [ ] **Step 4: Update the module docstring**

In `poseidon/bench/scoring.py`, in the module docstring, replace the sentence:
```
Tool-call correctness (ADR 0002 §Benchmark): observed top-level tool set must
equal the expected set (order-tolerant).
```
with:
```
Tool-call correctness (ADR 0002 §Benchmark): every expected tool must appear in
the observed tools (recall/subset, order-tolerant); extra/helper tool calls are
allowed and do not fail the ask — efficiency is the latency metric's job.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_bench_scoring.py -v`
Expected: PASS (8 tests: the 6 retained + the 2 new). Confirm `test_score_ask_missing_tool_fails` still passes (a missing required tool violates subset → `False`).

- [ ] **Step 6: Commit**

```bash
git add poseidon/bench/scoring.py tests/test_bench_scoring.py
git commit -m "feat(bench): recall/subset scoring (expected ⊆ observed)"
```

---

## Task 2: Re-annotate the explain-alarm golden ask

**Files:**
- Modify: `poseidon/bench/golden_asks.json`
- Test: `tests/test_bench_golden.py` (existing tests must still pass)

- [ ] **Step 1: Edit the explain-alarm entry**

In `poseidon/bench/golden_asks.json`, in the `explain-alarm` object, change:
```json
    "expected_tools": ["Agent"],
```
to:
```json
    "expected_tools": ["mcp__signalk__get_active_alarms"],
```
Leave its `id`, `category` (`delegated`), `prompt`, and `multi_tool` (`false`) unchanged.

- [ ] **Step 2: Run the golden tests**

Run: `uv run pytest tests/test_bench_golden.py -v`
Expected: PASS (4 tests). The `test_every_ask_has_nonempty_expected_tools` check requires tools to start with `mcp__` or `Agent`; `mcp__signalk__get_active_alarms` starts with `mcp__`, so it passes. `test_single_tool_asks_expect_exactly_one_tool` still holds (one tool).

- [ ] **Step 3: Commit**

```bash
git add poseidon/bench/golden_asks.json
git commit -m "bench: re-annotate explain-alarm expected tool (get_active_alarms)"
```

---

## Task 3: Correct the golden.py docstring

**Files:**
- Modify: `poseidon/bench/golden.py`

- [ ] **Step 1: Replace the stale subagent caveat**

In `poseidon/bench/golden.py`, in the module docstring, replace:
```
v1 targets the Navigator-root-direct safety/nav core (signalk/weather/currents/
pilotbook), where the expected tool surfaces at the top level. Delegated asks
(Engineer/Logbook subagents) expect the top-level "Agent" delegation tool;
capturing subagent-internal tool calls is a v2 follow-up requiring live SDK
verification that receive_response() surfaces subagent tool_use blocks.
```
with:
```
Targets the Navigator-root-direct safety/nav core (signalk/weather/currents/
pilotbook). Subagent (Engineer/Logbook) tool calls DO surface in the top-level
receive_response() stream and are captured by the collector, so delegated asks
are annotated with the underlying tool that reliably appears (e.g. explain-alarm
→ get_active_alarms), not the "Agent" delegation wrapper. Scoring is recall/
subset, so any extra helper tools the model adds do not fail an ask.
```

- [ ] **Step 2: Verify the module still imports and golden tests pass**

Run: `uv run pytest tests/test_bench_golden.py -q`
Expected: PASS (4 tests). (Docstring-only change; no behavior impact.)

- [ ] **Step 3: Commit**

```bash
git add poseidon/bench/golden.py
git commit -m "docs(bench): correct golden docstring — subagent tool calls do surface"
```

---

## Task 4: Re-baseline and update ADR 0002

This task runs the live harness (needs `ANTHROPIC_API_KEY` in `~/.hermes/.env` and the Pi SignalK reachable at `naturalaspi.local:3000`) and updates the ADR in the **`planning`** repo.

- [ ] **Step 1: Confirm the full bench suite is green first**

Run (from `naturali-agents`): `uv run pytest tests/test_bench_*.py -q`
Expected: PASS (all bench tests). Do not proceed to the live run if any unit test fails.

- [ ] **Step 2: Confirm live prerequisites**

Run: `ssh naturalaspi docker ps | grep signalk && grep -q ANTHROPIC_API_KEY ~/.hermes/.env && echo "prereqs ok"`
Expected: a running `signalk` container line, then `prereqs ok`. If not, stop and report BLOCKED (external infra).

- [ ] **Step 3: Re-run the baseline under recall scoring**

Run: `uv run python -m poseidon.bench --model claude-sonnet-4-6`
Expected: a summary block and refreshed `dev/bench-results/2026-06-13-claude-sonnet-4-6.{json,md}`. Correctness should be higher than the prior 50% (the composed asks now pass under subset); latency p50/p95 will be similar to before (scoring doesn't change timing). Record whatever the run produces — do not re-run to chase a number.

- [ ] **Step 4: Sanity-check the refreshed scorecard**

Run: `cat dev/bench-results/2026-06-13-claude-sonnet-4-6.md`
Expected: per-ask table; the four root-direct asks still ✓; `wind-forecast`, `anchorage-near`, and `explain-alarm` should now ✓ under subset scoring (assuming their expected tools appear). Note any still-✗ ask in the commit message rather than editing the data.

- [ ] **Step 5: Commit the refreshed artifacts (naturali-agents repo)**

```bash
git add dev/bench-results/
git commit -m "bench: refresh Sonnet 4.6 baseline under recall/subset scoring"
```

- [ ] **Step 6: Update ADR 0002 (planning repo)**

In `~/src/sailingnaturali/planning/docs/adr/0002-model-strategy.md`, under `## Benchmark results`:
1. Replace the `### Benchmark run 2026-06-13 — claude-sonnet-4-6` header line, the two summary bullets, and the per-ask table with the contents of the refreshed `dev/bench-results/2026-06-13-claude-sonnet-4-6.md`.
2. Rewrite the "**Reading this baseline.**" paragraph's two numbered bullets to reflect the correction: (1) scoring is now recall/subset — the earlier 50% was the exact-set-equality artifact, now resolved; (2) subagent tool calls DO surface and are captured (the earlier "not captured" caveat was wrong). Keep the "**Latency**" paragraph (latency reasoning is unchanged).

Then:
```bash
cd ~/src/sailingnaturali/planning
git add docs/adr/0002-model-strategy.md
git commit -m "adr: 0002 — refresh baseline under recall scoring; correct subagent-capture note"
git push
```

---

## Self-Review

**Spec coverage:**
- §1 scoring rule change → Task 1 (Steps 3–4). ✓
- §2 explain-alarm re-annotation → Task 2. ✓
- §3 test changes (invert extra-tool, add recall-with-helpers, keep the rest) → Task 1 Step 1. ✓
- §4 doc corrections: golden.py → Task 3; ADR note → Task 4 Step 6. ✓
- §5 re-baseline → Task 4 Steps 3–6. ✓

**Placeholder scan:** No TBD/TODO; every edit shows exact before/after text; every run step has a command + expected result. ✓

**Type/consistency:** No new types or signatures — `score_ask(ask, observed_tools, observed_args=None)` is unchanged in shape, only its internal predicate changes. Test names referenced (`test_score_ask_extra_tool_allowed`, `test_score_ask_recall_with_helpers`) are defined in Task 1. The `explain-alarm` tool name `mcp__signalk__get_active_alarms` matches the id used elsewhere in the golden set and the live MCP surface. ✓
