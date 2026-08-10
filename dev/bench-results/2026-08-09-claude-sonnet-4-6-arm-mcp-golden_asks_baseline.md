### Benchmark run 2026-08-09 — claude-sonnet-4-6 — arm: mcp

- Asks: 1 | tool-match: 100.0% | error rate: 0.0%
- Warm-hop latency: p50 1.33s | p95 1.33s
- Tokens/ask: in 3 | out 11 | cache-read 1160 | run cost $0.0047

> `tool-match` compares observed tools to `expected_tools`, which are MCP names — a Bash arm scores 0 by construction. Grade these arms on the answer-vs-truth table below.

| ask | category | observed | match | dt (s) | in | out | cache |
|-----|----------|----------|-------|--------|----|----|-------|
| no-tool | baseline | — | ✓ | 1.33 | 3 | 11 | 1160 |

#### Answers vs live SignalK truth

**no-tool** — truth `n/a`

> Hello there, sailor! Safe travels!

