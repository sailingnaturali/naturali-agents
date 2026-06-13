# Model Benchmark Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the engine-swappable benchmark harness that ADR 0002 makes the gate for primary-engine selection, and run it once to record the Sonnet 4.6 baseline.

**Architecture:** Pure, testable logic (golden ask set, turn-observation collector, scoring, decision rule, report) lives in a new `poseidon/bench/` subpackage so pytest can import it and it ships with the daemon. A thin async runner builds a `ClaudeSDKClient` from the production `crew_options()` with the model overridden, runs the golden asks on one warm session, and captures per-ask tools + timing + errors. A `python -m poseidon.bench` CLI wires runner → scoring → report. Results (markdown + JSON scorecards) are written under `dev/bench-results/`. (ADR 0002 named `dev/` as the home; the testable logic moved into the package for pytest import, with the dev-facing entry preserved — a deliberate, documented deviation.)

**Tech Stack:** Python 3.11+, `claude-agent-sdk` 0.2.97 (already a dep), `pytest` + `respx` (dev deps), `uv` for running. No new dependencies.

**Scope note:** This plan covers the benchmark harness only. The Phase-0 failover plumbing (API-health probe + engine swap + debounce + degraded-mode announcement in Poseidon) is a separate runtime subsystem and gets its own plan. The v1 golden set targets the Navigator-root-direct safety/nav core (signalk / weather / currents / pilotbook), because Engineer/Logbook subagent tool calls may not surface in the top-level SDK message stream; capturing subagent-internal tool calls is a documented v2 follow-up (Task 1 notes it).

---

## File Structure

- Create: `naturali-agents/poseidon/bench/__init__.py` — subpackage marker + public exports
- Create: `naturali-agents/poseidon/bench/golden.py` — `Ask` dataclass + JSON loader
- Create: `naturali-agents/poseidon/bench/golden_asks.json` — the golden ask corpus (data)
- Create: `naturali-agents/poseidon/bench/collect.py` — `TurnObservation` + `collect_turn()` pure reducer over SDK messages
- Create: `naturali-agents/poseidon/bench/scoring.py` — per-ask scoring, latency percentiles, `Scorecard`
- Create: `naturali-agents/poseidon/bench/decision.py` — `compare()` swap rule → `Verdict`
- Create: `naturali-agents/poseidon/bench/report.py` — render markdown + JSON, write to results dir
- Create: `naturali-agents/poseidon/bench/runner.py` — async live runner (build client, run asks)
- Create: `naturali-agents/poseidon/bench/__main__.py` — argparse CLI wiring
- Create: `naturali-agents/tests/test_bench_golden.py`
- Create: `naturali-agents/tests/test_bench_collect.py`
- Create: `naturali-agents/tests/test_bench_scoring.py`
- Create: `naturali-agents/tests/test_bench_decision.py`
- Create: `naturali-agents/tests/test_bench_report.py`
- Modify: `naturali-agents/planning/docs/adr/0002-model-strategy.md` (in the `planning` repo) — append the baseline scorecard under § Benchmark results (Task 8)

All `pytest`/`uv` commands run from `~/src/sailingnaturali/naturali-agents`.

---

## Task 1: Golden ask set + loader

**Files:**
- Create: `naturali-agents/poseidon/bench/__init__.py`
- Create: `naturali-agents/poseidon/bench/golden.py`
- Create: `naturali-agents/poseidon/bench/golden_asks.json`
- Test: `naturali-agents/tests/test_bench_golden.py`

- [ ] **Step 1: Create the empty subpackage marker**

Create `naturali-agents/poseidon/bench/__init__.py`:

```python
"""poseidon.bench — the ADR-0002 model benchmark harness.

Pure logic (golden set, collect, scoring, decision, report) is importable and
unit-tested here; the async live runner and CLI sit alongside. See
docs/superpowers/plans/2026-06-13-model-benchmark-harness.md.
"""
```

- [ ] **Step 2: Write the failing test**

Create `naturali-agents/tests/test_bench_golden.py`:

```python
from poseidon.bench.golden import Ask, load_golden_asks


def test_load_golden_asks_returns_asks():
    asks = load_golden_asks()
    assert len(asks) >= 6
    assert all(isinstance(a, Ask) for a in asks)


def test_ask_ids_are_unique():
    asks = load_golden_asks()
    ids = [a.id for a in asks]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


def test_every_ask_has_nonempty_expected_tools():
    for a in load_golden_asks():
        assert a.expected_tools, f"{a.id} has no expected_tools"
        assert all(t.startswith(("mcp__", "Agent")) for t in a.expected_tools)


def test_single_tool_asks_expect_exactly_one_tool():
    for a in load_golden_asks():
        if not a.multi_tool:
            assert len(a.expected_tools) == 1, f"{a.id} not single-tool"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_bench_golden.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'poseidon.bench.golden'`

- [ ] **Step 4: Write the data file**

Create `naturali-agents/poseidon/bench/golden_asks.json`. Tool names are the exact MCP tool ids the model sees (`mcp__<server>__<tool>`). `expected_tools` lists the top-level tool(s) expected; delegated asks expect `Agent`.

```json
[
  {
    "id": "depth",
    "category": "engineer-direct",
    "prompt": "What's my depth right now?",
    "expected_tools": ["mcp__signalk__depth_state"],
    "multi_tool": false
  },
  {
    "id": "battery",
    "category": "engineer-direct",
    "prompt": "How's the battery doing?",
    "expected_tools": ["mcp__signalk__battery_state"],
    "multi_tool": false
  },
  {
    "id": "alarms",
    "category": "engineer-direct",
    "prompt": "Are there any active alarms?",
    "expected_tools": ["mcp__signalk__get_active_alarms"],
    "multi_tool": false
  },
  {
    "id": "wind-forecast",
    "category": "navigator",
    "prompt": "What's the wind forecast for tonight?",
    "expected_tools": ["mcp__weather__get_marine_forecast"],
    "multi_tool": false
  },
  {
    "id": "current-boundary",
    "category": "navigator",
    "prompt": "What's the current doing at Boundary Pass?",
    "expected_tools": ["mcp__currents__get_tidal_gate"],
    "multi_tool": false
  },
  {
    "id": "anchorage-near",
    "category": "navigator",
    "prompt": "Find me an anchorage near here for tonight.",
    "expected_tools": ["mcp__pilotbook__find_anchorages_near"],
    "multi_tool": false
  },
  {
    "id": "safe-to-anchor",
    "category": "navigator-multi",
    "prompt": "Is it safe to anchor here tonight given the weather and current?",
    "expected_tools": ["mcp__pilotbook__find_anchorages_near", "mcp__weather__get_marine_forecast"],
    "multi_tool": true
  },
  {
    "id": "explain-alarm",
    "category": "delegated",
    "prompt": "What does the low house battery alarm mean and what should I do?",
    "expected_tools": ["Agent"],
    "multi_tool": false
  }
]
```

- [ ] **Step 5: Write minimal implementation**

Create `naturali-agents/poseidon/bench/golden.py`:

```python
"""poseidon.bench.golden — the fixed golden ask corpus + loader.

v1 targets the Navigator-root-direct safety/nav core (signalk/weather/currents/
pilotbook), where the expected tool surfaces at the top level. Delegated asks
(Engineer/Logbook subagents) expect the top-level "Agent" delegation tool;
capturing subagent-internal tool calls is a v2 follow-up requiring live SDK
verification that receive_response() surfaces subagent tool_use blocks.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_GOLDEN_JSON = Path(__file__).with_name("golden_asks.json")


@dataclass(frozen=True)
class Ask:
    id: str
    category: str
    prompt: str
    expected_tools: tuple[str, ...]
    multi_tool: bool
    expected_args: dict = field(default_factory=dict)


def load_golden_asks(path: Path | None = None) -> list[Ask]:
    raw = json.loads((path or _GOLDEN_JSON).read_text(encoding="utf-8"))
    return [
        Ask(
            id=row["id"],
            category=row["category"],
            prompt=row["prompt"],
            expected_tools=tuple(row["expected_tools"]),
            multi_tool=bool(row.get("multi_tool", False)),
            expected_args=row.get("expected_args", {}),
        )
        for row in raw
    ]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_bench_golden.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
cd ~/src/sailingnaturali/naturali-agents
git add poseidon/bench/__init__.py poseidon/bench/golden.py poseidon/bench/golden_asks.json tests/test_bench_golden.py
git commit -m "feat(bench): golden ask set + loader for the ADR-0002 harness"
```

---

## Task 2: Turn-observation collector

A pure reducer that turns a sequence of SDK messages into the facts scoring needs: tool names invoked (with inputs), final text, error flag, usage. Duck-typed (checks attributes) so tests use trivial fakes and the collector stays decoupled from SDK internals. (Production `engine.py` uses `isinstance`; this deliberately does not.)

**Files:**
- Create: `naturali-agents/poseidon/bench/collect.py`
- Test: `naturali-agents/tests/test_bench_collect.py`

- [ ] **Step 1: Write the failing test**

Create `naturali-agents/tests/test_bench_collect.py`:

```python
from dataclasses import dataclass, field

from poseidon.bench.collect import TurnObservation, collect_turn


# Minimal duck-typed fakes mirroring the SDK message shapes.
@dataclass
class FakeToolUse:
    name: str
    input: dict = field(default_factory=dict)


@dataclass
class FakeText:
    text: str


@dataclass
class FakeAssistant:
    content: list


@dataclass
class FakeResult:
    is_error: bool = False
    usage: dict | None = None


def test_collects_tool_names_and_inputs_in_order():
    messages = [
        FakeAssistant(content=[FakeToolUse(name="mcp__signalk__depth_state", input={"x": 1})]),
        FakeAssistant(content=[FakeText(text="Twelve metres.")]),
        FakeResult(is_error=False, usage={"input_tokens": 100}),
    ]
    obs = collect_turn(messages)
    assert isinstance(obs, TurnObservation)
    assert obs.tools == ["mcp__signalk__depth_state"]
    assert obs.tool_inputs == [{"x": 1}]
    assert obs.text == "Twelve metres."
    assert obs.is_error is False
    assert obs.usage == {"input_tokens": 100}


def test_multiple_tools_preserve_order():
    messages = [
        FakeAssistant(content=[
            FakeToolUse(name="mcp__pilotbook__find_anchorages_near"),
            FakeToolUse(name="mcp__weather__get_marine_forecast"),
        ]),
        FakeResult(is_error=False),
    ]
    obs = collect_turn(messages)
    assert obs.tools == [
        "mcp__pilotbook__find_anchorages_near",
        "mcp__weather__get_marine_forecast",
    ]


def test_error_result_sets_flag():
    obs = collect_turn([FakeResult(is_error=True)])
    assert obs.is_error is True
    assert obs.tools == []
    assert obs.text == ""


def test_text_blocks_join_with_space():
    messages = [FakeAssistant(content=[FakeText(text="One."), FakeText(text="Two.")])]
    obs = collect_turn(messages)
    assert obs.text == "One. Two."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bench_collect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'poseidon.bench.collect'`

- [ ] **Step 3: Write minimal implementation**

Create `naturali-agents/poseidon/bench/collect.py`:

```python
"""poseidon.bench.collect — reduce a turn's SDK messages to scorable facts.

Duck-typed on purpose (hasattr, not isinstance) so unit tests use trivial fakes
and the reducer does not couple to claude_agent_sdk internals. A block is a tool
use if it has both .name and .input; a text block if it has .text.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TurnObservation:
    tools: list[str] = field(default_factory=list)
    tool_inputs: list[dict] = field(default_factory=list)
    text: str = ""
    is_error: bool = False
    usage: dict | None = None


def _is_tool_use(block) -> bool:
    return hasattr(block, "name") and hasattr(block, "input")


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

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bench_collect.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/src/sailingnaturali/naturali-agents
git add poseidon/bench/collect.py tests/test_bench_collect.py
git commit -m "feat(bench): turn-observation collector"
```

---

## Task 3: Scoring (tool-call correctness + latency percentiles)

Scores one ask (tool set match + optional arg-subset check) and aggregates many `AskResult`s into a `Scorecard` (correctness fraction, p50/p95 warm-hop latency, error rate). Pure; no SDK.

**Files:**
- Create: `naturali-agents/poseidon/bench/scoring.py`
- Test: `naturali-agents/tests/test_bench_scoring.py`

- [ ] **Step 1: Write the failing test**

Create `naturali-agents/tests/test_bench_scoring.py`:

```python
from poseidon.bench.golden import Ask
from poseidon.bench.scoring import (
    AskResult,
    Scorecard,
    percentile,
    score_ask,
    build_scorecard,
)


def _ask(id, tools, multi=False, args=None):
    return Ask(id=id, category="c", prompt="p", expected_tools=tuple(tools),
               multi_tool=multi, expected_args=args or {})


def test_score_ask_exact_set_match_passes():
    a = _ask("depth", ["mcp__signalk__depth_state"])
    assert score_ask(a, observed_tools=["mcp__signalk__depth_state"]) is True


def test_score_ask_order_tolerant_for_multi():
    a = _ask("x", ["A", "B"], multi=True)
    assert score_ask(a, observed_tools=["B", "A"]) is True


def test_score_ask_extra_tool_fails():
    a = _ask("depth", ["mcp__signalk__depth_state"])
    assert score_ask(a, observed_tools=["mcp__signalk__depth_state", "mcp__weather__x"]) is False


def test_score_ask_missing_tool_fails():
    a = _ask("x", ["A", "B"], multi=True)
    assert score_ask(a, observed_tools=["A"]) is False


def test_score_ask_arg_subset_checked_when_present():
    a = _ask("g", ["mcp__currents__get_tidal_gate"], args={"mcp__currents__get_tidal_gate": {"gate": "boundary_pass"}})
    ok = score_ask(a, observed_tools=["mcp__currents__get_tidal_gate"],
                   observed_args=[{"gate": "boundary_pass", "extra": 1}])
    bad = score_ask(a, observed_tools=["mcp__currents__get_tidal_gate"],
                    observed_args=[{"gate": "active_pass"}])
    assert ok is True and bad is False


def test_percentile_p50_p95():
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(data, 50) == 3.0
    assert percentile(data, 95) == 5.0


def test_build_scorecard_aggregates():
    a1 = _ask("depth", ["mcp__signalk__depth_state"])
    a2 = _ask("wind", ["mcp__weather__get_marine_forecast"])
    results = [
        AskResult(ask=a1, observed_tools=["mcp__signalk__depth_state"],
                  observed_args=[{}], dt_total=2.0, is_error=False),
        AskResult(ask=a2, observed_tools=["mcp__weather__get_marine_forecast"],
                  observed_args=[{}], dt_total=4.0, is_error=False),
    ]
    card = build_scorecard(model="claude-sonnet-4-6", results=results)
    assert isinstance(card, Scorecard)
    assert card.correctness == 1.0
    assert card.error_rate == 0.0
    assert card.latency_p50 == 3.0
    assert card.n == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bench_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'poseidon.bench.scoring'`

- [ ] **Step 3: Write minimal implementation**

Create `naturali-agents/poseidon/bench/scoring.py`:

```python
"""poseidon.bench.scoring — per-ask correctness + scorecard aggregation.

Tool-call correctness (ADR 0002 §Benchmark): observed top-level tool set must
equal the expected set (order-tolerant). When an ask declares expected_args for
a tool, the observed input for that tool must be a superset of the expected
key/values. Latency uses p50/p95 over dt_total; the cold warm-up ask is excluded
upstream by the runner, so every AskResult here is a warm measurement.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from poseidon.bench.golden import Ask


@dataclass
class AskResult:
    ask: Ask
    observed_tools: list[str]
    observed_args: list[dict]
    dt_total: float
    is_error: bool
    text: str = ""


@dataclass
class Scorecard:
    model: str
    n: int
    correctness: float          # fraction of asks with a tool-set match
    error_rate: float
    latency_p50: float
    latency_p95: float
    per_ask: list[dict] = field(default_factory=list)


def score_ask(ask: Ask, observed_tools: list[str],
              observed_args: list[dict] | None = None) -> bool:
    if set(observed_tools) != set(ask.expected_tools):
        return False
    if not ask.expected_args:
        return True
    observed_args = observed_args or []
    by_tool: dict[str, dict] = {}
    for name, args in zip(observed_tools, observed_args):
        by_tool.setdefault(name, args or {})
    for tool, expected in ask.expected_args.items():
        got = by_tool.get(tool, {})
        if any(got.get(k) != v for k, v in expected.items()):
            return False
    return True


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (p / 100) * (len(ordered) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def build_scorecard(model: str, results: list[AskResult]) -> Scorecard:
    n = len(results)
    passes = sum(
        1 for r in results
        if not r.is_error and score_ask(r.ask, r.observed_tools, r.observed_args)
    )
    errors = sum(1 for r in results if r.is_error)
    latencies = [r.dt_total for r in results if not r.is_error]
    per_ask = [
        {
            "id": r.ask.id,
            "category": r.ask.category,
            "expected": list(r.ask.expected_tools),
            "observed": r.observed_tools,
            "match": (not r.is_error) and score_ask(r.ask, r.observed_tools, r.observed_args),
            "dt_total": round(r.dt_total, 3),
            "is_error": r.is_error,
        }
        for r in results
    ]
    return Scorecard(
        model=model,
        n=n,
        correctness=(passes / n) if n else 0.0,
        error_rate=(errors / n) if n else 0.0,
        latency_p50=round(percentile(latencies, 50), 3),
        latency_p95=round(percentile(latencies, 95), 3),
        per_ask=per_ask,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bench_scoring.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/src/sailingnaturali/naturali-agents
git add poseidon/bench/scoring.py tests/test_bench_scoring.py
git commit -m "feat(bench): per-ask scoring + scorecard aggregation"
```

---

## Task 4: Decision rule (swap verdict)

Implements ADR 0002's rule: a candidate replaces the incumbent only if it is faster on p50 warm hop AND within tolerance on correctness (≥ incumbent − ε) AND session-stable (no errors). Pure.

**Files:**
- Create: `naturali-agents/poseidon/bench/decision.py`
- Test: `naturali-agents/tests/test_bench_decision.py`

- [ ] **Step 1: Write the failing test**

Create `naturali-agents/tests/test_bench_decision.py`:

```python
from poseidon.bench.scoring import Scorecard
from poseidon.bench.decision import compare, Verdict


def _card(model, correctness, p50, error_rate=0.0):
    return Scorecard(model=model, n=8, correctness=correctness, error_rate=error_rate,
                     latency_p50=p50, latency_p95=p50 + 1)


def test_faster_and_as_accurate_swaps():
    base = _card("sonnet", 1.0, 6.0)
    cand = _card("oss-14b", 1.0, 4.0)
    v = compare(base, cand, eps=0.05)
    assert isinstance(v, Verdict)
    assert v.swap is True


def test_faster_but_less_accurate_beyond_eps_holds():
    base = _card("sonnet", 1.0, 6.0)
    cand = _card("oss-14b", 0.80, 4.0)
    v = compare(base, cand, eps=0.05)
    assert v.swap is False
    assert "correctness" in v.reason


def test_within_eps_correctness_ok():
    base = _card("sonnet", 1.0, 6.0)
    cand = _card("oss-14b", 0.96, 4.0)
    assert compare(base, cand, eps=0.05).swap is True


def test_slower_holds_even_if_more_accurate():
    base = _card("sonnet", 0.9, 4.0)
    cand = _card("oss-14b", 1.0, 5.0)
    v = compare(base, cand, eps=0.05)
    assert v.swap is False
    assert "faster" in v.reason


def test_candidate_with_errors_holds():
    base = _card("sonnet", 1.0, 6.0)
    cand = _card("oss-14b", 1.0, 4.0, error_rate=0.1)
    v = compare(base, cand, eps=0.05)
    assert v.swap is False
    assert "stable" in v.reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bench_decision.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'poseidon.bench.decision'`

- [ ] **Step 3: Write minimal implementation**

Create `naturali-agents/poseidon/bench/decision.py`:

```python
"""poseidon.bench.decision — ADR-0002 swap rule.

A candidate replaces the incumbent primary only if ALL hold:
  1. faster on p50 warm hop,
  2. correctness >= incumbent - eps,
  3. session-stable (zero error rate).
Returns a Verdict with a human reason naming the first failing condition.
"""
from __future__ import annotations

from dataclasses import dataclass

from poseidon.bench.scoring import Scorecard


@dataclass
class Verdict:
    swap: bool
    reason: str


def compare(incumbent: Scorecard, candidate: Scorecard, eps: float = 0.05) -> Verdict:
    if candidate.error_rate > 0:
        return Verdict(False, f"candidate not session-stable "
                              f"(error_rate={candidate.error_rate:.2f})")
    if candidate.latency_p50 >= incumbent.latency_p50:
        return Verdict(False, f"candidate not faster "
                              f"(p50 {candidate.latency_p50:.2f}s vs "
                              f"incumbent {incumbent.latency_p50:.2f}s)")
    if candidate.correctness < incumbent.correctness - eps:
        return Verdict(False, f"candidate correctness below tolerance "
                              f"({candidate.correctness:.2f} < "
                              f"{incumbent.correctness:.2f} - {eps})")
    return Verdict(True, f"{candidate.model} is faster "
                         f"({candidate.latency_p50:.2f}s vs "
                         f"{incumbent.latency_p50:.2f}s) and within correctness "
                         f"tolerance — replaces {incumbent.model}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bench_decision.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/src/sailingnaturali/naturali-agents
git add poseidon/bench/decision.py tests/test_bench_decision.py
git commit -m "feat(bench): ADR-0002 swap decision rule"
```

---

## Task 5: Report (markdown + JSON; ADR-pasteable block)

Renders a `Scorecard` to a JSON file and a markdown block, and produces the exact snippet to paste under ADR 0002 § Benchmark results. Pure string/IO.

**Files:**
- Create: `naturali-agents/poseidon/bench/report.py`
- Test: `naturali-agents/tests/test_bench_report.py`

- [ ] **Step 1: Write the failing test**

Create `naturali-agents/tests/test_bench_report.py`:

```python
import json

from poseidon.bench.scoring import Scorecard
from poseidon.bench.report import render_markdown, write_results


def _card():
    return Scorecard(
        model="claude-sonnet-4-6", n=8, correctness=0.875, error_rate=0.0,
        latency_p50=5.6, latency_p95=7.1,
        per_ask=[{"id": "depth", "category": "engineer-direct",
                  "expected": ["mcp__signalk__depth_state"],
                  "observed": ["mcp__signalk__depth_state"], "match": True,
                  "dt_total": 5.6, "is_error": False}],
    )


def test_render_markdown_contains_headline_numbers():
    md = render_markdown(_card(), run_date="2026-06-13")
    assert "claude-sonnet-4-6" in md
    assert "87.5%" in md          # correctness as percent
    assert "5.6" in md            # p50
    assert "depth" in md          # per-ask row


def test_write_results_emits_json_and_md(tmp_path):
    paths = write_results(_card(), out_dir=tmp_path, run_date="2026-06-13")
    data = json.loads(paths["json"].read_text())
    assert data["model"] == "claude-sonnet-4-6"
    assert data["correctness"] == 0.875
    assert paths["md"].read_text().startswith("### Benchmark run")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bench_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'poseidon.bench.report'`

- [ ] **Step 3: Write minimal implementation**

Create `naturali-agents/poseidon/bench/report.py`:

```python
"""poseidon.bench.report — scorecard → JSON + markdown, written to a results dir.

render_markdown() returns the exact block to paste under ADR 0002 § Benchmark
results. write_results() persists <date>-<model>.json and .md under out_dir
(default dev/bench-results/).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from poseidon.bench.scoring import Scorecard

_DEFAULT_OUT = Path(__file__).resolve().parents[2] / "dev" / "bench-results"


def render_markdown(card: Scorecard, run_date: str) -> str:
    lines = [
        f"### Benchmark run {run_date} — {card.model}",
        "",
        f"- Asks: {card.n} | correctness: {card.correctness * 100:.1f}% | "
        f"error rate: {card.error_rate * 100:.1f}%",
        f"- Warm-hop latency: p50 {card.latency_p50:.2f}s | p95 {card.latency_p95:.2f}s",
        "",
        "| ask | category | expected | observed | match | dt_total (s) |",
        "|-----|----------|----------|----------|-------|--------------|",
    ]
    for row in card.per_ask:
        lines.append(
            f"| {row['id']} | {row['category']} | "
            f"{', '.join(row['expected'])} | {', '.join(row['observed']) or '—'} | "
            f"{'✓' if row['match'] else '✗'} | {row['dt_total']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def write_results(card: Scorecard, out_dir: Path | None = None,
                  run_date: str = "") -> dict[str, Path]:
    out_dir = Path(out_dir or _DEFAULT_OUT)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_model = card.model.replace("/", "_").replace(":", "_")
    stem = f"{run_date}-{safe_model}" if run_date else safe_model
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(asdict(card), indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(card, run_date), encoding="utf-8")
    return {"json": json_path, "md": md_path}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bench_report.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/src/sailingnaturali/naturali-agents
git add poseidon/bench/report.py tests/test_bench_report.py
git commit -m "feat(bench): JSON + markdown scorecard report"
```

---

## Task 6: Async live runner

Builds a `ClaudeSDKClient` from the production `crew_options()` with the model overridden, warms one throwaway ask, then runs each golden ask (optionally `repeat` times), capturing tools/args/timing via `collect_turn`. This is the only module that touches the live SDK + MCP servers; it is not unit-tested (mirrors `dev/acp_spike.py`). It is smoke-verified in Task 8 by running the Sonnet baseline.

**Files:**
- Create: `naturali-agents/poseidon/bench/runner.py`

- [ ] **Step 1: Write the runner**

Create `naturali-agents/poseidon/bench/runner.py`:

```python
"""poseidon.bench.runner — live runner over one warm SDK session.

Reuses the production crew_options() (real system prompt, tool subsets,
subagents) and overrides only the model, so the benchmark measures the agent as
shipped. One throwaway warm-up ask absorbs connect/cold-cache cost; every scored
ask is therefore warm. Engine swap = pass a different model id (Sonnet/Fable via
the Anthropic API; an OSS model needs ANTHROPIC_BASE_URL pointed at a compatible
gateway — a Phase-1 extension, not exercised here).
"""
from __future__ import annotations

import time

from claude_agent_sdk import ClaudeSDKClient

from poseidon.bench.collect import collect_turn
from poseidon.bench.golden import Ask, load_golden_asks
from poseidon.bench.scoring import AskResult
from poseidon.profiles import crew_options


async def _run_one(client: ClaudeSDKClient, ask: Ask) -> AskResult:
    t0 = time.monotonic()
    await client.query(ask.prompt)
    messages = [m async for m in client.receive_response()]
    dt = time.monotonic() - t0
    obs = collect_turn(messages)
    return AskResult(
        ask=ask,
        observed_tools=obs.tools,
        observed_args=obs.tool_inputs,
        dt_total=dt,
        is_error=obs.is_error,
        text=obs.text,
    )


async def run_benchmark(model: str, repeat: int = 1,
                        asks: list[Ask] | None = None) -> list[AskResult]:
    asks = asks or load_golden_asks()
    options = crew_options()
    options.model = model
    client = ClaudeSDKClient(options=options)
    await client.connect()
    try:
        # Throwaway warm-up: pay connect/cold-cache cost off the clock.
        await client.query("Hello.")
        async for _ in client.receive_response():
            pass

        results: list[AskResult] = []
        for _ in range(repeat):
            for ask in asks:
                results.append(await _run_one(client, ask))
        return results
    finally:
        await client.disconnect()
```

- [ ] **Step 2: Verify it imports cleanly (no live call yet)**

Run: `uv run python -c "import poseidon.bench.runner; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
cd ~/src/sailingnaturali/naturali-agents
git add poseidon/bench/runner.py
git commit -m "feat(bench): async live runner over one warm SDK session"
```

---

## Task 7: CLI entry

Wires runner → scoring → report. `python -m poseidon.bench --model <id> [--repeat N] [--baseline <json>]`. When `--baseline` is given, also prints the swap verdict.

**Files:**
- Create: `naturali-agents/poseidon/bench/__main__.py`

- [ ] **Step 1: Write the CLI**

Create `naturali-agents/poseidon/bench/__main__.py`:

```python
"""python -m poseidon.bench — run the ADR-0002 benchmark and write a scorecard.

Examples:
  uv run python -m poseidon.bench --model claude-sonnet-4-6
  uv run python -m poseidon.bench --model oss-candidate --repeat 3 \
      --baseline dev/bench-results/2026-06-13-claude-sonnet-4-6.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path

from poseidon import config
from poseidon.bench.decision import compare
from poseidon.bench.report import write_results
from poseidon.bench.runner import run_benchmark
from poseidon.bench.scoring import Scorecard, build_scorecard


def _load_baseline(path: str) -> Scorecard:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Scorecard(**data)


def main() -> None:
    parser = argparse.ArgumentParser(prog="poseidon.bench")
    parser.add_argument("--model", default=config.MODEL,
                        help="engine model id (default: config.MODEL)")
    parser.add_argument("--repeat", type=int, default=1,
                        help="run the golden set N times (stability)")
    parser.add_argument("--baseline", default=None,
                        help="incumbent scorecard JSON to compare against")
    parser.add_argument("--eps", type=float, default=0.05,
                        help="correctness tolerance for the swap rule")
    args = parser.parse_args()

    # Env file holds ANTHROPIC_API_KEY (interim ~/.hermes/.env).
    config.load_env_file(config.ENV_FILE)

    results = asyncio.run(run_benchmark(args.model, repeat=args.repeat))
    card = build_scorecard(model=args.model, results=results)
    run_date = date.today().isoformat()
    paths = write_results(card, run_date=run_date)

    print(f"\nmodel={card.model}  n={card.n}  "
          f"correctness={card.correctness * 100:.1f}%  "
          f"error_rate={card.error_rate * 100:.1f}%")
    print(f"warm-hop p50={card.latency_p50:.2f}s  p95={card.latency_p95:.2f}s")
    print(f"wrote {paths['json']}  {paths['md']}")

    if args.baseline:
        verdict = compare(_load_baseline(args.baseline), card, eps=args.eps)
        print(f"\nSWAP={verdict.swap} — {verdict.reason}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the CLI parses (help, no live call)**

Run: `uv run python -m poseidon.bench --help`
Expected: usage text listing `--model`, `--repeat`, `--baseline`, `--eps`

- [ ] **Step 3: Commit**

```bash
cd ~/src/sailingnaturali/naturali-agents
git add poseidon/bench/__main__.py
git commit -m "feat(bench): python -m poseidon.bench CLI"
```

---

## Task 8: Run the Sonnet baseline + record it in ADR 0002

This is the live run. It requires the MCP servers reachable (signalk at `naturalaspi.local:3000` serving the mocked vessel — confirm with `ssh naturalaspi docker ps | grep signalk`) and `ANTHROPIC_API_KEY` in `~/.hermes/.env`.

- [ ] **Step 1: Confirm prerequisites**

Run: `ssh naturalaspi docker ps | grep signalk && grep -q ANTHROPIC_API_KEY ~/.hermes/.env && echo "prereqs ok"`
Expected: a running `signalk` container line, then `prereqs ok`

- [ ] **Step 2: Run the baseline benchmark against Sonnet 4.6**

Run: `uv run python -m poseidon.bench --model claude-sonnet-4-6`
Expected: a summary block (model, n=8, correctness %, p50/p95) and two written paths under `dev/bench-results/`. The p50 should land near the ADR-0001 spike's 5.5–7s; correctness should be high on the root-direct asks. If the run errors on every ask, stop and debug connectivity (MCP servers / API key) — do not record a degenerate scorecard.

- [ ] **Step 3: Sanity-check the scorecard**

Run: `cat dev/bench-results/$(date +%F)-claude-sonnet-4-6.md`
Expected: a per-ask table; verify the root-direct asks (depth/battery/alarms/wind/current/anchorage) matched their expected tools. Note any mismatches in the commit message rather than hand-editing the data.

- [ ] **Step 4: Commit the baseline artifacts (naturali-agents repo)**

```bash
cd ~/src/sailingnaturali/naturali-agents
git add dev/bench-results/
git commit -m "bench: record Sonnet 4.6 baseline scorecard (ADR 0002)"
```

- [ ] **Step 5: Append the baseline to ADR 0002 (planning repo)**

In `~/src/sailingnaturali/planning/docs/adr/0002-model-strategy.md`, replace the placeholder under `## Benchmark results`:

```
_None yet. First run (Sonnet 4.6 baseline) to be appended when the harness
ships._
```

with the contents of `dev/bench-results/<date>-claude-sonnet-4-6.md` (the `render_markdown` block). Then:

```bash
cd ~/src/sailingnaturali/planning
git add docs/adr/0002-model-strategy.md
git commit -m "adr: 0002 — record Sonnet 4.6 benchmark baseline"
git push
```

---

## Self-Review

**Spec coverage (against ADR 0002 § Benchmark harness):**
- Home in `naturali-agents/dev/` → results land in `dev/bench-results/`; logic moved into `poseidon/bench/` for testability (documented deviation, Architecture note). ✓
- Generalizes `dev/acp_spike.py` (drive runtime headless, one session, timed asks) → runner.py, one warm session. ✓
- Engine-swappable via config switch → `--model` overrides `options.model`; OSS-via-`ANTHROPIC_BASE_URL` noted as Phase-1 extension. ✓
- Golden ask set across the agent surface with expected tools → Task 1 (Navigator-root-direct core + a delegated ask). ✓
- Metrics: warm-hop latency p50/p95 (Task 3), tool-call correctness incl. optional args (Task 3), session stability via error rate + `--repeat` (Tasks 3/6), adequacy → consciously deferred (see gap below). 
- Pass bar / decision rule (faster AND within ε correctness AND stable) → Task 4. ✓
- Scorecard appended to ADR → Task 8. ✓

**Known gaps (intentional, not placeholders):**
- *Answer adequacy* (ADR metric 3) is not auto-scored in v1 — it's the coarse rubric/spot-check the ADR itself calls "deliberately coarse." The per-ask `text` is captured in `AskResult` and surfaced for manual spot-check; an automated adequacy judge is a follow-up. Flagged here rather than faked.
- *Subagent-internal tool calls* aren't captured (delegated asks score on `Agent`); v2 follow-up noted in `golden.py`.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every run step shows the command + expected output. ✓

**Type consistency:** `Ask`, `AskResult`, `Scorecard`, `Verdict`, `TurnObservation` names and fields match across golden.py → collect.py → scoring.py → decision.py → report.py → runner.py → `__main__.py`. `score_ask(ask, observed_tools, observed_args=None)`, `build_scorecard(model, results)`, `compare(incumbent, candidate, eps)`, `write_results(card, out_dir, run_date)`, `render_markdown(card, run_date)`, `run_benchmark(model, repeat, asks)` signatures are consistent between their definitions and call sites. ✓
