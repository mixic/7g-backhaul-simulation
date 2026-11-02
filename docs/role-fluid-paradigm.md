# The role-fluid multipath paradigm

This document defines the paradigm the simulator is now built around, the model
that implements it, and the measured results. It supersedes the earlier
predictive-scheduling framing, which measured a consequence of the idea rather
than the idea itself.

## 1. The claim

The proposal is not "forecast congestion and schedule packets accordingly". It
is that **a network node has no fixed role**. At any moment a node may be a
router, a server/cache, or a load balancer, and the role itself is a control
variable chosen continuously from local state. Because a path terminates at a
node that may become a server, path selection and role selection are the same
optimisation: choosing a path also decides what the node at its end should
become. MPTCP cannot express this, because its endpoints are fixed by the
connection.

The load-balancing and route-calculation function across heterogeneous
backhauls is carried by a multipath protocol whose two governing rules are:

- **Gradient flow (water overflowing a river).** Flow splits across candidate
  paths in proportion to a potential gradient, and excess above a path's
  capacity spills onto the alternatives. No forecast, no central solver: a local
  water-filling rule with memory.
- **Boundary coefficients (seismic waves crossing the crust).** At every medium
  boundary, energy partitions into a transmitted part that fits the next
  medium's MTU and a reflected part that must be requeued. The transmission
  coefficient is bounded by the MTU ratio, so heterogeneous fragmentation is a
  first-class term in the potential rather than an implementation detail.

## 2. What this document does and does not claim

- The **protocol** derived from this paradigm is specified separately
  ([rfmp-protocol.md](rfmp-protocol.md)) and its role-transition mechanics are
  cross-validated against ns-3 ([rfmp-validation.md](rfmp-validation.md)). That
  validates the protocol, not the controller.
- The **controller is not shown to beat a static design.** Section 6 reports a
  negative result for the local rule, and states which conditions it needs.
- The economics are stipulated, though they are now *less* stipulated than in
  the previous version: serving is bounded by a cache with a finite capacity, a
  hit ratio and a warm-up period, so a node that serves cannot serve everything
  from the first tick.
- No cache eviction, no content-popularity dynamics and no request-level hit
  accounting: the hit ratio is a deterministic fraction of a fixed working set.

## 3. Model

Implemented in [`simulation/role_fluid.py`](../simulation/role_fluid.py) and
compared by [`tools/benchmark_role_fluid.py`](../tools/benchmark_role_fluid.py).

**Topology.** One origin, two core nodes and three edge demand nodes over nine
heterogeneous links: fibre (9000-byte MTU, 0.5 $/GB), microwave (1500-byte MTU,
1.2 $/GB), Wi-Fi (1200-byte MTU, 1.5 $/GB) and satellite (1200-byte MTU, 25 ms,
4.0 $/GB). Twenty-eight simple origin-to-edge paths are enumerated (10 to E1, 8
to E2, 10 to E3); each carries a bottleneck capacity, summed latency,
compounded loss, summed cost and an MTU fragmentation factor.

**Roles.**

| Role | Effect on flow | Cost |
| --- | --- | --- |
| `forward` | passes traffic to the next hop | transit cost only |
| `balance` | attracts flow and reduces queueing on its incident links when they are unequally loaded | 0.01 $ per tick |
| `serve` | terminates demand at its cache, or forwards the cached copy over the remaining path | 6 $/GB served |

**Caches.** Every node has a cache capacity (0.10–0.35 GB) and a fixed 0.5 GB
working set. The hit ratio is `cached / 0.5 GB`, capped by
`capacity / 0.5 GB`, and warms linearly to that cap over 8 s of serving.
Serving is limited to `demand × hit`, the remainder transits as usual; a miss is
served from the origin and *also* populates the cache, so the investment is paid
in transit, not in an invented fill fee. A node that stops serving keeps its
cache. A cached copy at an intermediate node still traverses the downstream
links to the demand node — only the upstream links are avoided.

**Potential and flow.**

- Path potential: `Φ_p = w_c·max_util_p + w_l·latency_p/L0 + w_f·(frag_p−1) + w_c$·cost_p/C0 − w_b·balancers_p`.
- Per-demand split: `w_target ∝ exp(−Φ_p/τ)`, then damped
  `w ← (1−λ)·w_prev + λ·w_target` with `λ = 0.5`.
- Allocation: sequential best-first water-filling across paths, at most three
  spill passes, clipped by residual link capacity.
- Role update every 5 ticks from a local potential that trades incident
  utilisation, operating cost, the amortised switch cost, the hit ratio the
  cache can reach, and — for the priced rule — the node's own unmet-demand
  fraction. A **role dwell timer** (20 ticks) prevents a node from leaving a
  role before its cache has warmed.

## 4. Controllers compared

| Arm | Information | Decision rule |
| --- | --- | --- |
| `static_design` | design time | `C1` balances, `E2` and `E3` serve, everything else forwards |
| `centralized_greedy` | whole network | myopic greedy descent on the true one-tick objective, switch cost amortised over 20 ticks |
| `local_fluid` | local | incident utilisation + own unmet demand + reachable hit ratio, damping 0.5, hysteresis 0.004 $, dwell 20 ticks |
| `local_congestion` | local | same but ignores unmet demand — the "roles priced by congestion alone" control |
| `local_reactive` | local | same as `local_fluid` with no memory (damping 1.0, hysteresis 0) |

## 5. Results (6 paired seeds, 95 % intervals)

| Scenario | Arm | Delivered | p95 | Total cost | Role switches | Share oscillation | Served locally | Cache hit |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| steady | static | 99.85 % | 18.5 ms | $10.21 | 0 | 0.014 | 43.0 % | 18.3 % |
| steady | centralised | 99.38 % | 59.8 ms | $5.13 | 0 | 0.015 | 0.0 % | 0.0 % |
| steady | local fluid | 99.63 % | 36.4 ms | $11.59 | 10.0 | 0.022 | 16.8 % | 12.8 % |
| flash crowd | static | 99.65 % | 48.2 ms | $12.48 | 0 | 0.024 | 29.0 % | 18.3 % |
| flash crowd | centralised | 99.34 % | 56.8 ms | $8.90 | 4.0 | 0.025 | 8.3 % | 12.2 % |
| flash crowd | local fluid | 95.90 % | 53.2 ms | $15.44 | 13.0 | 0.034 | 17.5 % | 20.1 % |
| outage | static | 99.85 % | 21.8 ms | $10.22 | 0 | 0.035 | 42.9 % | 18.3 % |
| outage | centralised | 99.41 % | 62.5 ms | $5.60 | 2.0 | 0.024 | 2.7 % | 3.9 % |
| outage | local fluid | 99.54 % | 51.5 ms | $11.76 | 10.0 | 0.035 | 17.3 % | 12.8 % |

Paired differences whose 95 % intervals exclude zero:

| Comparison | Metric | Steady | Flash crowd | Outage |
| --- | --- | ---: | ---: | ---: |
| fluid − static | delivered | −0.22 pp | −3.76 pp | −0.31 pp |
| fluid − static | cost | +$1.39 | +$2.97 | +$1.54 |
| fluid − centralised | delivered | +0.25 pp | −3.45 pp | +0.13 pp |
| fluid − centralised | cost | +$6.46 | +$6.54 | +$6.16 |
| congestion-only − fluid | delivered | 0 | 0 | 0 |
| reactive − fluid | delivered | −0.10 pp | −0.56 pp | −2.83 pp |

## 6. What the numbers say

1. **The local rule still loses to a static design.** In the flash crowd it
   delivers 3.76 pp less and costs $2.97 more. The cache dimension did not
   rescue it: the static design pre-warms two edge caches, while the local rule
   keeps switching and its caches warm slowly.
2. **A centralised controller is much cheaper but not always better.** It
   delivers less in the steady and outage scenarios (99.38 % / 99.41 % versus
   99.85 %), because it is myopic: it will not pay to warm a cache for demand it
   cannot foresee. In the flash crowd it is both cheaper and better than the
   local rule, but still 0.31 pp behind the static design.
3. **Damping is now unambiguous.** Undamped share oscillation is 0.29–0.46;
   with `λ = 0.5` it falls to 0.022–0.034, and with `λ = 0.3` to about 0.015.
   The earlier claim that instability peaks at *moderate* path heterogeneity was
   an artifact of the cache-free model and is withdrawn: with cache warm-up,
   undamped oscillation is 0.39–0.50 at every latency spread tested.
4. **Role churn is the paradigm's hidden cost, and a dwell timer is part of the
   protocol, not a tuning detail.** Without a dwell timer the priced rule flaps
   because the one-tick unmet signal collapses as soon as it serves, which
   prevents the cache from warming. Hysteresis then trades responsiveness for
   churn: 15.8 switches / 95.20 % / $15.83 at zero hysteresis, 6.8 switches /
   97.90 % / $13.20 at 0.02 $, 1.0 switch / 91.66 % / $10.18 at 0.05 $.
5. **The unmet-demand signal is inert under these settings.** Congestion-only
   and priced arms are identical in all three scenarios because delivery stays
   above 95 %, so the signal never activates. It remains a local, computable
   signal, but this experiment does not demonstrate its value.
6. **Serving is a finite resource.** Cache hit ratios (3.9–20.1 % across the
   serving arms) cap what serving can deliver; a node that serves always can no longer serve everything, which
   is the correction the previous version of this document listed as missing.

## 7. Price calibration

The local potential trades congestion, latency, fragmentation and money with
fixed weights. Raising the cost weight reduces cost and, up to a point, raises
delivery; it does not close the gap to the static design:

| `w_cost` | local cost (steady / flash) | local delivered (steady / flash) | centralised cost | centralised delivered |
| ---: | ---: | ---: | ---: | ---: |
| 0.3 | $11.59 / $15.49 | 99.63 % / 95.62 % | $5.13 / $8.89 | 99.38 % / 99.37 % |
| 1.0 | $11.12 / $14.63 | 99.67 % / 96.71 % | $4.55 / $8.10 | 99.46 % / 99.52 % |
| 3.0 | $9.73 / $14.01 | 99.68 % / 95.03 % | $4.15 / $7.79 | 99.51 % / 99.55 % |

## 8. Threats to validity

- **Cache model is coarse.** Uniform popularity, no eviction, no churn, no
  request-level accounting. A real cache has a hit-ratio curve, not a linear
  warm-up.
- **The controller is not wired to the protocol.** RFMP v0.1
  ([rfmp-protocol.md](rfmp-protocol.md)) is specified and validated separately
  with *scripted* role epochs; this model decides roles on 1 s ticks and does
  not emit packets. Bridging the two is the next experiment.
- **Myopic centralised baseline.** One-tick greedy understates what
  centralisation can do.
- **One topology, stipulated prices.** Section 7 shows the conclusions move
  with the cost weight.
- **Intermediate serving was corrected during this work.** A cached copy at a
  core node now traverses the downstream path; the earlier version credited it
  with delivery while only using the upstream links. Results before and after
  are not comparable.

## 9. Next steps, in order

1. **Done — protocol specification** ([rfmp-protocol.md](rfmp-protocol.md)) and
   **role-transition cross-validation** ([rfmp-validation.md](rfmp-validation.md)).
2. **Done — cache capacity and hit-ratio limit** in this model.
3. Add eviction and a popularity curve, so caches have churn and a real
   hit-ratio function.
4. Extend the RFMP scenario to a cold-cache transition (RT2): the protocol
   currently assumes the serving node can answer immediately.
5. Close the loop: let this controller drive the protocol's epochs instead of
   scripting them.
6. Compare against a real MPTCP stack, so the multipath claim is measured rather
   than modelled.
7. Pre-register the acceptance criterion (delivery, churn, cost) before the next
   round, following the negative-result discipline of the earlier
   predictive-scheduling work.
