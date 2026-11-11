# CRMR predictions (H15) — frozen before the 30-seed run

**Status:** frozen. A pilot run on seed 2026 fixed the thresholds below and is
**excluded** from the evaluation; the reported run uses seeds 2030–2059. The
scenario and controller constants live in `simulation/crmr.py` and
`simulation/crmr_scenario.py` and were fixed before the pilot.

## Hypothesis H15

> A phase-continuous rotation of the DDMR metric family keeps the legitimate
> CDR under a sustained DDoS within 5 points of discrete DDMR and at least 15
> points above static T-NDN, while reducing the peak per-tick reconfiguration
> share by at least 50 %. Under *flapping* bursts the rotation cannot complete
> inside a burst, and the CDR cost is measured as the boundary of the mechanism.

The earlier draft in `docs/future-work-complex-rotation.md` proposed a 2-point
sustained gap. The pilot showed the rotation's settling time costs about three
points even when the attack is sustained, so the frozen guardrail is 5 points.
The flapping gap is not a pass/fail criterion: it is the measured cost.

H15 is refuted by any of:

1. peak reconfiguration share above 50 % of DDMR's;
2. sustained CDR gap above 5 points, or a gain below 15 points over static;
3. a 4-D homology cost above the energy saved by the prevented losses.

## Scenario (frozen)

| Quantity | Value |
|---|---|
| Nodes / topology | the M10 100-node geometric network, seed-paired |
| Prefix blocks | 20 blocks × 500 names; block 0 carries 40 % of legitimate traffic |
| Instances | 3 per block (primary + two replicas), 200 requests/s capacity, `20 ms·u³` queue |
| Legitimate traffic | Poisson 200/s for 60 s |
| Attack | 500/s from 20 bots to block 0 |
| Flapping regime | five 3 s bursts with 3 s gaps, t = 30–57 s |
| Sustained regime | one 15 s burst, t = 30–45 s |
| Control tick | 0.1 s |
| Anomaly monitor | M11 block monitor, 10 s warm-up, **1 s** rate window |
| Seeds | 30 (2030–2059), paired across arms |
| Pilot | seed 2026, excluded |

## Controller constants (frozen)

| Constant | Value |
|---|---:|
| `ANOMALY_LO` / `ANOMALY_HI` | 0.20 / 0.80 |
| `ZETA` / `OMEGA` | 1.0 / 3.0 rad/s |
| `RADIUS_GAIN` | 1.0 |
| Gate for "phase active" (churn crossings) | π/4 |
| Calm threshold (1-D manifold) | 0.05 rad |
| Manifold period | 2 s, plus the calm→phase transition |
| Points per manifold | up to 150 active flows |
| Homology | `ripser`, Vietoris–Rips, `maxdim=1`, phase-scaled ε |

## Arms (frozen)

| Arm | Detector | State | Legitimate routing |
|---|---|---|---|
| Static T-NDN | same block monitor | 1-D, pinned | primary |
| DDMR | same | discrete 1→4 with M11 hysteresis | healthy replica when dimension 4 and block attacked, all-or-nothing |
| CRMR | same | continuous phase θ(t) | healthy replica with probability `sin²θ`, attack component always primary |

## Metrics (frozen)

1. **Peak reconfiguration share** — the largest single-tick change of the
   theoretical legitimate share routed to a healthy replica.
2. **CDR** — delivered legitimate requests / legitimate requests in the attack
   windows, overall and for block 0.
3. **Per-cycle CDR standard deviation** (flapping regime).
4. **p95 latency** of delivered legitimate requests in the attack windows.
5. **Energy** — 4-D homology at 15 W against 0.02 J per prevented legitimate
   loss, with the break-even reported.

## Expected outcome (stated in advance)

- Peak reconfiguration: CRMR ≤ 0.5 × DDMR (the phase ramps over ~0.5 s).
- Sustained: CRMR within 5 points of DDMR, and ≥ static + 15.
- Flapping: the CDR gap exceeds the sustained gap because each 3 s burst is
  shorter than the rotation's settle time; the gap is reported, not hidden.
- Energy: passes at the stipulated 0.02 J/loss; the break-even is reported.

Per-seed pass fractions, the measured gaps and the break-even are reported
whether or not the criteria pass.
