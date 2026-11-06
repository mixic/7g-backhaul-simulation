# M5: Cognitive Stack Compiler (H7)

30 paired seeds, one Fiber -> Microwave -> Satellite boundary sequence.
The Oracle is a mocked deterministic LLM (no API); its hallucinations are
logged so the guardrail is measured, not asserted.

## Mean metrics per arm

| arm | Wire_Bytes_Total | Throughput_Overhead_Ratio | Auth_Acceptance | Hallucinations | Oracle_Decision_Time_s |
|---|---|---|---|---|---|
| static_iso | 4650.0 +/- 0.0 | 0.8543 +/- 0.0000 | 100.0 % | 0 | 0.000000 |
| greedy_heuristic | 2673.9 +/- 84.1 | 1.5294 +/- 0.0570 | 100.0 % | 0 | 0.000000 |
| llm_compiler | 2673.9 +/- 84.1 | 1.5294 +/- 0.0570 | 100.0 % | 10 | 0.000009 |

## H7 verdict

**H7 Cognitive Stack Compilation — PARTIALLY CONFIRMED.**

- vs static_iso: mean wire-byte difference -1976.1 B (95% CI +/- 84.1, p = 1.126e-28) -> beats static.
- vs greedy_heuristic: mean wire-byte difference +0.0 B (95% CI +/- 0.0, p = 1) -> does not beat greedy.

## Guardrail behaviour (the LLM arm only)

The mocked Oracle produced **10** hallucinated proposals and the guardrail intervened **10** times. Auth acceptance stayed at **100 %** for every arm and every seed because the P3 guardrail strips an ``authenticate_outer`` proposal whenever NAT is present.

## Oracle decision time

The mocked Oracle is deterministic and near-instant (sub-millisecond). This does **not** exercise the > 500 ms latency concern of a real LLM; a local model (e.g. Ollama) must be benchmarked separately before any latency claim is made.
