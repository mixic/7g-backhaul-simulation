# Attack-aware admission results

**Claim:** pre-registered in [`docs/attack-aware.md`](attack-aware.md) before
this run. **Verdict: REFUTED** at the pre-registered false-negative rate of
0.5, and the perfect-classifier gain misses the 5 pp bar by 0.09 pp.

The experiment tests whether filtering unauthenticated attack-shaped load
before it reaches the dual-role controller fixes the collateral damage
documented in [`dual-role-results.md`](dual-role-results.md). It uses the same
`ddos` scenario (a +250 Mbps flood at `E2`), 12 paired seeds, and a stipulated
name-class classifier with a 2 % false-positive rate.

## 1. Arms (legitimate delivery, mean over 12 seeds)

| Arm | E1 | E2 (attacked) | E3 | Total delivered |
|---|---:|---:|---:|---:|
| separated, no filter | 99.05 | 84.14 | 98.79 | 80.89 % |
| fluid, no filter | 98.98 | 71.61 | 92.08 | 64.91 % |
| fluid, authenticated, `fn = 0.0` | 96.96 | 97.68 | 96.99 | 99.25 % |
| fluid, authenticated, `fn = 0.1` | 96.99 | 97.35 | 96.95 | 99.13 % |
| fluid, authenticated, `fn = 0.2` | 97.03 | 96.18 | 96.87 | 98.37 % |
| fluid, authenticated, `fn = 0.3` | 97.03 | 92.36 | 96.40 | 95.24 % |
| fluid, authenticated, `fn = 0.4` | 97.03 | 87.31 | 95.63 | 90.16 % |
| fluid, authenticated, `fn = 0.5` | 97.03 | 83.26 | 93.81 | 85.13 % |
| fluid, authenticated, `fn = 0.9` | 97.04 | 72.36 | 90.52 | 68.48 % |

Admission recovers most of the damage: at `fn = 0`, legitimate delivery at the
attacked target rises from 71.61 % to 97.68 % (the flood no longer crowds it),
and the unattacked `E3` rises from 92.08 % to 96.99 %. The 2 % false-positive
cost caps the recovered delivery near 97 % (some legitimate requests are
dropped).

## 2. Pre-registered tests

| Test | Value | Threshold | Result |
|---|---:|---|---|
| claim at `fn = 0.5` | E2 83.26 %, E3 93.81 %, E3 gain +1.73 ± 0.18 pp | all targets ≥ 95 %, E3 gain ≥ 5 pp | **FAIL** |
| perfect-classifier gain | +4.91 ± 0.17 pp | ≥ 5 pp | **FAIL** (by 0.09 pp) |
| classifier leakage threshold | none on the grid | ≥ 50 % | **FAIL** |

The claim as written is refuted: at a 50 % flood leakage, the attacked target
falls to 83.26 % and `E3` to 93.81 %, and the `E3` gain is only 1.73 pp.
Even with perfect flood rejection, the `E3` gain is 4.91 pp, just under the
5 pp bar; the 95 % interval is [4.74, 5.08], so the bar is not clearly met.

## 3. What the classifier must achieve

Although the pre-registered bound fails, the sweep quantifies the requirement:

- **All targets ≥ 95 %** holds for false-negative rate **≤ 0.2** (80 % of the
  flood rejected). `E2` is the binding target.
- **`E3` ≥ 95 %** holds up to about `fn = 0.4` (95.63 %), but `E2` has already
  fallen below 95 % at `fn = 0.3`.
- The **+5 pp `E3` gain** is never reached because the stipulated 2 % false
  positive caps all-target delivery near 97 %.

So the condition under which the fluid controller is safe under this flood is
not "authenticate the name" alone: the filter must also reject at least ~80 %
of the attack volume, and the false-positive cost must be small enough to
leave room for the delivery target.

## 4. What this does and does not show

- It shows that **separating authenticated demand from flood volume before the
  role controller is the right lever**: it removes most of the collateral
  damage that made the unclassified controller fail. It does **not** show that
  the pre-registered 5 pp / 50 % classifier bound is met.
- The classifier is stipulated: false-positive and false-negative rates are
  inputs, not measurements. No signature scheme, name resolution or
  attestation is implemented.
- The defence is dropping unverified volume before it competes for capacity.
  Verified and admitted attack traffic are not given different priority after
  admission; the proportional-attribution of delivered volume is stipulated.
- The RFMP loop is **not** closed here: this is still a flow-level controller.
  Wiring a policy-driven controller to RFMP role epochs remains the next step.
- A refutation is reported, not removed. The 5 pp threshold was not relaxed
  after seeing the result.

## 5. Reproduction

```powershell
py -3 tools\benchmark_attack_aware.py --output-dir figures
py -3 tools\plot_attack_aware.py --input-dir figures --output-dir figures
py -3 -m pytest tests\test_dual_role.py -q
```

Outputs: `figures/attack_aware_summary.csv`, `attack_aware_sweep.csv`,
`attack_aware_verdict.csv`, and `figures/attack_aware_ddos.png`.

## 6. Limitations

- Flow-level model; no packets, no signature verification, no rate limiting.
- One topology and one flood profile; the 80 % rejection threshold is
  conditional on them.
- False-positive/negative rates are stipulated, not calibrated against a real
  classifier.
- The `E2` legitimate-delivery attribution assumes proportional sharing after
  admission; `E1`/`E3` are unaffected by that assumption because they carry no
  attack demand.
