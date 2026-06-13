# Benchmark Scoring Calibration (v2) — Design

**Status:** Approved 2026-06-13
**Consumes:** the ADR-0002 benchmark harness (`poseidon/bench/`, shipped 2026-06-13)
**Plan:** `docs/superpowers/plans/2026-06-13-bench-scoring-calibration.md` (to be written)

## Context

The first baseline run (Sonnet 4.6, recorded in ADR 0002) scored 50% tool-call
correctness. Investigation showed the misses were **scoring artifacts, not model
errors**: the `score_ask` rule used exact set-equality (`observed == expected`),
which fails any ask where the model adds a reasonable helper call —
`wind-forecast` fetched position + local time before the forecast,
`anchorage-near` did find→rank, `explain-alarm` answered at the top level.

A spike (`dev/`, throwaway) against the live SDK also corrected a wrong
assumption from the ADR: **subagent (Engineer/Logbook) tool calls DO surface** in
the top-level `receive_response()` stream as ordinary `AssistantMessage` /
`ToolUseBlock`s, so the collector already captures them. The "subagent calls
aren't captured" caveat in `golden.py` and the ADR is incorrect. The spike also
confirmed the duck-typed collector correctly ignores the non-tool message/block
types (`ThinkingBlock`, `ToolResultBlock`, `SystemMessage`, `Task*Message`) —
none expose both `.name` and `.input`, none expose `.text`.

So v2 is narrow: fix the scoring rule, re-annotate one ask, correct the docs, and
re-baseline.

## Decision

**Switch correctness from set-equality to recall/subset:** an ask passes when
every expected tool appears in the observed tools (`expected ⊆ observed`). Extra
or helper tool calls are allowed and do not fail the ask. This gives a clean
separation of concerns:

- **Correctness** = "did the model reach for the right tools to answer this?"
- **Latency** (already measured) = "was it efficient?" — over-calling shows up
  here, not as a correctness failure.

Extra tools remain visible per-ask in the scorecard `observed` column for manual
inspection. A missing *required* tool still fails (subset is violated). The
optional `expected_args` superset check is unchanged.

## Components & changes

### 1. `poseidon/bench/scoring.py` — `score_ask`
One-line semantic change:

- From: `if set(observed_tools) != set(ask.expected_tools): return False`
- To: `if not set(ask.expected_tools).issubset(set(observed_tools)): return False`

Everything else in `score_ask` (the `expected_args` superset check) and the rest
of the module (`build_scorecard`, `percentile`) is unchanged. Docstring updated
to say "recall/subset" instead of "set equality."

### 2. `poseidon/bench/golden_asks.json` — annotations
Only one ask changes. The four root-direct asks and the two composed Navigator
asks (`wind-forecast`, `anchorage-near`, `safe-to-anchor`) keep their existing
expected tools — under subset scoring they now pass with their realistic
trajectories.

- `explain-alarm`: `expected_tools` `["Agent"]` → `["mcp__signalk__get_active_alarms"]`.
  Rationale: subagent tools surface, and `get_active_alarms` reliably appears
  whether or not the model delegates; it represents "consulted alarm state," the
  core of explaining an alarm. The "ideal" `mcp__vessel-knowledge__explain_notification`
  path is **not** encoded as required — the model reliably checks live alarm
  state instead, and whether that is a product gap is a separate question, not a
  harness-calibration one. `category` stays `delegated`.

### 3. `tests/test_bench_scoring.py`
- `test_score_ask_extra_tool_fails` → invert to `test_score_ask_extra_tool_allowed`:
  an extra observed tool beyond the expected set now scores `True`.
- Add `test_score_ask_recall_with_helpers`: expected `[A]`, observed `[B, A, C]`
  → `True` (helpers around the required tool).
- Keep `test_score_ask_exact_set_match_passes` (still `True`),
  `test_score_ask_order_tolerant_for_multi` (still `True`),
  `test_score_ask_missing_tool_fails` (expected `[A,B]`, observed `[A]` → `False`),
  and `test_score_ask_arg_subset_checked_when_present`.

### 4. Documentation corrections
- `poseidon/bench/golden.py` module docstring: remove the "capturing
  subagent-internal tool calls is a v2 follow-up requiring live SDK verification"
  sentence; replace with: subagent tool calls surface in the top-level stream and
  are captured; scoring is recall/subset so delegation is transparent.
- `planning/docs/adr/0002-model-strategy.md` "Reading this baseline" note: correct
  the two bullets — (1) scoring is now recall/subset (was the cause of the low
  number), (2) subagent tool calls *are* captured (the earlier caveat was wrong).
  Replace the recorded scorecard with the v2 re-run (see §5).

### 5. Re-baseline
Re-run `uv run python -m poseidon.bench --model claude-sonnet-4-6` under the new
scoring, commit the refreshed `dev/bench-results/` artifacts, and update the ADR
scorecard table + headline numbers. Latency figures are expected to be similar
(scoring doesn't affect timing); correctness should rise to reflect the real
signal. Record honestly whatever the re-run produces — do not tune to a target.

## Out of scope
- Required+allowed-list scoring (rejected: brittle per-ask allow-lists).
- A separate tool-efficiency metric (latency already covers over-calling).
- Any change to the collector (`collect.py`) — confirmed correct by the spike.
- Whether the Engineer agent *should* call `explain_notification` (product
  question, not harness).

## Testing
Unit: the scoring tests above run with no network. Integration: the §5 re-run is
the live end-to-end check (needs `ANTHROPIC_API_KEY` + Pi SignalK up). Full repo
suite must stay green.
