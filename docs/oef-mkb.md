# OEF compensation and multidimensional baselining (M4)

**Status:** pre-registered before running the M4 experiments. Two additions to
the surgical controller, framed strictly as control theory; the biological
language is an analogy, not evidence.

## 1. OEF — the Fick-principle mapping (H5)

The brain keeps metabolic rate (CMRO2) constant when blood flow (CBF) falls by
raising the oxygen extraction fraction (OEF): `CMRO2 = CBF * OEF * Ca`.

| biology | network |
|---|---|
| CBF (cerebral blood flow) | delivered throughput of a link/node |
| Ca (arterial oxygen) | nominal capacity |
| CMRO2 (metabolic rate) | legitimate goodput |
| OEF (extraction fraction) | WFQ weight of the legitimate class |
| caffeine (CBF reducer) | the DDoS shockwave |

**Control law.** Each node measures CBF over a 1 s window and keeps an EMA
baseline (`oef_cbf_tau = 2 s`). When `CBF < 0.8 * EMA(CBF)` for three
consecutive ticks, the OEF actuator raises the legitimate (bulk) class's WFQ
weight `1 -> oef_max`, with `target = clip(oef_gain * CBF_deficit, 0, 1)`. The
change is rate-limited by a double integrator (`oef_speed_max = 0.5 /s`,
`oef_accel_max = 0.4 /s^2`), and the speed limit is logged when hit. Schmitt
hysteresis (engage after 3 low ticks, release after 5 high ticks) prevents
steady-state chatter. OEF is never hard-coded to 1; it is a function of the
measured CBF deficit.

**H5.** OEF-surgical maintains legitimate goodput (CMRO2) within 10 % of
baseline under a DDoS shockwave, while the standard surgical controller loses
more than 25 %.

## 2. MKB — multidimensional kinematic baselining

Network state is a vector `S(t) = [util, queue_delay, loss, OEF]` at each node.
Velocity `v = dS/dt` and acceleration `a = d^2S/dt^2` are the geometry of a
short-window (0.3 s) EMA manifold of `S`. A surgical edit is triggered when

1. `||a - EMA(a)|| > max(mkb_floor_a, k * EWMA(||a - EMA(a)||))`, or
2. the velocity vector turns more than `mkb_angle_deg = 45°` away from its
   EMA while both have magnitude above `mkb_floor_v`.

This replaces scalar thresholding with a threshold on the trajectory's geometry;
cross-correlations between dimensions (a simultaneous CBF drop and OEF demand)
become visible to the trigger.

## 3. Anti-cheat rules

1. OEF is computed from the CBF deficit, never hard-coded.
2. Rate limits are strict; the acceleration limit is enforced and a limit hit is
   logged.
3. The cost (transit drop rate / general-flow loss) is reported alongside any
   local gain.

## 4. Pre-registered failure modes

We expect, and commit to report if true:

* **The zero-sum trap.** On a pure forwarder (the congested node is the last
  router before a single-uplink origin, `alpha = 0`), the legitimate class
  already wins ~95 % of the link once the attack is isolated, so OEF has no
  further degree of freedom to extract. H5's contrast then fails because the
  baseline does not lose 25 % and OEF does not add to it.
* **Self-referential triggering.** The MKB state vector includes the OEF
  actuator's own output, so the vector trigger can detect the controller's own
  feedback as a spike, producing false positives.
