# Peer Review: Kalman Filtering and Its Correlation to Rate-Controlled Network State Estimation

**Reviewer:** internal peer review (self-assessment against the project's
Scientific Oath).
**Document reviewed:** `kalman-filtering-foundation.md` (the submitted draft).
**Disposition:** **Major revision required** — accepted after correction. The
central thesis (EWMA/α-β-γ as steady-state Kalman filters) is *correct and worth
keeping*; several secondary claims were factually or quantitatively wrong and
have been corrected.

---

## 1. Strengths (retained)

- **§3.1 is exact and correct.** For a scalar random-walk model (`Φ = 1`,
  `H = 1`), the steady-state Kalman filter *is* the EWMA, and `α` is the fixed
  Kalman gain, a monotone function of `Q/R`. This is a textbook result and is
  stated correctly.
- **§3.2's theoretical claim is correct.** The α-β-γ filter is the steady-state
  Kalman filter for a constant-acceleration model; `α, β, γ` are the fixed gains
  for position/velocity/acceleration.
- The document correctly identifies the raw-derivative noise problem and the
  value of joint (predictor–corrector) derivative estimation.
- The choice to tie the work to a single citable reference (Grewal & Andrews) is
  appropriate.

## 2. Findings and resolutions

### Finding 1 (Major — factual) — the α-β-γ filter was reverted, not shipped

> "In M5, we introduced the Alpha-Beta-Gamma filter to smooth the kinematic
> derivatives …"

**Problem.** The full α-β-γ filter was implemented and then **reverted** during
M5.1: with a small `γ` it smooths away the single-tick DDoS step and the
controller fired zero edits. The controller that ran the H8 benchmark is the
**two-EWMA form** (separate EWMA on velocity and acceleration, no prediction
step). The draft described α-β-γ as the shipped mechanism, which is inaccurate.

**Resolution.** Corrected in §3.2: the exact theoretical correspondence is kept,
and the revert is recorded explicitly, cross-referencing
`docs/kinematics-filtering.md`. H8's refutation is stated in the same section.

### Finding 2 (Major — quantitative) — the "Riccati O(n³) cost" argument is wrong

> "Matrix inversions … scale at `O(n³)` per node … the CPU energy cost would
> catastrophically exceed the energy saved by preventing state churn."

**Problem.** Under the project's *own* stipulated energy model
(`E_cpu = 1e-9 J/cycle`, `E_churn = 5 J/edit`), a 4-D Riccati/covariance update
is `O(4³) ≈ 64` multiply-adds — a few hundred cycles per node per tick. Over the
whole 60 s run (100 nodes × 300 ticks) that is ≈ 0.01 J of CPU, while **one**
surgical edit costs 5 J. The covariance arithmetic is ~three orders of magnitude
cheaper than a single edit, so it cannot "catastrophically exceed" the churn
savings. The argument is quantitatively false.

**Resolution.** §4.1 now *withdraws* the claim explicitly (and keeps the
withdrawal visible for auditability), and states the correct conclusion: the
full Kalman's CPU cost is negligible; the reasons not to ship it are statistical
(§4.2–4.3), not computational.

### Finding 3 (Major — technical) — "requires an EKF" is wrong

> "Applying a full Kalman Filter to a DDoS shockwave would require an Extended
> Kalman Filter …"

**Problem.** The EKF is for *non-linear dynamics or measurement models*, not
non-Gaussian *noise*. The network state model here is linear; the noise is
non-Gaussian. The correct statement is that the filter loses its
conditional-mean optimality under non-Gaussian noise, not that an EKF is needed.

**Resolution.** Corrected in §4.2 with the precise statement and the relevant
Grewal & Andrews chapters.

### Finding 4 (Minor — accuracy) — "bimodal" is not justified

> "DDoS traffic is fundamentally non-Gaussian (bimodal and heavy-tailed)."

**Problem.** "Heavy-tailed" and "step-like" are defensible; "bimodal" is an
unsupported claim about the marginal distribution and should not be asserted
without evidence.

**Resolution.** Changed to "heavy-tailed and step-like."

### Finding 5 (Minor — overclaim) — "elevate … to rigorous control theory"

> "we elevate our work from empirical network engineering to rigorous control
> theory."

**Problem.** The framing overstates the contribution, and — more importantly —
the project's empirical record (H8, H9, M7 all **refuted**) shows the filters
did *not* win against the baselines. A document that only celebrates the
correspondence while omitting the refutations would violate the Scientific Oath
(which requires reporting negative results).

**Resolution.** §6 now states the contribution as two parts — the (correct)
correspondence *and* the (honest) refutation of "filter = win" — and keeps a
prominent honesty note in §1.

### Finding 6 (Minor — stale) — "will be empirically validated in M6"

**Problem.** M6 is complete, and its verdict (H9 refuted: EWMA spends *more*
churn energy than raw MKB) is the opposite of what the draft implied would be
"validated."

**Resolution.** Updated to the actual M6/M7 verdicts and cross-referenced.

### Finding 7 (Minor — precision) — MKB "maps directly to the Kalman state vector"

**Problem.** MKB is a *state-space* formulation, but it propagates no covariance
and computes no Kalman gain; it thresholds a residual against an EMA of its own
magnitude. Calling its 4-D vector "the Kalman state vector" overstates the
relationship.

**Resolution.** §3.3 now says "state-space formulation" and states precisely
what MKB is *not*.

## 3. Verdict

Accept the document after the corrections above (now applied in
`kalman-filtering-foundation.md`). The core theorem is sound and worth keeping;
the revisions remove three wrong claims (reverted-α-β-γ, Riccati-cost, EKF) and
align the document with the project's honest, evidence-first record.
