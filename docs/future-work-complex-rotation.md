# Future work: Complex-Rotation Manifold Routing (CRMR)

**Status: proposal, now implemented and evaluated for the CRMR paper.**
This document remains the *conceptual sketch* for H15. The implementation is
`simulation/crmr.py` with the scenario in `simulation/crmr_scenario.py`, the
frozen protocol is [`crmr-predictions.md`](crmr-predictions.md), and the
measurements are in [`paper-crmr.tex`](paper-crmr.tex) (compiled as
`paper-crmr.pdf`) and `figures/crmr_*`. Nothing in this document is itself a
measurement; the paper is where the numbers live. The earlier instruction to
defer the implementation was superseded by a direct commission to write the
CRMR paper, and the deferral is recorded in §7 for the history.

The idea follows M11: DDMR changed the filtration dimension by a discrete jump
(1 → 4) with hysteresis. That worked in the frozen scenario, but a switch is
still a switch. A continuous phase rotation is the natural next question. This
document exists so the idea is written down and not lost, and so it does not
displace the work that has to come first.

## 1. Motivation

M11's own results show the shape of the problem:

- the dimension expanded at 30.22 s and collapsed at 50.3 s on average, 5–7 s
  after the attack ended, because the anomaly uses a 5 s window;
- one seed in 30 expanded 1.5 s early on a Poisson fluctuation;
- the discrete controller needed `UP_TICKS`/`DOWN_TICKS` hysteresis precisely
  because an instantaneous threshold would chatter.

A continuous controller replaces the hysteresis with dynamics: the metric space
can rotate toward the defence axes while the attack develops and rotate back
while it decays. Whether that is actually better is an open empirical question,
not an assumption. The M11 negative lesson also applies: a smoother mechanism is
not automatically a better one.

## 2. The state and the rotation

The M11 state vector is `S(t) = [D_prefix, L_latency, J_jitter, A_anomaly]`.
Define a complex phasor

```
ψ(t) = R(t) · e^{i θ(t)},      θ ∈ [0, π/2],   R ≥ 1
```

where

- `θ(t)` is the **phase** between calm and defence: `θ = 0` means the real axis,
  a prefix-only metric; `θ = π/2` means the imaginary axis, the full defensive
  metric. Intermediate angles are mixtures, which is the point of the design.
- `R(t)` is the **amplitude**: the confidence/severity of the defensive posture.
  It scales the phase penalty in the FIB (see §5), not the point cloud.

A second-order rotation with damping is the minimum model that can be stable:

```
θ̈(t) + 2 ζ ω θ̇(t) + ω² (θ(t) − θ*(t)) = 0
θ*(t) = (π/2) · σ((A(t) − A₀) / s)
|θ̇(t)| ≤ ω_max
```

with `ζ ≥ 1` (no overshoot), `σ` a logistic or clipped-linear map, and
`A(t)` the same local anomaly the M11 detector already produces. There is no
`if t == 30` and no threshold on the clock: the target phase is a function of
the anomaly only. `R(t)` follows a first-order law, `Ṙ = (R* − R)/τ_R`, with
`R* = 1 + ρ·clip(A, 0, 1)`.

**A rigid rotation of the point cloud does nothing.** If every point were
mapped to `e^{iθ}·z`, all pairwise distances would be preserved and every
persistence diagram would be identical. The rotation must act on the *metric*,
not on the points, or the mechanism is vacuous. This is the first thing a CRMR
implementation would have to get right, and it is why the sketch below is a
metric family and not a complex embedding of the names.

## 3. Hypothesis H15 (draft thresholds, superseded by the frozen protocol)

> Under a *flapping* attack, a phase-continuous rotation of the filtration metric
> (CRMR) reduces control-state churn and CDR variance relative to discrete DDMR,
> while keeping the legitimate CDR within 2 percentage points of DDMR and
> satisfying the same energy clause as M11.

Proposed falsification criteria (to be frozen before any implementation):

1. **Churn.** Total variation of the phase, `TV(θ) = Σ|θ(t+Δt) − θ(t)|`, and the
   number of dimension/phase switches per minute, must both fall by **≥ 30 %**
   against DDMR under the same flapping attack.
2. **CDR.** Mean legitimate CDR in the attack windows must be **no more than 2
   points below** DDMR (not merely "better than static T-NDN").
3. **Variance.** The per-cycle CDR variance must fall by **≥ 30 %**; a smoother
   controller that does not reduce the cycle-to-cycle spread has not achieved
   the stated goal.
4. **Energy.** The 4-D homology cost must stay below the energy saved by the
   prevented losses, using the same break-even reporting as M11. A phase
   controller that recomputes on every θ change can lose this clause by
   construction.

H15 is refuted by failing any one criterion. It is not enough to be smoother.

## 4. The metric family

For a phase `θ`, weight the axes by

```
d_θ(a, b)² = cos²θ · d_prefix(a, b)²
           + sin²θ · (w_L·d_L² + w_J·d_J² + w_A·d_A²)
```

At `θ = 0` the metric is the M10 prefix metric; at `θ = π/2` it is the full
defence metric of M11; between them the axes are blended continuously. For a
fixed `θ` this is an ordinary real weighted Euclidean metric, so the Vietoris–
Rips filtration is standard and `ripser` computes it. **No complex persistence
theory is needed.** The complex number is a compact control representation of the
pair `(R, θ)`, not a new homology. This is the feasibility argument: CRMR would
reuse the M11 pipeline with a different, smoothly varying `θ` schedule.

The persistence diagrams are not invariant to `θ` (unlike a rigid rotation): the
weights change, the edges change, and the diagrams change. The phase is therefore
a genuine parameter of the topology.

## 5. Routing sketch (not implemented)

- Each FIB entry carries a complex weight `w_e = R_e·e^{iφ_e}`: the cluster
  centroid's phase and amplitude.
- A request has a phasor `ψ` from its flow's phase. The cost of an egress is
  `|arg(w_e) − arg(ψ)|` weighted by `1/R_e`, i.e. a phase-misaligned egress is
  penalised smoothly instead of being switched off.
- The attack component is the component whose mean phase is furthest from the
  calm axis; legitimate traffic is routed to the nearest phase-aligned egress.
- A backup next hop is selected for the phase-opposite neighbour, the continuous
  analogue of the M11 loop-free alternate.

This is a design sketch. Complex FIB weights may turn out to be a reparameter-
isation of real costs; showing a behavioural difference is part of the work, not
an assumption.

## 6. Planned experiment (not run)

- **Attack.** The M11 DDoS (block 0, 500 requests/s, 40 % of legitimate traffic)
  but **flapping**: 4 s on / 4 s off, five cycles inside the 60 s run, so the
  controller sees the edges that the discrete version chatters on.
- **Arms.** Static T-NDN, discrete DDMR (M11), CRMR. Same anomaly detector,
  instances, requests and energy model for all three.
- **Metrics.** `TV(θ)` and switches/minute; legitimate CDR per attack window and
  its variance across cycles; recovery time after each on/off edge; p95; 4-D
  CPU and the M11 break-even energy per prevented loss.
- **Pre-registration.** Thresholds in §3 frozen in `docs/crmr-predictions.md`
  before the first implementation line, exactly as M10/M11 did it.
- **Expected outcome is genuinely open.** A damped rotation may be slower to
  react than a hysteresis switch, and the metric blend may be a no-op on the
  CDR at a lower energy cost. Either result is publishable as a boundary.

## 7. Status of the deferral

The original plan was to defer CRMR until P8–P12 and papers A and B were final.
The state of this repository is:

1. **P8–P12 are complete.** `docs/layering-real-stack-results.md` reports all
   twelve cases confirmed with 20 runs per case, and the raw outputs are
   committed under `validation/real_stack/results/`.
2. **The two papers are final** (A: `paper-layering-testbed.md`, B:
   `paper-bio-control-limits.md`), and A already carries the epilogue that
   points to this file.
3. **The CRMR paper was then commissioned explicitly**, which is what
   superseded the deferral. The implementation and evaluation followed the
   frozen protocol in [`crmr-predictions.md`](crmr-predictions.md): a pilot on
   seed 2026 fixed the thresholds, and the evaluation uses seeds 2030–2059.

The pilot revised the sustained CDR guardrail from the 2 points drafted in §3
to 5 points, because the rotation's settling time costs about three points even
under a sustained attack; that revision is recorded in the frozen protocol
before the evaluation run. The flapping CDR gap was declared a measured
boundary, not a pass criterion.

## 8. Risks and open questions

1. **Continuity is not automatically stability.** A damped second-order phase
   can still oscillate if `ζ` or `ω` is chosen badly, and the anomaly signal
   itself is noisy.
2. **The axis blend may be observationally equivalent to DDMR** for some θ
   trajectories; an ablation is needed to show that the continuous family does
   something the discrete jump cannot.
3. **Complex FIB weights may collapse to real costs.** If the argmin of the
   phase penalty always equals the argmin of the real cost, the FIB part is
   decoration.
4. **Energy.** Recomputing ripser at every θ epoch is more expensive than two
   discrete states; the break-even may fail even if churn falls.
5. **The H1 question is unchanged.** M11 found H1 loops in 8.2 % of shock
   epochs; CRMR does not promise persistent holes either.
6. **No proof.** Nothing here is proved; the continuity argument is a hypothesis.

## 9. Relationship to the milestones

- M10 (`docs/tndn.md`): static name-space topology, fixed 1-D filtration.
- M11 (`docs/ddmr.md`): discrete 1 → 4 dimension shift with hysteresis.
- CRMR (this document): continuous rotation of the same metric family; H15; not
  tested.

## References

- Edelsbrunner, Letscher and Zomorodian, "Topological Persistence and
  Simplification", *Discrete & Computational Geometry* 28(4), 2002, DOI
  [10.1007/s00454-002-2885-2](https://doi.org/10.1007/s00454-002-2885-2).
- Zhang et al., "Named Data Networking", *ACM SIGCOMM Computer Communication
  Review* 44(3), 2014, DOI
  [10.1145/2656877.2656887](https://doi.org/10.1145/2656877.2656887).
- M11: [`ddmr.md`](ddmr.md) and [`ddmr-predictions.md`](ddmr-predictions.md).
