# Signed-trend results

**Claim:** pre-registered in [`docs/signed-trends.md`](signed-trends.md) before
this run. **Verdict: REFUTED.** Signing the trend terms lowers delivery to the
unattacked target during the flood's decay by 10.1 pp, not raises it by 2 pp,
and costs 1.10 pp of steady-state delivery (limit 1 pp). The recovery-time
bound passes trivially because the controller keeps `α` chronically low.

## 1. Arms (12 paired seeds, `flood_wave`)

| Arm | E3 legit delivery, ticks [85,105) | E2 α recovery (ticks) | Steady delivered |
|---|---:|---:|---:|
| positive-only (current) | 93.07 % | 2.17 | 99.24 % |
| signed | 82.99 % | 0.00 | 98.14 % |
| signed, release gain 2.0 | 82.99 % | 0.00 | 98.14 % |
| separated (fixed roles) | 100.00 % | — | 99.24 % |

## 2. Pre-registered tests

| Test | Value | Threshold | Result |
|---|---:|---|---|
| E3 decay gain | **−10.08 pp** | ≥ +2 pp | **FAIL** |
| recovery-time reduction | 100 % | ≥ 15 % | PASS (degenerate) |
| steady-state loss | **1.10 pp** | ≤ 1 pp | **FAIL** |

The claim is refuted: the signed controller moves in the wrong direction on the
metric it was supposed to improve, and it also misses the steady-state guard by
0.10 pp. The release gain of 2.0 has no effect at all — the negative trend
already saturates the `α` clamp, so weighting it harder changes nothing.

## 3. What happened

The figure (`figures/signed_trends_alpha.png`) shows the mechanism. The
positive-only controller holds `α(E2)` around 0.6–0.9 through the flood. The
signed controller swings `α` between roughly 0.33 and 0.66 at **every control
interval**: the finite-difference velocity and acceleration alternate sign from
tick to tick, so the release signal flips on and off. This is role churn, the
failure mode the damping discussion warned about, reintroduced through the
trend channel.

Two consequences:

1. **`α` is lower everywhere, not just where the flood recedes.** Pressure falls
   at every node during the ramp-down, so every node releases serving capacity.
   `E3` — which is not attacked — also serves less locally and pushes its
   demand onto the transit paths, so its delivery falls from 93.07 % to 82.99 %.
2. **Recovery is “faster” only because the controller never committed much.**
   The 2.17 → 0 tick recovery is not a benefit; `α` is already low before the
   flood ends.

The separated baseline keeps `E3` at 100 % throughout the decay window because
its edge server never reallocates away from serving.

## 4. What this does and does not show

- It shows that negative velocity and acceleration **do carry information** —
  `α` does move down during the ramp-down — but that an unfiltered, global
  signed term is the wrong way to use it. The sign flip is noise-dominated and
  the release is not localised to the attacked node.
- It does not show that negative trend is useless. A plausible next design
  applies the release only where the flood is identified (using the
  authenticated name-class filter from
  [`attack-aware.md`](attack-aware.md)), with a deadband or a low-pass filter so
  the second-order estimate cannot flip the role every control step. That is a
  new claim, not a result of this one.
- It does not close the RFMP loop and is not a DDoS defence.
- The 2 pp / 15 % / 1 pp thresholds were not relaxed after the result.

## 5. Reproduction

```powershell
py -3 tools\benchmark_signed_trends.py --output-dir figures
py -3 tools\plot_signed_trends.py --input-dir figures --output-dir figures
py -3 -m pytest tests\test_dual_role.py -q
```

Outputs: `figures/signed_trends_summary.csv`,
`figures/signed_trends_verdict.csv`, `figures/signed_trends_alpha.csv`, and
`figures/signed_trends_alpha.png`.

## 6. Limitations

- One flood shape and one topology; the sign-flip pathology is a property of
  the finite-difference estimator at a 2-tick control interval.
- The recovery metric is degenerate when the controller never commits; it is
  reported but not treated as evidence of a benefit.
- The controller still cannot distinguish attack from legitimate demand.
