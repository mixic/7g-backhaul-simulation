# Complex-Rotation Manifold Routing (CRMR): a mathematical specification

**Status: theoretical specification only.** This document defines CRMR and its
falsifiable hypothesis H15. It contains no implementation, no simulation and no
experimental result. Nothing here has been evaluated; it is a proposal for future
research and must not be cited as evidence. There is no `complex_router.py`, and
this specification does not authorise one.

CRMR is the continuous counterpart of the discrete dimension jump studied in the
T-NDN and DDMR work: instead of switching the forwarding metric between a calm
and a defensive state, the node state is a point in the complex plane that
rotates continuously under a damped control law.

## Notation

| Symbol | Meaning |
|---|---|
| $n$ | network node |
| $t$ | time |
| $\psi_n(t)$ | complex state of node $n$ |
| $R_n(t)\in\mathbb{R}_{\ge 0}$ | real component (baseline state) |
| $A_n(t)\in\mathbb{R}_{\ge 0}$ | imaginary component (anomaly state) |
| $\lvert\psi_n\rvert$ | magnitude (systemic pressure) |
| $\theta_n(t)$ | phase angle, the threat rotation |
| $\mu$ | rotation gain |
| $\gamma$ | damping factor |
| $\Phi_p$ | complex impedance of path $p$ |
| $\phi_p$ | phase of the path impedance |
| $\theta_{\mathrm{net}}(t)$ | network phase used for the FIB projection |

## 1. The complex state space

The state of node $n$ at time $t$ is a point in the complex plane,
\begin{equation}
\psi_n(t) = R_n(t) + i\,A_n(t), \qquad R_n(t)\ge 0,\; A_n(t)\ge 0 .
\label{eq:state}
\end{equation}

The real component $R_n$ is a function of stable telemetry: prefix stability,
nominal queue depth and baseline latency. The imaginary component $A_n$ is a
function of the kinematic anomaly score of the node: jitter, packet-drop
acceleration and the local DDoS signature. Both are normalised to a common,
dimensionless scale before they enter \eqref{eq:state}; the specification does
not fix that scale, and the calibration is part of any future implementation.

Two derived quantities carry the interpretation:

\begin{align}
\lvert\psi_n(t)\rvert &= \sqrt{R_n(t)^2 + A_n(t)^2}
   && \text{(total systemic pressure)}, \label{eq:magnitude}\\
\theta_n(t) &= \arctan\!\left(\frac{A_n(t)}{R_n(t)}\right)\in\left[0,\frac{\pi}{2}\right]
   && \text{(threat rotation)}. \label{eq:phase}
\end{align}

For $R_n=0$ and $A_n>0$ the phase is defined as $\pi/2$; for $A_n=0$ it is zero.
The unit phasor is $\hat\psi_n=\psi_n/\lvert\psi_n\rvert=\cos\theta_n+i\sin\theta_n$,
so the components are the projections
\begin{equation}
R_n=\lvert\psi_n\rvert\cos\theta_n,\qquad
A_n=\lvert\psi_n\rvert\sin\theta_n .
\label{eq:projections}
\end{equation}

The plane has a precise reading: the real axis is the calm, prefix-compatible
state, the imaginary axis is the anomaly-dominated state, and the angle $\theta_n$
is how far the node has rotated from calm toward anomaly.

## 2. The rotation dynamics

The state does not jump between states; it rotates. The phase evolves under the
first-order law
\begin{equation}
\frac{d\theta_n(t)}{dt} = \omega_n(t)
= \mu\bigl(A_n(t)-R_n(t)\bigr) - \gamma\,\theta_n(t),
\label{eq:rotation}
\end{equation}
with rotation gain $\mu>0$ and damping factor $\gamma>0$. The phase is clipped to
$[0,\pi/2]$; the clip is part of the model, not a numerical convenience.

\paragraph{Equilibrium and stability.}
For frozen telemetry the equilibrium of \eqref{eq:rotation} is
\begin{equation}
\theta_n^{*} = \operatorname{clip}\!\left(
\frac{\mu\bigl(A_n-R_n\bigr)}{\gamma},\,0,\,\frac{\pi}{2}\right).
\label{eq:equilibrium}
\end{equation}
Linearising \eqref{eq:rotation} around $\theta_n^{*}$ gives
$\dot{\delta\theta}_n=-\gamma\,\delta\theta_n$, so the equilibrium is
exponentially stable for every $\gamma>0$, with time constant $1/\gamma$. The
damping factor is therefore the term that prevents oscillation: the homogeneous
response is a decaying exponential, not a damped oscillation, and there is no
overshoot to chatter around. A larger $\mu$ reacts faster to the anomaly and
settles at a larger phase; a larger $\gamma$ slows the rotation and pulls the
equilibrium toward calm. The two parameters are not independent knobs: the
steady-state threat rotation is $\mu(A-R)/\gamma$, so the ratio $\mu/\gamma$ sets
the defensive posture and $\gamma$ sets the settling time.

\paragraph{Unitary evolution.}
Between control ticks the state is propagated by the unitary rotation
\begin{equation}
\psi_n(t+\Delta t)=\psi_n(t)\,e^{\,i\,\omega_n(t)\,\Delta t},
\label{eq:unitary}
\end{equation}
which preserves the magnitude, $\lvert\psi_n(t+\Delta t)\rvert=\lvert\psi_n(t)\rvert$,
and advances the phase by $\omega_n(t)\Delta t$. Equation \eqref{eq:unitary} is
the discrete form of $\dot\psi_n=i\omega_n\psi_n$.

\paragraph{Filtered phase versus measured phase.}
The definition \eqref{eq:phase} and the dynamics \eqref{eq:rotation} would
over-determine $\theta_n$ if both were applied to the same measured $R_n,A_n$.
The specification resolves this explicitly: the measured components
$R_n^{\mathrm m},A_n^{\mathrm m}$ supply the magnitude
$\lvert\psi_n\rvert=\sqrt{(R_n^{\mathrm m})^2+(A_n^{\mathrm m})^2}$ and the input
$A_n^{\mathrm m}-R_n^{\mathrm m}$ of \eqref{eq:rotation}; the phase $\theta_n$ is
the *filtered* control state produced by \eqref{eq:rotation}. The components used
downstream are the projections \eqref{eq:projections} of the filtered phase. This
is the only internally consistent reading, and it is the one stated here.

## 3. The complex FIB

A path $p$ is described by a complex impedance
\begin{equation}
\Phi_p = \lvert\Phi_p\rvert\,e^{\,i\phi_p},
\qquad
\lvert\Phi_p\rvert=\sqrt{R_p^2+A_p^2},
\qquad
\phi_p=\arctan\!\left(\frac{A_p}{R_p}\right),
\label{eq:impedance}
\end{equation}
where $R_p$ is the baseline cost of the path (prefix distance, nominal latency)
and $A_p$ is its anomaly penalty (measured jitter, drop acceleration, attack
signature). The router projects the impedance onto the real axis of the current
network frame:
\begin{equation}
\operatorname{Cost}_p(t)
= \operatorname{Re}\!\left(\Phi_p\,e^{-i\theta_{\mathrm{net}}(t)}\right)
= \lvert\Phi_p\rvert\cos\!\left(\phi_p-\theta_{\mathrm{net}}(t)\right).
\label{eq:cost}
\end{equation}

The selection rule is
\begin{equation}
p^{*}(t)=\arg\min_{p\,:\,\operatorname{Cost}_p(t)\;>\;0}\operatorname{Cost}_p(t),
\label{eq:select}
\end{equation}
with a small positive floor replacing the strict inequality in an implementation
and paths with non-positive projection excluded from the candidate set.

\paragraph{The two limits.}
At $\theta_{\mathrm{net}}=0$ the projection is
$\operatorname{Cost}_p=\lvert\Phi_p\rvert\cos\phi_p=R_p$: the router minimises the
baseline cost and recovers ordinary shortest-path routing. At
$\theta_{\mathrm{net}}=\pi/2$ the projection is
$\operatorname{Cost}_p=\lvert\Phi_p\rvert\sin\phi_p=A_p$: the router minimises the
anomaly penalty, so paths with a large imaginary component are dominated and
dropped from the candidate set. Between the limits the cost is a continuous
blend of the two, which is the formal content of the phrase "rotating the metric
rather than switching it".

A path is projected out when $\phi_p-\theta_{\mathrm{net}}$ leaves
$(-\pi/2,\pi/2)$: the cosine becomes non-positive and \eqref{eq:select} excludes
it. This is the precise mechanism behind the requirement that an attacked path
must not remain the least-cost egress.

## 4. Topological filtration

The persistent homology of the T-NDN plan is computed on the set of complex node
states $\{\psi_1(t),\dots,\psi_N(t)\}$ with the complex modulus as distance,
\begin{equation}
d(\psi_i,\psi_j)=\lvert\psi_i-\psi_j\rvert
=\sqrt{(R_i-R_j)^2+(A_i-A_j)^2}.
\label{eq:distance}
\end{equation}
For a scale $\varepsilon\ge 0$, the Vietoris--Rips complex
$\mathrm{VR}_\varepsilon$ contains the simplex on a subset $S$ of nodes whenever
every pair in $S$ is at distance at most $\varepsilon$. Its persistent homology
in dimensions zero and one, $\mathrm{PH}(\mathrm{VR}_\bullet)$, is the topological
signature of the fabric: $H_0$ counts connected components of the node cloud and
$H_1$ counts loops.

\paragraph{An invariance that must be stated.}
A *global* rotation of every node by the same angle, $\psi_n\mapsto e^{i\alpha}\psi_n$,
is an isometry of \eqref{eq:distance}: every pairwise distance is preserved and
every persistence diagram is unchanged. A uniformly rotating fabric therefore has
a constant topology even though its phase is changing. The mechanism can only
produce a topological change when the nodes rotate by *different* phases
$\theta_n$, i.e. when \eqref{eq:rotation} is driven by local telemetry and the
cloud deforms. This distinction is essential and is easy to lose.

\paragraph{The hole hypothesis.}
The proposal is that a cluster of nodes rotating toward the imaginary axis
($\theta_n\to\pi/2$) opens a void in the real-axis routing topology, which
appears as a persistent $H_1$ feature of the deformed cloud and can be routed
around. That statement is a *hypothesis*, not a theorem: it requires a
configuration in which the attacked nodes become a loop enclosing the calm
component, and it may fail for symmetric or low-dimensional configurations. It is
included because it is the topological reading of the mechanism, not because it
has been shown.

## 5. Falsifiable hypothesis H15

> **H15.** A continuous complex rotation controller will maintain a Content
> Delivery Rate (CDR) at least 10 % higher than a discrete state-jump controller
> under DDoS, due to the damping factor $\gamma$ preventing oscillation.

The hypothesis is testable, and the protocol is fixed here rather than after the
measurement:

1. **Arms.** A discrete state-jump controller and the CRMR controller, with the
   same anomaly detector, the same instances, the same request stream and the
   same attack. The discrete arm is the control: if the gain survives against it,
   the rotation is doing the work; if not, it is not.
2. **Primary endpoint.** Legitimate CDR in the attack windows: the delivered
   fraction of legitimate requests. "10 % higher" is read as a relative gain,
   $\mathrm{CDR}_{\mathrm{CRMR}}\ge 1.10\cdot\mathrm{CDR}_{\mathrm{discrete}}$,
   on the paired-seed mean.
3. **Mechanism endpoint.** The oscillation that $\gamma$ is supposed to suppress
   must be measured, not assumed: the number of phase reversals or direction
   changes of the routing state per unit time, and the variance of the phase
   trajectory. A CDR gain without a reduction in oscillation does not support the
   stated causal claim.
4. **Refutation.** H15 is refuted if the CDR gain is below 10 %, if the damping
   does not reduce the measured oscillation relative to the discrete controller,
   or if the gain is attributable to a difference in detection latency or traffic
   rather than to the rotation. A positive CDR result with an unchanged
   oscillation metric is a refutation of the *explanation* even if the number
   looks good.

No part of H15 has been tested. The hypothesis is stated with the 10 % threshold
specified here; it is not a result.

## 6. Relation to the existing work and open questions

\paragraph{Relation.}
T-NDN fixes a static name metric; DDMR changes the dimension of that metric in a
discrete jump with hysteresis; CRMR makes the state a point of $\mathbb{C}$ and
rotates it continuously under \eqref{eq:rotation}. The complex FIB \eqref{eq:cost}
is a strict generalisation of a real cost: at $\theta_{\mathrm{net}}=0$ it is the
baseline cost, and the real routing plan is recovered as a special case.

\paragraph{Open questions.}
The following are unresolved by construction:

1. **Parameter identification.** $\mu$ and $\gamma$ are not measurable from the
   model; their ratio fixes the posture and $1/\gamma$ the settling time. A
   deployment must estimate both.
2. **Over-determination.** The filtered-phase reading in §2 is a modelling choice;
   alternatives (drive the components directly, or evolve the phasor without
   telemetry re-anchoring) give different dynamics and must be compared before
   any claim is made.
3. **Topology.** The hole hypothesis of §4 is unproven, and the global-rotation
   invariance means a uniform controller has no topological effect. Node-local
   phases are a requirement, not a detail.
4. **Projection loss.** The four-dimensional state of DDMR is compressed to the
   two coordinates $(R,A)$; the compression discards latency and jitter
   separately. Whether the loss matters is untested.
5. **Distributed consistency.** $\theta_{\mathrm{net}}$ is a network-level phase
   used in \eqref{eq:cost}; how nodes agree on it without a central controller is
   unspecified.
6. **Energy and cost.** The complex FIB and the topological filtration have a
   computational cost that no part of this document bounds.
7. **Evidence.** There is none. This is a specification.

## References

- H. Edelsbrunner, D. Letscher and A. Zomorodian, "Topological Persistence and
  Simplification", *Discrete & Computational Geometry* 28(4), 2002, DOI
  [10.1007/s00454-002-2885-2](https://doi.org/10.1007/s00454-002-2885-2).
- L. Zhang et al., "Named Data Networking", *ACM SIGCOMM Computer Communication
  Review* 44(3), 2014, DOI
  [10.1145/2656877.2656887](https://doi.org/10.1145/2656877.2656887).
