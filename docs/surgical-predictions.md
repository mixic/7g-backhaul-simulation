# Surgical and savant state updates: frozen predictions (M3 input)

**Status:** FROZEN — written before any M3 experiment ran. This file is the
pre-registration for the executable models in
[`simulation/surgical/`](../simulation/surgical/) and
[`simulation/savant/`](../simulation/savant/). If a measurement contradicts a
prediction, the prediction is recorded as refuted and the code is **not** tuned
to force a pass.

## 1. State plane

A node's editable state is the vector `S = (alpha, queue policy, FIB overrides)`:

* `alpha in [0, 1]` — role fraction. `0` = pure router/balancer, `1` = pure
  cache/server. Forwarding capacity is `(1 - alpha) C_n`, serving capacity is
  `alpha C_n` (with a 2 % forwarding floor so a node at `alpha = 1` still drains
  keepalive traffic).
* queue policy — per-class weighted-fair-queueing weight and per-class byte
  limit (class = one `(content name, source region)` pair).
* FIB overrides — per-flow next hop layered over the loop-free name table
  (NDN-style name-based forwarding; no IP, no DNS).

Every mutation passes through `StateLedger`, which is the single place where
state-change speed `|dS|/dt` and acceleration `|dspeed|/dt` are computed.

## 2. Observation layer

Per node, normalised pressure (the vision paper's quantity):

```
p(t) = clip(0.70 u + 0.20 q/(d+q+1) + 0.10 loss, 0, 1)
```

with `u` utilisation, `q` queueing delay, `d` base delay, `loss` drop ratio.
Velocity `v = dp/dt` and acceleration `a = d^2p/dt^2` are computed by finite
difference from the raw per-tick pressure samples. The surgical package also
carries an `ArrivalAccelerometer` that derives `a` directly from raw arrival
timestamps, because the anti-cheat rule forbids computing the second derivative
from smoothed averages.

## 3. Baselines (what must be beaten)

| arm | label | behaviour |
|---|---|---|
| Baseline A | `k8s` | static roles (edge `alpha=1`, transit `alpha=0`), slow central scaling |
| Baseline B | `vdr` | spatial gradient descent: a pressure-weighted loop-free potential (flux field) ignores temporal acceleration entirely |
| Baseline C | `pressure` | the previous iteration's naive kinematic controller: global, reactive, oscillatory |

## 4. Surgical controller (the temporal control law)

1. **EMA monitor** — exponentially weighted baselines of `v` and `a`.
2. **Spike trigger** — an edit fires only when `|a - EMA(a)| > threshold`, where
   `threshold = max(floor, k * EWMA(|a - EMA(a)|))` and `k = 4`.
3. **Rate limiter (the "mass")** — the rate of change of `alpha` and of FIB
   entries is bounded: `Max_State_Change_Speed = 0.35` normalised units/s and
   `Max_State_Change_Acceleration = 0.60` units/s^2. Discrete edits (one FIB
   entry, one class promotion) spend a per-node token bucket with burst 2.2
   units; continuous knobs (`alpha`, buffer scale) move through a double
   integrator.
4. **Locality** — the surgical edit changes only the specific flow's FIB entry
   and queue class, never the node's global `alpha` distribution.
5. **Hysteresis** — release is a pressure test (not an acceleration test) and
   requires the culprit class's arrival rate to have stopped for five ticks.

## 5. VDR interface (spatial target -> temporal actuator)

Baseline B computes a **target flux field** only. The surgical/savant controllers
do not compute a competing field; they govern the **transition** to any supplied
target. The interface is therefore:

```
target_field = VDR.compute_potential(pressure)   # spatial, loop-free
SurgicalActuator.apply(target_field, speed_cap, accel_cap)   # temporal
```

The composability test holds the target constant and varies only the actuation
speed. On a topology with a single-uplink origin the target field is empty
(no admissible loop-free alternative), which is itself a recorded result, not an
implementation gap to be hidden.

## 6. Savant controller (compensatory hyper-specialisation)

| parameter | value | meaning |
|---|---|---|
| `savant_alpha` (gain) | swept over `{0.50, 0.70, 0.85, 0.95, 0.99}` | the extreme `alpha` target |
| `savant_weight` | 1.0 | the affected class gets full WFQ weight |
| `savant_limit` | 0.60 | the affected class's byte-limit fraction |
| `savant_hold` | 3.0 s | minimum hold once triggered |

On a spike the node sheds general transit (drives `alpha -> savant_alpha` through
the same double integrator), gives the affected class top priority, and the
`StarvationLogger` counts every packet of **other** flows dropped at that node
while savant mode is active. The savant edit is node-local; it does not propagate
to other nodes unless Baseline B's rerouting explicitly moves traffic in response
to the induced failure.

## 7. Hypotheses (frozen)

**H1 — the surgical advantage.** Under a 10 s DDoS shockwave on one content name,
the surgical arm holds p95 latency `<= 1.5x` baseline and legitimate goodput
`> 95 %`, while the global pressure controller (Baseline C) exceeds `2.2x` p95 and
loses `> 10 %` goodput. *Refuted if any clause fails.*

**H2 — rate control versus churn.** Capping the speed and acceleration of state
changes prevents role oscillation without sacrificing responsiveness. Measured by
`State_Change_Speed` and `State_Change_Acceleration` time series: Baseline C is a
seismograph; the surgical arm is flat with single spikes per edit.

**H3 — the medium boundary.** Surgical edits localised at a fiber-to-satellite
boundary prevent reassembly deadlock caused by MTU mismatch. Measured by
`Reordering_Buffer_Occupancy` and `Fragment_Drop_Rate` under the four layer
orderings of the layering predictions (`C->F`, `F->C`, `E->F`, `F->E`), with real
AES-GCM authentication (`cryptography`), not dummy hashes.

**H4 — the savant trade-off.** Under an attack 10x normal, savant rewiring
maintains higher affected-name delivery than Baseline A and Baseline B, at the
measured cost of general-flow delivery and a cascading-failure rate in the rest of
the network. The trade-off has a threshold in `savant_alpha`.

## 8. Experiments (30 paired seeds)

| experiment | arms | KPIs written to CSV |
|---|---|---|
| 1 — shockwave (H1, H2) | A, B, C, surgical | `Goodput_Legitimate`, `p95_Latency`, `State_Change_Speed`, `State_Change_Acceleration` |
| 2 — savant trade-off (H4) | surgical, savant | `Affected_Flow_Delivery`, `General_Flow_Delivery`, `Cascading_Failure_Rate` |
| 3 — boundary (H3) | layer orderings | `Reordering_Buffer_Occupancy`, `Fragment_Drop_Rate` |

## 9. Anti-cheat rules (binding)

1. **No tuning.** If the surgical controller fails to hold 1.5x, the negative
   result is logged and the EMA windows and thresholds are left untouched.
2. **Real cryptography.** Experiment 3 uses AES-GCM from the `cryptography`
   library. No dummy hashes or hand-rolled ciphers.
3. **Real acceleration.** The second derivative is computed from raw arrival
   timestamps, never from smoothed averages.
4. **Isolation.** Savant mode does not leak to other nodes unless routing
   explicitly reroutes traffic because of the induced failure.
