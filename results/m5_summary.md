# M5: Cognitive Stack Compiler (H7) + EWMA-smoothed Kinematics (H8)

## M5.1 (H8) — EWMA-smoothed kinematics

| arm | Peak_State_Change_Speed | Detection_Latency_s | Role_Churn_Rate | Edits | RER_Events |
|---|---|---|---|---|---|
| m3_raw_1d | 230.58 +/- 27.97 | 0.274 +/- 0.101 | 0.7216 +/- 0.0881 | 1422 | 0 |
| m4_raw_4d | 189.71 +/- 41.79 | 1.755 +/- 0.319 | 0.6536 +/- 0.1592 | 1288 | 0 |
| m5_ewma_mkb | 223.87 +/- 32.16 | 1.785 +/- 0.291 | 0.8191 +/- 0.1511 | 1614 | 6 |

**H8 EWMA-smoothed kinematics — REFUTED.**

- Cap peak speed: m5 223.87 vs m4_raw_4d 189.71 and m3_raw_1d 230.58 -> does not cap.
- Detection latency: m5 1.785 s vs m4_raw_4d 1.755 s (15 % budget: 2.018 s) -> within budget.

The peak burst is dominated by the synchronous surgical edit (one class promoted across ~15 routers in a single tick), which EWMA smoothing does not change: it only lags the *trigger*, not the *edit*. RER engaged rarely (6 events across 30 seeds) because the shock is a sharp step, so the pre-trigger band is crossed for almost no ticks. The latency budget is met, but the cap is not.

## M5.2 (H7) — Cognitive Stack Compiler

30 paired seeds, one Fiber -> Microwave -> Satellite boundary sequence.
The Oracle is a mocked deterministic LLM (no API); its hallucinations are
logged so the guardrail is measured, not asserted.

## Mean metrics per arm

| arm | Wire_Bytes_Total | Throughput_Overhead_Ratio | Auth_Acceptance | Hallucinations | Oracle_Decision_Time_s |
|---|---|---|---|---|---|
| static_iso | 4650.0 +/- 0.0 | 0.8543 +/- 0.0000 | 100.0 % | 0 | 0.000000 |
| greedy_heuristic | 2673.9 +/- 84.1 | 1.5294 +/- 0.0570 | 100.0 % | 0 | 0.000000 |
| llm_compiler | 2673.9 +/- 84.1 | 1.5294 +/- 0.0570 | 100.0 % | 10 | 0.000017 |

## H7 verdict

**H7 Cognitive Stack Compilation — PARTIALLY CONFIRMED.**

- vs static_iso: mean wire-byte difference -1976.1 B (95% CI +/- 84.1, p = 1.126e-28) -> beats static.
- vs greedy_heuristic: mean wire-byte difference +0.0 B (95% CI +/- 0.0, p = 1) -> does not beat greedy.

## Guardrail behaviour (the LLM arm only)

The mocked Oracle produced **10** hallucinated proposals and the guardrail intervened **10** times. Auth acceptance stayed at **100 %** for every arm and every seed because the P3 guardrail strips an ``authenticate_outer`` proposal whenever NAT is present.

## Oracle decision time

The mocked Oracle is deterministic and near-instant (sub-millisecond). This does **not** exercise the > 500 ms latency concern of a real LLM; a local model (e.g. Ollama) must be benchmarked separately before any latency claim is made.
