# Benchmark Subagent-Tool Capture (v3) — Design

**Status:** Approved 2026-06-14
**Consumes:** the ADR-0002 benchmark harness (`poseidon/bench/`) at v2 (recall/subset scoring)
**Plan:** `docs/superpowers/plans/2026-06-14-bench-subagent-capture.md` (to be written)

## Context

ADR 0002's v2 baseline left two ✗ asks and named "single-session context bleed"
as the v3 item (per-ask session isolation). A spike disproved that premise:
running each golden ask under its own `query(..., session_id=ask.id)` on one
connected client produced results identical to the shared session. There is no
context bleed. Raw-message inspection found the real causes:

- **`explain-alarm` — a harness gap.** When the model delegates via the `Agent`
  tool, the SDK emits a `TaskProgressMessage` carrying `last_tool_name` for each
  subagent tool call (`get_active_alarms`, `battery_state`, …). The subagent's
  `ToolUseBlock`s *also* sometimes surface as top-level `AssistantMessage`s, but
  inconsistently (the v1 baseline missed them; the spike caught them). The
  collector currently reads only the `AssistantMessage` path, so subagent tools
  are captured unreliably. `TaskProgressMessage.last_tool_name` is the reliable
  signal it ignores.
- **`safe-to-anchor` — a model miss, not a bug.** In an isolated session it
  called zero tools and answered the safety question ("safe to anchor given
  weather and current?") with "conditions are benign tonight." Correctly scored
  ✗; nondeterministic (other runs it does call tools). Nothing to fix in the
  harness — it is honest signal that the agent sometimes skips data-gathering.

So v3 is: make subagent-tool capture deterministic via `TaskProgressMessage`, and
correct the ADR's mistaken context-bleed framing. Session isolation is dropped.

## Decision

Teach the collector to capture subagent tool calls from `TaskProgressMessage`s,
deduped against the top-level `ToolUseBlock`s so each tool is counted once.

## Components & changes

### 1. `poseidon/bench/collect.py` — `collect_turn`

Switch the internal accumulator from two parallel lists to a single
**insertion-ordered dict** `tools_by_name: dict[str, dict]` (Python dicts preserve
insertion order), then derive the outputs:

- **Top-level tool use** (a content block with both `.name` and `.input`):
  `tools_by_name[block.name] = dict(block.input or {})` — sets/overwrites with the
  real input, preserving first-seen position.
- **Subagent tool use** (a message with no `.content` and a truthy
  `last_tool_name` — i.e. `TaskProgressMessage`): `tools_by_name.setdefault(name, {})`
  — records the subagent tool without clobbering a real input captured elsewhere.
- **Result** (a message with no `.content`, no truthy `last_tool_name`, and an
  `is_error` attr — i.e. `ResultMessage`): set `obs.is_error` / `obs.usage` as today.
- Text blocks: unchanged (joined, stripped).

At the end: `obs.tools = list(tools_by_name)`, `obs.tool_inputs = list(tools_by_name.values())`.

Branch order in the message loop: `content is not None` → blocks; `elif` truthy
`getattr(message, "last_tool_name", None)` → subagent tool; `elif`
`hasattr(message, "is_error")` → result. (`ResultMessage.last_tool_name` is
`None`/falsy, so it correctly falls through to the result branch; `TaskStarted`/
`TaskNotification` carry no `last_tool_name`, so they're ignored.)

Behavioral notes:
- **Dedup is new and intended.** A tool that appears via both a `TaskProgress`
  message and a later `ToolUseBlock` yields one entry (real input preferred). A
  tool genuinely called twice in one turn now appears once. Correctness scoring
  already uses sets, so this is neutral there and cleaner in the report.
- The `Agent` delegation wrapper remains in `observed_tools` (it's a real
  top-level tool call signalling delegation occurred).

Docstring updated to describe the two capture paths + dedup.

### 2. `tests/test_bench_collect.py`

Add a local `FakeTaskProgress` dataclass (`last_tool_name: str`, no `.content`)
and tests:

- `test_captures_subagent_tool_from_task_progress`: messages = `[FakeTaskProgress("mcp__signalk__get_active_alarms"), FakeResult()]`
  → `obs.tools == ["mcp__signalk__get_active_alarms"]`.
- `test_dedups_task_progress_and_tool_use`: a `FakeTaskProgress("X")` followed by a
  `FakeAssistant([FakeToolUse("X", {"a": 1})])` → `obs.tools == ["X"]` and
  `obs.tool_inputs == [{"a": 1}]` (one entry, real input preferred, original
  position kept).
- `test_agent_wrapper_and_subagent_tool_both_present`: `FakeAssistant([FakeToolUse("Agent")])`
  then `FakeTaskProgress("mcp__signalk__battery_state")` → `obs.tools == ["Agent", "mcp__signalk__battery_state"]`.

Existing tests (collect names/inputs/text/usage, multi-tool order, error flag,
text join, empty-messages) must still pass unchanged — none carry `last_tool_name`.

### 3. Re-baseline + ADR update

Re-run `uv run python -m poseidon.bench --model claude-sonnet-4-6`; commit the
refreshed `dev/bench-results/` artifacts. `explain-alarm` is expected to pass
consistently now (`get_active_alarms` captured via `TaskProgress`). Then update
`planning/docs/adr/0002-model-strategy.md` § Benchmark results:

1. Replace the scorecard table + headline numbers with the v3 re-run.
2. Rewrite the "Reading this baseline" note to **correct v2**: (a) no context
   bleed — per-ask `session_id` isolation was tested and changed nothing; (b)
   subagent tool calls are now captured deterministically via
   `TaskProgressMessage.last_tool_name`; (c) `safe-to-anchor`'s empty observed,
   when it occurs, is a genuine model miss (no data-gathering on a safety
   question), nondeterministic, and left as honest signal — not masked.

Record whatever the re-run produces; do not tune to a target.

### 4. `poseidon/bench/golden.py` docstring

Update the subagent note to: subagent tool calls are captured via
`TaskProgressMessage.last_tool_name` (reliable) in addition to any top-level
`ToolUseBlock`s; delegated asks are annotated with the underlying tool.

## Out of scope
- Per-ask session isolation (premise disproven by the spike).
- "Fixing" `safe-to-anchor`'s nondeterministic no-tool answers (model behavior,
  not harness; kept as honest signal).
- Any change to scoring (`scoring.py`), the runner, the CLI, or the report
  modules — the collector is the only code change.

## Testing
Unit: the collect tests above run with no network. Integration: the §3 re-run is
the live end-to-end check (needs `ANTHROPIC_API_KEY` + Pi SignalK up). Full repo
suite must stay green.
