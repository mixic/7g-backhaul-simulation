# DDMR predictions (M11) — frozen before the run

**Status:** frozen. The constants below live in code
(`simulation/ddmr.py`, `simulation/ddmr_scenario.py`) and were fixed before the
30 paired seeds ran. Results are in [`ddmr.md`](ddmr.md).

## Hypothesis H14

> Under a DDoS shockwave, an NDN forwarding plan that dynamically increases the
> dimensionality of its metric space will keep the legitimate Content Delivery
> Rate at least 15 percentage points higher than a static T-NDN baseline,
> because the higher-dimensional space separates the attack's topological
> signature from legitimate traffic.

The strict reading of "15 % higher" is used: **15 percentage points** on the
legitimate CDR during the attack window. H14 is refuted by any of:

1. a CDR gain below 15 points on the 30-seed mean;
2. DDMR's CDR in the attack window below 95 %;
3. a 4-D homology cost above the energy saved by the prevented legitimate
   losses;
4. an early collapse: the dimension returning to 1 before the attack ends.

## Scenario (frozen)

| Quantity | Value |
|---|---|
| Nodes | the M10 100-node geometric topology (seed-paired) |
| Prefix blocks | 20, 500 names each (`/service/region/type/object`) |
| Instances | 3 per block: the primary plus the two nearest distinct nodes |
| Capacity | 200 requests/s per instance, drop-tail, `20 ms · u³` queue |
| Legitimate traffic | Poisson 200/s for 60 s; block 0 carries 40 % |
| Attack | Poisson 500/s from 20 bots to *block 0* for t in [30, 45) s |
| Attack jitter | 10 ms + exponential(30 ms); legitimate 2 ms exponential |
| Seeds | 30, base 2026, paired: one network, request stream and instances for all strategies |

## State vector and manifold (frozen)

`S(t) = [D_prefix, L_latency, J_jitter, A_anomaly]`

| Axis | Definition |
|---|---|
| `D_prefix` | `0.1 · block / 19` (position in the prefix hierarchy) |
| `L_latency` | `max(0, latency − baseline) / 100 ms`, clipped to 1 |
| `J_jitter` | flow jitter EMA / 50 ms, clipped to 1 |
| `A_anomaly` | `clip((flow_rate − 2)/2, 0, 1)` requests/s |

The dimension trigger is the **local block anomaly**: the nominal rate per
prefix block is measured during a 10 s warm-up and frozen; the anomaly is the
Poisson z-score mapped by `(z − 3)/3` to `[0, 1]`. The only time constants are
the monitor's own warm-up and rate window; there is no attack schedule or
attack flag in the detector.

| Constant | Value |
|---|---:|
| `EPS_MANIFOLD` | 0.25 |
| `ANOMALY_HIGH` / `ANOMALY_LOW` | 0.70 / 0.45 |
| `UP_TICKS` / `DOWN_TICKS` | 2 / 4 telemetry ticks (0.5 s / 1 s) |
| Manifold period | 2 s (plus an immediate recomputation on a switch) |
| Points per manifold | up to 150 active flows, top by rate |
| Homology | `ripser`, Vietoris–Rips, `maxdim=1` |

The attack cluster is a component whose mean anomaly is above 0.70 **and**
whose mean jitter is above 0.20; a flow whose nearest centroid is an attack
component stays on the primary instance, while every other flow goes to the
healthy replica with the lowest measured latency.

## Baselines (frozen, same inputs)

| Strategy | Anomaly detector | Dimension | Routing |
|---|---|---|---|
| NLSR | no | none | primary instance (prefix cost) |
| FSR-NDN | no | none | primary instance (prefix cost) |
| Static T-NDN | **yes, identical** | pinned to 1 | primary instance |
| DDMR | yes | 1 → 4 on anomaly | attack component primary, legitimate component healthy replica |

All four see the same three instances per block, the same request stream, the
same attack and the same drop-tail model. Only the selection rule differs.

## Energy accounting (stipulated)

| Constant | Value |
|---|---:|
| CPU power while computing homology | 15 W |
| Energy per prevented lost legitimate request | 0.02 J |

The break-even value is reported: `E_cpu / prevented_losses`. If a prevented
loss is worth less than that, the energy clause refutes H14 even when the CDR
clause passes.

## Expected outcome (stated in advance)

- DDMR expands at the attack onset (30–31 s) and contracts after the attack
  ends, not before it.
- Static T-NDN, NLSR and FSR-NDN stay near `capacity / (legit + attack)` for
  the attacked block, so the legitimate CDR in the window is roughly 35–74 %.
- DDMR stays above 95 % for the legitimate traffic.
- The expanded complex gains components; whether it also gains `H1` loops is
  measured and reported, not assumed.
- The 4-D cost is a few joules, far below the prevented-loss energy at the
  stipulated 0.02 J/request.

The result is **supported only if all four criteria pass on the 30-seed means**;
per-seed pass fractions, the collapse time and any oscillation are reported
either way.
