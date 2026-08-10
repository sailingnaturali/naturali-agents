### Benchmark run 2026-08-09 — claude-sonnet-4-6 — arm: curl-cold

- Asks: 1 | tool-match: 100.0% | error rate: 0.0%
- Warm-hop latency: p50 7.81s | p95 7.81s
- Tokens/ask: in 3 | out 10 | cache-read 3860 | run cost $0.0050

> `tool-match` compares observed tools to `expected_tools`, which are MCP names — a Bash arm scores 0 by construction. Grade these arms on the answer-vs-truth table below.

| ask | category | observed | match | dt (s) | in | out | cache |
|-----|----------|----------|-------|--------|----|----|-------|
| no-tool | baseline | — | ✓ | 7.81 | 3 | 10 | 3860 |

#### Answers vs live SignalK truth

**no-tool** — truth `n/a`

> Hello there, welcome on board!

