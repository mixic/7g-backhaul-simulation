# M4 summary (means and 95% confidence intervals over 30 paired seeds)

Bare numbers plus the mechanical H5/H6 verdicts.  Interpretation follows.

## Verdicts

| H5 OEF compensation | **REFUTED** |

OEF legitimate goodput (CMRO2) = **0.8576 +/- 0.0573** vs static_isolation **0.8810 +/- 0.0147** (M3 confound, documented at 86.5 % / 0.865). Target: > 0.90 and > static_isolation. Starvation cost (transit drop rate) = **0.0990 +/- 0.0344**.

| H6 MKB baselining | **REFUTED** |

MKB peak state-change speed = **316.5900 +/- 40.1900** vs 1D limiter **230.5800 +/- 27.9742** (must be lower to cap the burst). MKB false-positive edits = **109.4000 +/- 20.3291** vs 1D limiter **0.0000 +/- 0.0000** (must be fewer).

## exp1 (H5): OEF vs static_isolation vs surgical

| baseline | Legitimate_Goodput_CMRO2 | Total_Throughput_CBF | OEF_Value | Transit_Drop_Rate | p95_Ratio | Goodput_Base |
|---|---|---|---|---|---|---|
| oef_surgical | 0.8576 +/- 0.0573 | 297541774.6914 +/- 10753156.7647 | 0.9951 +/- 0.0095 | 0.0990 +/- 0.0344 | 1.0718 +/- 0.0430 | 0.9522 +/- 0.0036 |
| static_isolation | 0.8810 +/- 0.0147 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0645 +/- 0.0090 | 1.1567 +/- 0.0309 | 0.9455 +/- 0.0064 |
| surgical | 0.8576 +/- 0.0573 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0990 +/- 0.0344 | 1.0718 +/- 0.0430 | 0.9522 +/- 0.0036 |

## exp2 (H6): MKB vs 1D limiter (peak burst test)

| baseline | Peak_State_Change_Speed | Number_of_Edits | False_Positive_Edits | Legitimate_Goodput |
|---|---|---|---|---|
| mkb | 316.5900 +/- 40.1900 | 168.4000 +/- 25.0131 | 109.4000 +/- 20.3291 | 0.5580 +/- 0.0442 |
| surgical | 230.5800 +/- 27.9742 | 47.4000 +/- 5.7874 | 0.0000 +/- 0.0000 | 0.9153 +/- 0.0332 |

## Interpretation

**H5 (OEF) — REFUTED.** The CBF monitor tracks *total delivered throughput*, which the DDoS shockwave does not lower: attack traffic is delivered alongside legitimate traffic, so the aggregate served-byte count climbs (the flood's bytes are served too) instead of collapsing.  The per-node CBF-drop trigger therefore never fires during the attack, and OEF reaches its recorded peak only when traffic stops at end-of-run.  Consequently OEF is identical to the plain surgical controller (both 0.8576) and sits below static_isolation.  The Fick premise — that a DDoS lowers delivered CBF — does not hold in this testbed, so the compensation has nothing to compensate.

**H6 (MKB) — REFUTED.** The vector trigger does not cap the peak burst state-change speed (it is *higher* than the 1D limiter) and it issues a large number of false-positive edits during steady traffic.  The short-window EMA manifold amplifies Poisson noise in the 4-dimensional state vector, so ||A - EMA(A)|| crosses its adaptive floor without any real anomaly and fires surgical edits on innocent classes — the opposite of the state economy the hypothesis predicts.
