# The role-fluid multipath paradigm

This document defines the paradigm the simulator is now built around, the model
that implements it, and the first measured results. It supersedes the earlier
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

## 2. What this document does not claim

- The model is not a protocol. There are no packets on a wire, no ACK clock, no
  retransmission, no scheduler, and no path manager. It is a control model.
- It is not cross-validated against ns-3. The transport cross-validation in
  [external-validation.md](external-validation.md) covers a different
  (fixed-role, two-path) scenario.
- The economics are stipulated. `serve` is an idealised local termination: the
  model has no cache-capacity or hit-ratio dimension yet, so a node that serves
  always can.
- The first results are negative for the naive local rule (Section 6). They
  identify which conditions the paradigm needs, not that it wins.

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
| `balance` | preferentially attracts flow and reduces queueing at its incident links | 0.01 $ per tick |
| `serve` | terminates demand locally up to its service capacity, saving transit | 6 $/GB served, 3 $/GB newly cached |

Serving at an *intermediate* node also truncates the remaining path, which is
how a server absorbs a flash crowd before congestion propagates upstream.

**Potential and flow.**

- Path potential: `Φ_p = w_c·max_util_p + w_l·latency_p/L0 + w_f·(frag_p-1) + w_c$·cost_p/C0 − w_b·balancers_p`.
- Per-demand split: `w_target ∝ exp(−Φ_p/τ)`, then damped
  `w ← (1−λ)·w_prev + λ·w_target` with `λ = 0.5`.
- Allocation: sequential best-first water-filling across paths, at most three
  spill passes, clipped by residual link capacity.
- Role update every 5 ticks from a local potential that trades incident
  utilisation, operating cost, the amortised switch cost, and — for the priced
  rule — the node's own unmet-demand fraction.

## 4. Controllers compared

| Arm | Information | Decision rule |
| --- | --- | --- |
| `static_design` | design time | `C1` balances, `E2` and `E3` serve, everything else forwards |
| `centralized_greedy` | whole network | myopic greedy descent on the true one-tick objective, switch cost amortised over 20 ticks |
| `local_fluid` | local | incident utilisation + own unmet demand, damping 0.5, hysteresis 0.004 $ |
| `local_congestion` | local | same but ignores unmet demand — the "roles priced by congestion alone" control |
| `local_reactive` | local | same as `local_fluid` with no memory (damping 1.0, hysteresis 0) |

## 5. Results (6 paired seeds, 95 % intervals)

| Scenario | Arm | Delivered | p95 | Total cost | Role switches | Share oscillation | Served locally |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| steady | static | 99.82 % | 18.9 ms | $11.03 | 0 | 0.006 | 42.5 % |
| steady | centralised | 99.38 % | 59.8 ms | $5.13 | 0 | 0.015 | 0.0 % |
| steady | local fluid | 99.43 % | 45.8 ms | $11.99 | 23.5 | 0.041 | 3.0 % |
| flash crowd | static | 95.13 % | 60.5 ms | $14.79 | 0 | 0.007 | 29.4 % |
| flash crowd | centralised | 88.73 % | 75.1 ms | $10.43 | 1.3 | 0.020 | 1.1 % |
| flash crowd | local fluid | 91.69 % | 58.4 ms | $16.99 | 27.3 | 0.048 | 7.7 % |
| backhaul outage | static | 99.82 % | 33.8 ms | $11.01 | 0 | 0.027 | 42.9 % |
| backhaul outage | centralised | 93.83 % | 63.2 ms | $5.88 | 0 | 0.022 | 0.0 % |
| backhaul outage | local fluid | 96.61 % | 60.4 ms | $12.78 | 25.0 | 0.041 | 4.2 % |

Paired differences whose 95 % intervals exclude zero:

| Comparison | Metric | Steady | Flash crowd | Outage |
| --- | --- | ---: | ---: | ---: |
| fluid − static | delivered | −0.39 pp | −3.44 pp | −3.22 pp |
| fluid − static | cost | +$0.96 | +$2.20 | +$1.77 |
| fluid − centralised | delivered | +0.05 pp | +2.96 pp | +2.77 pp |
| fluid − centralised | cost | +$6.85 | +$6.56 | +$6.90 |
| congestion-only − fluid | delivered | 0 | −1.41 pp | −0.10 pp |
| reactive − fluid | oscillation | +0.005 | +0.006 | +0.003 |

## 6. What the numbers say

1. **The naive local rule does not beat a sensible static design.** It delivers
   less and costs more in all three scenarios. The paradigm is not demonstrated
   by this controller; the experiment shows what a potential-field rule *without
   calibrated prices* does.
2. **A centralised controller with the true objective is much cheaper but
   delivers less under stress** (88.7 % vs 91.7 % in the flash crowd, 93.8 % vs
   96.6 % in the outage). It is myopic: it will not pay to serve now for demand
   it cannot foresee, whereas the static design pre-provisions caches.
3. **Pricing roles by congestion alone is not enough.** Adding the node's own
   unmet-demand fraction is worth +1.41 pp of delivery in the flash crowd for
   $0.67. The information a node needs is local — its own deficit — not global.
4. **Damping is mandatory.** On the steady scenario, share oscillation falls
   from 0.190 (no memory) to 0.048 (λ = 0.6) and 0.031 (λ = 0.3). Undamped
   gradient flow oscillates, as the water analogy predicts for a delayed
   feedback loop.
5. **Instability is not monotonic in heterogeneity.** With path latencies scaled
   ×1 and ×4 the undamped rule oscillates (0.190 and 0.163), but at ×2 it does
   not (0.048, five role switches). The dangerous regime is *moderate*
   heterogeneity, where two paths remain competitive; with a clear winner the
   gradient is unambiguous.
6. **Role churn is the paradigm's hidden cost.** Hysteresis buys stability at the
   price of responsiveness: 33.8 switches / $17.30 / 91.88 % at zero hysteresis
   versus 2.0 switches / $11.95 / 89.18 % at 0.05 $. Any credible version of the
   paradigm must budget for migration, not just for steady-state routing.

## 7. Why the local rule loses, and what would fix it

The local potential aggregates congestion, latency, fragmentation and money
with fixed weights. The centralised controller minimises the true objective.
The gap is a pricing error, and it is measurable: raising the potential's cost
weight from 0.3 to 1.0 cuts local steady-state cost from $12.03 to $9.66, and
the flash-crowd delivered fraction rises from 91.9 % to 94.4 %. Further
increases over-fire on cost (at 3.0, delivery falls back to 92.6 %). A
calibrated potential — or one whose weights are learned online — is therefore a
necessary component, not a tuning detail:

| `w_cost` | local cost (steady / flash) | centralised cost | local delivered (flash) | centralised delivered |
| ---: | ---: | ---: | ---: | ---: |
| 0.3 | $12.03 / $16.97 | $5.13 / $10.48 | 91.9 % | 88.2 % |
| 1.0 | $9.66 / $15.30 | $4.55 / $8.74 | 94.4 % | 96.2 % |
| 3.0 | $10.16 / $15.46 | $4.15 / $8.02 | 92.6 % | 98.0 % |

## 8. Threats to validity

- **No cache capacity.** Serving is idealised; a real cache has finite content,
  a hit ratio, and eviction churn. This is the most important missing dimension,
  because it is what makes "serve everywhere" uneconomic in reality.
- **No protocol.** No ACK clock, no reordering buffer, no path manager, no
  failure detector. Cross-validation of role transitions in ns-3 is the next
  experiment, not a completed one.
- **Myopic centralised baseline.** `centralized_greedy` minimises a one-tick
  objective; a lookahead controller would be stronger. The comparison therefore
  understates what centralisation can do, which makes the local result look
  relatively better than it should.
- **One topology, stipulated prices.** The 6 $/GB serve cost, 10 $/GB unmet
  penalty and link prices are assumptions. Section 7 shows the conclusions move
  with them, which is a warning, not a sensitivity analysis.

## 9. Next steps, in order

1. Add cache capacity and a hit-ratio curve, so serving has a real marginal cost
   and a real limit.
2. Specify the multipath protocol around this controller: path manager, ACK
   clock, reordering buffer, and the boundary/reflection queue.
3. Cross-validate role transitions in ns-3 against a fixed-role baseline — the
   analogous experiment to the transport validation already published.
4. Compare against a real MPTCP stack, so the multipath claim is measured rather
   than modelled.
5. Pre-register the acceptance criterion (delivery, churn, cost) before running
   the next round, following the negative-result discipline of the earlier
   predictive-scheduling work.
