# Dual-role nodes: continuous capacity split between serving and load balancing

**Status:** frozen claim and scenario, committed before the experiment code.
This document fixes what the experiment measures; results are reported
separately in `docs/dual-role-results.md`.

## 1. The falsifiable claim

> For a stipulated P2P mesh under heterogeneous, time-varying demand, a
> controller that continuously reallocates every node's resource between
> **serving** (fraction `α`) and **load balancing / forwarding** (fraction
> `1 − α`) sustains **at least 5 % higher aggregate delivered goodput** at the
> load point where the separated baseline first drops below 95 % delivered, and
> its p95 latency at matched delivered load never exceeds **1.5 ×** the
> separated baseline's p95.

The separated baseline fixes roles at design time, the way a proxy-based
service mesh separates serving pods from proxy pods: middle nodes are pure
load balancers (`α = 0`) and edge nodes are pure servers (`α = 1`). The two
arms share the same topology, demand, flow allocator and loss model; only the
role variable changes. That isolates the one claim under test: fluid
reallocation versus architectural separation.

The claim is falsifiable in two independent ways: goodput can fail to beat the
5 % margin, and latency can exceed the 1.5 × bound. Either failure refutes it.

## 2. Model

A discrete-time flow model in `simulation/dual_role.py`. One tick is one
simulated second.

**Topology.** A mesh of nodes joined by heterogeneous links (capacity, latency,
MTU). `O` is the origin; `E1`, `E2`, `E3` are demand nodes with serving
capacity; `M1`, `M2` are interior nodes that may serve or balance. Simple
origin-to-edge paths are enumerated and each carries a bottleneck capacity,
summed latency and an MTU fragmentation factor.

**Node resource and roles.** Every non-origin node has a total resource
`R` (Mbps). At each control interval the node chooses `α ∈ [0, 1]`:

- serving capacity `= α · R · hit`, where `hit` is the node's warmed cache-hit
  ratio (linear warm-up, capped by cache size);
- forwarding (balancing) capacity `= (1 − α) · R`, which bounds transit flow
  through the node.

A cached copy still traverses the downstream links to the demand node; only
the upstream links are avoided. This keeps the comparison honest against the
earlier discrete-role model.

**Flow.** Demand per edge node splits across paths in proportion to a potential
(latency, congestion, fragmentation), damped in time, then water-fills within
residual link capacity and the per-node forwarding budgets. Serving relieves
upstream links up to the node's serving capacity.

**Fluid controller.** Each control interval, a node sets

```text
pressure     = incident load / incident capacity           (clamped to [0, 1])
trend        = velocity and acceleration of pressure,      (finite differences)
               normalised by the reference values below
serve_signal = w_p · pressure · hit + w_v · max(0, velocity) + w_a · max(0, acceleration)
target_α     = clamp(α₀ + gain · serve_signal, 0, 1)
α            = (1 − λ) · α_prev + λ · target_α             (damping λ)
```

The velocity/acceleration terms are the "turbo" feed-forward: a node that sees
pressure rising commits to serving before the queue builds. `α₀`, `gain`, the
weights and the damping `λ` are **stipulated** controller parameters, fixed
here and not tuned after results.

**Separated baseline.** `α` is fixed per node: interior nodes are pure load
balancers (`α = 0`), edge nodes pure servers (`α = 1`). No reallocation is
possible; capacity stranded in a server cannot be used to forward, and vice
versa.

## 3. Scenarios (stipulated)

| Scenario | Purpose | Demand |
|---|---|---|
| `steady` | nominal heterogeneous load | fixed per-edge demand |
| `flash_crowd` | the `α`-over-time trace | demand spike at `E2` and `E3` during `t ∈ [40, 80)` |
| `ddos` | exploratory flood behaviour | focused +250 Mbps flood at `E2` during `t ∈ [40, 100)` |
| `demand_sweep` | throughput-vs-load | offered load `0.2 … 2.0 ×` nominal, applied uniformly |

Stochastic runs use paired seeds; the model adds a small multiplicative demand
noise per tick.

## 4. Observables (fixed before experiments)

1. aggregate delivered goodput (Mbps);
2. delivered fraction (% of offered demand);
3. p95 latency (ms);
4. `α` trace per node and `|Δα/Δt|` (role stability).

## 5. Acceptance criteria (frozen)

Let `L*` be the lowest sweep load at which the **separated** arm delivers less
than 95 % of offered demand. The claim is **confirmed** only if, at `L*`:

1. fluid delivered goodput ≥ separated delivered goodput × 1.05 (paired-seed
   interval excludes zero below that margin), **and**
2. fluid p95 latency ≤ 1.5 × separated p95 latency at the same swept load `L*`.

It is **refuted** if either bound fails at `L*`, and **inconclusive** if `L*`
does not exist within the swept range (the topology never drops below 95 %).

### 5.1 Exploratory DDoS question (added after the main run)

After the main comparison was run, a focused demand flood at `E2` was added to
ask whether the same controller helps or hurts under attack-shaped load. This
is **exploratory, not pre-registered**, and is reported separately:

> Under the `ddos` scenario, fluid delivery to the unattacked targets `E1` and
> `E3` is at least as high as separated delivery (paired 95 % interval).

It is refuted if either unattacked target's fluid delivery is significantly
below the separated arm. The flood is a demand surge; the model cannot tell
malicious from legitimate bytes and implements no scrubbing, rate limiting or
source classification. It measures collateral delivery, not a security
defence.

Controller parameters, topology, links, demand schedules and seed sets are
stipulated in `simulation/dual_role.py`; none are fitted to results.

## 6. Scope and non-goals

- This is a flow-level model, not a packet-level protocol. It does not
  implement TCP, ACK clocks, retransmission or MPTCP scheduling.
- No security claim, no wireless PHY/MAC model, no congestion-control stack.
- The claim is about a simulated mesh under stipulated conditions; it is not a
  statement about any deployed network.
- A refutation is a valid result and is reported, not removed.
