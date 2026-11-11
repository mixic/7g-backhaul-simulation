# T-NDN: topological NDN forwarding against NLSR, FSR-NDN and a fisheye overlay

**Status:** M10, complete. The hypothesis and all constants were frozen in
[`tndn-predictions.md`](tndn-predictions.md) before the 30 paired seeds ran.
This document reports what the run measured, including the two sensitivities
that decide how far the result generalises.

**One-line result:** H13 is supported under the frozen scenario — T-NDN needs
38.2 FIB entries instead of 140 (overlay), 779.8 (FSR) and 9 900 (NLSR), and it
reconverges in 0.31 s instead of 1.24 s, 2.97 s and 15.48 s, at an unchanged
CDR — but the FIB clause depends on NLSR being denied prefix aggregation and the
convergence margin depends on NLSR's one-second failure detection. Both
sensitivities are reported in §6.

## 1. What was tested

| Strategy | Implementation | Forwarding state |
|---|---|---|
| NLSR | [`nlsr_baseline.py`](../simulation/nlsr_baseline.py) | global link-state, one entry per announced name |
| FSR-NDN | [`fsr_baseline.py`](../simulation/fsr_baseline.py) | hop-scoped refresh, full names near, block prefixes far |
| Fisheye-Overlay | [`fisheye_overlay_baseline.py`](../simulation/fisheye_overlay_baseline.py) | RTT-only peer view, 128 name buckets, one extra overlay leg |
| T-NDN | [`tndn_router.py`](../simulation/tndn_router.py) | 20 persistent ``H0`` clusters plus loop-free alternates for the ``H1`` loop |

Scenario: 100-node random geometric graph, 10 000 names in
``/service/region/type/object``, 20 producer blocks of 500 names, Poisson
traffic at 200 requests/s for 60 s, Interest lifetime 1 s, and the
highest-usage non-bridge link severed at t = 30 s. All four strategies are
evaluated on the same network, name space, request stream and failure (paired
by seed, 30 seeds). The failed path carried 14.4 % of the consumer→producer
pairs on average.

This is a routing and control-plane model, not a packet simulator. Delivery is
scored against route availability and the Interest lifetime; latency is
shortest-path latency plus 2 ms/hop of queueing. There is no caching, no PIT
behaviour and no per-packet forwarding strategy.

## 2. The T-NDN mechanism

**Name metric.** ``d(a,b) = 0.4·prefix(a,b) + 0.6·topic(a,b)``: a weighted
mismatch of the four name components plus a chord distance on a stipulated
semantic circle with 20 positions. The circle is what makes the name complex
non-ultrametric. With a pure prefix metric every Vietoris–Rips complex is a
disjoint union of cliques and ``H1`` is identically zero; the semantic part is
therefore not decoration, it is the only source of loops. It is stipulated, not
measured.

**Persistent homology.** 64 landmarks are chosen by farthest-point sampling
(no producer labels, no topology). The Vietoris–Rips filtration is computed
with a union-find for ``H0`` and a Z2 boundary reduction for ``H1``. Frozen
radii: ``EPS_CLUSTER = 0.15``, ``EPS_HOLE = 0.43``, triangle-reduction horizon
``EPS_DEATH = 0.60``. The result is 20 persistent clusters and exactly one
persistent loop spanning all 20 clusters. Every other name is assigned to the
nearest landmark.

**FIB.** One entry per ``H0`` cluster, not per name. A distance-vector solve
over neighbour advertisements gives the next hop for each cluster's producer
block. For the clusters on the ``H1`` loop, a second next hop is installed if a
loop-free alternate exists (the neighbour's advertised distance to the producer
is strictly smaller than the node's own). No failure and no void is known at
build time: the plan is built on the intact network and the alternate is
already in the table when the link goes down.

**Repair.** When a neighbour stops advertising, the node switches to the
installed alternate after a 200 ms heartbeat; when no alternate exists it needs
one more distance-vector round, 400 ms. The "void" is the missing advertisement,
not a scenario parameter.

**No global topology.** The router reads only its adjacency, the name
advertisements and neighbour cost vectors. The simulator solves the
distance-vector centrally for exactness (as it does for FSR's scoped variant),
which is the one place where the implementation is not distributed; the routing
state itself is local.

## 3. Results (30 paired seeds, mean ± 95 % CI)

| Strategy | FIB entries | Reconvergence p99 (s) | CDR (%) | p95 latency (ms) |
|---|---:|---:|---:|---:|
| NLSR | 9900.0 ± 0.0 | 1.2373 ± 0.0139 | 99.9196 ± 0.0156 | 144.42 ± 7.30 |
| FSR-NDN | 779.8 ± 13.0 | 15.4833 ± 0.0327 | 96.704 ± 0.4263 | 140.84 ± 5.08 |
| Fisheye-Overlay | 140.0 ± 0.0 | 2.9663 ± 0.0093 | 99.3101 ± 0.0829 | 290.65 ± 10.99 |
| T-NDN | 38.2 ± 0.1 | 0.3133 ± 0.0361 | 100.0 ± 0.0 | 144.13 ± 7.19 |

Two things in the table are not part of the hypothesis but matter:

- The fisheye overlay's p95 is roughly twice the others because every request
  pays the consumer→peer→producer path: the RTT-aware view buys convergence at
  a latency cost.
- FSR's CDR is 96.7 % because far-scope requests are still stale when their
  1 s Interest lifetime expires. That is the fisheye trade-off, not a coding
  artefact.

The CDR constraint is correspondingly easy to satisfy: T-NDN's worst repair
(0.4 s) is inside the 1 s Interest lifetime, so it loses no request, while NLSR
loses the 0.08 % issued in the first 0.24 s of its outage. The constraint is met
without a latency penalty (p95 144.1 ms versus NLSR's 144.4 ms), but it does not
discriminate between the two plans.

### H13 verdict

| Criterion | T-NDN | Baseline | Ratio | Limit | Verdict |
|---|---:|---:|---:|---:|---|
| FIB vs NLSR | 38.2 | 9900.0 | 0.0039 | ≤ 0.80 | PASS |
| FIB vs FSR-NDN | 38.2 | 779.8 | 0.049 | ≤ 0.80 | PASS |
| FIB vs Fisheye-Overlay | 38.2 | 140.0 | 0.273 | ≤ 0.80 | PASS |
| Convergence vs NLSR | 0.3133 | 1.2373 | 0.2532 | ≤ 0.80 | PASS |
| Convergence vs FSR-NDN | 0.3133 | 15.4833 | 0.0202 | ≤ 0.80 | PASS |
| Convergence vs Fisheye-Overlay | 0.3133 | 2.9663 | 0.1056 | ≤ 0.80 | PASS |
| CDR vs NLSR | 100.0 | 99.9196 | 1.0008 | ≥ 0.95 | PASS |
| TDA cost vs saved convergence | 21.73 ms | 924.0 ms | 0.0235 | < 1.0 | PASS |

Per-seed checks: all four criteria hold on 30/30 paired seeds. T-NDN's own
reconvergence is 0.2 s on 13 seeds and 0.4 s on 17 seeds (0.4 s when the node
next to the failure has no loop-free alternate for some cluster).

**H13: SUPPORTED** as frozen, subject to §6.

## 4. TDA overhead

Measured on the same seed set, wall-clock, one FIB build:

| Step | Cost (ms) |
|---|---:|
| Landmark selection (64 points, farthest-point) | 5.45 |
| Persistent homology (distance matrix, H0, H1 reduction) | 8.25 |
| Nearest-landmark assignment of 10 000 names | 8.03 |
| **Total** | **21.73** |

The convergence time the invariants buy is 924 ms against NLSR (1.237 −
0.313 s), so the overhead is 2.4 % of the saving. It is paid once per FIB
build, not per packet, and a link failure does not invalidate it: the
invariants are properties of the name space, so the failure triggers a table
switch, not a recomputation. If the name set changes continuously, the cost
recurs per change; that regime is not tested.

## 5. What this establishes, and what it does not

Establishes, on this scenario: name-space aggregation plus a preinstalled
loop-free alternate produces a small FIB and sub-second local repair without
losing delivery, and the invariant computation is cheap relative to the repair
it buys.

Does not establish:

1. **That T-NDN beats an aggregating NLSR on FIB.** See §6 — it does not.
2. **That the convergence advantage survives equal detection rates.** See §6.
3. **Anything packet-level.** This is a control-plane model; no PIT, no
   caching, no per-packet strategy, no queue dynamics beyond 2 ms/hop.
4. **That the name metric is the right one.** The semantic circle is
   stipulated. Without a loop (``H1 = 0``) T-NDN installs no backups and its
   repair is the 400 ms distance-vector fallback.
5. **Scalability of route-by-name state.** The FIB is counted, not memory-
   modelled.

## 6. The two sensitivities the verdict depends on

**(a) NLSR FIB aggregation.** The frozen scenario announces each of the 10 000
names individually, so NLSR installs one entry per name. If each producer
announced its block prefix instead — the normal thing to do with a hierarchical
namespace — NLSR would need **19.8** entries, and T-NDN's 38.2 would be 93 %
*larger*. The FIB criterion would then be **refuted**, and T-NDN would beat
only FSR (779.8) and the overlay (140.0), both of which already aggregate.
The FIB claim is therefore about the cost of per-name routing, not about a
property NLSR lacks; the invariant contribution is the *derivation* of the
clusters and the redundancy signal, not the aggregation itself.

**(b) Detection rate.** The frozen comparison gives NLSR a classical 1 s
failure detection and T-NDN a 200 ms heartbeat. Equalising detection at 200 ms
gives NLSR ≈ 0.44 s (the flood over the post-failure diameter remains), so
T-NDN is 28 % faster on the mean (ratio 0.72) and clears the 20 % margin on
**15 of 30 seeds**. The mechanism claim — local repair avoids the flood — still
holds; the "at least 20 % on every seed" claim does not survive equal
detection. The comparisons against FSR (15.48 s) and the overlay (2.97 s) are
insensitive to this: even a ten-times faster FSR (1.5 s) is far behind T-NDN.

Both sensitivities are post-hoc, reported rather than folded into H13. The
frozen thresholds were not moved.

## 7. Related work and positioning

This is the University of Bern lineage applied to NDN forwarding: the same
institute (Communication and Distributed Systems) produced the overlay
topology-awareness result this baseline comes from, the service-centric
architecture this namespace formalisation can serve, the forwarding-strategy
evaluation this routing plan complements, and the self-scaling CDN this
programme descends from.

- **Fisheye overlay (Milić and Braun, IEEE LCN 2009).** "Fisheye: Topology
  aware choice of peers for overlay networks" builds an overlay view from
  measured RTT distances, with no coordinate embedding, and chooses peers by
  proximity and diversity (DOI
  [10.1109/LCN.2009.5355168](https://doi.org/10.1109/LCN.2009.5355168)). The
  baseline in §1 implements that mechanism as faithfully as the model allows,
  including the extra overlay leg and the probe-round repair time. T-NDN keeps
  the "no embedding" constraint but changes what is measured: the distance is
  between *names*, and the structure used for forwarding is the persistent
  homology of that space, not the RTT graph. The result is content-routing
  state (clusters and alternates) rather than a peer set, and the comparison
  shows the trade: the RTT-only overlay converges in seconds and pays a
  two-leg latency, the name-space plan converges in fractions of a second
  without an extra leg.

- **Service-Centric Networking (Gasparyan, PhD thesis, University of Bern,
  2020).** SCN extends NDN from content to services, where the named object is
  a service instance rather than a fixed object (thesis:
  [boris.unibe.ch/144626](https://boris.unibe.ch/144626/1/thesis_gasparyan.pdf)).
  T-NDN is not a service architecture; it is a way to formalise the *namespace*
  such an architecture addresses — a metric, persistent clusters and loops —
  so that forwarding state can be derived from the namespace rather than from
  per-name configuration. The service/instance/content naming of
  [`paper-layering-testbed.md`](paper-layering-testbed.md) §3.1 is the natural
  place to apply it.

- **NDN forwarding strategies (Woo, Bachelor thesis, University of Bern,
  2025).** "Evaluation of Forwarding Strategies in Named Data Networking: A
  Simulation Based Approach" compares per-packet forwarding strategies in
  simulation (thesis:
  [cds.unibe.ch](https://www.cds.unibe.ch/unibe/portal/fak_naturwis/a_dept_math/c_iinfamath/micro_cds/content/e389283/e389288/e389289/e1812895/e1757260/Ilyas_Thesis.pdf)).
  T-NDN is complementary: a forwarding strategy chooses among next hops for a
  packet, while T-NDN decides how many FIB entries exist and which of them have
  a preinstalled alternate. The present experiment fixes a single-path FIB and
  does not evaluate strategy interaction — a limitation, not a claim that
  strategies are unnecessary.

- **Gezora (Nikolic, MSc thesis, University of Bern, 2010).** The
  self-scaling CDN in [`Ni10.pdf`](../Ni10.pdf) is the historical precursor: its
  cache placement and scaling decisions used local EWMA feedback rather than a
  global map. T-NDN inherits the principle — act on local measurement — and
  replaces the scalar EWMA with a structural object: the persistence of the
  name complex. The FIB and the repair rule are local decisions in the same
  sense Gezora's cache decisions were.

- **Background.** NDN (Zhang et al., *ACM SIGCOMM CCR* 44(3), 2014, DOI
  [10.1145/2656877.2656887](https://doi.org/10.1145/2656877.2656887)), NLSR
  (Hoque et al., ICN 2013, DOI
  [10.1145/2491224.2491231](https://doi.org/10.1145/2491224.2491231)), FSR
  (Pei, Gerla and Chen, IEEE ICC 2000, DOI
  [10.1109/ICC.2000.853066](https://doi.org/10.1109/ICC.2000.853066)), and
  persistent homology (Edelsbrunner, Letscher and Zomorodian, *Discrete &
  Computational Geometry* 28(4), 2002, DOI
  [10.1007/s00454-002-2885-2](https://doi.org/10.1007/s00454-002-2885-2)).

## 8. Reproduction

```bash
py tools/benchmark_tndn.py --seeds 30 --output-dir figures
py -m pytest tests/test_tndn.py -q
```

Outputs: [`figures/tndn_per_seed.csv`](../figures/tndn_per_seed.csv),
[`figures/tndn_summary.csv`](../figures/tndn_summary.csv),
[`figures/tndn_h13.csv`](../figures/tndn_h13.csv),
[`figures/tndn_tda.csv`](../figures/tndn_tda.csv),
[`figures/tndn_equal_detection.csv`](../figures/tndn_equal_detection.csv).
The run is deterministic per seed; 30 seeds take a few seconds on one CPU.

## 9. Limitations

- **Scenario, not deployment.** One random-geometric topology family, one
  failure per seed, one traffic rate, one name-space shape, no caching.
- **Stipulated constants.** FSR's scope intervals, the overlay's probe
  interval and T-NDN's heartbeat are design parameters, not measurements. The
  ordering of the baselines is robust to large changes in these (FSR would
  need a ten-fold faster far scope to approach T-NDN), but the absolute
  convergence numbers are model outputs.
- **The semantic circle is an assumption.** It is the only reason ``H1`` is
  non-empty. A namespace with no persistent loop yields no backups, and the
  repair falls back to the 400 ms distance-vector round.
- **NLSR is not given prefix aggregation.** §6(a).
- **The distance-vector solve is centralised in the simulator**, although its
  state is local by construction.
- **FIB size is counted, not memory-modelled**, and no control-message volume
  is reported; "high overhead" for NLSR is represented by detection + flood
  time, not by bytes.
