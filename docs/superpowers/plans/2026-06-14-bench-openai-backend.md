# Benchmark OpenAI/Ollama Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a native OpenAI/Ollama benchmark backend — a flat agent loop that calls Ollama `/v1` over httpx and executes MCP tools itself — so the harness can score local OSS models (first target qwen3.6), reusing the existing scoring/report.

**Architecture:** Two new modules (`oai_tools.py` for MCP connection + OpenAI-schema conversion + tool dispatch; `oai_runner.py` for the chat loop producing `AskResult`s), an optional `expected_tools_flat` field on `Ask` for the no-subagent topology, and a `--backend openai` CLI flag. The Claude SDK path is unchanged and remains default. No new dependencies (`mcp` client + `httpx` already present). Spec: `docs/superpowers/specs/2026-06-14-bench-openai-backend-design.md`.

**Tech Stack:** Python 3.11+, `httpx` (Ollama `/v1`), `mcp` (stdio client), pytest, `uv`.

---

## File Structure

- Modify: `naturali-agents/poseidon/bench/golden.py` (+ `expected_tools_flat`) + `golden_asks.json`
- Create: `naturali-agents/poseidon/bench/oai_tools.py` (MCP→OpenAI tool provider)
- Create: `naturali-agents/poseidon/bench/oai_runner.py` (flat agent loop)
- Modify: `naturali-agents/poseidon/bench/__main__.py` (backend selection)
- Create: `naturali-agents/tests/test_bench_oai_tools.py`, `naturali-agents/tests/test_bench_oai_runner.py`
- Modify: `naturali-agents/tests/test_bench_golden.py` (one assertion)
- Modify: `planning/docs/adr/0002-model-strategy.md` (add the qwen3.6 result, Task 7)
- Regenerate: `naturali-agents/dev/bench-results/<date>-qwen3.6_latest.{json,md}` (Task 7)

All `uv`/`pytest`/`git` commands for Tasks 1–6 run from `~/src/sailingnaturali/naturali-agents`.

---

## Task 1: Add `expected_tools_flat` to the golden set

**Files:**
- Modify: `poseidon/bench/golden.py`
- Modify: `poseidon/bench/golden_asks.json`
- Test: `tests/test_bench_golden.py`

- [ ] **Step 1: Add the failing test**

In `tests/test_bench_golden.py`, append:

```python
def test_explain_alarm_has_flat_expectation():
    by_id = {a.id: a for a in load_golden_asks()}
    assert by_id["explain-alarm"].expected_tools_flat == ("mcp__signalk__get_active_alarms",)


def test_expected_tools_flat_defaults_empty():
    by_id = {a.id: a for a in load_golden_asks()}
    assert by_id["depth"].expected_tools_flat == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_bench_golden.py -v`
Expected: FAIL — `Ask` has no `expected_tools_flat` attribute yet.

- [ ] **Step 3: Add the field + loader support**

In `poseidon/bench/golden.py`, add the field to the `Ask` dataclass (after `expected_args`):

```python
@dataclass(frozen=True)
class Ask:
    id: str
    category: str
    prompt: str
    expected_tools: tuple[str, ...]
    multi_tool: bool
    expected_args: dict = field(default_factory=dict)
    expected_tools_flat: tuple[str, ...] = ()
```

And in `load_golden_asks`, add the new key to the `Ask(...)` construction:

```python
        Ask(
            id=row["id"],
            category=row["category"],
            prompt=row["prompt"],
            expected_tools=tuple(row["expected_tools"]),
            multi_tool=bool(row.get("multi_tool", False)),
            expected_args=row.get("expected_args", {}),
            expected_tools_flat=tuple(row.get("expected_tools_flat", ())),
        )
```

- [ ] **Step 4: Annotate explain-alarm in `golden_asks.json`**

In `poseidon/bench/golden_asks.json`, the `explain-alarm` object currently has
`"expected_tools": ["Agent"]` and `"multi_tool": false`. Add the flat key so the
object reads:

```json
  {
    "id": "explain-alarm",
    "category": "delegated",
    "prompt": "What does the low house battery alarm mean and what should I do?",
    "expected_tools": ["Agent"],
    "expected_tools_flat": ["mcp__signalk__get_active_alarms"],
    "multi_tool": false
  }
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/test_bench_golden.py -v`
Expected: PASS (6 tests: 4 existing + 2 new). The existing `test_single_tool_asks_expect_exactly_one_tool` still holds (it checks `expected_tools`, unaffected).

- [ ] **Step 6: Commit**

```bash
git add poseidon/bench/golden.py poseidon/bench/golden_asks.json tests/test_bench_golden.py
git commit -m "feat(bench): expected_tools_flat for the no-subagent flat backend"
```

---

## Task 2: `oai_tools.py` — pure schema helpers

**Files:**
- Create: `poseidon/bench/oai_tools.py`
- Test: `tests/test_bench_oai_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bench_oai_tools.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from poseidon.bench.oai_tools import split_tool_name, to_openai_schema


@dataclass
class FakeMcpTool:
    name: str
    description: str = ""
    inputSchema: dict = field(default_factory=dict)


def test_to_openai_schema_builds_prefixed_function():
    tool = FakeMcpTool(name="depth_state", description="Depth below transducer",
                       inputSchema={"type": "object", "properties": {}})
    schema = to_openai_schema("signalk", tool)
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "mcp__signalk__depth_state"
    assert schema["function"]["description"] == "Depth below transducer"
    assert schema["function"]["parameters"] == {"type": "object", "properties": {}}


def test_to_openai_schema_defaults_empty_params():
    schema = to_openai_schema("weather", FakeMcpTool(name="get_marine_forecast"))
    assert schema["function"]["parameters"] == {"type": "object", "properties": {}}
    assert schema["function"]["description"] == ""


def test_split_tool_name_happy():
    assert split_tool_name("mcp__signalk__get_local_time") == ("signalk", "get_local_time")


def test_split_tool_name_rejects_non_mcp():
    with pytest.raises(ValueError):
        split_tool_name("Agent")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_bench_oai_tools.py -v`
Expected: FAIL — `No module named 'poseidon.bench.oai_tools'`.

- [ ] **Step 3: Write the pure helpers**

Create `poseidon/bench/oai_tools.py`:

```python
"""poseidon.bench.oai_tools — MCP servers adapted to OpenAI tools.

For the native OpenAI/Ollama benchmark backend: connect the same stdio MCP
servers the SDK uses (mcp_servers.json), expose their tools as OpenAI function
schemas named mcp__<server>__<tool>, and dispatch tool calls back to the right
server. The pure helpers (to_openai_schema, split_tool_name) are unit-tested; the
async McpToolset is exercised by the live benchmark run.
"""
from __future__ import annotations

from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from poseidon.profiles import load_mcp_servers


def to_openai_schema(server: str, mcp_tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": f"mcp__{server}__{mcp_tool.name}",
            "description": getattr(mcp_tool, "description", "") or "",
            "parameters": getattr(mcp_tool, "inputSchema", None)
            or {"type": "object", "properties": {}},
        },
    }


def split_tool_name(name: str) -> tuple[str, str]:
    if not name.startswith("mcp__") or name.count("__") < 2:
        raise ValueError(f"not an mcp tool name: {name!r}")
    _, server, tool = name.split("__", 2)
    return server, tool
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_bench_oai_tools.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add poseidon/bench/oai_tools.py tests/test_bench_oai_tools.py
git commit -m "feat(bench): oai_tools schema helpers (to_openai_schema, split_tool_name)"
```

---

## Task 3: `oai_tools.py` — `McpToolset` + `create_toolset`

The async layer that starts the MCP servers and dispatches calls. Not unit-tested
(needs live stdio servers); verified by import + the Task 7 live run. Everything
runs in one event loop / one task (run via `asyncio.run` in Task 5) to avoid
anyio cancel-scope issues with `AsyncExitStack`.

**Files:**
- Modify: `poseidon/bench/oai_tools.py`

- [ ] **Step 1: Append the toolset class + factory**

Add to `poseidon/bench/oai_tools.py`:

```python
class McpToolset:
    """Live MCP connections for the OpenAI backend. Build via create_toolset();
    use within a single asyncio task; call aclose() to tear down."""

    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self._index: dict[str, tuple[ClientSession, object]] = {}  # full name -> (session, tool)

    async def _add_server(self, server: str, cfg: dict) -> None:
        params = StdioServerParameters(
            command=cfg["command"], args=cfg.get("args", []), env=cfg.get("env"))
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        for tool in (await session.list_tools()).tools:
            self._index[f"mcp__{server}__{tool.name}"] = (session, tool)

    def openai_schemas(self) -> list[dict]:
        return [to_openai_schema(split_tool_name(name)[0], tool)
                for name, (_session, tool) in self._index.items()]

    async def call(self, name: str, arguments: dict) -> str:
        entry = self._index.get(name)
        if entry is None:
            return f"ERROR: unknown tool {name}"
        session, _tool = entry
        try:
            result = await session.call_tool(split_tool_name(name)[1], arguments)
        except Exception as e:  # tool errors must not kill the loop
            return f"ERROR: {e}"
        return "".join(getattr(b, "text", "") for b in (result.content or []))

    async def aclose(self) -> None:
        await self._stack.aclose()


async def create_toolset(servers: dict | None = None) -> McpToolset:
    servers = servers if servers is not None else load_mcp_servers()
    toolset = McpToolset()
    try:
        for server, cfg in servers.items():
            await toolset._add_server(server, cfg)
    except Exception:
        await toolset.aclose()
        raise
    return toolset
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `uv run python -c "import poseidon.bench.oai_tools as t; print(hasattr(t, 'McpToolset'), hasattr(t, 'create_toolset'))"`
Expected: `True True`

- [ ] **Step 3: Commit**

```bash
git add poseidon/bench/oai_tools.py
git commit -m "feat(bench): McpToolset — live MCP connect + dispatch for OpenAI backend"
```

---

## Task 4: `oai_runner.py` — pure helpers

**Files:**
- Create: `poseidon/bench/oai_runner.py`
- Test: `tests/test_bench_oai_runner.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bench_oai_runner.py`:

```python
from __future__ import annotations

from poseidon.bench.golden import Ask
from poseidon.bench.oai_runner import flat_scored_ask, parse_choice


def _resp(message: dict, finish_reason: str = "stop") -> dict:
    return {"choices": [{"message": message, "finish_reason": finish_reason}]}


def test_parse_choice_with_tool_calls():
    tc = [{"id": "c1", "function": {"name": "mcp__signalk__depth_state", "arguments": "{}"}}]
    tool_calls, text, finish = parse_choice(_resp({"role": "assistant", "content": None,
                                                   "tool_calls": tc}, "tool_calls"))
    assert tool_calls == tc
    assert text == ""
    assert finish == "tool_calls"


def test_parse_choice_final_text():
    tool_calls, text, finish = parse_choice(_resp({"role": "assistant", "content": "Twelve metres."}))
    assert tool_calls == []
    assert text == "Twelve metres."
    assert finish == "stop"


def test_flat_scored_ask_substitutes_when_flat_present():
    ask = Ask(id="explain-alarm", category="delegated", prompt="p",
              expected_tools=("Agent",), multi_tool=False,
              expected_tools_flat=("mcp__signalk__get_active_alarms",))
    scored = flat_scored_ask(ask)
    assert scored.expected_tools == ("mcp__signalk__get_active_alarms",)


def test_flat_scored_ask_unchanged_without_flat():
    ask = Ask(id="depth", category="engineer-direct", prompt="p",
              expected_tools=("mcp__signalk__depth_state",), multi_tool=False)
    assert flat_scored_ask(ask) is ask
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_bench_oai_runner.py -v`
Expected: FAIL — `No module named 'poseidon.bench.oai_runner'`.

- [ ] **Step 3: Write the pure helpers**

Create `poseidon/bench/oai_runner.py`:

```python
"""poseidon.bench.oai_runner — native OpenAI/Ollama flat-agent benchmark runner.

Calls an OpenAI-compatible /chat/completions endpoint over httpx, executing MCP
tools itself via McpToolset (flat: all tools, no subagents). Produces AskResults
the existing scoring/report consume. The pure helpers (parse_choice,
flat_scored_ask) are unit-tested; the async loop is exercised by the live run.
"""
from __future__ import annotations

import contextlib
import json
import time
from dataclasses import replace

import httpx

from poseidon import prompts
from poseidon.bench.golden import Ask, load_golden_asks
from poseidon.bench.oai_tools import create_toolset
from poseidon.bench.scoring import AskResult


def parse_choice(response_json: dict) -> tuple[list[dict], str, str]:
    choice = response_json["choices"][0]
    message = choice.get("message", {})
    tool_calls = message.get("tool_calls") or []
    text = message.get("content") or ""
    return tool_calls, text, choice.get("finish_reason", "")


def flat_scored_ask(ask: Ask) -> Ask:
    """Score a flat-backend run against expected_tools_flat when set (no Agent
    wrapper exists off-SDK), leaving scoring.py untouched."""
    if ask.expected_tools_flat:
        return replace(ask, expected_tools=ask.expected_tools_flat)
    return ask
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_bench_oai_runner.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add poseidon/bench/oai_runner.py tests/test_bench_oai_runner.py
git commit -m "feat(bench): oai_runner pure helpers (parse_choice, flat_scored_ask)"
```

---

## Task 5: `oai_runner.py` — the async agent loop

**Files:**
- Modify: `poseidon/bench/oai_runner.py`

- [ ] **Step 1: Append the loop functions**

Add to `poseidon/bench/oai_runner.py`:

```python
async def run_ask_openai(http: httpx.AsyncClient, base_url: str, model: str,
                         system_prompt: str, schemas: list[dict], toolset,
                         ask: Ask, max_rounds: int = 10) -> AskResult:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": ask.prompt},
    ]
    observed: dict[str, dict] = {}  # insertion-ordered; first-seen args per tool
    text = ""
    is_error = False
    t0 = time.monotonic()
    try:
        for _ in range(max_rounds):
            resp = await http.post(
                base_url.rstrip("/") + "/chat/completions",
                json={"model": model, "messages": messages, "tools": schemas,
                      "tool_choice": "auto", "stream": False},
            )
            resp.raise_for_status()
            tool_calls, text, _finish = parse_choice(resp.json())
            if not tool_calls:
                break
            messages.append({"role": "assistant", "content": text or None,
                             "tool_calls": tool_calls})
            for tc in tool_calls:
                fn = tc.get("function", {}).get("name", "")
                try:
                    args = json.loads(tc.get("function", {}).get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                observed.setdefault(fn, args)
                result = await toolset.call(fn, args)
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                                 "content": result})
    except Exception as e:
        is_error = True
        text = text or f"ERROR: {e}"
    dt = time.monotonic() - t0
    return AskResult(ask=flat_scored_ask(ask), observed_tools=list(observed),
                     observed_args=list(observed.values()), dt_total=dt,
                     is_error=is_error, text=text)


async def run_benchmark_openai(model: str, base_url: str, repeat: int = 1,
                               asks: list[Ask] | None = None) -> list[AskResult]:
    asks = asks or load_golden_asks()
    system_prompt = prompts.crew_system_prompt()
    toolset = await create_toolset()
    try:
        schemas = toolset.openai_schemas()
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as http:
            # Throwaway warm-up: load the model off the clock.
            with contextlib.suppress(Exception):
                await http.post(
                    base_url.rstrip("/") + "/chat/completions",
                    json={"model": model,
                          "messages": [{"role": "user", "content": "Hello."}],
                          "stream": False},
                )
            results: list[AskResult] = []
            for _ in range(repeat):
                for ask in asks:
                    results.append(await run_ask_openai(
                        http, base_url, model, system_prompt, schemas, toolset, ask))
            return results
    finally:
        await toolset.aclose()
```

- [ ] **Step 2: Verify it imports cleanly + pure tests still pass**

Run: `uv run python -c "import poseidon.bench.oai_runner as r; print(hasattr(r,'run_benchmark_openai'), hasattr(r,'run_ask_openai'))"`
Expected: `True True`
Run: `uv run pytest tests/test_bench_oai_runner.py -q`
Expected: PASS (4).

- [ ] **Step 3: Commit**

```bash
git add poseidon/bench/oai_runner.py
git commit -m "feat(bench): openai flat-agent loop (run_ask_openai, run_benchmark_openai)"
```

---

## Task 6: CLI backend selection

**Files:**
- Modify: `poseidon/bench/__main__.py`

- [ ] **Step 1: Add the flags + branch**

In `poseidon/bench/__main__.py`, add two arguments inside `main()` (after the existing `--eps` argument):

```python
    parser.add_argument("--backend", choices=["sdk", "openai"], default="sdk",
                        help="agent backend: sdk (Claude Agent SDK) or openai (Ollama /v1)")
    parser.add_argument("--base-url", default="http://localhost:11434/v1",
                        help="OpenAI-compatible base URL (openai backend)")
```

Then REPLACE the existing results line:
```python
    results = asyncio.run(run_benchmark(args.model, repeat=args.repeat))
```
with:
```python
    if args.backend == "openai":
        from poseidon.bench.oai_runner import run_benchmark_openai
        results = asyncio.run(
            run_benchmark_openai(args.model, args.base_url, repeat=args.repeat))
    else:
        results = asyncio.run(run_benchmark(args.model, repeat=args.repeat))
```

(The existing top-level `from poseidon.bench.runner import run_benchmark` import stays; the openai runner is imported lazily so the SDK path doesn't pay its import.)

- [ ] **Step 2: Verify the CLI parses**

Run: `uv run python -m poseidon.bench --help`
Expected: usage text now lists `--backend {sdk,openai}` and `--base-url`.

- [ ] **Step 3: Run the full bench unit suite (no regressions)**

Run: `uv run pytest tests/test_bench_*.py -q`
Expected: PASS (all bench unit tests across golden/collect/scoring/decision/report/oai_tools/oai_runner).

- [ ] **Step 4: Commit**

```bash
git add poseidon/bench/__main__.py
git commit -m "feat(bench): --backend {sdk,openai} + --base-url CLI selection"
```

---

## Task 7: Live qwen3.6 run + record

Live run (needs Ollama serving qwen3.6 on `localhost:11434`, the Pi SignalK
reachable, and the MCP servers runnable). Updates the ADR in the **`planning`** repo.

- [ ] **Step 1: Confirm prerequisites**

Run: `curl -s -m 5 http://localhost:11434/api/tags | grep -q "qwen3.6" && ssh naturalaspi docker ps | grep -q signalk && echo "prereqs ok"`
Expected: `prereqs ok`. If not, stop and report BLOCKED (external infra).

- [ ] **Step 2: Run the benchmark against qwen3.6**

Run: `uv run python -m poseidon.bench --backend openai --model qwen3.6:latest`
Expected: a summary block (model=qwen3.6:latest, n=8, correctness %, p50/p95) and written `dev/bench-results/2026-06-14-qwen3.6_latest.{json,md}` (the run-date stamp is today). First call may be slow while the 24 GB model loads (absorbed by the warm-up). If every ask errors, stop and debug connectivity (Ollama / MCP servers / Pi) — do not record a degenerate scorecard.

- [ ] **Step 3: Sanity-check the scorecard**

Run: `cat dev/bench-results/2026-06-14-qwen3.6_latest.md`
Expected: a per-ask table. Note which asks matched. `explain-alarm` is scored against its flat expectation (`get_active_alarms`). Note anything notable in the commit message rather than editing data.

- [ ] **Step 4: Commit the artifacts (naturali-agents repo)**

```bash
git add dev/bench-results/
git commit -m "bench: qwen3.6 baseline via native OpenAI backend (flat topology)"
```

- [ ] **Step 5: Add the qwen3.6 result to ADR 0002 (planning repo)**

In `~/src/sailingnaturali/planning/docs/adr/0002-model-strategy.md`, under `## Benchmark results`, add a new subsection **after** the existing Sonnet run (do not replace it):
1. Paste the contents of `dev/bench-results/2026-06-14-qwen3.6_latest.md` (its `### Benchmark run …` block + table).
2. Add a 2–3 sentence note: this is the **first OSS data point**, run via the **native OpenAI flat-agent backend** (Ollama, no Claude SDK, no subagents) — so it reflects how an OSS model would actually deploy on the boat, and is **not** a literal head-to-head with the SDK-Sonnet scorecard above (different topology). State the headline correctness + p50/p95 and one sentence on how it compares to the bar.

Then:
```bash
cd ~/src/sailingnaturali/planning
git add docs/adr/0002-model-strategy.md
git commit -m "adr: 0002 — first OSS result (qwen3.6, native OpenAI backend)"
git push
```

---

## Self-Review

**Spec coverage:**
- §Components 1 `oai_tools` pure helpers → Task 2; `McpToolset`/`create_toolset` → Task 3. ✓
- §Components 2 `oai_runner` `parse_choice`/`flat_scored_ask` → Task 4; `run_ask_openai`/`run_benchmark_openai` → Task 5. ✓
- §Components 3 `expected_tools_flat` (Ask + loader + explain-alarm) → Task 1. ✓
- §Components 4 CLI `--backend`/`--base-url` → Task 6. ✓
- §Reuse (scoring/report/decision untouched) — confirmed: only `golden.py` gains a field; the flat substitution happens in `oai_runner` via `dataclasses.replace`, so `score_ask`/`build_scorecard` are unchanged. ✓
- §Testing unit list → Tasks 1/2/4; integration live run → Task 7. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every run step has a command + expected result. ✓

**Type/consistency:** `to_openai_schema(server, mcp_tool)` and `split_tool_name(name) -> (server, tool)` defined in Task 2 are used by `McpToolset` (Task 3) and not redefined. `parse_choice`/`flat_scored_ask` (Task 4) are used by `run_ask_openai` (Task 5). `run_benchmark_openai(model, base_url, repeat, asks)` (Task 5) matches the CLI call in Task 6. `AskResult(ask, observed_tools, observed_args, dt_total, is_error, text)` matches the dataclass in `scoring.py`. `Ask.expected_tools_flat` (Task 1) is read by `flat_scored_ask` (Task 4) and the golden tests (Task 1). Tool-name format `mcp__<server>__<tool>` is consistent across `to_openai_schema`, `McpToolset._add_server`, and the golden `expected_tools_flat`. ✓

**Risk note (for Task 3/7):** `AsyncExitStack` + `stdio_client`/`ClientSession` must be entered and exited in the same asyncio task; `run_benchmark_openai` does all of it under one `asyncio.run`, so this holds. If the live run raises an anyio cancel-scope error on teardown, that's the place to look.
