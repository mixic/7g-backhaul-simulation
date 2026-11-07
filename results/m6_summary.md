# M6: energy-aware evaluation

Stipulated energy model (`simulation/energy.py`); nothing is a hardware
measurement. 30 paired seeds per experiment.

## exp1 — shockwave energy audit (H9, H11)

| arm | Total_Energy_J | E_tx_J | E_cpu_J | E_churn_J | E_setup_J | Total_Edits |
|---|---|---|---|---|---|---|
| static_isolation | 918.2 +/- 17.7 | 918.2 +/- 17.7 | 0 +/- 0 | 0 +/- 0 | 1071 +/- 26.9 | 6425 |
| m4_oef | 1119 +/- 30.7 | 907.9 +/- 20.2 | 1.5e-05 +/- 1.23e-21 | 211 +/- 34.7 | 0 +/- 0 | 1266 |
| m4_raw_mkb | 1149 +/- 30.7 | 909.3 +/- 19.4 | 1.5e-05 +/- 1.23e-21 | 239.7 +/- 39.6 | 0 +/- 0 | 1438 |
| m5_ewma_mkb | 1166 +/- 25.7 | 908.5 +/- 17.1 | 1.5e-05 +/- 1.23e-21 | 257.7 +/- 32.3 | 0 +/- 0 | 1546 |

**H9 EWMA energy efficiency — REFUTED.**
m5_ewma_mkb churn energy = 257.7 J vs m4_raw_mkb 239.7 J (higher — the EWMA arm edits *more*, not less).

**H11 static-isolation energy baseline — CONFIRMED.**
static_isolation total energy = 918.2 J vs m4_oef 1119 J (static has zero runtime churn; its one-time setup is reported as E_setup).

## exp2 — LLM EROI (H10)

| arm | Wire_Bytes_Total | E_tx_J | E_cpu_J | E_llm_J | E_tx_saved_J | EROI |
|---|---|---|---|---|---|---|
| static_iso | 4650.0 | 0.000465 | 0.00042 | 0 | 0 | — |
| greedy_heuristic | 2673.9 | 0.0002674 | 0.00042 | 0 | 0.0001976 | — |
| llm_compiler | 2673.9 | 0.0002674 | 0.00042 | 60 | 0.0001976 | 3.29e-06 |

**H10 LLM EROI — REFUTED.**
Transmission energy saved = 0.0001976 J vs inference cost 60 J -> EROI = 3.29e-06 (< 1). At the stipulated 1e-7 J/byte and 20 J/call, the LLM only breaks even once a flow saves ~200 MB of transmission — far more than the ~1400-byte payload modelled.
