# Common-mode resilience, Monte Carlo protocol (MC-H16-MC-H20) — frozen before the run

**Status: FROZEN.** This file is committed before `simulation/common_mode_mc.py`
exists. The distributional parameters, the replication counts, the decision rule
and the expected outcomes are fixed here. Results go in
[`common-mode-mc-results.md`](common-mode-mc-results.md); this file is not edited
afterwards. The freeze commit is recorded there.

The predecessor document [`common-mode-predictions.md`](common-mode-predictions.md)
(commit `1c781f3`) remains the frozen protocol of the deterministic flow-level
reference model. It is not edited, and it is not superseded as a record: it is the
zero-variance limit of the model described here. This document is a second,
independent pre-registration for a stochastic simulation of the same scenario, the
same nine arms, the same ten incident classes and the same thresholds.

## 0. What this study changes, and why

The reference model computes availability as a capacity/dependency conjunction at
one-second ticks with a single random draw per seed (event timing, demand jitter,
fallback draw). Everything else is exact: the 100 % and 0 % entries in its results
table are membership tests in a dependency list, and the 90 % is the stipulated
0.9 local-policy efficiency. Section 7 of Paper D states this as a threat to
validity: the model checks are exact properties of the model, not estimates.

This protocol replaces the exact evaluation with a **continuous-time Monte Carlo
simulation**:

1. Every dependency (shared identity, DNS, AI endpoint, tenant gateway, provider
   control planes, provider nodes, edge links, aggregation conduits, provider-cloud
   links) fails and recovers as an independent stochastic process over the
   simulated horizon: Poisson arrivals, lognormal durations.
2. The incident of interest is injected at a sampled time with a sampled duration,
   and is superimposed on the background failure process rather than replacing it.
3. Offered demand is a diurnal process with Ornstein-Uhlenbeck noise; effective
   link capacity is a protocol-efficiency factor times a modulation factor that is
   itself a stochastic process, so a healthy path can still be congested.
4. A fallback activates with a probability, a sampled delay and a sampled capacity,
   per tenant and per incident, not at a fixed tick.
5. Every reported quantity is a sample mean over replications with a confidence
   interval; every hypothesis is decided by a pre-registered interval rule.

The stochastic process is not calibrated to a particular operator. The rate and
duration parameters are stipulated priors, chosen to be consistent with the
order of magnitude reported by the public failure corpora cited in the paper
(median time between failures of days to weeks, median durations of tens of
minutes, heavy-tailed durations [23,24,28]); they are swept in Section 6. This is
a simulation, not a measurement, and the paper says so.

## 1. Principles (unchanged)

The six principles of the reference protocol still hold and are still what the
simulation encodes: availability is a conjunction; multipath counts only across
independent failure domains; isolation trades capability for containment; a
fallback is a tested state; the controller is a dependency; a common-mode event is
sampled once per event, not per tenant.

## 2. Hypotheses, thresholds and the decision rule

The hypotheses and thresholds are **identical to the frozen reference protocol**
Section 2. They are not retuned, so a change in verdict is attributable to the
engine, not to the analyser.

| ID | Criterion | Threshold |
|---|---|---|
| H16 | `A4 − A3` under `tenant_gw` | `≥ 50` points |
| H16 | `|A4 − A3|` under `idp` | `≤ 5` points |
| H17 | `A3 − A2` under `srlg` | `≥ 20` points |
| H17 | `A2 − A1` under `link` | `≥ 50` points |
| H18 | `A6 − A5` under `ai` | `≥ 50` points |
| H18 | `A6` level under `ai` | `≥ 80` points |
| H18 | `A5 − A6` under `none` | `≤ 15` points |
| H19 | `(A6 − A3) − (A9 − A1)` under `ai_link` | `≥ 20` points |
| H19 | `A6` level under `ai_link` | `≥ 80` points |
| H19 | `A3` level under `ai_link` | `≤ 20` points |
| H20 | `A5 − A8` under `controller_link` | `≥ 50` points |
| H20 | `|A5 − A8|` under `none` | `≤ 5` points |

All quantities are percentage points of tenant demand, time-weighted over tenants
and over the incident window.

### 2.1 Decision rule (new; fixed before the run)

For each criterion, form the paired per-replication difference across the two
arms named in the criterion (both arms see the same replication, so the
comparison is paired by construction). Let `[lo, hi]` be the 95 % percentile
bootstrap interval of the mean difference (10 000 resamples) and let `est` be the
mean difference.

- **PASS** if the whole interval is inside the passing region:
  `est` and `[lo, hi]` satisfy the criterion (for `≥ t`: `lo ≥ t`;
  for `≤ t`: `hi ≤ t`; for `|·| ≤ t`: `lo ≥ −t` and `hi ≤ t`).
- **FAIL** if the whole interval is outside the passing region
  (for `≥ t`: `hi < t`; for `≤ t`: `lo > t`; for `|·| ≤ t`: `lo > t` or `hi < −t`).
- **INCONCLUSIVE** otherwise.

A hypothesis passes only if every one of its criteria passes; it fails if any
criterion fails. INCONCLUSIVE criteria are reported as such and are not counted
as support.

The rule is deliberately conservative: an effect that is large but imprecise is
not support. The per-replication pass fraction is reported as a descriptive
statistic, not as the decision.

Because twelve criteria are tested, the analysis also reports each criterion at a
Bonferroni-adjusted level `α = 0.05/12 = 0.00417` (equivalent to a 99.58 %
interval). The frozen verdict uses the 95 % interval; the Bonferroni column is
reported so that a reader can see whether any verdict depends on the nominal
level. A verdict that changes under Bonferroni is reported as "nominal-only".

## 3. Scenario (topology unchanged)

The topology, tenants, path sets, SRLG membership, arm definitions, cost index
and metric definitions are those of the frozen reference protocol Sections 3-4 and
7. The simulator imports `build_backhaul_scenario`, `select_paths`,
`path_independence`, `ARMS` and `EVENT_KINDS` from `simulation/common_mode.py`, so
the structural scenario has one source of truth and cannot drift between the two
engines.

## 4. Stochastic model

### 4.1 Clock and horizons

The simulation is continuous-time; the service state is piecewise constant between
breakpoints. There is no fixed tick.

| Experiment | Horizon | Purpose |
|---|---|---|
| incident experiment | 24 h | availability during the injected incident class |
| campaign experiment | 30 d | steady-state availability, congestion loss, attribution |

### 4.2 Background failure processes

Each dependency is an alternating renewal process: exponential time to failure,
lognormal duration. Parameters are fixed here and swept in Section 6.

| Class | Members | MTBF | Median duration | `σ_ln` |
|---|---|---:|---:|---:|
| shared control | `idp`, `dns`, `ai` | 21 d | 45 min | 1.00 |
| tenant gateway | `mt-gw` | 30 d | 30 min | 0.80 |
| provider control plane | `p1-cp`, `p2-cp`, `p3-cp` | 14 d | 20 min | 1.00 |
| provider node | `p1`, `p2`, `p3` | 120 d | 10 min | 0.80 |
| edge link | `e_i → a_j` (18) | 60 d | 3 min | 0.60 |
| aggregation conduit | SRLG `agg-1..3` (3) | 45 d | 8 min | 0.80 |
| provider-cloud link | 3 links | 90 d | 6 min | 0.70 |

A conduit failure takes down every link in its SRLG (all `a_j → p_*` links of
aggregation site `j`); a provider-node failure takes down every link incident to
that provider; a provider control-plane failure removes every path through that
provider, as in the reference model.

Intermediate values: MTBF is the mean of the exponential inter-arrival
distribution, `p95` duration is `median · exp(1.645·σ_ln)`. Durations are
truncated at 6 h and at the horizon.

### 4.3 Incident injection (incident experiment only)

For incident class `e` the failure set is the one in the frozen reference protocol
Section 6 (`link`, `srlg`, `backhaul_cut`, `provider_cp`, `idp`, `ai`,
`tenant_gw`, `controller_link`, `ai_link`; `none` injects nothing). The injected
incident

- starts at `U(6 h, 18 h)` in the 24 h horizon;
- lasts `Lognormal(median m_e, σ_ln = 0.80)`, truncated at 6 h, where `m_e` is
  45 min for `idp`, `ai` and `provider_cp`, 40 min for `backhaul_cut`, 30 min for
  `ai_link` and `tenant_gw`, and 25 min for `link`, `srlg` and `controller_link`;
- is superimposed on the background process: if a background failure hits the same
  target, the union is down.

The incident window is `[start, start + duration)`. For `none` the window is the
whole 24 h horizon and no failure is injected.

### 4.4 Demand

Per tenant, offered demand in Gbps is

```
d_i(t) = 1.00 · (1 + 0.10·sin(2π(t − 2)/24 h)) · exp(x_i(t))
```

with `x_i` an Ornstein-Uhlenbeck process, stationary `sd = 0.05`, correlation time
30 min, independent per tenant. The diurnal factor peaks at 14:00 and troughs at
02:00. Demand is sampled once per replication and shared by all arms.

### 4.5 Capacity

For link `l` at time `t`:

```
c_l(t) = c_l^nominal · η · m_l(t),   η = 0.95
```

`η` is the protocol/encapsulation efficiency and `m_l` is an adaptive-modulation
factor: Ornstein-Uhlenbeck, stationary `sd = 0.03`, mean 0.98, correlation time
2 min, clipped to `[0.60, 1.00]`. A path's effective capacity is the minimum over
its links, so a temporarily degraded link depresses the path. Sampled once per
replication and shared by all arms.

### 4.6 Service

At any time, for each arm and tenant:

- the control plane is available per the arm's mechanisms (shared control required
  unless independent; AI required unless one-way; tenant gateway required unless
  tenant isolation), as in the reference model;
- a path is available if none of its links is down, its provider node is up and
  its provider control plane is up; under a failed global controller the arm may
  use only its primary path;
- `path_served = min(d, Σ c_p)` over available paths if the control plane is
  available, else 0; if the arm is one-way, `path_served ·= 0.90`;
- if the control plane is unavailable, or no path is available, the tenant **needs**
  the fallback: with the arm's activation probability it activates after its
  sampled delay, and serves `min(max(0, d − path_served), c_fb)`;
- `served = min(d, path_served + fallback_served)`; the tenant's instantaneous
  availability is `served / d`.

The one-way efficiency (0.90) is unchanged and remains a stipulated constant; it
is swept. The fallback release delay is not modelled (the fallback serves while it
is needed and stops when the need clears).

### 4.7 Fallback profiles

| Arm | Profile | Activation `p` | Delay (median, `σ_ln`) | Capacity Gbps (median, `σ_ln`) |
|---|---|---:|---|---|
| A6, A8, A9 | tested | 0.98 | 2 s, 0.50 | 0.50, 0.15 |
| A7 | untested | 0.60 | 8 s, 0.60 | 0.30, 0.20 |

Delay is truncated to `[0.5 s, 300 s]`, capacity to `[0.05, 1.0]` Gbps. The
activation uniform is drawn once per tenant and per incident and is shared by
every arm that has a fallback, so the fallback comparison is paired across arms.
The delay and capacity draws are per arm profile, per tenant and per incident.

### 4.8 Common random numbers

Every random input (background timelines, incident start and duration, demand
processes, modulation processes, fallback draws) is generated once per replication
from a stream keyed by `(base_seed = 2026, replication index)` and is shared by all
nine arms. Arms differ only in mechanism. This is what makes the per-replication
paired differences meaningful, and it removes the seed confound.

## 5. Experiments and replication counts

| Experiment | Design | Replications | Arm-runs |
|---|---|---|---|
| E1 incident | 9 arms × 10 incident classes | 2 000 | 180 000 |
| E2 campaign | 9 arms × 30 d | 500 | 4 500 |
| E3 one-factor sensitivity | 7 constants × 25 values × the E1 design at 500 replications | 500/value | 787 500 arm-runs |
| E4 global sensitivity | Saltelli/Sobol, `N_base = 256`, 7 parameters | — | 9 216 model evaluations |

E1 and E2 replications are paired across arms. E3 and E4 use the same seed
discipline. The replication index `r = 0…N−1`; the base seed is 2026.

## 6. Sensitivity design

**One-factor break-even (E3).** Sweep each of the following one at a time over 25
linearly spaced values, all else frozen, using the E1 design at 500 replications:
one-way efficiency `0.50–1.00`; tested activation probability `0–1`; untested
activation probability `0–1`; tested delay `0–25 s`; untested delay `0–30 s`;
tested fallback capacity `0–1` Gbps; untested fallback capacity `0–1` Gbps. The
break-even is the value at which the named criterion stops passing, located by
linear interpolation between adjacent grid points on the criterion value, as in
the reference study.

**Global sensitivity (E4).** Saltelli/Sobol total-order indices for the seven
constants above plus the shared-control MTBF, on three outputs of the E1 engine
(single replication, all nine arms): `A6` under `ai`, `A6` and `A7` under
`backhaul_cut`, and the H19 interaction under `ai_link`. `N_base = 256`, so
`N_base·(k+2)` evaluations for `k = 8` parameters.

**Two-factor check.** A 5×5 grid of one-way efficiency × tested fallback capacity,
reporting H19's interaction and H18's normal-operation cost, because the reference
study's one-factor design could not see interactions.

## 7. Metrics

For each arm, replication and incident class (E1):

| Metric | Definition |
|---|---|
| `availability_event` | time-weighted mean `served/d` over tenants and the incident window |
| `availability_overall` | time-weighted mean over tenants and the 24 h horizon |
| `recovery_s` | time from incident start to the first time served ≥ 0.90 continuously for 3 s; the incident duration if never |
| `blast_radius` | fraction of tenants whose event availability is below 0.50 |
| `fallback_rate` | fraction of tenants whose fallback activated during the incident |
| `path_independence` | as in the reference model (a structural property) |
| `cost_index` | as in the reference model (a stipulated accounting device) |

For each arm and replication (E2):

| Metric | Definition |
|---|---|
| `availability_ss` | time-weighted mean `served/d` over tenants and 30 d |
| `congestion_loss_pct` | time-weighted `max(0, 1 − Σc/d)` share while no dependency is down |
| `dependency_loss_pct` | time-weighted `1 − served/d` share while at least one dependency is down |
| `shared_attrib_pct` | share of `dependency_loss` attributable to shared dependencies, by ablation (re-running the same replication with shared dependencies always up and taking the difference) |
| `slo_breach_days` | tenant-days with availability below 99 % |
| `shared_incidents` | number of shared-control incidents during the campaign |

## 8. Expected outcomes (frozen predictions)

These are predictions, not results. Deviations are reported with their cause, as
the reference study requires. Predicted values are the model's expected means;
the intervals are the predicted 95 % Monte Carlo intervals, not thresholds.

| Quantity | Prediction | Reasoning |
|---|---|---|
| normal availability, A1-A5, A8 | 96.0-97.5 % | congestion at the diurnal peak (demand 1.10 Gbps vs usable 0.98 Gbps) plus rare background failures |
| normal availability, A6, A7, A9 | 86.5-88.5 % | the 0.90 one-way efficiency applied to a capacity-limited path |
| `A3` under `tenant_gw` | < 1 % | shared gateway on the availability path |
| `A4` under `tenant_gw` | 96-98 % | isolation removes the gateway |
| `A3`, `A4` under `idp` | < 1 % | shared identity is still required by both |
| `A2` under `srlg` | < 1 % | three paths share the conduit |
| `A3` under `srlg` | 96-98 % | paths are SRLG-disjoint |
| `A1` under `link` | < 1 % | single path |
| `A2` under `link` | 96-98 % | two surviving paths |
| `A5` under `ai` | < 1 % | AI endpoint still required |
| `A6` under `ai` | 86-88 % | one-way boundary, local policy |
| `A9` under `link` | 48-51 % | fallback capacity 0.50 Gbps of 1.0 Gbps demand |
| `A6` under `backhaul_cut` | 48-51 % | tested fallback, 2 s delay averaged over ~40 min |
| `A7` under `backhaul_cut` | 16-20 % | 0.60 activation × 0.30 Gbps |
| A6 − A7 under `backhaul_cut` | 30-34 points | tested minus untested |
| H19 interaction | 34-42 points | `(86.5 − 0.5) − (49 − 0.5)` |
| `A5 − A8` under `controller_link` | 95-98 points | global controller loses the surviving paths |
| `A8` under `controller_link` | < 1 % | falls back to the failed primary path |
| steady-state availability, 30 d campaign | 96-97 % current-cloud arms; 86-88 % one-way arms | congestion dominates normal operation |
| shared share of dependency-caused unavailability | 55-80 % for A1-A4, ~15-25 % for A5, ~0 % for A6-A9 | the dependency ladder |

The qualitative prediction is that all five hypotheses pass under the interval
rule, with the same sign and ordering as the deterministic reference model, and
that the simulated levels sit slightly below the deterministic ceilings because
background failures and congestion are now present.

## 9. Refutation and reporting

A criterion that fails under the interval rule is reported as a refutation of the
model check, not suppressed. A criterion that is INCONCLUSIVE is reported as
inconclusive, with its interval, and the hypothesis is not claimed as supported.
The paper reports, for every criterion: the point estimate, the 95 % interval, the
Bonferroni interval, the permutation p-value, the per-replication pass fraction
and the verdict.

The deterministic reference values are reported side by side with the simulated
values. If a simulated interval does not contain the reference value, that is a
finding about the difference between the two engines and is reported as such.

## 10. What this does not test

Unchanged from the reference protocol Section 11, plus one addition:

- packet-level behaviour, congestion control, queueing, TCP dynamics;
- cryptographic security or the data diode as a security control;
- real providers, identity services or AI endpoints;
- the cost of operating a data diode;
- **the calibrated rates of the failure processes.** The MTBF and duration
  parameters are stipulated priors consistent with the order of magnitude of the
  cited corpora; they are not fitted to a specific operator, and the break-even
  and Sobol analyses describe the sensitivity to them rather than removing it.

The simulation is an instrument for the structural question, not an estimate of
any operator's availability.
