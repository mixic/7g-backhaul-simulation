# Isolation and multipath under common-mode failure: results (H16-H20)

**Status:** complete. The hypotheses, scenario, arms and thresholds were frozen
in [`common-mode-predictions.md`](common-mode-predictions.md) at commit
`1c781f3`, before `simulation/common_mode.py` existed. This document interprets
the 30-seed run; it does not change the frozen text.

**One-line result:** H16-H20 are all supported under the frozen scenario.
Tenant isolation contains a tenant-shared fault (100 % vs 0 %) but not a global
identity failure (0 % vs 0 %); SRLG-disjoint multipath survives a conduit failure
(100 % vs 0 %) while shared-fate multipath does not; a one-way boundary with a
tested fallback holds 90 % under an AI control-plane failure against 0 % without
it; the isolation-multipath interaction is **+44.38 points**; and a global
cooperative controller loses **100 points** when it fails with its primary path.

The support is conditional on a stipulated flow-level scenario and on the
fallback parameters. The scenario is a testbed, not a measurement of a production
network; §6 states the limits.

## 1. Protocol

| Quantity | Value |
|---|---|
| Seeds | 30, base 2026, paired |
| Arms | 9 (A1-A9) |
| Events | 10 (`none`, `link`, `srlg`, `backhaul_cut`, `provider_cp`, `idp`, `ai`, `tenant_gw`, `controller_link`, `ai_link`) |
| Runs | 2 700 (30 × 9 × 10) |
| Scenario | cooperative AI backhaul: 6 tenants, 3 aggregation sites, 3 providers, 2 clouds, shared identity/DNS/AI, shared tenant gateway, global controller, local fallbacks |
| Freeze commit | `1c781f3` |
| Command | `py -3 tools/benchmark_common_mode.py --seeds 30` |

Each seed draws one event (start and duration), one demand vector and one
fallback vector; every arm sees the same draws. The event window is 20-30 s
starting at 15-25 s in a 60 s run. Availability is the mean served/offered
fraction over tenants and the event ticks.

## 2. Availability during the event (%, 30-seed mean)

| Event | A1 | A2 | A3 | A4 | A5 | A6 | A7 | A8 | A9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `none` | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 90.0 | 90.0 | 100.0 | 90.0 |
| `link` | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 90.0 | 90.0 | 100.0 | 45.6 |
| `srlg` | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 90.0 | 90.0 | 100.0 | 45.6 |
| `backhaul_cut` | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 45.6 | 11.1 | 0.0 | 45.6 |
| `provider_cp` | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 90.0 | 90.0 | 100.0 | 45.6 |
| `idp` | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 90.0 | 90.0 | 100.0 | 90.0 |
| `ai` | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 90.0 | 90.0 | 0.0 | 90.0 |
| `tenant_gw` | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 90.0 | 90.0 | 100.0 | 90.0 |
| `controller_link` | 0.0 | 100.0 | 100.0 | 100.0 | 100.0 | 90.0 | 90.0 | 0.0 | 45.6 |
| `ai_link` | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 90.0 | 90.0 | 0.0 | 45.6 |

Arms: A1 concentration; A2 multipath shared fate; A3 SRLG-disjoint multipath;
A4 A3 + tenant isolation; A5 A4 + independent control; A6 A5 + one-way boundary +
tested fallback; A7 A6 with untested fallback; A8 A5 + global controller; A9 A1 +
isolation + tested fallback.

The 95 % CI is 0.0 for every deterministic mechanism. The stochastic component is
fallback activation: A9's `link` mean is 45.62 ± 0.57, A6's `backhaul_cut` mean
is 45.62 ± 0.57 and A7's `backhaul_cut` mean is 11.11 ± 1.61. The event window
averages are otherwise exact because the flow-level model has no packet-level
randomness.

## 3. Hypothesis verdicts

| Hypothesis | Criterion | Value | Threshold | Pass fraction | Verdict |
|---|---|---:|---:|---:|---|
| H16 | A4 − A3 under `tenant_gw` | 100.0 | ≥ 50 | 1.000 | PASS |
| H16 | \|A4 − A3\| under `idp` | 0.0 | ≤ 5 | 1.000 | PASS |
| H17 | A3 − A2 under `srlg` | 100.0 | ≥ 20 | 1.000 | PASS |
| H17 | A2 − A1 under `link` | 100.0 | ≥ 50 | 1.000 | PASS |
| H18 | A6 − A5 under `ai` | 90.0 | ≥ 50 | 1.000 | PASS |
| H18 | A6 level under `ai` | 90.0 | ≥ 80 | 1.000 | PASS |
| H18 | A5 − A6 under `none` | 10.0 | ≤ 15 | 1.000 | PASS |
| H19 | Interaction `(A6−A3) − (A9−A1)` under `ai_link` | 44.38 | ≥ 20 | 1.000 | PASS |
| H19 | A6 level under `ai_link` | 90.0 | ≥ 80 | 1.000 | PASS |
| H19 | A3 level under `ai_link` | 0.0 | ≤ 20 | 1.000 | PASS |
| H20 | A5 − A8 under `controller_link` | 100.0 | ≥ 50 | 1.000 | PASS |
| H20 | \|A5 − A8\| under `none` | 0.0 | ≤ 5 | 1.000 | PASS |

All five hypotheses are supported on the 30-seed means and on every seed for
every criterion. The verdict rules and per-seed rows are in
`output/common-mode/common_mode_verdicts.csv` and
`output/common-mode/common_mode_per_seed.csv`.

## 4. What the numbers show

**H16 — isolation is a boundary, not a control-plane cut.** Tenant isolation
turns the `tenant_gw` failure from a total outage (A3: 0 %) into normal service
(A4: 100 %). It does nothing for the `idp` failure: both A3 and A4 are 0 %. The
cut is in the right graph for tenant-to-tenant faults and in the wrong graph for
the shared control plane.

**H17 — independence, not count.** A2 has three paths and A3 has three paths;
under the `agg-1` conduit failure A2 is 0 % because all three paths share the
conduit, while A3 is 100 % because its paths use three aggregation sites. Under
the independent `a1-p1` link failure A2 is 100 % and A1 is 0 %. Path count alone
would have predicted the opposite ordering.

**H18 — a boundary without capacity is a partition.** Under the AI control-plane
failure A5 (independent control but AI still required) is 0 %, while A6 (one-way
boundary, local policy, tested fallback) is 90 %. The 10-point normal-operation
gap is the price of local policy: A6 serves 90 % even with no failure.

**H19 — the interaction is positive.** Under the combined AI + link failure:
A1 = 0, A3 = 0, A9 = 45.6, A6 = 90.0. The interaction term is
`(90 − 0) − (45.6 − 0) = 44.38` points. Isolation alone (A9) covers the control
failure but not the path failure; multipath alone (A3) covers neither because
the shared AI dependency is still on the availability path; only the combination
reaches 90.

**H20 — the controller is a dependency.** Under the controller + primary-link
failure A5 (local reallocation) is 100 % and A8 (global controller) is 0 %: once
the controller is down, A8 falls back to its primary path, which is the failed
link. With no failure, both are 100 %, so the global controller buys nothing in
normal operation and costs everything at the wrong moment.

**Tested fallback.** Under the full backhaul cut A6 serves 45.6 % with a 99.4 %
activation rate; A7 serves 11.1 % with a 56.1 % activation rate. The tested
fallback is worth 34.5 points on the same failure. The absolute level is below
the 50 % capacity because the 2 s activation delay is averaged into the event
window (see §5).

## 5. Deviations from the frozen expectations

The following are reported rather than hidden:

1. **`backhaul_cut` level.** The prediction was "A6 about 50, A7 about 18". The
   measured values are 45.6 and 11.1. The cause is the fallback delay: A6's 2 s
   delay removes about 8 % of a ~24 s event, and A7's 8 s delay removes about a
   third, on top of its 0.60 activation probability. The ordering (tested >
   untested) and H18/H19 are unaffected.
2. **A9 under `link`.** The prediction was "about 50"; the measurement is 45.6,
   for the same 2 s delay reason.
3. **`recovery_s` for A9.** A9's partial service (45.6 %) never reaches the 90 %
   recovery target, so its recovery time is reported as the event duration even
   though the fallback is serving. The availability column carries the partial
   restoration; the recovery column does not. This is a metric limitation, not a
   service failure.

The other expected outcomes in the frozen document match the run: A1/A2/A3/A4/
A5/A8 normal 100 %, A6/A7/A9 normal 90 %, H16-H20 signs and levels.

## 6. Limits

- **Flow-level model.** No packet-level queueing, congestion control, TCP
  behaviour or reordering. Availability is a capacity/dependency calculation.
- **Stipulated scenario.** The topology, link capacities, SRLG membership,
  failure targets, fallback probabilities and the 0.9 local-policy efficiency are
  design choices. They are reported in the predictions document; they are not
  measurements of an operator.
- **Structural, not statistical.** The determinants are exact by construction;
  the seed variation is fallback activation and event timing. The 30 seeds are a
  pairing device, not a sample of a population.
- **No security evaluation.** The one-way boundary is an availability cut, not a
  cryptographic control.
- **No cost model.** `cost_index` is a stipulated accounting device, not a price.
- **One scenario.** A different topology, SRLG grouping or control-plane layout
  could change the levels; the refutation rules in the frozen document are what
  would make the result informative there.

## 7. Reproduce

```bash
py -3 tools/benchmark_common_mode.py --seeds 30
py -3 -m unittest tests.test_common_mode -v
```

The benchmark writes three CSVs under `output/common-mode/` (ignored by Git):
`common_mode_per_seed.csv`, `common_mode_summary.csv` and
`common_mode_verdicts.csv`. The module is `simulation/common_mode.py`; the
benchmark is `tools/benchmark_common_mode.py`; the tests are
`tests/test_common_mode.py`.

## 8. Artifacts

| Artifact | Path |
|---|---|
| Frozen protocol | [`docs/common-mode-predictions.md`](common-mode-predictions.md) |
| Paper | [`docs/paper-common-mode.md`](paper-common-mode.md) and [PDF](paper-common-mode.pdf) |
| Run/extend guide | [`docs/common-mode-testbed.md`](common-mode-testbed.md) |
| Simulator | [`simulation/common_mode.py`](../simulation/common_mode.py) |
| Benchmark | [`tools/benchmark_common_mode.py`](../tools/benchmark_common_mode.py) |
| Tests | [`tests/test_common_mode.py`](../tests/test_common_mode.py) |
| Argument | [`docs/isolation-concentration-multipath.md`](isolation-concentration-multipath.md) |
| Research note | [`docs/common-mode-resilience.md`](common-mode-resilience.md) |
