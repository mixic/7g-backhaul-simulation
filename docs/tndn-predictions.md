# T-NDN predictions (M10) — frozen before the run

**Status:** frozen. The constants below live in code
(`simulation/topology.py`, `simulation/ndn_scenario.py`, the four strategy
modules) and were fixed before the 30 paired seeds were run. The results are
reported in [`tndn.md`](tndn.md).

## Hypothesis H13

> A forwarding plan built on name-space topological invariants (persistent
> ``H0`` name clusters and ``H1`` loops) reduces FIB size *and* reconvergence
> time by at least 20 % against NLSR, FSR-NDN and a Fisheye-Overlay baseline,
> without reducing the Content Delivery Rate below 95 % of the NLSR baseline.

The hypothesis is refuted by any of:

1. no 20 % FIB reduction against every baseline;
2. no 20 % reconvergence reduction against every baseline;
3. CDR below 95 % of NLSR;
4. a persistent-homology cost larger than the convergence time it saves.

Criterion 4 is the anti-cheat clause: if the invariants are so expensive to
compute that they cost more than the repair time they buy, H13 fails regardless
of the other numbers.

## Scenario (frozen)

| Quantity | Value |
|---|---|
| Nodes | 100 on the unit square, random geometric graph, radius 0.175 |
| Link latency | `10 + 40 * distance` ms, one-way |
| Name space | `/service/region/type/object`, 5 x 4 x 5 x 100 = 10 000 names |
| Producers | 20, one per (service, region) block, 500 names each, evenly spread |
| Requests | Poisson, 200/s, 60 s, consumer and name uniform |
| Interest lifetime | 1.0 s |
| Failure | the highest-usage non-bridge link with both endpoint degrees >= 3, severed at t = 30 s |
| Seeds | 30, base 2026, paired by seed: one network, one request stream, one failure for all strategies |

Each name is announced individually; the scenario does not aggregate name
prefixes at announcement time. That stipulation is what makes the NLSR FIB one
entry per name, and it is stated as a limitation in the results, not hidden.

## Frozen topological constants

| Constant | Value | Reason |
|---|---:|---|
| Prefix weights | 0.35 / 0.25 / 0.15 / 0.05 | service, region, type, object |
| Prefix vs. topic weight | 0.4 / 0.6 | stipulated semantic circle |
| `EPS_CLUSTER` | 0.15 | above within-block diameter (<= 0.10), below closest inter-block distance (>= 0.219) |
| `EPS_HOLE` | 0.43 | closes the circle (widest adjacent edge 0.419), below the shortest-lived micro-loop (0.447) |
| `EPS_DEATH` | 0.60 | triangle-reduction horizon, not a routing threshold |
| Landmarks | 64, farthest-point sampling | bounded cost; all other names go to the nearest landmark |

## Strategy mechanisms and stipulated constants (all frozen)

| Strategy | Mechanism | Stipulated constants |
|---|---|---|
| NLSR | global link-state flood, per-name FIB, full SPF | 1 s detection, 20 ms/hop flood, 10 ms SPF |
| FSR-NDN | scope refresh by hop distance; full names near, type/block aggregation far | 1 / 4 / 8 / 15 s refresh, 30 % loop chance, 0.5 s loop penalty |
| Fisheye-Overlay | RTT-only peer view (8 nearest + 4 diverse), 128 name buckets, one extra overlay leg | 2 s probe interval, up to 1 s re-map |
| T-NDN | 20 H0 clusters, one FIB entry each, one loop-free backup per H1-cluster | 200 ms heartbeat, 200 ms DV round |

All four see the same network, name space, producers, traffic and failure. Only
the control-plane mechanism differs.

## Expected outcome (stated in advance)

- FIB: T-NDN < Fisheye-Overlay < FSR-NDN < NLSR.
- Reconvergence: T-NDN fastest (local switch), Fisheye next (probe round),
  NLSR next (global flood), FSR slowest (far-scope refresh).
- CDR: T-NDN within 5 % of NLSR; FSR loses far-scope requests during the
  outage.
- TDA: tens of milliseconds per FIB build, far below the hundreds of
  milliseconds of convergence it is claimed to save.

The expected result is **supported only if all four criteria pass on the
30-seed means**; per-seed pass fractions are reported as well, because a
criterion that holds only on the mean is weaker than one that holds on every
paired seed.
