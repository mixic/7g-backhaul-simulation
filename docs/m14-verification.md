# M14 verification report: Paper A and Paper B abstracts

**Date:** 2026 · **Scope:** verification only. No experiment was re-run, no CSV was
modified, and no conclusion was changed. Where the abstract and the data
disagreed, the abstract was corrected.

**Papers under test**

- Paper A: [`paper-layering-testbed.md`](paper-layering-testbed.md) (21 pages in
  the built PDF).
- Paper B: [`paper-bio-control-limits.md`](paper-bio-control-limits.md) (4 pages in
  the built PDF).

**How to reproduce every number below**

```powershell
py -3 tools\verify_m14.py
```

The script is read-only. It reads the four verdict files, the layering and
real-stack observation CSVs, the M4/M6 CSVs, the two calibration files, and the
test sources. Its full output is reproduced in §8.

---

## 1. Paper A: the prediction count

The ambiguity was "sixteen predictions" versus "more than sixteen once
sub-cases are counted". The committed data supports three different, all correct
counts, because they count different things:

| Quantity | Count | Definition | Source |
|---|---:|---|---|
| Verdict rows | 62 | 21 + 15 + 20 + 6 rows across the four files | `validation/*/results/verdicts.csv` |
| Distinct prediction values | 22 | P1–P16 plus P17a–P17f (P17's cases are separate values) | same |
| **Main categories, files 1–3 only** | **16** | P1–P16; this is exactly what the goal's snippet counts, because it omits round 3 | same |
| **Main categories, all four files** | **17** | P1–P17 (P17a–P17f normalise to P17) | same |
| Headline predictions (Figure 2) | 22 | 7 + 5 + 4 + 6 | `tools/make_layering_figures.py` |
| **Scored predictions (Table 8, Brier denominators)** | **36** | 7 + 5 + 18 + 6 | `tools/make_paper_tables.py` |
| **Confirmed** | **34** | 6 + 5 + 17 + 6 | same |

**Literal output of the goal's count snippet** (paths relative to the repo root;
the category list is a set, so its order is not meaningful):

```text
Distinct main prediction categories: 16
Categories: ['P1', 'P10', 'P11', 'P12', 'P13', 'P14', 'P15', 'P16', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9']

P10: 2 sub-cases (P10a, P10b)
P11: 3 sub-cases (P11a, P11b, P11c)
P12: 3 sub-cases (P12a, P12b, P12c)
P13: 10 sub-cases (P13h_ipip, P13h_wg, P13h_esp, P13a, P13b, P13c, P13d, P13e, P13f, P13g)
P14: 4 sub-cases (P14a, P14b, P14c, P14d)
P15: 2 sub-cases (P15a, P15b)
P16: 4 sub-cases (P16a, P16b, P16c, P16d)
P8: 6 sub-cases (P8a, P8a_control, P8b, P8b_control, P8c, P8c_control)
```

Sum of the printed sub-cases: 6 + 2 + 3 + 3 + 10 + 4 + 2 + 4 = **34**. P9 has a
single case (`P9`), so the snippet does not print it, and it is not a sub-case.

Why 36 and not 62: the generator scores at different granularity per round, and
that rule is itself committed code:

- P1–P7: one score per prediction; the 21 fidelity rows collapse to 7.
- P8–P12: one score per prediction; the 15 case rows collapse to 5.
- P13–P16: one score per calibration entry; 20 case rows map to 18 entries
  (P13h's three control cases are one entry: P13h_ipip/wg/esp → `P13h`).
- P17: one score per case; 6.

**Decision.** The goal's snippet counts **16 main categories** and prints **34
named sub-cases**. The abstract now says "sixteen prediction categories (34
sub-cases in the real-stack rounds) plus a six-case replay-window follow-up",
expanded into 36 scored predictions. The 16 and 34 are the snippet's output; the
six-case follow-up is the six `round3/verdicts.csv` rows; 36 is the scored total
(7 + 5 + 18 + 6). The goal's suggested phrase "across the three fidelity levels"
was not used verbatim: the 34 sub-cases belong to the kernel rounds (P8–P16), and
only P1–P7 are tested at three fidelities. The table above keeps the 17-family
reading so a reviewer can reconcile the abstract with Table 8.

---

## 2. Paper A: confirmed and refuted counts

| Round | Rows | Row verdicts | Prediction-level | Scored |
|---|---:|---|---|---|
| P1–P7 | 21 | 20 CONFIRMED, 1 REFUTED | 6 of 7 (P5 refuted at Linux only) | 6 of 7 |
| P8–P12 | 15 | 15 CONFIRMED | 5 of 5 | 5 of 5 |
| P13–P16 | 20 | 19 CONFIRMED, 1 REFUTED | 17 of 18 (P16d refuted) | 17 of 18 |
| P17 | 6 | 6 CONFIRMED | 6 of 6 | 6 of 6 |
| **Total** | **62** | 60 CONFIRMED, 2 REFUTED at row level | — | **34 of 36** |

**Literal output of the goal's verdict snippet:**

```text
P1-P7: {'CONFIRMED': 20, 'REFUTED': 1}
P8-P12: {'CONFIRMED': 15}
P13-P16: {'CONFIRMED': 19, 'REFUTED': 1}
```

These are row-level counts. The abstract states prediction-level counts, which
collapse the P1–P7 fidelity rows and the P8–P16 case rows as described in §1,
giving 6 of 7, 5 of 5 and 17 of 18.

The one row-level refutation in P1–P7 is P5 at the Linux fidelity; the other two
fidelities confirmed it, which is why the prediction-level count is 6 of 7. The
second row-level refutation is P16d in round 2. Both stay in the paper; neither
is hidden.

---

## 3. Paper A: every abstract number

| Abstract claim | Abstract value | Committed value | Source |
|---|---|---:|---|
| Prediction categories | 16 | 16 (P1–P16) | goal snippet over three verdict files |
| Named sub-cases | 34 | 34 (printed sum) | same |
| P17 follow-up | 6 cases | 6 verdict rows | `validation/round3/results/verdicts.csv` |
| Scored predictions | 36 | 36 | generator (`verdict_matrix` + `headline_counts`) |
| Confirmed | 34 | 34 | same |
| Round counts | 6/7, 5/5, 17/18, 6/6 | identical | same |
| P4: six orderings, one size | 1104 B | 1104.0 B in all six, model and Linux | `validation/layering/results/*_observations.csv` |
| P10: quantised ordering difference | −4 or +12 B | d(L) = +12, −4, −4, +12, +12, −4, −4, +12 | `validation/real_stack/results/observations.csv` |
| P2: ordering difference | 224 B (12,100 vs 12,324) | 12,100 / 12,324 → 224 | `validation/layering/results/linux_observations.csv` |
| P2: per-fragment statement | 28 B per affected fragment | 224 = 28 × (9 − 1) | frozen text in `layering-predictions.md` |
| P8a: AH through NAT | 0 % | 0.0 % | `validation/real_stack/results/observations.csv` |
| P13: outer CE under IPIP / WireGuard / ESP | fatal / inert / inert | 0.0 % / 100.0 % / 100.0 % | `validation/round2/results/observations.csv` |
| P5: Linux delivery difference | 12.35 pp | 64.28 − 51.92 = +12.35 pp | `validation/layering/results/linux_observations.csv` |
| P5: frozen expectation | 19.76 pp | 0.9³ − 0.9⁶ = 19.76 pp | frozen formula in `layering-predictions.md` |
| P16d: delivered | 673–717 of 2000 | min 673, max 717, sent 2000, 20 runs | `validation/round2/results/observations.csv` |
| Brier, round 2 | 0.0833 | 0.0833 over 18 predictions | `validation/round2/results/calibration.md` |
| Brier, round 3 | 0.0542 | 0.0542 over 6 predictions | `validation/round3/results/calibration.md` |
| Tamper tests | 27 | 27 (10 generator + 17 claim lint) | `tests/test_*` |

---

## 4. Paper B: statistical verification

### 4.1 Paired p-values (same paired seeds as the paper)

| Comparison | Abstract | Recomputed | n | Match |
|---|---|---:|---:|---|
| OEF vs static isolation, legitimate goodput | 84.65 % vs 86.48 %, p = 0.527 | 0.8465 vs 0.8648, diff −0.0183, p = 0.5274 | 30 | yes (0.5274 → 0.527) |
| MKB vs 1-D limiter, peak burst speed | 218.4 vs 222.0, p = 0.891 | 218.38 vs 222.04, diff −3.66, p = 0.8912 | 30 | yes (0.8912 → 0.891) |
| OEF + MKB combined goodput | 48.2 % | 0.4823 | 30 | yes |

The test is `scipy.stats.ttest_rel` on the paired per-seed rows of
`results/m4/final_benchmark_raw.csv`, matching the paper's stated method.

### 4.2 Break-even and EROI

The goal's suggested break-even formula (`E_tx_saved / requests`) returns
joules per request, not an energy threshold. EROI = 1 means the inference
budget equals the *total* transmission saving, so the break-even is
`E_llm* = E_tx_saved` (total). Both quantities are reported:

| Quantity | Abstract | Recomputed | Match |
|---|---|---:|---|
| Wire bytes, static → LLM | −42 % | 4650.0 → 2673.9 (−42.5 %) | yes |
| Transmission saving | 2.0×10⁻⁴ J | 1.976×10⁻⁴ J | yes |
| Inference cost | 60 J | 60.0 J (3 × 20 J) | yes |
| EROI | 3.3×10⁻⁶ | 3.294×10⁻⁶ | yes |
| Break-even inference, per 3-call transition | 0.2 mJ | 0.198 mJ | yes (2 s.f.) |
| Break-even inference, per call | 0.07 mJ | 0.066 mJ | yes (2 s.f.) |
| Static-vs-MKB churn break-even | about 0.19 J/edit | 0.185 J/edit | yes (0.185 → 0.19) |
| Stipulation margin | 27× | 5 / 0.185 = 27.1× | yes |
| OEF goodput deficit | 1.83 points | 0.0183 | yes |

### 4.3 Design constants

| Claim | Verified | Source |
|---|---|---|
| 30 paired seeds | 30 in M4, M6 exp1 and M6 exp2 | `results/m4/*.csv`, `results/m6/*.csv` |
| Five controller arms | all five arm names present in the CSVs | `results/m4/final_benchmark_raw.csv`, `results/m6/m6_exp1_raw.csv`, `results/m6/m6_exp2_raw.csv` |
| 100-node SimPy fabric | "100 nodes" in the topology builder | `simulation/surgical/topology.py` |

---

## 5. Corrections applied

| # | Paper | Before | After | Why |
|---|---|---|---|---|
| 1 | A | "test it with 36 scored predictions" | "test it with sixteen prediction categories (34 sub-cases in the real-stack rounds) plus a six-case replay-window follow-up. Together they expand into 36 scored predictions" | the goal snippet counts 16 categories and 34 sub-cases; P17 is a separate six-case follow-up; 36 is the scored total |
| 2 | B | "without significance (p = 0.891) at about 135× the per-tick CPU" | "without significance (p = 0.891)" | no results CSV records per-tick CPU; the 813.4 µs/tick values exist only in `results/m4_summary.md`, so the claim is not CSV-traceable |

An earlier draft of correction 1 said "seventeen prediction categories (P1–P17)".
When the goal was re-issued with its exact snippet, that wording was replaced by
the snippet's own output (16 categories, 34 sub-cases) plus the six-case P17
follow-up, so the abstract now matches the prescribed output literally. The
17-family reading stays in the §1 table for reconciliation with Table 8.

No numeric value needed changing. Every other number in both abstracts matched
the data exactly at the precision stated.

The removed CPU claim is not wrong; it is documented in
[`../results/m4_summary.md`](../results/m4_summary.md) ("Computational overhead"
table). It was removed from the abstract only because the abstract's standard is
now "reproducible from a committed data file by the verification script". Anyone
re-running the M4 benchmark can restore it with a persisted CPU column.

---

## 6. Cross-paper consistency

- **No shared predictions.** Paper A scores P1–P17 (layering); Paper B scores
  H5–H11 (bio-control). There is no prediction that one paper confirms and the
  other refutes.
- **Seed methodology is different by design, and correctly so.** Paper A uses
  2,000 paired seeds in the model/SimPy, 40 netem seeds × 100 datagrams on
  Linux, and 20 runs per kernel case. Paper B uses 30 paired seeds. The goal's
  premise of a shared 30-seed methodology does not hold for Paper A; the
  abstracts already state each design, and no change was made.
- **Terminology.** Both papers use "quantised". Paper B's "zero-sum and
  time-quantised" is specific to buffer behaviour and does not appear in Paper A;
  Paper A's "quantised fields" and "fixed size effects" are consistent with it.
  Paper B does not use "settling time" (that term belongs to Paper C / CRMR), so
  the three papers do not collide.

---

## 7. Residual traceability notes

Three quantities cannot come from a CSV row, and are disclosed rather than
dropped:

1. **Brier scores (0.0833, 0.0542).** The credences live in
   `validation/round2/results/calibration.md` and
   `validation/round3/results/calibration.md`. The generator parses those
   tables; no CSV records credences. The values are reproducible with the
   committed files.
2. **19.76 pp.** This is the frozen expectation `0.9³ − 0.9⁶` stated in
   `layering-predictions.md`, not a measurement. The script recomputes it.
3. **100 nodes.** A scenario constant in `simulation/surgical/topology.py`
   ("10x10 grid, 100 nodes"), not a measured count.

Front-matter counts (21 pages, 15 tables, 2 figures in Paper A; 4 pages, 1 table
in Paper B) are artifact counts from `pdfinfo`/`pdftotext`, not abstract claims.

---

## 8. Full script output

```text
M14 verification: committed data -> abstract numbers
repository: C:\Users\Milan\Projects\7g-backhaul-simulation

==============================================================================
1. VERDICT FILES: rows, categories and outcomes
==============================================================================
P1-P7   rows=21  distinct prediction values= 7  distinct cases= 0  verdicts={'CONFIRMED': 20, 'REFUTED': 1}
        per-prediction (any fidelity refuted -> REFUTED): {'P1': 'CONFIRMED', 'P2': 'CONFIRMED', 'P3': 'CONFIRMED', 'P4': 'CONFIRMED', 'P5': 'REFUTED', 'P6': 'CONFIRMED', 'P7': 'CONFIRMED'}
P8-P12  rows=15  distinct prediction values= 5  distinct cases=15  verdicts={'CONFIRMED': 15}
P13-P16 rows=20  distinct prediction values= 4  distinct cases=20  verdicts={'CONFIRMED': 19, 'REFUTED': 1}
P17     rows= 6  distinct prediction values= 6  distinct cases= 6  verdicts={'CONFIRMED': 6}

total verdict rows: 62
distinct prediction values, all four files: 22 -> ['P1', 'P10', 'P11', 'P12', 'P13', 'P14', 'P15', 'P16', 'P17a', 'P17b', 'P17c', 'P17d', 'P17e', 'P17f', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9']
distinct main categories, first three files only (the goal script): 16 -> ['P1', 'P10', 'P11', 'P12', 'P13', 'P14', 'P15', 'P16', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9']
normalised categories (P17a-f -> P17): 17 -> ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9', 'P10', 'P11', 'P12', 'P13', 'P14', 'P15', 'P16', 'P17']

==============================================================================
2. SCORED PREDICTIONS (the unit Table 8 and the Brier denominators use)
==============================================================================
verdict-matrix rows: 50 (P1-P7 contribute 21 fidelity rows that collapse to 7 predictions)
  P1-P7        6 of 7
  P8-P12       5 of 5
  P13-P16      17 of 18
  P17          6 of 6
  total        34 of 36
total scored predictions: 36, confirmed 34

==============================================================================
3. PAPER A: abstract numbers
==============================================================================
P4 wire bytes by ordering (linux): {'E>S>T': 1104.0, 'E>T>S': 1104.0, 'S>E>T': 1104.0, 'S>T>E': 1104.0, 'T>E>S': 1104.0, 'T>S>E': 1104.0}
P4 wire bytes by ordering (model): {'E>S>T': 1104.0, 'E>T>S': 1104.0, 'S>E>T': 1104.0, 'S>T>E': 1104.0, 'T>E>S': 1104.0, 'T>S>E': 1104.0}
  -> all six orderings equal 1104 B: True
P2 wire bytes E->F 12100, F->E 12324, difference 224
P10 d(L) = wire(IPIP then WG) - wire(WG then IPIP): {64: 12.0, 65: -4.0, 76: -4.0, 77: 12.0, 79: 12.0, 100: -4.0, 1000: -4.0, 1008: 12.0}
  -> non-empty and d(L) in {-4, +12}: True
P5 Linux delivery C->F 64.28 %, F->C 51.92 %, difference +12.35 pp
  frozen expectation 0.9^3 - 0.9^6 = 19.76 pp
P8a AH through NAT delivery: 0.0 %
P13 delivery with outer CE: IPIP P13a 0.0 %, WireGuard P13d 100.0 %, ESP P13f 100.0 %
P16d delivered: min 673, max 717, n=20 runs, sent/run 2000
round-2 Brier over 18 scored predictions: 0.0833
round-3 Brier over 6 scored predictions: 0.0542
tamper tests: 27

==============================================================================
4. PAPER B: abstract numbers
==============================================================================
m4 arms: ['m3_surgical_1d', 'm4_combined', 'm4_mkb', 'm4_oef', 'static_isolation']; seeds per arm: [30]
OEF vs static goodput: 0.8465 vs 0.8648, diff -0.0183, paired p=0.5274, n=30
MKB vs 1-D limiter peak speed: 218.38 vs 222.04, diff -3.66, paired p=0.8912, n=30
combined OEF+MKB goodput: 0.4823
churn edits over 30 seeds: raw MKB 1438, EWMA 1546, ratio 1.0751 (+7.5 %)
static-vs-MKB churn break-even: 0.185 J/edit (= (E_tx_static - E_tx_mkb) / edits_per_seed); 5 J stipulation is 27.1x
wire bytes static 4650.0 -> LLM 2673.9 (42.5 % reduction)
E_tx_saved 1.976133e-04 J, E_llm 60.0 J, EROI 3.294e-06
break-even inference energy: 0.198 mJ per 3-call transition, 0.066 mJ/call
arms present in the M4/M6 CSVs: ['greedy_heuristic', 'llm_compiler', 'm3_surgical_1d', 'm4_combined', 'm4_mkb', 'm4_oef', 'm4_raw_mkb', 'm5_ewma_mkb', 'static_iso', 'static_isolation']
  -> the five controller arms of the Paper B table are all present: True
paired seeds: M4 30, M6 exp1 30, M6 exp2 30
'813.4 us/tick' (the ~135x per-tick CPU claim) present in any results CSV: False
fabric size: topology.py says 100 nodes -> True

No files were modified by this script.
```

---

## 9. Conclusion

The abstracts are now defensible against the committed data:

- Every result number in both abstracts is reproduced by `tools/verify_m14.py`
  from a committed data file.
- The prediction-count ambiguity is resolved and documented: **16 main
  categories with 34 named sub-cases, plus a six-case P17 follow-up, expanded
  into 36 scored predictions, 34 confirmed**; the 17-family reading (P1–P17) is
  kept in §1 for reconciliation with Table 8.
- One claim was removed because it had no CSV backing (the ~135× per-tick CPU
  multiple in Paper B). No number was changed to a different value, and no data
  was touched.
