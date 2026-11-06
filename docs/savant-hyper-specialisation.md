# Compensatory hyper-specialisation: the "savant" mechanism

**Status:** pre-registered claim, written before running Experiment 4. The
biological framing is an analogy, not evidence. This document translates savant
syndrome into control theory and resource allocation, states a falsifiable
network mechanism, and fixes the metric and thresholds before measurement.

## 1. Concept

Standard self-scaling networks (Kubernetes, MEC) employ symmetric, proportional
scaling in response to load. We propose an alternative inspired by biological
neuroplasticity: **Compensatory Hyper-Specialisation**. When a node detects a
kinematic shockwave (injury), it may intentionally shed its general routing role
and execute a severe, asymmetric shift in its role fraction `α`, dedicating
100% of its local resources to the affected circuit. We hypothesise that this
localised "savant" behaviour provides superior resilience for the affected flow
under extreme attack, at the measurable cost of system-wide transit efficiency.
The experiment quantifies this trade-off and identifies the threshold where
local hyper-specialisation triggers cascading global starvation.

## 2. Translation table

| biological concept | network equivalent | implementation |
|---|---|---|
| neural tissue | the 7G backhaul mesh | 100-node three-medium fabric |
| injury / deficit | DDoS shockwave, link failure, congestion spike | 10 s flood at 300 k req/s on one name |
| neuroplastic rewiring | role fluidity, `α ∈ [0,1]` | `NodeState.alpha`, forwarding `(1-α)C_n` |
| hyper-allocated circuit | surgical edit isolating one flow | one `(content, source-region)` WFQ class |
| savant skill | a node drops general routing to serve/scrub one circuit | `α → α_target`, affected class given top priority |
| cost of the gift | neighbours absorb shed transit; system-wide starvation | `spillover`, system-wide goodput, p95 |

## 3. Control law

On a kinematic spike the savant controller performs three actions at the
congested node:

1. isolate the culprit class and give it full weight and a large byte limit
   (the hyper-allocated circuit);
2. drive `α` toward `α_target` through the same double-integrator governor used
   by the surgical controller, with `v_max = 0.35/s` and `a_max = 0.60/s²`, so
   the "violent" shift is still a bounded trajectory rather than a discontinuity;
3. hold until the pressure recovers, then release.

`α_target` is the **gain** of the mechanism and is swept, because a single value
cannot test a threshold.

## 4. Falsifiable claim (H4)

> Under a localised extreme shockwave, savant rewiring maintains a **higher
> delivery probability for the affected name** than symmetric load balancing
> (Kubernetes-style) or smooth gradient actuation (VDR-style flux field), at the
> measurable cost of system-wide transit efficiency.

The **control** is the smooth, rate-controlled surgical arm, which tries to
balance general traffic and the spike rather than sacrificing one for the other.

Metrics, fixed in advance:

* **Affected Flow Delivery Rate** — delivered / offered for the attacked name in
  the shock window.
* **General Flow Delivery Rate** — the same for every other name.
* **System-wide throughput** — delivered / offered across all legitimate traffic.
* **p95 latency ratio** — shock window over steady window.
* **Neighbour spillover** — throughput change at the neighbours of every
  `α`-edited node, shock window versus steady window.

**Refuted if** any of these hold:

1. the best gain in the sweep does not beat Baseline A on affected delivery; or
2. it does not beat VDR on affected delivery; or
3. the sweep shows no interior optimum — that is, no threshold exists and the
   mechanism is monotone in its own gain.

**Confirmed with cost** if 1 and 2 hold *and* system-wide delivery degrades as
the gain rises, with p95 inflating beyond the threshold. Losing to the
rate-controlled control arm does **not** refute H4 as stated (the claim is
against K8s and VDR), but it is reported because it bounds the paradigm's value.

## 5. Why it might fail

In the mesh an origin sits behind a single uplink, and the congested node is that
uplink's last router. Shedding its forwarding capacity removes the capacity the
affected flow itself needs, so the mechanism may be self-defeating. In biology a
savant often cannot perform ordinary tasks; here the analogue is that neighbours
must absorb shed transit, and if they are already loaded the result is a shared
cascade rather than a local rescue. That is measured, not assumed.

## 6. Reproduction

```bash
py tools/benchmark_surgical.py --replicates 30
py tools/plot_surgical.py
```

Results in [`surgical-results.md`](surgical-results.md) §6; figure
`figures/surgical_h4_gain_sweep.png`.
