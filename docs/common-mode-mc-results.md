# Isolation and multipath under common-mode failure: Monte Carlo results (MC-H16-MC-H20)

**Status:** complete. The distributional model, the decision rule and the expected
outcomes were frozen in
[`common-mode-mc-predictions.md`](common-mode-mc-predictions.md) at commit
`6c8d320`, before `simulation/common_mode_mc.py` existed. This document interprets
the run; it does not change the frozen text. The deterministic reference study
([`common-mode-results.md`](common-mode-results.md)) is reported separately and is
not superseded: it is the zero-variance limit of the same structural model.

**One-line result:** under the frozen stochastic model all five hypotheses pass
under the interval rule, nominal and Bonferroni: tenant isolation contains a
tenant-shared fault but not a shared identity failure; SRLG-disjoint multipath
survives a conduit failure that shared-fate multipath does not; a one-way boundary
holds **90.00 % [90.00, 90.00]** under an AI failure where independent control
without the boundary holds 0 %; the isolation-multipath interaction is
**+41.51 points [+41.27, +41.75]**; and a global cooperative controller loses
**+99.64 points [+99.38, +99.86]** when it fails with its primary path. A tested
fallback is worth **+30.52 points** over an untested one on the same backhaul cut.

The simulation also changes two readings that the deterministic model could not
express. First, in a 30-day campaign the shared control plane accounts for
**61-98 %** of dependency-driven unavailability for the arms that require it, and
0 % for the one-way arms. Second, congestion, not failure, dominates the
unavailability of the single-path arms: A1 loses 4.70 points to congestion and
1.04 to dependency failures, and isolation without multipath (A9) pays the 9.84
point policy cost *and* 4.23 points of congestion.

## 1. Protocol

| Quantity | Value |
|---|---|
| Engine | continuous-time piecewise-constant simulation; no fixed tick |
| Incident experiment (E1) | 9 arms x 10 incident classes x 2 000 replications = 180 000 arm-runs, 24 h horizon |
| Campaign experiment (E2) | 9 arms x 500 replications = 4 500 arm-campaigns, 30-day horizon |
| Sensitivity (E3) | 7 constants x 25 values x 500 replications per point |
| Global sensitivity (E4) | Saltelli/Sobol, base 256, 8 parameters, 20 replications per evaluation |
| Two-factor grid (E5) | 5 x 5 efficiency x tested-fallback capacity, 500 replications per cell |
| Common random numbers | every draw shared by all nine arms within a replication |
| Decision rule | 95 % percentile bootstrap interval wholly inside the passing region |
| Freeze commits | MC protocol `6c8d320`; reference protocol `1c781f3` |

Command:

```bash
py -3 tools/benchmark_common_mode_mc.py
py -3 tools/benchmark_common_mode_mc.py --sensitivity --sensitivity-points 25 --sensitivity-replications 500
py -3 tools/benchmark_common_mode_mc.py --sobol
py -3 tools/benchmark_common_mode_mc.py --two-factor
py -3 tools/make_common_mode_mc_figures.py
```

A rerun of the first command reproduces `common-mode-mc-differences.csv` and
`common-mode-mc-verdicts.csv` byte for byte (SHA-256
`A8109C28...363AC2` and `7706B049...898835`).

## 2. Availability during the event (%, mean over 2 000 replications)

| Event | A1 | A2 | A3 | A4 | A5 | A6 | A7 | A8 | A9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `none` | 92.58 | 99.24 | 99.25 | 99.36 | 99.81 | 90.00 | 90.00 | 99.80 | 84.05 |
| `link` | 0.00 | 99.04 | 99.08 | 99.18 | 99.64 | 89.98 | 89.98 | 99.53 | 48.41 |
| `srlg` | 0.00 | 0.00 | 99.08 | 99.18 | 99.64 | 89.98 | 89.98 | 99.53 | 48.41 |
| `backhaul_cut` | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 48.59 | 18.07 | 0.00 | 48.59 |
| `provider_cp` | 0.00 | 99.04 | 99.06 | 99.17 | 99.64 | 89.98 | 89.98 | 99.52 | 48.64 |
| `idp` | 0.00 | 0.00 | 0.00 | 0.00 | 99.66 | 90.00 | 90.00 | 99.65 | 84.49 |
| `ai` | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 90.00 | 90.00 | 0.00 | 84.49 |
| `tenant_gw` | 0.00 | 0.00 | 0.00 | 99.20 | 99.66 | 90.00 | 90.00 | 99.65 | 84.34 |
| `controller_link` | 0.00 | 99.04 | 99.08 | 99.18 | 99.64 | 89.98 | 89.98 | 0.00 | 48.41 |
| `ai_link` | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 89.98 | 89.98 | 0.00 | 48.48 |

Half-widths of the 95 % interval are 0.00-0.40 points; the widest are A2 and A3
under `link` and `controller_link` (0.39-0.40), where a background conduit failure
sometimes coincides with the incident window. Cells whose mechanism is
deterministic in the model have zero-width intervals by construction; that is a
property of the model, not a property of the world.

## 3. Hypothesis verdicts

| Criterion | Quantity | Estimate | 95 % interval | p | Pass fraction | Verdict | Bonferroni |
|---|---|---:|---|---:|---:|---|---|
| H16a | A4 - A3, `tenant_gw` | 99.20 | [98.82, 99.54] | < 0.0001 | 0.991 | PASS | PASS |
| H16b | abs(A4 - A3), `idp` | 0.00 | [0.00, 0.00] | < 0.0001 | 1.000 | PASS | PASS |
| H17a | A3 - A2, `srlg` | 99.08 | [98.67, 99.44] | < 0.0001 | 0.993 | PASS | PASS |
| H17b | A2 - A1, `link` | 99.04 | [98.62, 99.41] | < 0.0001 | 0.990 | PASS | PASS |
| H18a | A6 - A5, `ai` | 90.00 | [90.00, 90.00] | < 0.0001 | 1.000 | PASS | PASS |
| H18b | A6 level, `ai` | 90.00 | [90.00, 90.00] | < 0.0001 | 1.000 | PASS | PASS |
| H18c | A5 - A6, `none` | 9.81 | [9.75, 9.86] | < 0.0001 | 1.000 | PASS | PASS |
| H19a | (A6-A3)-(A9-A1), `ai_link` | 41.51 | [41.27, 41.75] | < 0.0001 | 1.000 | PASS | PASS |
| H19b | A6 level, `ai_link` | 89.98 | [89.97, 89.99] | < 0.0001 | 1.000 | PASS | PASS |
| H19c | A3 level, `ai_link` | 0.00 | [0.00, 0.00] | < 0.0001 | 1.000 | PASS | PASS |
| H20a | A5 - A8, `controller_link` | 99.64 | [99.38, 99.86] | < 0.0001 | 0.997 | PASS | PASS |
| H20b | abs(A5 - A8), `none` | 0.01 | [0.00, 0.01] | < 0.0001 | 1.000 | PASS | PASS |

H16 PASS, H17 PASS, H18 PASS, H19 PASS, H20 PASS, and the same verdicts hold at
the Bonferroni level `0.05/12`. The per-replication pass fractions are 0.990-1.000;
the criteria that are not 1.000 are those where a background failure can coincide
with the incident window and move a difference across the threshold on that
replication.

## 4. Readings

**H16 — isolation is a boundary, not a control-plane cut.** The tenant gateway
failure takes A3 from normal to 0.00 and leaves A4 at 99.20 [98.82, 99.54]. The
identity failure takes both to 0.00: the shared node sits outside the tenant
boundary, so the isolation cut does not reach it. This is the same reading as the
reference study, now with an interval and a per-replication pass fraction.

**H17 — independence, not count.** A2 and A3 have three paths each. Under the
`agg-1` conduit failure A2 is 0.00 and A3 is 99.08 [98.67, 99.44]; under the
independent `a1-p1` link failure A2 is 99.04 and A1 is 0.00. Path count would
predict the opposite ordering for the conduit event. The path independence index is
0.333 for A2 and 1.0 for A3.

**H18 — a boundary without capacity is a partition.** A5 has independent identity
and DNS but still requires the AI endpoint: 0.00 under `ai`. A6 removes that
dependency and serves 90.00 [90.00, 90.00], exactly the stipulated 0.9 local-policy
efficiency, because its three disjoint paths are not capacity-limited. The
normal-operation cost is 9.81 [9.75, 9.86] points.

**The fallback quality result.** Under the full backhaul cut A6 serves 48.59 with a
97.8 % activation rate; A7 serves 18.07 with a 60.2 % activation rate. The tested
fallback is worth 30.52 points on the same failure. A7's 18.07 is close to
`0.60 x 0.30 / 1.00`: the untested fallback delivers roughly its activation
probability times its capacity fraction.

**H19 — the interaction is positive.** Under the combined AI + link failure,
A1 = 0.00, A3 = 0.00, A9 = 48.48, A6 = 89.98, so the interaction is
`(89.98 - 0.00) - (48.48 - 0.00) = 41.51` points [41.27, 41.75]. Multipath alone
does not survive the AI failure and isolation alone does not survive the link
failure; the combination does.

**H20 — the controller is a dependency.** Under the controller + primary-link
failure A5 is 99.64 and A8 is 0.00: with the controller down, A8 falls back to its
primary path, which is the failed link. In normal operation the two differ by
0.01 [0.00, 0.01] points, so the global controller buys nothing when it is healthy
and costs everything when it fails.

## 5. The 30-day campaign

| Arm | Availability (%) | Policy | Congestion | Dependency | Shared share | Days < 99 % |
|---|---:|---:|---:|---:|---:|---:|
| A1 | 94.26 [94.14, 94.38] | 0.00 | 4.70 | 1.04 | 0.61 | 21.5 |
| A2 | 99.16 [99.11, 99.21] | 0.00 | 0.00 | 0.84 | 0.81 | 4.6 |
| A3 | 99.18 [99.13, 99.23] | 0.00 | 0.00 | 0.82 | 0.85 | 4.4 |
| A4 | 99.29 [99.25, 99.33] | 0.00 | 0.00 | 0.71 | 0.98 | 3.7 |
| A5 | 99.75 [99.72, 99.78] | 0.00 | 0.00 | 0.25 | 0.75 | 1.3 |
| A6 | 90.00 [90.00, 90.00] | 9.84 | 0.00 | 0.16 | 0.00 | 30.0 |
| A7 | 90.00 [90.00, 90.00] | 9.84 | 0.00 | 0.16 | 0.00 | 30.0 |
| A8 | 99.75 [99.72, 99.78] | 0.00 | 0.00 | 0.25 | 0.73 | 1.3 |
| A9 | 85.64 [85.54, 85.74] | 9.84 | 4.23 | 0.29 | 0.00 | 30.0 |

Columns 3-5 are the decomposition of the lost campaign time in percentage points;
`shared share` is the fraction of dependency-driven unavailability attributable to
the shared control plane by ablation; the last column is the mean number of
tenant-days below 99 % out of 30. The campaign contains a mean of 4.26
shared-control incidents per replication.

Three readings matter.

1. **The shared control plane dominates dependency-driven unavailability** for
   every arm that requires it: 0.61 for A1, 0.81 for A2, 0.85 for A3, 0.98 for A4,
   0.75 for A5/A8, and 0.00 for the one-way arms. That is the paper's central
   claim expressed as an availability budget rather than as an event table.
2. **Congestion is the largest single loss for the single-path arms.** A1 loses
   4.70 points of the 5.74 it loses in total; A9 loses 4.23 of 14.36. The
   three-path arms lose none. The deterministic model, which had no capacity
   process, could not show this.
3. **A 99 % daily SLO is unreachable for the one-way arms by construction.** Their
   ceiling is 90 %, so all 30 tenant-days breach; they are better described by a
   90 % SLO. The arms that require the shared control plane breach 1.3-21.5 days
   out of 30.

## 6. Sensitivity and break-even

Grid: 25 values per constant, 500 replications per point, linear interpolation
between adjacent grid points. The full grid and every criterion are in
`docs/paper-tables/common-mode-mc-sensitivity.csv` and
`common-mode-mc-break-even.csv`.

| Constant | Stipulated | Sweep | Primary break-even | Claim that fails there |
|---|---:|---|---:|---|
| one-way local-policy efficiency | 0.90 | 0.50-1.00 | 0.848 | H18: normal-operation cost <= 15 points |
| tested fallback activation probability | 0.98 | 0-1 | 0.368 | tested beats untested under the cut |
| untested fallback activation probability | 0.60 | 0-1 | none in range | survives the whole range |
| tested fallback activation delay | 2 s | 0-25 s | none in range | survives the whole range |
| untested fallback activation delay | 8 s | 0-30 s | none in range | survives the whole range |
| tested fallback capacity | 0.50 Gbps | 0-1 | 0.186 | tested beats untested under the cut |
| untested fallback capacity | 0.30 Gbps | 0-1 | 0.833 | tested beats untested under the cut |

Two differences from the reference study are substantive rather than cosmetic.
The activation-delay break-even disappears: with a 39-minute median incident
window, raising the tested delay to 25 s costs only about one point of the gap,
because the delay is short relative to the outage. And the untested-fallback
capacity now has a break-even (0.833 Gbps): the tested fallback wins by *expected
capacity* (0.98 x 0.50 against 0.60 x 0.30), so an untested fallback that is
sufficiently capable erases the gap without any testing. "Tested" is a proxy for
capacity, not a substitute for it.

H19's interaction keeps its two-sided boundary: it falls below 20 points below
0.688 one-way efficiency and above 0.719 Gbps tested-fallback capacity (a stronger
fallback helps A9, which has no multipath, more than it helps A6). The H18 absolute
level fails below 0.800 efficiency, so the binding clause remains the
normal-operation cost, as in the reference study.

## 7. Global sensitivity and the two-factor check

Saltelli total-order indices (base 256, first order in the table's other column,
full table in `docs/paper-tables/common-mode-mc-sobol.csv`):

| Output | Dominant parameters (total order) |
|---|---|
| A6 under `ai` | one-way efficiency (1.00); all fallback parameters and the shared MTBF (0.00) |
| A6 under `backhaul_cut` | tested activation probability (0.55) and tested capacity (0.54); efficiency 0.00 |
| A7 under `backhaul_cut` | untested capacity (0.67) and untested activation probability (0.61) |
| H19 interaction | efficiency (0.30), tested activation probability (0.36), tested capacity (0.35) |

The total-order indices for the interaction (0.36 + 0.35 + 0.30 against a first-order
sum of 0.57) are larger than the first-order indices, which means the parameters
interact: a one-factor sweep cannot attribute the interaction's variance
additively. The two-factor grid makes the interaction explicit. At the stipulated
(0.90, 0.50) the H19 interaction is 41.62 points and the normal cost 9.72; at
(0.85, 0.75) the interaction is 12.71 and the normal cost 14.72, so both criteria
pass separately at values that jointly make the interaction fragile, and at
(0.90, 1.00) the interaction is -0.64. The grid is in
`docs/paper-tables/common-mode-mc-two-factor.csv`.

## 8. Deviations from the frozen expectations

The frozen expectations are in Section 8 of
[`common-mode-mc-predictions.md`](common-mode-mc-predictions.md). Every
qualitative prediction held: every contrast has the predicted sign and ordering,
every hypothesis passes, and the fallback ordering and interaction levels are in
the predicted ranges. The level predictions were less accurate, and the causes are
informative rather than arbitrary.

| Prediction | Observed | Cause |
|---|---|---|
| normal availability, A1-A5, A8: 96.0-97.5 % | A1 92.58; A2-A4 99.2-99.4; A5/A8 99.8 | only the single-path arms are capacity-limited; three disjoint paths triple the energy of the path set, so those arms are never congested |
| normal availability, A6, A7, A9: 86.5-88.5 % | A6/A7 90.00; A9 84.05 | A6's three paths are abundant, so the 0.9 boundary binds exactly; A9's single path is congested, so it pays 0.9 *and* congestion |
| A4 under `tenant_gw`: 96-98 % | 99.20 | a 30-minute window rarely coincides with a background shared-control failure |
| A2, A3 under `link`/`srlg`: 96-98 % | 99.04-99.08 | same cause |
| A5 - A8 under `controller_link`: 95-98 points | 99.64 | A8 is 0 for the whole window, so the gap is A5's level |
| campaign: 96-97 % and 86-88 % | 94.26; 99.2; 90.00; 85.64 | the same capacity structure |
| shared share for A5: 15-25 % | 0.75 | A5 covers path failures with multipath, so its residual dependency loss is mostly the AI endpoint |

No threshold, hypothesis or dataset was changed after the freeze. The prediction
that the simulation would "sit slightly below the deterministic ceilings" was
right for the levels that congestion touches and wrong for the deterministic
mechanism contrasts, which the simulation reproduces exactly.

**A pre-run design correction.** During engine validation, before the reported
run, the modulation process was applied to every link of a path. Because a path's
capacity is the minimum over its links, independent modulation on three links
biases the path capacity about 4 % below the per-link mean; that is an artefact of
the minimum, not a property of the link. Adaptive modulation is a property of the
radio edge link, so the reported model applies it to the `e_i -> a_j` links and
models the fibre links as stable. The correction changes no threshold and no
verdict; it was made before any reported number was produced.

## 9. Limits

- **Stipulated rates.** The MTBF and duration parameters are priors consistent
  with the order of magnitude of the cited corpora, not fits to an operator. The
  break-even and Sobol analyses describe the sensitivity to them; they do not
  remove it.
- **Deterministic contrasts.** Eight of the twelve criteria are exact membership
  tests in the structural model, so their intervals have zero width. The
  simulation adds timing, duration, demand, capacity and fallback variability to
  the levels, the recovery behaviour, the campaign and the sensitivity; it cannot
  add variability to a contrast the model defines exactly.
- **Flow-level.** No packet-level queueing, congestion control or TCP behaviour.
  The congestion term is a capacity shortfall, not a queue.
- **One scenario.** The topology, SRLG grouping and demand level are fixed; the
  external-validity argument rests on the refutation rules, not on a sample of
  operators.
- **No security evaluation.** The one-way boundary is an availability cut.

## 10. Artifacts

| Artifact | Path |
|---|---|
| Frozen MC protocol | [`common-mode-mc-predictions.md`](common-mode-mc-predictions.md) |
| Engine | [`simulation/common_mode_mc.py`](../simulation/common_mode_mc.py) |
| Benchmark | [`tools/benchmark_common_mode_mc.py`](../tools/benchmark_common_mode_mc.py) |
| Statistics | [`tools/mc_stats.py`](../tools/mc_stats.py) |
| Figures | [`tools/make_common_mode_mc_figures.py`](../tools/make_common_mode_mc_figures.py) |
| Tests | [`tests/test_common_mode_mc.py`](../tests/test_common_mode_mc.py) |
| Summary, verdicts, campaign | [`common-mode-mc-summary.csv`](paper-tables/common-mode-mc-summary.csv), [`common-mode-mc-verdicts.csv`](paper-tables/common-mode-mc-verdicts.csv), [`common-mode-mc-campaign.csv`](paper-tables/common-mode-mc-campaign.csv) |
| Per-replication differences | [`common-mode-mc-differences.csv`](paper-tables/common-mode-mc-differences.csv) |
| Deterministic comparison | [`common-mode-mc-comparison.csv`](paper-tables/common-mode-mc-comparison.csv) |
| Break-even, grid, Sobol, two-factor | [`common-mode-mc-break-even.csv`](paper-tables/common-mode-mc-break-even.csv), [`common-mode-mc-sensitivity.csv`](paper-tables/common-mode-mc-sensitivity.csv), [`common-mode-mc-sobol.csv`](paper-tables/common-mode-mc-sobol.csv), [`common-mode-mc-two-factor.csv`](paper-tables/common-mode-mc-two-factor.csv) |
