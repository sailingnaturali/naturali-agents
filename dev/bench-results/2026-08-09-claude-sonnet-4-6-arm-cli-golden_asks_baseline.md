### Benchmark run 2026-08-09 — claude-sonnet-4-6 — arm: cli

- Asks: 1 | tool-match: 100.0% | error rate: 0.0%
- Warm-hop latency: p50 2.66s | p95 2.66s
- Tokens/ask: in 3 | out 10 | cache-read 3943 | run cost $0.0048

> `tool-match` compares observed tools to `expected_tools`, which are MCP names — a Bash arm scores 0 by construction. Grade these arms on the answer-vs-truth table below.

| ask | category | observed | match | dt (s) | in | out | cache |
|-----|----------|----------|-------|--------|----|----|-------|
| no-tool | baseline | — | ✓ | 2.66 | 3 | 10 | 3943 |

#### Answers vs live SignalK truth

**no-tool** — truth `n/a`

> Hello there, welcome aboard sailor!

