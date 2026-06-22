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
    parser.add_argument("--backend", choices=["sdk", "openai"], default="sdk",
                        help="agent backend: sdk (Claude Agent SDK) or openai (Ollama /v1)")
    parser.add_argument("--base-url", default="http://localhost:11434/v1",
                        help="OpenAI-compatible base URL (openai backend)")
    parser.add_argument("--offpath", action="store_true",
                        help="run the off-golden set ON vs OFF and report answer-rate delta")
    args = parser.parse_args()

    # Env file holds ANTHROPIC_API_KEY (interim ~/.hermes/.env).
    config.load_env_file(config.ENV_FILE)

    if args.offpath:
        from poseidon.bench.offpath import answer_rate, run_offpath
        off = asyncio.run(run_offpath(args.model, use_fallback=False))
        on = asyncio.run(run_offpath(args.model, use_fallback=True))
        print(f"\noff-golden answer-rate  OFF={answer_rate(off)*100:.1f}%  "
              f"ON={answer_rate(on)*100:.1f}%  (n={len(off)})")
        return

    if args.backend == "openai":
        from poseidon.bench.oai_runner import run_benchmark_openai
        results = asyncio.run(
            run_benchmark_openai(args.model, args.base_url, repeat=args.repeat))
    else:
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
