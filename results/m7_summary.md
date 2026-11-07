# M7: dual-band (LPF + HPF) filtering

Steady traffic (Poisson jitter), 10 s DDoS shockwave at t = 30 s, 30 paired seeds.

## Detection (H13)

| arm | Detection_Latency_s | False_Positives | Detected |
|---|---|---|---|
| m4_raw_mkb | 1.514 +/- 0.300 | 0 | 28/30 |
| lpf_only | 0.220 +/- 0.022 | 6 | 30/30 |
| dual_band | 0.200 +/- 0.000 | 115 | 30/30 |

**H13 dual-band detection — REFUTED.**
False positives (total over 30 seeds): dual_band 115, lpf_only 6, m4_raw_mkb 0.
Mean detection latency (s): dual_band 0.200, lpf_only 0.220, m4_raw_mkb 1.514.

**Jitter cost (reported, not tuned away).** The dual-band HPF is too sensitive to Poisson jitter: its dynamic k-sigma threshold adapts down during quiet periods and is crossed by isolated batch arrivals, so the high-pass band does not isolate the attack energy from the background noise. The single-LPF baseline (a fixed 0.10 utilization threshold) has nearly the same latency but ~20x fewer false positives, so the dual-band filter does *not* beat it on the false-positive requirement of H13.

## Protection (H14)

| arm | Legit_Goodput | E_churn_J | Peak_State_Change_Speed | RER_Events |
|---|---|---|---|---|
| m4_raw_mkb | 0.870 +/- 0.037 | 238.0 +/- 24.0 | 239.73 +/- 23.35 | 0 |
| lpf_only | 0.915 +/- 0.032 | 355.0 +/- 41.7 | 258.03 +/- 13.36 | 2 |
| dual_band | 0.659 +/- 0.057 | 988.0 +/- 85.5 | 281.21 +/- 26.11 | 15 |

**H14 protection efficacy — REFUTED.**
dual_band goodput 0.659 (>0.90 required); dual_band E_churn 988.0 J vs m4_raw_mkb 238.0 J.
