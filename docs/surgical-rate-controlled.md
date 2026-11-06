# Surgical, rate-controlled state updates

**Status:** pre-registered claim, written before running the surgical
experiment. The observation layer used here is the one specified in
[`7g-backhaul-vision-paper.md`](7g-backhaul-vision-paper.md) §5: link pressure
`p_i(t)`, pressure velocity `v_i(t) = dp_i/dt`, and pressure acceleration
`a_i(t) = d²p_i/dt²`, with "acceleration-triggered cross-medium overflow" named
as the target regime. The paper does not specify the *control law* that maps
those observations to state changes. This document specifies it and fixes the
falsification conditions before measurement.

The prior iteration's controller (``simulation/dual_role.py``) already consumed
velocity and acceleration, but applied them **globally** to `α` on every node.
The claim tested here is therefore not "kinematics versus no kinematics". It is
that *localised, rate-capped actuation* beats *global actuation* built from the
same observations.

## 1. State plane

A node's editable state is

```
S = (α, queue policy, FIB overrides)
```

* `α ∈ [0, 1]` — role fraction. `α = 0` is a pure router/balancer, `α = 1` a
  pure cache/server. Forwarding capacity is `(1 - α)·C_n`, serving capacity
  `α·C_n`, with a 2 % forwarding floor so a node pushed to `α = 1` still drains
  keepalive traffic instead of deadlocking the event queue.
* Queue policy — per-class WFQ weight and per-class byte limit.
* FIB overrides — per-flow next hop, layered over the loop-free name table.

Every mutation goes through `simulation/surgical/state.py::StateLedger`, the
only place speed and acceleration of state change are computed:

```
speed(t) = |ΔS| / Δt        accel(t) = |Δspeed| / Δt
```

## 2. Kinematic monitor

Adaptive thresholds, so that the steady state is silent without a hand-tuned
constant:

```
residual_a = |a - EMA(a)|
threshold  = max(floor, k · EWMA(|residual_a|)),   k = 4
spike      = residual_a > threshold
```

Two estimators are implemented because the literature (the α-β filter used for
RTT prediction) argues a trend-following filter beats a moving average:
`EmaMonitor` (default) and `ABMonitor`.

## 3. Control law (the contribution)

Two kinds of rate control, deliberately different:

1. **Discrete edit** — promote one `(content, source-region)` class into its own
   WFQ lane at the routers it crosses, applied in a single step. Bounded by a
   **per-node token bucket**: `edit_speed_max = 0.35` normalised units/s, burst
   `2.2`. A node that has just fired cannot fire again for `|ΔS| / v_max`
   seconds.
2. **Continuous knob** — `α` and buffer scale move through a **double
   integrator** with `v_max = 0.35 /s` and `a_max = 0.60 /s²`.

**Hysteresis is a pressure test, not an acceleration test.** A sustained flood
has zero acceleration and high pressure, so releasing on "calm acceleration"
un-isolates in the middle of an attack. Release additionally requires the
culprit class's arrival rate to have stopped for five consecutive control ticks.

## 4. Falsifiable claims

**H1 (surgical advantage).** Under a high-acceleration DDoS shockwave, the
surgical arm limits p95 latency to **≤ 1.5× baseline** and holds legitimate
goodput **> 95 %**, whereas the global pressure controller starves the system
(p95 **> 2.2×**) and loses **> 10 %** goodput.

*Refuted if* any of the four clauses fails. A controller that keeps p95 low by
discarding traffic must not pass: goodput is reported separately and a
loss-aware p95 (dropped requests censored at the deadline) is also computed.

**H2 (rate control versus churn).** Capping the speed and frequency of state
changes prevents role oscillation without sacrificing responsiveness.

*Refuted if* the surgical arm's **sustained** state-change rate is not below 50 %
of the pressure controller's, or if the peak cannot also be bounded.

**H3 (MTU boundary).** Surgical edits localised at the fiber→satellite boundary
prevent reassembly deadlock caused by MTU mismatch.

*Refuted if* the reassembly buffer is never engaged, in which case the
hypothesis is **untested** rather than confirmed — a zero deadlock fraction on a
mechanism that never fires is not evidence.

**H4 (savant hyper-specialisation).** Compensatory hyper-specialisation —
shedding general transit to hyper-allocate local resources to the affected
circuit — maintains higher delivery for the affected name than symmetric
load balancing or smooth gradient actuation.

*Refuted if* the savant arm does not beat the surgical arm on affected-name
delivery, or if the cost to unrelated traffic is not the predicted trade-off.

## 5. Arms

| arm | role |
|---|---|
| `k8s` | Baseline A — static roles, slow central scaling (15 s, step 0.25) |
| `pressure` | Baseline B — the previous iteration's global `α` law, reproduced verbatim (`α0 = 0.5`, gain 1.0, damping 0.5, trend gains 0.5/0.3, 2 s period) |
| `pressure_tuned` | Baseline B given its best shot (signed release, faster period, `α0` = initial role) |
| `surgical` | the thesis arm |
| `surgical_unlimited` | same trigger and scope, no rate cap, no hold |
| `surgical_ab` | α-β filter trigger instead of the EMA |
| `surgical_global` | same trigger and caps, but the edit lands on the whole node |
| `static_isolation` | **confound control** — per-flow isolation always on for every flow, no trigger at all |
| `vdr` / `vdr_surgical` | loop-free potential-gradient flux field installed instantly vs. through the governor (composability pairing) |
| `savant` | H4 |

`static_isolation` is the most important arm. Per-flow fair queueing is a
deployment practice that predates this work; if the triggered arm cannot beat it
by more than noise, most of H1's gain is attributable to queue isolation rather
than to the kinematic trigger.

## 6. Model scope and honest limits

* **This is a SimPy discrete-event model, not ns-3.** No ns-3 binary is used.
  Channel parameters are stated in ns-3's vocabulary
  (`PointToPoint` / `Csma` / `Satellite` attribute tuples) so they are
  exportable, but the dynamics are flow-granular: no PHY, no CSMA contention, no
  ARQ, no TCP. Absolute latencies are model outputs, not predictions.
* **Attribution is clean.** Legitimate sources are drawn from rows 2-9, the
  botnet from the aggregation ring. A spoofed-source DDoS would defeat this
  controller exactly as it defeats FlowSpec. H1 is an upper bound.
* Retransmission is absent, so a link's packet error rate applies once per
  coalesced batch rather than once per fragment.
* Reordering is modelled as reassembly-buffer pressure from partial fragment-train
  admission, not as per-fragment arrival-order inversion.
* Traffic is coalesced into batches (one SimPy event carries several requests of
  one name from one source region). That is deliberate: the design mandate is not
  to micromanage individual packets.

## 7. Reproduction

```bash
py tools/benchmark_surgical.py --replicates 30
py tools/plot_surgical.py
py -m pytest tests/test_surgical.py -q
```

Results, including the refutations, are in
[`surgical-results.md`](surgical-results.md). Machine-readable output:
`output/surgical/{per_seed,summary,timeseries,verdict,failures}.csv` and
`figures/surgical_*.png`.
