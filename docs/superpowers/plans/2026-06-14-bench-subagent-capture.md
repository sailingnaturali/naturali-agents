# Benchmark Subagent-Tool Capture (v3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture subagent tool calls deterministically by reading `TaskProgressMessage.last_tool_name` in the benchmark collector, then re-baseline and correct ADR 0002's mistaken context-bleed note.

**Architecture:** One change to `collect_turn` — switch its accumulator to an insertion-ordered dict keyed by tool name, add a branch for messages carrying a truthy `last_tool_name` (the SDK's `TaskProgressMessage`), and dedup so a tool seen via both channels counts once (real input preferred). Then a live re-run and doc corrections. Spec: `docs/superpowers/specs/2026-06-14-bench-subagent-capture-design.md`.

**Tech Stack:** Python 3.11+, pytest, `uv`. No new dependencies.

---

## File Structure

- Modify: `naturali-agents/poseidon/bench/collect.py` (`collect_turn` + docstring)
- Modify: `naturali-agents/tests/test_bench_collect.py` (add `FakeTaskProgress` + 3 tests)
- Modify: `naturali-agents/poseidon/bench/golden.py` (docstring correction, Task 2)
- Modify: `planning/docs/adr/0002-model-strategy.md` (scorecard + reading note, Task 2)
- Regenerate: `naturali-agents/dev/bench-results/2026-06-13-claude-sonnet-4-6.{json,md}` (Task 2 re-run)

All `uv`/`pytest`/`git` commands for Task 1 run from `~/src/sailingnaturali/naturali-agents`.

---

## Task 1: Capture subagent tools via TaskProgressMessage

**Files:**
- Modify: `poseidon/bench/collect.py`
- Test: `tests/test_bench_collect.py`

- [ ] **Step 1: Add the failing tests**

In `tests/test_bench_collect.py`, add a new fake dataclass next to the existing fakes (after `FakeResult`):

```python
@dataclass
class FakeTaskProgress:
    last_tool_name: str
```

Then append these three test functions to the file:

```python
def test_captures_subagent_tool_from_task_progress():
    messages = [
        FakeTaskProgress(last_tool_name="mcp__signalk__get_active_alarms"),
        FakeResult(is_error=False),
    ]
    obs = collect_turn(messages)
    assert obs.tools == ["mcp__signalk__get_active_alarms"]


def test_dedups_task_progress_and_tool_use():
    messages = [
        FakeTaskProgress(last_tool_name="X"),
        FakeAssistant(content=[FakeToolUse(name="X", input={"a": 1})]),
        FakeResult(is_error=False),
    ]
    obs = collect_turn(messages)
    assert obs.tools == ["X"]
    assert obs.tool_inputs == [{"a": 1}]  # real input preferred, position kept


def test_agent_wrapper_and_subagent_tool_both_present():
    messages = [
        FakeAssistant(content=[FakeToolUse(name="Agent")]),
        FakeTaskProgress(last_tool_name="mcp__signalk__battery_state"),
        FakeResult(is_error=False),
    ]
    obs = collect_turn(messages)
    assert obs.tools == ["Agent", "mcp__signalk__battery_state"]
```

Leave the existing tests unchanged.

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_bench_collect.py -v`
Expected: the 3 new tests FAIL — `collect_turn` currently ignores `last_tool_name`, so `test_captures_subagent_tool_from_task_progress` yields `obs.tools == []`, and the dedup/both-present tests get wrong tool lists. Existing tests still pass.

- [ ] **Step 3: Rewrite `collect_turn` to use an ordered dict + the TaskProgress branch**

In `poseidon/bench/collect.py`, REPLACE the entire `collect_turn` function:
```python
def collect_turn(messages) -> TurnObservation:
    obs = TurnObservation()
    texts: list[str] = []
    for message in messages:
        content = getattr(message, "content", None)
        if content is not None:
            for block in content:
                if _is_tool_use(block):
                    obs.tools.append(block.name)
                    obs.tool_inputs.append(dict(getattr(block, "input", {}) or {}))
                elif hasattr(block, "text"):
                    texts.append(block.text)
        elif hasattr(message, "is_error"):
            obs.is_error = bool(message.is_error)
            obs.usage = getattr(message, "usage", None)
    obs.text = " ".join(texts).strip()
    return obs
```
with:
```python
def collect_turn(messages) -> TurnObservation:
    obs = TurnObservation()
    tools_by_name: dict[str, dict] = {}  # insertion-ordered; dedups by tool name
    texts: list[str] = []
    for message in messages:
        content = getattr(message, "content", None)
        if content is not None:
            for block in content:
                if _is_tool_use(block):
                    # Real input wins; updating an existing key keeps its position.
                    tools_by_name[block.name] = dict(getattr(block, "input", {}) or {})
                elif hasattr(block, "text"):
                    texts.append(block.text)
        elif getattr(message, "last_tool_name", None):
            # Subagent tool call (TaskProgressMessage); no input on this channel.
            tools_by_name.setdefault(message.last_tool_name, {})
        elif hasattr(message, "is_error"):
            obs.is_error = bool(message.is_error)
            obs.usage = getattr(message, "usage", None)
    obs.tools = list(tools_by_name)
    obs.tool_inputs = list(tools_by_name.values())
    obs.text = " ".join(texts).strip()
    return obs
```

Note the branch order: `last_tool_name` is checked BEFORE `is_error` so a `ResultMessage` (whose `last_tool_name` is `None`/falsy) falls through to the result branch, while a `TaskProgressMessage` (truthy `last_tool_name`) is caught as a subagent tool.

- [ ] **Step 4: Update the `collect.py` module docstring**

In `poseidon/bench/collect.py`, REPLACE the docstring body:
```
Duck-typed on purpose (hasattr, not isinstance) so unit tests use trivial fakes
and the reducer does not couple to claude_agent_sdk internals. A block is a tool
use if it has both .name and .input; a text block if it has .text.
```
with:
```
Duck-typed on purpose (hasattr, not isinstance) so unit tests use trivial fakes
and the reducer does not couple to claude_agent_sdk internals. A content block is
a tool use if it has both .name and .input; a text block if it has .text.
Subagent tool calls are captured from messages carrying a truthy .last_tool_name
(the SDK's TaskProgressMessage), which is more reliable than the subagent's
ToolUseBlocks surfacing as top-level AssistantMessages. Tools are deduped by name
(insertion-ordered; a real ToolUseBlock input wins over the input-less
TaskProgress entry), so a tool seen via both channels counts once.
```

- [ ] **Step 5: Run the full collect suite to verify all pass**

Run: `uv run pytest tests/test_bench_collect.py -v`
Expected: PASS (8 tests: the 5 existing + 3 new). Confirm the existing `test_collects_tool_names_and_inputs_in_order`, `test_multiple_tools_preserve_order`, `test_error_result_sets_flag`, `test_text_blocks_join_with_space`, and `test_empty_messages_returns_default_observation` still pass.

- [ ] **Step 6: Run the full bench suite (no regressions)**

Run: `uv run pytest tests/test_bench_*.py -q`
Expected: PASS (all bench tests — scoring/golden/decision/report unaffected).

- [ ] **Step 7: Commit**

```bash
git add poseidon/bench/collect.py tests/test_bench_collect.py
git commit -m "feat(bench): capture subagent tools via TaskProgressMessage.last_tool_name"
```

---

## Task 2: Re-baseline, correct golden docstring, update ADR

This task runs the live harness (needs `ANTHROPIC_API_KEY` in `~/.hermes/.env` and the Pi SignalK reachable at `naturalaspi.local:3000`) and updates the ADR in the **`planning`** repo.

- [ ] **Step 1: Correct the golden.py docstring**

In `poseidon/bench/golden.py`, REPLACE:
```
pilotbook). Subagent (Engineer/Logbook) tool calls can surface in the top-level
receive_response() stream (and are captured when they do), but inconsistently —
some runs show only the "Agent" delegation wrapper. Delegated asks are annotated
with the underlying tool (e.g. explain-alarm → get_active_alarms); a mismatch
there can reflect that inconsistency rather than wrong tool choice. Scoring is
recall/subset, so extra helper tools the model adds do not fail an ask.
```
with:
```
pilotbook). Subagent (Engineer/Logbook) tool calls are captured from the SDK's
TaskProgressMessage.last_tool_name (reliable) in addition to any top-level
ToolUseBlocks, so delegated asks are annotated with the underlying tool (e.g.
explain-alarm → get_active_alarms), not the "Agent" wrapper. Scoring is recall/
subset, so extra helper tools the model adds do not fail an ask.
```

- [ ] **Step 2: Verify golden tests + commit the docstring**

Run: `uv run pytest tests/test_bench_golden.py -q`
Expected: PASS (4 tests; docstring-only change).
```bash
git add poseidon/bench/golden.py
git commit -m "docs(bench): golden docstring — subagent tools captured via TaskProgress"
```

- [ ] **Step 3: Confirm prerequisites**

Run: `ssh naturalaspi docker ps | grep signalk && grep -q ANTHROPIC_API_KEY ~/.hermes/.env && echo "prereqs ok"`
Expected: a running `signalk` container line, then `prereqs ok`. If not, stop and report BLOCKED (external infra).

- [ ] **Step 4: Re-run the baseline**

Run: `uv run python -m poseidon.bench --model claude-sonnet-4-6`
Expected: a summary block and refreshed `dev/bench-results/2026-06-13-claude-sonnet-4-6.{json,md}`. `explain-alarm` should now show `get_active_alarms` (captured via `TaskProgress`) and pass; `safe-to-anchor` may still be ✗ when the model skips tools (a real model miss). Record whatever the run produces — do not re-run to chase a number.

- [ ] **Step 5: Sanity-check the refreshed scorecard**

Run: `cat dev/bench-results/2026-06-13-claude-sonnet-4-6.md`
Expected: per-ask table; `explain-alarm` observed should now include `mcp__signalk__get_active_alarms`. Note any still-✗ ask in the commit message.

- [ ] **Step 6: Commit the refreshed artifacts (naturali-agents repo)**

```bash
git add dev/bench-results/
git commit -m "bench: refresh Sonnet 4.6 baseline with subagent-tool capture"
```

- [ ] **Step 7: Update ADR 0002 (planning repo)**

In `~/src/sailingnaturali/planning/docs/adr/0002-model-strategy.md`, under `## Benchmark results`:
1. Replace the `### Benchmark run …` header, the two summary bullets, and the per-ask table with the contents of the refreshed `dev/bench-results/2026-06-13-claude-sonnet-4-6.md`.
2. Rewrite the "**Reading this baseline**" note to correct the v2 framing, with these three points: (a) there is **no context bleed** — running each ask under its own `session_id` was tested and produced identical results; (b) subagent tool calls are now captured deterministically via `TaskProgressMessage.last_tool_name`, so `explain-alarm` resolves; (c) `safe-to-anchor`'s empty observed, when it occurs, is a **genuine model miss** (no data-gathering on a safety question), nondeterministic, and left as honest signal — not masked. Keep the "**Latency**" paragraph, refreshing its numbers from the re-run.

Then:
```bash
cd ~/src/sailingnaturali/planning
git add docs/adr/0002-model-strategy.md
git commit -m "adr: 0002 — v3 baseline (subagent capture); correct context-bleed note"
git push
```

---

## Self-Review

**Spec coverage:**
- §1 collector change (ordered dict + TaskProgress branch + dedup) → Task 1 Steps 3–4. ✓
- §2 collect tests (TaskProgress capture, dedup, Agent+subagent both, existing still pass) → Task 1 Step 1, verified Step 5. ✓
- §3 re-baseline + ADR correction → Task 2 Steps 3–7. ✓
- §4 golden.py docstring → Task 2 Steps 1–2. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete before/after; every run step has a command + expected result. ✓

**Type/consistency:** `TurnObservation` fields (`tools`, `tool_inputs`, `text`, `is_error`, `usage`) are unchanged; only `collect_turn`'s internals change, and it still returns `obs.tools: list[str]` / `obs.tool_inputs: list[dict]`. The new `FakeTaskProgress(last_tool_name=...)` matches the `getattr(message, "last_tool_name", None)` access. Branch-order reasoning (last_tool_name before is_error) is stated so `ResultMessage` still sets the error/usage. ✓
