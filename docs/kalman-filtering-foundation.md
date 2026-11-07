# Theoretical Foundation: Kalman Filtering and Its Correlation to Rate-Controlled Network State Estimation

**Document Status:** Theoretical justification (written post-M7; the empirical
verdicts of M5/M6/M7 are recorded at the end and are **not** edited to match the
narrative).
**Reference Literature:** Grewal, M. S., & Andrews, A. P. (2001). *Kalman
Filtering: Theory and Practice Using MATLAB* (2nd ed.). John Wiley & Sons.
**Project Context:** 7G-Backhaul-Simulation (Surgical, Rate-Controlled
Multicooperative Backhauls).

> **Peer-reviewed.** This document was revised after a peer review (see
> [`kalman-filtering-peer-review.md`](kalman-filtering-peer-review.md)). Two
> corrections matter most: (1) the full α-β-γ filter was *attempted and reverted*
> in M5.1, so the shipped controller is the two-EWMA form, not α-β-γ; and (2) the
> original "Riccati cost" argument for avoiding the full Kalman filter was
> quantitatively wrong under the project's own energy model — the CPU cost of even
> a full 4-D Kalman filter is negligible next to one surgical edit. The honest
> reasons for not shipping the full filter are *statistical*, not computational.

---

## 1. Executive Summary

This document establishes the theoretical correlation between the classical
Kalman Filter framework and the network control mechanisms implemented in the
`7g-backhaul-simulation`.

The historical evolution of the controller design — the 2010 Gezora EWMA, the
M5 kinematic smoothing, and the Multidimensional Kinematic Baselining (MKB) — is
**not** a series of ad-hoc heuristics, but a family of *steady-state* and
*state-space* estimators closely related to the Kalman Filter.

We also give a rigorous justification for **not** implementing the full,
covariance-propagating Kalman Filter in the testbed. Crucially, and unlike an
earlier draft of this document, that justification is **not** the CPU energy of
the Riccati recursion — under the stipulated M6 energy model that cost is
negligible. The real reasons are the *statistics* of the DDoS signal: it is a
non-Gaussian step, and the process/measurement noise pair `(Q, R)` has no
stationary ground truth to tune against.

> **Honesty note (kept deliberately prominent).** The elegance of the Kalman
> correspondence did **not** translate into empirical wins in this project.
> H8 (EWMA smoothing caps the burst) was **refuted**, H9 (EWMA saves churn energy)
> was **refuted**, and M7 (dual-band LPF+HPF detection) was **refuted** on false
> positives. The theory explains *why the filters behave the way they do*; it does
> not make them win. Both halves are reported.

## 2. Core Concepts of the Kalman Filter

According to Grewal & Andrews, the Kalman Filter is the minimum-variance
estimator for a linear dynamic system driven by white noise. It alternates two
phases:

1. **Prediction (time update):** the state-transition matrix Φ projects the
   state estimate x̂ and its covariance P forward in time.
2. **Update (measurement update):** the Kalman gain K corrects the prediction
   using the noisy measurement z and the measurement matrix H.

The model is:

```text
state:        x_k = Φ_{k-1} x_{k-1} + w_{k-1}     (process noise w ~ N(0, Q))
measurement:  z_k = H_k x_k + v_k                 (measurement noise v ~ N(0, R))
```

The gain is `K = P^- H^T (H P^- H^T + R)^-1`, and the covariance obeys the
discrete algebraic Riccati equation (DARE). When `Q` and `R` are constant and the
system is time-invariant, the gain converges to a **fixed point** — the
steady-state Kalman filter.

## 3. Direct Correlation to the 7G-Backhaul-Simulation

### 3.1. The 2010 Gezora Connection: EWMA as a 1-D Steady-State Filter

In 2010 the Gezora architecture smoothed server load with an EWMA:

```text
S_t = α x_t + (1 − α) S_{t−1}
```

**Theoretical correlation (exact).** For the scalar random-walk model
(`Φ = 1`, `H = 1`), the steady-state Kalman filter is *algebraically identical*
to the EWMA. Substituting the fixed gain `K` into the update gives

```text
x̂_k = x̂_{k−1} + K (z_k − x̂_{k−1}) = (1 − K) x̂_{k−1} + K z_k,
```

which is the EWMA with `α = K`. The fixed gain is the positive root of the
scalar DARE,

```text
P = (P + Q) − (P + Q)² / (P + Q + R),
```

so `α` is a monotone function of the noise ratio `q = Q / R` (process variance to
measurement variance). The 2010 intuition was therefore formally correct: the
EWMA *is* the optimal steady-state estimator for a random walk observed in
noise, and its single tunable `α` is the Kalman gain in disguise.

### 3.2. The M5 Connection: α-β-γ as a Steady-State Constant-Acceleration Filter

The α-β-γ filter is, in the standard literature, the steady-state Kalman filter
for a **constant-acceleration** state model: `α`, `β`, `γ` are the fixed gains
for position, velocity and acceleration respectively.

**Theoretical correlation (exact, but see the factual caveat).** The prediction /
residual / update loop

```text
prediction   x̂_{k|k−1} = x_{k−1} + v_{k−1} dt + ½ a_{k−1} dt²
residual     r_k = x_k − x̂_{k|k−1}
update       x_k = x̂_{k|k−1} + α r_k
             v_k = v_{k−1} + a_{k−1} dt + β r_k / dt
             a_k = a_{k−1} + γ r_k / dt²
```

is the steady-state predictor–corrector for the constant-acceleration model. It
solves the noise-amplification problem of raw derivatives (see
[`kinematics-filtering.md`](kinematics-filtering.md)) by estimating the
derivatives *jointly* instead of finite-differencing the noisy measurement.

**Factual caveat (recorded honestly).** In M5.1 the *full* α-β-γ filter was
implemented, tested, and **reverted** — with a small `γ` it smooths away the
single-tick DDoS step (the shock is a step, not a ramp) and the controller fired
zero edits. The controller that shipped and ran the H8 benchmark is the
**two-EWMA form** (a separate EWMA on the velocity and on the acceleration, no
prediction step). H8 itself was **refuted** for its peak-burst clause: the
synchronous surgical edit dominates the burst, and smoothing only *lags* the
trigger, it does not *bound* the edit. The Kalman correspondence is correct; the
empirical outcome is not what the theory would naïvely promise.

### 3.3. MKB as a Multidimensional State-Space Formulation

MKB tracks a 4-D state vector

```text
S(t) = [CBF, OEF, Queue_Depth, Drop_Rate]
```

and declares a spike when the *geometry* of the trajectory
(`‖A − EMA(A)‖ > k · EMA(‖A − EMA(A)‖)`, or an angle test) deviates from its
moving-average manifold.

**Theoretical correlation (partial, stated precisely).** This is a **state-space
formulation** of congestion dynamics, and Grewal & Andrews note that state
variables can be augmented with derivatives of other state variables (§2.7). It
is **not**, however, a Kalman filter: MKB does not propagate a covariance, and
its "baseline" is an EMA of the residual magnitude, not a Riccati-derived gain.
Calling it a state-space model is accurate; calling it "the Kalman state vector"
would overstate it.

## 4. Why the Full Kalman Filter Is Not Implemented

The full, covariance-propagating Kalman filter is deliberately *not* shipped.
The reasons below are the **statistical** ones. An earlier draft also claimed the
matrix-Riccati CPU cost was prohibitive; that claim is withdrawn (see §4.1).

### 4.1. (Withdrawn) The Riccati Cost — *not* a reason

The earlier claim — that solving the DARE at `O(n³)` per node per tick would make
`E_cpu` "catastrophically exceed" the churn savings — is **quantitatively wrong**
under the project's own stipulated energy model (`simulation/energy.py`):

```text
E_cpu  = 1e-9 J/cycle      E_churn = 5.0 J/edit
```

For the 4-D state used here, the Riccati/covariance update is `O(4³) ≈ 64`
multiply-adds, a few hundred cycles per node per tick. Over a 60 s run
(100 nodes × 300 ticks) that is on the order of `10⁷` cycles ≈ **0.01 J** of CPU.
A single surgical edit costs **5 J** — about three orders of magnitude more than
the *entire* run's Kalman covariance arithmetic. The Riccati recursion is cheap;
it is not the reason.

The error is instructive and is kept here (withdrawn, not deleted) so the
revision is auditable: a plausible-sounding `O(n³)` argument collapsed on contact
with the actual numbers. Energy-aware design must be checked against the
stipulated model, not asserted.

### 4.2. The Gaussian Assumption (Chapter 3.2)

The Kalman filter is the *minimum-variance linear* estimator for **any** noise;
it is the *conditional-mean* (fully optimal) estimator only under Gaussian noise.
DDoS traffic violates Gaussianity: it is **heavy-tailed** and step-like (a sudden
saturated arrival rate), not a zero-mean random walk. Under such noise the filter
remains a linear estimator but loses its optimality guarantee, and its
innovations are dominated by the shock rather than by the noise it was tuned for.

**Correction to the earlier draft.** Non-Gaussian *noise* does **not** require an
Extended Kalman Filter. The EKF exists for *non-linear dynamics or measurement
models* (Grewal & Andrews ch. 5, 7.4). The network state model here is linear;
the problem is the noise distribution, not the model linearity. The correct
statement is: "the full filter is optimal under Gaussian noise, and DDoS noise is
non-Gaussian, so the optimality guarantee does not apply" — not "an EKF is
required."

### 4.3. Parameter Ambiguity (Chapter 7)

Tuning the `Q` and `R` matrices requires stationary ground truth for the process
and measurement noise. A DDoS shockwave is non-stationary by construction, so any
`(Q, R)` fitted to the baseline is wrong the moment the attack starts. The
steady-state approximations (EWMA, two-EWMA, dual-band) expose one or two
*robust* tuning knobs (`α`, the k-sigma multiplier, the fixed threshold) whose
behaviour degrades gracefully, instead of a covariance that can silently
diverge.

## 5. The M7 Dual-Band Filter as an Innovation Detector

The dual-band filter ([`simulation/filters.py`](../simulation/filters.py)) is the
same idea decomposed differently:

```text
LPF(t) = α · raw(t) + (1 − α) · LPF(t−1)      (steady-state random-walk estimate)
HPF(t) = raw(t) − LPF(t)                       (the innovation / residual)
trigger ⇔ HPF(t) > k · σ(HPF) and LPF stable
```

The LPF is the §3.1 steady-state Kalman estimate; the HPF is its **innovation**
(the measurement minus the prediction, where the "prediction" is the lagging LPF);
and the trigger is an innovation-based change detector with a k-sigma gate. This
is, again, not a full Kalman filter (no covariance, no gain update), but it is
the same estimator family.

The empirical result (M7) is that this detector is **too sensitive** to Poisson
jitter — 115 false positives over 30 seeds, more than a fixed-threshold LPF —
which is itself consistent with §4.2: the innovation of a non-Gaussian,
heavy-tailed arrival process is not well-described by a Gaussian k-sigma gate.
The theory predicts *why* the dual-band is fragile; the experiment confirms it.

## 6. Conclusion and Scientific Contribution

The `7g-backhaul-simulation` does not invent a new filter. It applies
steady-state and state-space estimation theory to the specific problem of 7G
backhaul survivability, and it *measures* the results rather than assuming them.

The honest scientific contribution is therefore twofold:

1. **A correct correspondence.** The 2010 EWMA and the M5 kinematic smoothers are
   recognized as steady-state Kalman estimators (random-walk and
   constant-acceleration models), and the M7 dual-band filter as an
   innovation-based change detector. This is rigorous, and it is retained.
2. **A refutation of the "filter = win" assumption.** The empirical record —
   H8 refuted (peak not capped), H9 refuted (EWMA does not save churn energy),
   M7 refuted (dual-band false positives) — shows that estimator *elegance* does
   not by itself buy robustness against a synchronous, step-like DDoS. The
   steady-state filters are necessary, not sufficient.

The decision not to implement the full Kalman filter is therefore **not** an
energy optimization (the CPU cost is negligible); it is a *statistical* judgment:
against a non-Gaussian, non-stationary shock, a full covariance-propagating
filter buys no robustness that its steady-state relatives lack, and it adds two
untunable matrices `(Q, R)` that have no stationary ground truth.

The correlation between our 2010 EWMA, the M5 ABG filter, and the Kalman Filter
framework is mathematically precise. However, the empirical M4 and M6 results
dictate a strict boundary on this theory. The central insight of this work is
that biologically-inspired and fluid-dynamic control laws face a hard
mathematical floor in discrete packet networks. While continuous control (EWMA,
Kalman, Fick's Principle) is mathematically elegant, the zero-sum and quantized
nature of finite packet buffers means that a simple, static per-flow isolation
mechanism consistently outperforms continuous biological compensation in both
goodput and energy efficiency. We identify the discrete packet boundary as the
fundamental limit of bio-inspired network control.

## 7. Cross-references

- [`kinematics-filtering.md`](kinematics-filtering.md) — raw-derivative noise,
  EWMA as IIR low-pass, the α-β-γ filter, RER, and the H8 record.
- [`../simulation/energy.py`](../simulation/energy.py) — the stipulated energy
  model used in §4.1.
- [`../results/m5/m5_summary.md`](../results/m5/m5_summary.md) — H8 verdict.
- [`../results/m6/m6_summary.md`](../results/m6/m6_summary.md) — H9/H10/H11
  verdicts.
- [`../results/m7/m7_summary.md`](../results/m7/m7_summary.md) — H13/H14
  verdicts.
