"""poseidon.bench.hermes_runner — run the golden-ask corpus through a sandboxed
Hermes agent and score with the same scorer used for Poseidon.

Hermes names MCP tools as ``mcp_<server>_<tool>`` (single underscores, dashes
replaced) while the scorer expects ``mcp__<server>__<tool>`` (double underscores,
original server name with dashes preserved).  ``normalize_tool_name`` handles that
translation using a known-server registry built from the same MCP server keys used
in the hermes-fresh config.

Session data is read from the Hermes SQLite state database
(``HERMES_HOME/state.db``).  Each ``-z`` invocation starts a new session; we
fetch the freshest session written *after* the subprocess call starts to isolate
exactly the messages that belong to our ask.

Usage (full run)::

    uv run python -m poseidon.bench.hermes_runner
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

from poseidon.bench.golden import Ask, load_golden_asks
from poseidon.bench.scoring import AskResult

# ---------------------------------------------------------------------------
# Constants — paths to the fresh sandbox
# ---------------------------------------------------------------------------

HERMES_HOME = os.path.expanduser("~/.hermes-fresh")
HERMES_BIN = os.path.expanduser(
    "~/src/hermes-fresh/hermes-agent/venv/bin/hermes"
)
HERMES_DB = os.path.join(HERMES_HOME, "state.db")

# Subprocess timeout per ask (seconds).  Some multi-tool asks can be slow.
_SUBPROCESS_TIMEOUT = 120

# ---------------------------------------------------------------------------
# Known server names (as registered in the scorer's namespace)
# Hermes converts dashes → underscores in the tool name; we reverse that here.
# Ordered longest-first so that "vessel_knowledge" is matched before "vessel".
# ---------------------------------------------------------------------------

_KNOWN_SERVERS: list[tuple[str, str]] = [
    # (hermes_prefix_with_underscores, canonical_scorer_server_name)
    ("vessel_knowledge", "vessel-knowledge"),
    ("club_moorage", "club-moorage"),
    ("signalk", "signalk"),
    ("logbook", "logbook"),
    ("currents", "currents"),
    ("weather", "weather"),
    ("pilotbook", "pilotbook"),
    ("colregs", "colregs"),
]


def normalize_tool_name(name: str) -> str:
    """Convert a Hermes tool name to the scorer's ``mcp__<server>__<tool>`` form.

    Hermes records tool names as ``mcp_<server>_<tool>`` — single underscores,
    dashes replaced with underscores.  The scorer uses ``mcp__<server>__<tool>``
    with the original server name (dashes preserved).

    For names that are already in SDK form or not MCP tools, the input is
    returned unchanged.
    """
    if not name.startswith("mcp_"):
        return name
    # Already in SDK form (double-underscore after mcp).
    if name.startswith("mcp__"):
        return name

    rest = name[4:]  # strip leading "mcp_"
    for hermes_server, canonical_server in _KNOWN_SERVERS:
        prefix = hermes_server + "_"
        if rest.startswith(prefix):
            tool = rest[len(prefix):]
            return f"mcp__{canonical_server}__{tool}"

    # Unknown server — fall back to a best-effort double-underscore split on
    # the first underscore boundary (split at second underscore from start).
    parts = rest.split("_", 1)
    if len(parts) == 2:
        return f"mcp__{parts[0]}__{parts[1]}"
    return name


# ---------------------------------------------------------------------------
# Session parser
# ---------------------------------------------------------------------------

def parse_hermes_session(session: dict) -> tuple[list[str], list[dict], str]:
    """Extract tool calls and final assistant text from a Hermes session dict.

    The session dict has the form exported from the state.db ``messages`` table::

        {
            "session_id": "...",
            "messages": [
                {"role": "user",      "content": "...", ...},
                {"role": "assistant", "tool_calls": [...], ...},
                {"role": "tool",      "tool_name": "mcp_signalk_depth_state", ...},
                {"role": "assistant", "content": "final text", "finish_reason": "stop"},
            ]
        }

    Tool calls are sourced from the ``tool_calls`` list on assistant messages
    (``message["tool_calls"][i]["function"]["name"]`` and ``.arguments``).
    Tool names are normalised to ``mcp__<server>__<tool>`` form.
    The final text is the last assistant message with a non-empty ``content`` and
    ``finish_reason == "stop"``.

    Returns:
        (tools, args, text) where tools and args are parallel lists ordered by
        first observation (deduplicated by tool name, same as poseidon.bench.collect).
    """
    messages = session.get("messages", [])
    tools_by_name: dict[str, dict] = {}  # insertion-ordered; first seen wins
    text = ""

    for msg in messages:
        role = msg.get("role")
        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                if isinstance(tool_calls, str):
                    try:
                        tool_calls = json.loads(tool_calls)
                    except json.JSONDecodeError:
                        tool_calls = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    raw_name = fn.get("name", "")
                    normalized = normalize_tool_name(raw_name)
                    raw_args = fn.get("arguments", "{}")
                    try:
                        args_dict = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except (json.JSONDecodeError, TypeError):
                        args_dict = {}
                    tools_by_name.setdefault(normalized, args_dict or {})
            # Capture final answer text (finish_reason == "stop" or last assistant).
            content = msg.get("content") or ""
            finish = msg.get("finish_reason") or ""
            if content and finish == "stop":
                text = content

    # If no stop-reason text found, take any non-empty assistant content.
    if not text:
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content") or ""
                if content:
                    text = content
                    break

    return list(tools_by_name), list(tools_by_name.values()), text


# ---------------------------------------------------------------------------
# Session DB helpers
# ---------------------------------------------------------------------------

def _fetch_session_from_db(db_path: str, session_id: str) -> dict:
    """Load all messages for a session from state.db into a session dict."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()

    messages = []
    for row in rows:
        msg = dict(row)
        if msg.get("tool_calls") and isinstance(msg["tool_calls"], str):
            try:
                msg["tool_calls"] = json.loads(msg["tool_calls"])
            except json.JSONDecodeError:
                pass
        messages.append(msg)

    return {"session_id": session_id, "messages": messages}


def _latest_session_after(db_path: str, started_after: float) -> str | None:
    """Return the session_id of the most-recently-started session after the given
    Unix timestamp, or None if no such session exists."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM sessions WHERE started_at > ? ORDER BY started_at DESC LIMIT 1",
            (started_after,),
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Per-ask runner
# ---------------------------------------------------------------------------

def _run_one_hermes(ask: Ask) -> AskResult:
    """Invoke Hermes for a single ask via subprocess; return an AskResult."""
    env = dict(os.environ)
    env["HERMES_HOME"] = HERMES_HOME

    t0 = time.monotonic()
    started_at_unix = time.time()

    try:
        proc = subprocess.run(
            [HERMES_BIN, "-z", ask.prompt],
            env=env,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        dt = time.monotonic() - t0
        is_error = proc.returncode != 0
    except subprocess.TimeoutExpired:
        dt = time.monotonic() - t0
        return AskResult(
            ask=ask,
            observed_tools=[],
            observed_args=[],
            dt_total=dt,
            is_error=True,
            text=f"ERROR: subprocess timeout after {_SUBPROCESS_TIMEOUT}s",
        )
    except Exception as exc:
        dt = time.monotonic() - t0
        return AskResult(
            ask=ask,
            observed_tools=[],
            observed_args=[],
            dt_total=dt,
            is_error=True,
            text=f"ERROR: {exc}",
        )

    # Locate the session that was started for this ask.
    session_id = _latest_session_after(HERMES_DB, started_at_unix)
    if session_id is None:
        return AskResult(
            ask=ask,
            observed_tools=[],
            observed_args=[],
            dt_total=dt,
            is_error=True,
            text="ERROR: could not find session in state.db",
        )

    session = _fetch_session_from_db(HERMES_DB, session_id)
    tools, args, text = parse_hermes_session(session)

    # Prefer the subprocess stdout text if the DB text is empty (Hermes echoes
    # the final response to stdout for -z mode).
    if not text and proc.stdout.strip():
        text = proc.stdout.strip()

    return AskResult(
        ask=ask,
        observed_tools=tools,
        observed_args=args,
        dt_total=dt,
        is_error=is_error,
        text=text,
    )


# ---------------------------------------------------------------------------
# Full benchmark runner
# ---------------------------------------------------------------------------

def run_hermes_benchmark(asks: list[Ask] | None = None) -> list[AskResult]:
    """Run all golden asks through the Hermes sandbox and return AskResults.

    One throwaway warm-up ask is fired first to absorb MCP server cold-start
    latency; it is not included in the returned results.
    """
    asks = asks or load_golden_asks()

    # Throwaway warm-up: pay MCP connect/cold-cache cost off the clock.
    env = dict(os.environ)
    env["HERMES_HOME"] = HERMES_HOME
    try:
        subprocess.run(
            [HERMES_BIN, "-z", "Hello."],
            env=env,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except Exception:
        pass  # warm-up failure is non-fatal

    results: list[AskResult] = []
    for ask in asks:
        results.append(_run_one_hermes(ask))
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path as _Path

    from poseidon.bench.report import write_results
    from poseidon.bench.scoring import build_scorecard

    card = build_scorecard(
        "hermes-blankslate-claude-sonnet-4-6",
        run_hermes_benchmark(),
    )
    paths = write_results(card, out_dir=_Path("dev/bench-results"))
    print(
        f"correctness={card.correctness:.2f} "
        f"p50={card.latency_p50:.2f}s "
        f"p95={card.latency_p95:.2f}s "
        f"-> {paths['json']}"
    )
