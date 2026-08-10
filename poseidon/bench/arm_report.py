"""poseidon.bench.arm_report — one table across the MCP-vs-CLI arms.

  uv run python -m poseidon.bench.arm_report [results_dir]

Reads the per-arm scorecards written by ``python -m poseidon.bench --arm ...``
and renders the comparison. Reports token *deltas* against the cheapest arm as
well as absolutes: every arm carries the same ~12k-token Claude Code CLI system
prompt underneath, so absolute totals understate the difference between tool
surfaces. Answers are printed next to live SignalK truth for hand-grading —
``tool-match`` is meaningless for the Bash arms (they call one tool, "Bash").
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_DEFAULT_OUT = Path(__file__).resolve().parents[2] / "dev" / "bench-results"
ARM_ORDER = ["mcp", "curl-cold", "curl-warm", "cli"]


def load_arm_cards(results_dir: Path) -> dict[str, dict]:
    cards: dict[str, dict] = {}
    for path in sorted(results_dir.glob("*-arm-*.json")):
        card = json.loads(path.read_text(encoding="utf-8"))
        arm = card.get("arm")
        if not arm:
            continue
        # Largest corpus wins: one-ask probes share the glob with full runs,
        # and a probe silently replacing a 12-ask run would be invisible here.
        if arm not in cards or card["n"] >= cards[arm]["n"]:
            cards[arm] = card
    return cards


def _total_in(card: dict) -> float:
    """Billed input per ask: fresh input plus cache reads. Cache reads are
    cheaper per token but they are not free, and they are exactly where a
    resident tool schema shows up."""
    return card["tokens_in_mean"] + card["cache_read_mean"]


def _session_in(card: dict) -> int:
    """Billed input across the whole run. Falls back to mean x n for scorecards
    written before session totals were recorded."""
    if card.get("tokens_in_total") or card.get("cache_read_total"):
        return card.get("tokens_in_total", 0) + card.get("cache_read_total", 0)
    return round(_total_in(card) * card["n"])


def _per_ask_cost(card: dict) -> float:
    return card.get("cost_usd_mean") or (card.get("cost_usd_total", 0.0) / (card["n"] or 1))


def render(cards: dict[str, dict]) -> str:
    arms = [a for a in ARM_ORDER if a in cards] + \
           [a for a in cards if a not in ARM_ORDER]
    if not arms:
        return "No arm scorecards found. Run: python -m poseidon.bench --arm mcp ...\n"

    cheapest = min(_total_in(cards[a]) for a in arms)
    lines = [
        "## MCP vs CLI — tool-delivery arms",
        "",
        "### Per turn — what one ask costs",
        "",
        "| arm | n | in+cache/ask | Δ vs cheapest | out/ask | p50 (s) | cost/ask | errors |",
        "|-----|---|--------------|---------------|---------|---------|----------|--------|",
    ]
    for arm in arms:
        c = cards[arm]
        billed = _total_in(c)
        lines.append(
            f"| {arm} | {c['n']} | {billed:,.0f} | "
            f"+{billed - cheapest:,.0f} | {c['tokens_out_mean']:,.0f} | "
            f"{c['latency_p50']:.2f} | ${_per_ask_cost(c):.4f} | "
            f"{c['error_rate'] * 100:.0f}% |"
        )

    # The session view is the one that matches a bill. A resident schema is
    # billed every turn, so its cost grows with conversation length — a
    # per-ask mean divides that back out and makes it look smaller than it is.
    session_cheapest = min(_session_in(cards[a]) for a in arms)
    lines += [
        "",
        "### Per session — what holding the whole conversation costs",
        "",
        "| arm | asks | in+cache total | Δ vs cheapest | out total | session cost |",
        "|-----|------|----------------|---------------|-----------|--------------|",
    ]
    for arm in arms:
        c = cards[arm]
        billed = _session_in(c)
        lines.append(
            f"| {arm} | {c['n']} | {billed:,} | +{billed - session_cheapest:,} | "
            f"{c.get('tokens_out_total', 0):,} | "
            f"${c.get('cost_usd_session') or c.get('cost_usd_total', 0):.4f} |"
        )

    lines += ["", "### Per-ask answers vs live truth", ""]
    ids = [row["id"] for row in cards[arms[0]]["per_ask"]]
    for ask_id in ids:
        truth = next((r.get("truth", "") for a in arms
                      for r in cards[a]["per_ask"] if r["id"] == ask_id), "")
        lines += [f"#### {ask_id} — truth `{truth}`", ""]
        for arm in arms:
            row = next((r for r in cards[arm]["per_ask"] if r["id"] == ask_id), None)
            if not row:
                continue
            t = row.get("tokens", {})
            billed = t.get("input", 0) + t.get("cache_read", 0)
            answer = (row.get("answer") or "(no answer)").strip().replace("\n", " ")
            lines += [f"- **{arm}** ({billed:,} in, {t.get('output', 0)} out, "
                      f"{row['dt_total']:.1f}s): {answer}"]
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    results_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_OUT
    cards = load_arm_cards(results_dir)
    text = render(cards)
    out = results_dir / "arm-comparison.md"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
