# Benchmark OpenAI/Ollama Backend — Design

**Status:** Approved 2026-06-14
**Consumes:** the ADR-0002 benchmark harness (`poseidon/bench/`) at v3
**Plan:** `docs/superpowers/plans/2026-06-14-bench-openai-backend.md` (to be written)

## Context

ADR 0002 calls for benchmarking OSS models against the tool-calling + latency
bar. The harness today drives the agent through the Claude Agent SDK (Anthropic
Messages API). Ollama exposes only an OpenAI-compatible API. Two bridges were
weighed (decision 2026-06-14, recorded here):

- **Anthropic→Ollama proxy** (keep SDK path): apples-to-apples topology with the
  Sonnet baseline, minimal repo code, but needs an external proxy, depends on its
  tool-translation fidelity, adds proxy latency, and inherits the subagent
  surfacing flakiness.
- **Native OpenAI path** (chosen): the runner calls Ollama `/v1` directly with its
  own MCP-executing flat agent loop. Most representative of how an OSS model would
  actually be deployed on the boat (via Ollama, not the Claude SDK), deterministic
  tool capture (flat agent → direct tool calls, no `Agent` wrapper / subagent
  surfacing flakiness), no external dependency, real local latency. Cost: new code
  (MCP client + agent loop + schema conversion) and a flat topology that is **not**
  a literal head-to-head with the SDK-Sonnet scorecard.

Probed facts (2026-06-14): qwen3.6:latest (36B) returns clean OpenAI-format
`tool_calls` via Ollama `/v1`; the `mcp` Python client (`ClientSession`,
`StdioServerParameters`, `stdio_client`) and `httpx` 0.28.1 are both available —
**no new dependencies**. Ollama serves on `localhost:11434` with qwen3.6 present.

First target: **qwen3.6:latest**.

## Decision

Add a second, selectable benchmark backend: a native OpenAI/Ollama flat-agent
runner that executes MCP tools itself, producing the same `AskResult`s the
existing scoring/report consume. The SDK backend is unchanged and remains default.

## Components (all new files in `poseidon/bench/`, except the golden + CLI edits)

### 1. `oai_tools.py` — MCP tool provider

Connects the MCP servers without the Claude SDK and adapts them to OpenAI tools.

Pure helpers (unit-tested, no I/O):
- `to_openai_schema(server: str, mcp_tool) -> dict` — returns
  `{"type": "function", "function": {"name": f"mcp__{server}__{mcp_tool.name}", "description": mcp_tool.description or "", "parameters": mcp_tool.inputSchema or {"type": "object", "properties": {}}}}`.
- `split_tool_name(name: str) -> tuple[str, str]` — `"mcp__signalk__depth_state"` →
  `("signalk", "depth_state")`. Raises `ValueError` on a name without the `mcp__<server>__` prefix.

Async `McpToolset`:
- `create_toolset(servers: dict | None = None) -> McpToolset` (async factory) —
  loads `poseidon/profiles.load_mcp_servers()` by default (the same
  `mcp_servers.json` the SDK uses, home-expanded), starts each server via
  `stdio_client(StdioServerParameters(command, args, env))` + `ClientSession`,
  `initialize()`s, and `list_tools()`s each. Holds the sessions + an
  `AsyncExitStack` for teardown, and a `name -> (session, tool)` index.
- `.openai_schemas() -> list[dict]` — every tool across servers, via `to_openai_schema`.
- `async .call(name: str, arguments: dict) -> str` — `split_tool_name`, route to the
  server's session, `call_tool(tool, arguments)`, return the result's text content
  joined (`"".join(b.text for b in result.content if hasattr(b, "text"))`); on a
  tool error return a short `"ERROR: ..."` string (the model may recover; never
  raise into the loop).
- `async .aclose()` — close the exit stack (terminates all server processes).

### 2. `oai_runner.py` — flat agent loop (httpx)

Pure helper (unit-tested):
- `parse_choice(response_json: dict) -> tuple[list[dict], str, str]` — returns
  `(tool_calls, text, finish_reason)` from `response_json["choices"][0]`. `tool_calls`
  is the raw list (each `{"id", "function": {"name", "arguments"}}`); `text` is
  `message.get("content") or ""`; `finish_reason` from the choice. Tolerates a
  missing `tool_calls` key (→ `[]`).

Async:
- `run_ask_openai(http, base_url, model, system_prompt, schemas, toolset, ask, max_rounds=10) -> AskResult`:
  - `messages = [{"role":"system","content":system_prompt}, {"role":"user","content":ask.prompt}]`.
  - `t0 = monotonic()`. Loop up to `max_rounds`: POST `base_url + "/chat/completions"`
    with `{model, messages, tools: schemas, tool_choice: "auto", stream: false}`;
    `parse_choice`; if `tool_calls`: append the assistant message (with tool_calls)
    then, for each call, `arguments = json.loads(args or "{}")`, record the function
    name in `observed` (unique-ordered), `result = await toolset.call(name, arguments)`,
    append `{"role":"tool","tool_call_id":id,"content":result}`; continue. Else break
    with final `text`.
  - `dt = monotonic()-t0`. On any exception or non-200, `is_error=True`, capture what
    we have. Build `AskResult(ask=<flat-adjusted>, observed_tools=observed,
    observed_args=[...], dt_total=dt, is_error=..., text=...)`. (`observed_args`:
    the parsed arguments per first-seen tool, aligned like the SDK path; `{}` when
    unavailable.)
  - **Flat-expected substitution:** if `ask.expected_tools_flat` is set, the result's
    ask is `dataclasses.replace(ask, expected_tools=ask.expected_tools_flat)` so the
    existing `score_ask`/`build_scorecard` need no change.
- `run_benchmark_openai(model, base_url, repeat=1, asks=None) -> list[AskResult]`:
  `create_toolset()`; `schemas = toolset.openai_schemas()`; one throwaway warm-up ask
  ("Hello.", loads the model off the clock); then `repeat × asks` via `run_ask_openai`;
  `aclose()` in a `finally`. Uses one `httpx.AsyncClient` (long read timeout, e.g. 300s).

`max_rounds` guards against a model that never stops calling tools (the turn ends with
`is_error=False` and whatever text/observed accumulated — note it as a truncated turn).

### 3. `golden.py` — `expected_tools_flat`

Add `expected_tools_flat: tuple[str, ...] = ()` to `Ask`; loader reads
`tuple(row.get("expected_tools_flat", ()))`. In `golden_asks.json`, only
`explain-alarm` gains `"expected_tools_flat": ["mcp__signalk__get_active_alarms"]`
(the flat agent calls the alarm tool directly; no `Agent` tool exists off-SDK).
All other asks rely on their existing `expected_tools`, which hold on the flat path.

### 4. `__main__.py` — backend selection

Add `--backend {sdk,openai}` (default `sdk`) and `--base-url` (default
`http://localhost:11434/v1`). When `--backend openai`: `results =
asyncio.run(run_benchmark_openai(args.model, args.base_url, repeat=args.repeat))`.
The rest (scorecard, report, optional `--baseline` compare) is unchanged. Scorecard
`model` label is the passed model id; `write_results` already sanitizes `:`/`/` in
filenames.

## Reuse (unchanged)
`golden.Ask`/`load_golden_asks` (extended only), `scoring` (`AskResult`,
`score_ask`, `build_scorecard`), `report`, `decision`. The SDK path (`collect.py`,
`runner.py`) is untouched and remains the default.

## Out of scope
- The Anthropic→Ollama proxy route (rejected; revisit only if an apples-to-apples
  SDK-topology comparison proves necessary).
- Reproducing subagent delegation in the flat path (deliberately flat — matches how
  an OSS model would deploy).
- Adding the `openai` PyPI package (use `httpx` directly).
- Multi-model orchestration / sweeps (one `--model` per run; `--baseline` already
  enables pairwise compare).

## Testing
Unit (no network): `to_openai_schema`, `split_tool_name` (incl. the `ValueError`
case), `parse_choice` (tool_calls present / absent / final-text), `Ask.expected_tools_flat`
loading, and the `dataclasses.replace` flat substitution (a flat-annotated ask scores
against its flat tools). Integration: the live `--backend openai --model qwen3.6:latest`
run (needs Ollama + Pi SignalK + MCP servers) — the actual benchmark, recorded as a
new scorecard with a note that it is a flat-topology measurement, not a head-to-head
with the SDK-Sonnet scorecard. Full repo suite stays green.
