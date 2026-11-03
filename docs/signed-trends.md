# Signed velocity and acceleration: releasing capacity when the flood recedes

**Status:** pre-registered claim, written before the experiment.

The dual-role controller currently uses only **positive** trend terms:

```text
serve_signal = w_p · pressure · hit
             + w_v · max(0, velocity) / v_ref
             + w_a · max(0, acceleration) / a_ref
```

Negative velocity and acceleration are discarded. That is deliberate for
commitment — a node should not abandon serving just because pressure dips —
but it also means a **receding flood** produces no release signal. The node
keeps serving capacity committed (high `α`) and therefore keeps forwarding
(`1 − α`, the load-balancing/proxy role) artificially small while the network
is recovering. A **signed** controller can use the negative trend to release
capacity back to forwarding earlier, i.e. to self-scale the role mix with the
load wave.

## 1. Falsifiable claim

> On a shaped flood that ramps up, plateaus and ramps down at `E2`, a
> signed-trend controller with asymmetric release gain (negative velocity and
> acceleration weighted twice as strongly as positive ones) delivers at least
> **2 percentage points more legitimate traffic to the unattacked target E3 in
> the flood's decay window** and recovers `E2`'s pre-flood `α` at least **15 %
> sooner** than the positive-only controller, while losing at most **1
> percentage point** of steady-state delivered goodput.

The claim is **refuted** if any of the three bounds fails. It is
**inconclusive** only if the model cannot produce the stipulated flood shape.

The 2 pp, 15 % and 1 pp thresholds are fixed here and are not adjusted after
the run.

## 2. Scenario: `flood_wave`

The existing `ddos` scenario is a step, so its trend is zero almost
everywhere. The new scenario is a trapezoid at `E2` (nominal demand 50 Mbps):

| Ticks | Attack at E2 | Trend |
|---|---|---|
| `[40, 55)` | ramps `0 → 250` Mbps | positive velocity, negative acceleration at start |
| `[55, 85)` | 250 Mbps | zero |
| `[85, 100)` | ramps `250 → 0` | **negative velocity** |
| `[100, 120)` | 0 | recovery |

The decay window is `[85, 105)`: the ramp-down plus the first recovery ticks.
All other demand and topology are unchanged from the frozen dual-role model.

## 3. Controller arms (all other parameters frozen)

| Arm | Trend terms | Release gain |
|---|---|---|
| `positive` | `max(0, v)` and `max(0, a)` | 1.0 (current controller) |
| `signed` | signed `v` and `a` | 1.0 |
| `signed_release` | signed `v` and `a` | 2.0 on negative terms |
| `separated` | fixed roles | — |

Twelve paired seeds. The controller update interval, damping, pressure term,
`α₀` and all network parameters stay at their frozen values.

## 4. Metrics

- **E3 decay delivery** — legitimate delivered volume to `E3` over ticks
  `[85, 105)`, as a percentage of legitimate offered volume in that window.
- **Recovery time** — ticks after the flood ends (`t = 100`) until `E2`'s `α`
  is within 0.05 of its pre-flood value (mean over `t ∈ [30, 40)`), capped at
  the end of the run.
- **Steady guard** — delivered goodput on the `steady` scenario (no flood),
  signed-release versus positive-only.

## 5. What this would and would not show

- A confirmed result would show that negative trend carries actionable
  information for **capacity release**, and that the role mix can self-scale
  down after a flood without hurting steady-state.
- It would **not** show a DDoS defence: the flood is stipulated and the node
  still cannot distinguish attack from legitimate demand. The previous
  classifier result stands.
- It would not close the RFMP loop; this is still a flow-level controller.
- A refutation would bound the usefulness of negative trend for this control
  problem: either the release is too small to matter, too slow, or it costs
  steady-state delivery through overshoot.
