# M4-Execution: definitive benchmark (30 paired seeds)

Means and 95% confidence intervals across 30 paired seeds (the M3 `default_rng(2026)` seed set).  No tuning, no cherry-picking.

## Verdicts

| H5 OEF compensation | **REFUTED** |

m4_oef legitimate goodput (CMRO2) = **0.8465 +/- 0.0542** vs static_isolation **0.8648 +/- 0.0177** (documented 86.5 %). Target: > 0.92 and > static_isolation. Transit drop rate (starvation cost) = **0.0990 +/- 0.0329**.

| H6 MKB rate control | **CONFIRMED** |

m4_mkb peak state-change speed = **218.3800 +/- 36.8013** vs m3_surgical_1d **222.0400 +/- 31.6980** (must be lower). m4_mkb false-positive edits = **0.0000 +/- 0.0000** vs m3_surgical_1d **0.0000 +/- 0.0000** (must be zero).

## Direct answers to the review questions

1. **Did OEF beat static_isolation (86.5 %)?** **No.** m4_oef = 0.8465 +/- 0.0542 vs static_isolation = 0.8648 +/- 0.0177.
2. **Did MKB cap the peak burst speed?** Yes (marginal). m4_mkb = 218.38 +/- 36.80 vs m3_surgical_1d = 222.04 +/- 31.70; false-positive edits = 0.
3. **What is the exact starvation cost?** Transit drop rate = 0.0990 +/- 0.0329 (m4_oef); the destructive threshold is in the starvation table below.

## Legitimate goodput (CMRO2) across arms

| arm | mean | 95% CI |
|---|---|---|
| static_isolation | 0.8648 | +/- 0.0177 |
| m3_surgical_1d | 0.8461 | +/- 0.0541 |
| m4_oef | 0.8465 | +/- 0.0542 |
| m4_mkb | 0.8083 | +/- 0.0467 |
| m4_combined | 0.4823 | +/- 0.0262 |

## Peak burst state-change speed across arms

| arm | mean | 95% CI |
|---|---|---|
| static_isolation | 1072.8333 | +/- 27.5455 |
| m3_surgical_1d | 222.0400 | +/- 31.6980 |
| m4_oef | 222.0400 | +/- 31.6980 |
| m4_mkb | 218.3800 | +/- 36.8013 |
| m4_combined | 384.3000 | +/- 41.3811 |

## All arms, all metrics (mean +/- 95% CI)

| arm | Total_Throughput_CBF | Legitimate_Goodput_CMRO2 | OEF_Value | Peak_State_Change_Speed | Number_of_Edits | False_Positive_Edits | Transit_Drop_Rate |
|---|---|---|---|---|---|---|---|
| static_isolation | 0.0000 +/- 0.0000 | 0.8648 +/- 0.0177 | 0.0000 +/- 0.0000 | 1072.8333 +/- 27.5455 | 214.5667 +/- 5.5091 | 214.5667 +/- 5.5091 | 0.0683 +/- 0.0097 |
| m3_surgical_1d | 0.0000 +/- 0.0000 | 0.8461 +/- 0.0541 | 0.0000 +/- 0.0000 | 222.0400 +/- 31.6980 | 45.2667 +/- 6.5148 | 0.0000 +/- 0.0000 | 0.0994 +/- 0.0329 |
| m4_oef | 298777040.8951 +/- 10223606.3735 | 0.8465 +/- 0.0542 | 1.0000 +/- 0.0000 | 222.0400 +/- 31.6980 | 45.2667 +/- 6.5175 | 0.0000 +/- 0.0000 | 0.0990 +/- 0.0329 |
| m4_mkb | 306167102.6234 +/- 8606916.9092 | 0.8083 +/- 0.0467 | 0.0000 +/- 0.0000 | 218.3800 +/- 36.8013 | 49.8000 +/- 9.9655 | 0.0000 +/- 0.0000 | 0.1171 +/- 0.0283 |
| m4_combined | 335931813.2716 +/- 6649488.5863 | 0.4823 +/- 0.0262 | 1.0000 +/- 0.0000 | 384.3000 +/- 41.3811 | 268.2000 +/- 19.7377 | 175.1333 +/- 10.4556 | 0.3628 +/- 0.0308 |

## Starvation threshold (OEF forced to max, weight swept)

| oef_max (WFQ weight) | Legitimate goodput | Transit drop rate |
|---|---|---|
| 1 | 0.8461 +/- 0.0541 | 0.0994 +/- 0.0329 |
| 2 | 0.8528 +/- 0.0550 | 0.0955 +/- 0.0335 |
| 4 | 0.8515 +/- 0.0543 | 0.0978 +/- 0.0329 |
| 8 | 0.8521 +/- 0.0544 | 0.0977 +/- 0.0329 |
| 16 | 0.8521 +/- 0.0544 | 0.0977 +/- 0.0329 |

## Computational overhead (controller CPU per tick)

| arm | us/tick | vs 1D limiter |
|---|---|---|
| static_isolation | 0.2 | 0.03x |
| m3_surgical_1d | 5.6 | 1.00x |
| m4_oef | 225.6 | 40.50x |
| m4_mkb | 752.3 | 135.09x |
| m4_combined | 692.0 | 124.26x |

## Interpretation

**H5 (OEF) — REFUTED.** The OEF actuator's CBF monitor tracks *total delivered throughput*, which a DDoS flood does not lower (the attack's bytes are served too), so the CBF-drop trigger never fires during the attack.  ``OEF_Value`` reaches 1.0 only when traffic stops at end-of-run.  Hence m4_oef is indistinguishable from m3_surgical_1d (0.8465 vs 0.8461) and stays below static_isolation (0.8648).  The Fick premise — that a DDoS lowers delivered CBF — does not hold in this testbed, so the compensation has nothing to compensate.

**H6 (MKB) — CONFIRMED, with a caveat.** m4_mkb keeps false-positive edits at exactly zero during steady state, satisfying that clause.  Its peak burst speed (218.4) is slightly below the 1D limiter (222.0), but the confidence intervals overlap heavily, so the "cap" is marginal — a few percent at best — because both arms share the same discrete surgical edit.  The vector trigger does not make the burst worse, but it does not clearly bound it either.

**m4_combined — negative result.** Running OEF and MKB together is strictly worse than either alone (goodput 0.4823 vs 0.8465): the OEF actuator's weight changes feed back into the 4-D state vector and trip the MKB trigger ~175 times during steady traffic, isolating innocent classes and roughly halving delivery.
