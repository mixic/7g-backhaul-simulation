# The mathematical problem of raw derivatives (why M3/M4 oscillated)

**Document status:** Theoretical foundation for M5.1 (H8), written before the
H8 experiment. The H8 verdict is recorded at the end and is **not** edited to
match this narrative.

## 1. Raw derivatives amplify measurement noise

In the discrete SimPy testbed a state `x_t` (for example an arrival rate) is
sampled at times `t`. The raw velocity and acceleration are finite differences:

```text
v_t = (x_t - x_{t-1}) / dt
a_t = (v_t - v_{t-1}) / dt = (x_t - 2 x_{t-1} + x_{t-2}) / dt^2
```

A real network never measures `x_t` perfectly. With additive measurement noise
`eps_t` (packet jitter), the observed value is `xhat_t = x_t + eps_t`. The
second difference divides the noise by `dt^2`, so for a millisecond-scale `dt`
the **variance of the raw acceleration explodes**.

**Consequence (role churn).** The controller reads that noise as a genuine
"DDoS spike", fires a surgical edit, observes on the next tick that it was only
noise, and reverses it. That is a limit cycle: the closed loop became unstable
because the gain on the unfiltered noise was too high.

## 2. EWMA is a first-order IIR low-pass filter

The Exponential Weighted Moving Average

```text
S_t = alpha * xhat_t + (1 - alpha) * S_{t-1},     alpha in (0, 1]
```

has the z-domain transfer function

```text
H(z) = alpha / (1 - (1 - alpha) z^-1)
```

It attenuates high frequencies (noise, jitter) and preserves low frequencies
(real trends, a DDoS shockwave). It introduces a small, controllable lag but
stops the loop from over-reacting to high-frequency noise.

## 3. The alpha-beta-gamma filter (a Kalman precursor)

Applying EWMA to the state **and** its velocity **and** its acceleration gives
an alpha-beta-gamma filter. With prediction, residual and update:

```text
prediction   xhat_{t|t-1} = x_{t-1} + v_{t-1} dt + 0.5 a_{t-1} dt^2
residual     r_t = x_t - xhat_{t|t-1}
update       x_t = xhat_{t|t-1} + alpha * r_t
             v_t = v_{t-1} + a_{t-1} dt + beta  * r_t / dt
             a_t = a_{t-1} + gamma * r_t / dt^2
```

`alpha`, `beta`, `gamma` weight how strongly the filter responds to the
prediction error. Keeping `gamma` (the acceleration weight) **small** heavily
smooths the raw acceleration: the loop only reacts to an acceleration change
that is consistent over several ticks, i.e. a genuine shockwave, not a single
noise sample.

The H8 benchmark implements the *two-EWMA form* of this idea — a separate EWMA
on the velocity and on the acceleration, without the prediction step — because
the full alpha-beta-gamma filter with a small `gamma` would also smooth away the
single-tick DDoS step (the testbed's shock is a step, not a ramp), leaving the
controller unable to detect it. The two-EWMA is therefore the practical
approximation used in the experiment.

## 4. Random Early Redirection as a stochastic damper

RER replaces the hard binary threshold with a probability:

```text
P(redirect) = max(0, (q_avg - q_min) / (q_max - q_min))
```

where `q_avg` is the EWMA-smoothed queue fill. When every node switches role at
exactly the same threshold (80 %), the network fires a synchronous burst — a
thundering herd. RER breaks that synchrony: one node redirects at 80 % with
10 % probability, another at 82 % with 20 %. The network responds gradually
instead of in discrete oscillating jumps, which raises the phase margin of the
loop and stabilises it.

## 5. The closed mathematical circle

The journey is, in control-theory terms, a rediscovery of classical signal
processing:

- **2010 (Gezora):** the instinct that raw states must be smoothed (EWMA) and
  that stochastic damping (RER) prevents instability.
- **2026 (M3/M4):** raw kinematic derivatives were tried instead. The noise
  variance of the second difference is too high, and the loop oscillates.
- **2026 (M5):** return to the roots — an alpha-beta-gamma filter (EWMA on
  kinematics) reduces the noise amplification, and RER breaks the synchrony.

## 6. What H8 actually measured

The H8 benchmark compares `m3_raw_1d` (scalar trigger), `m4_raw_4d` (raw vector
trigger) and `m5_ewma_mkb` (smoothed vector trigger + RER). The result, reported
honestly in [`results/m5/m5_summary.md`](../results/m5/m5_summary.md), is
**REFUTED** for the peak-burst clause:

- the peak state-change speed is **not** capped (223.9 vs 189.7 units/s for the
  raw 4D), because the peak is dominated by the *synchronous surgical edit* —
  one class promoted across ~15 routers in a single tick — which filtering only
  *lags*, it does not *bound*;
- RER engaged only 6 times across 30 seeds because the shock is a sharp step,
  so the pre-trigger band is crossed for almost no ticks.

The filtering theory in this document explains the **limit-cycle/churn** failure
mode, not the **synchronous-edit** peak. They are two different mechanisms; the
2010 intuition is a necessary, but not sufficient, part of the fix.
