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
from poseidon.bench.arms import ARMS
from poseidon.bench.decision import compare
from poseidon.bench.golden import load_golden_asks
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
    parser.add_argument("--backend", choices=["sdk", "openai"], default="sdk",
                        help="agent backend: sdk (Claude Agent SDK) or openai (Ollama /v1)")
    parser.add_argument("--base-url", default="http://localhost:11434/v1",
                        help="OpenAI-compatible base URL (openai backend)")
    parser.add_argument("--reasoning-effort", default=None,
                        help="reasoning_effort for the openai backend "
                             "(GPT-5.6+ requires 'none' for tools on /chat/completions)")
    parser.add_argument("--arm", choices=sorted(ARMS), default=None,
                        help="tool-delivery arm to measure (MCP vs CLI experiment). "
                             "Omit for the original production-crew benchmark.")
    parser.add_argument("--asks", default=None,
                        help="path to an ask corpus JSON "
                             "(default: golden_asks.json; use golden_asks_signalk.json "
                             "with --arm, since curl only replaces SignalK)")
    args = parser.parse_args()

    # ~/.poseidon/.env (subscription auth — no ANTHROPIC_API_KEY).
    config.load_env_file(config.ENV_FILE)

    asks = load_golden_asks(Path(args.asks)) if args.asks else None

    if args.backend == "openai":
        from poseidon.bench.oai_runner import run_benchmark_openai
        results = asyncio.run(
            run_benchmark_openai(args.model, args.base_url, repeat=args.repeat,
                                 reasoning_effort=args.reasoning_effort))
    else:
        results = asyncio.run(run_benchmark(args.model, repeat=args.repeat,
                                            asks=asks, arm=args.arm))
    card = build_scorecard(model=args.model, results=results, arm=args.arm or "")
    run_date = date.today().isoformat()
    # Corpus in the stem: a one-ask probe and a full run must not collide on
    # the same filename and silently overwrite each other's scorecard.
    stem_model = f"{args.model}-arm-{args.arm}" if args.arm else args.model
    if args.asks:
        stem_model = f"{stem_model}-{Path(args.asks).stem}"
    paths = write_results(card, run_date=run_date, stem_model=stem_model)

    print(f"\nmodel={card.model}  arm={card.arm or 'production-crew'}  n={card.n}  "
          f"tool-match={card.correctness * 100:.1f}%  "
          f"error_rate={card.error_rate * 100:.1f}%")
    print(f"warm-hop p50={card.latency_p50:.2f}s  p95={card.latency_p95:.2f}s")
    print(f"tokens/ask: in={card.tokens_in_mean:.0f}  out={card.tokens_out_mean:.0f}  "
          f"cache_read={card.cache_read_mean:.0f}  cost=${card.cost_usd_total:.4f}")
    print(f"wrote {paths['json']}  {paths['md']}")

    if args.baseline:
        verdict = compare(_load_baseline(args.baseline), card, eps=args.eps)
        print(f"\nSWAP={verdict.swap} — {verdict.reason}")


if __name__ == "__main__":
    main()
