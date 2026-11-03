# GOAL — Layered-protocol testbed (phase 0, revised)

**Status:** active, phase 0. Predictions are frozen in
[`docs/layering-predictions.md`](docs/layering-predictions.md). Results are
reported in [`docs/layering-results.md`](docs/layering-results.md).

This file replaces the arithmetic-centred draft goal with the same testbed,
but a sharper research question. The original milestone structure (M1–M6) is
kept. What changes is *what the testbed is for*.

## Research question

> What formal condition determines whether a composed protocol stack survives
> a middlebox that rewrites a header field?

The draft goal compared layer orderings whose size and delivery differences
can be derived on paper (28·(n−1) bytes, a sum of overheads, (1−p)^n). Those
are useful regression tests, not research results. The middlebox question is
different: it composes visibility, integrity scope, parser reachability and
framing structure, and the number of interacting cases is large enough that
the model has to carry the load.

## Claim under test

For a target field `f` introduced by layer index `i` in a stack
`L0 -> ... -> L(n-1)` (`L0` applied first), define:

- `visible(f)` — no encryption or compression layer is applied after `i`;
- `reachable(f, d)` — `n - i <= d` for a middlebox whose fixed parser
  understands `d` layers from the wire outwards;
- `authenticated(f)` — `f` is in an encryption layer's AAD scope;
- `structural(f)` — `f` is a length- or offset-bearing field.

Then the model predicts:

| Quantity | Prediction |
|---|---|
| rewrite applied | `reachable(f, d) and visible(f)` |
| authentication accepted | `not (rewrite applied and authenticated(f))` |
| datagram delivered | `authentication accepted and not (rewrite applied and structural(f))` |

The condition is deliberately falsifiable. If a visible, unauthenticated,
length-bearing field survives a rewrite, the structural clause is wrong. If a
field that is invisible at the wire is rewritten, the visibility clause is
wrong. If a reachable authenticated field is rewritten and still authenticates,
the integrity clause is wrong. A refutation is a result.

The testbed checks this condition at three fidelity levels: the executable
Python model, SimPy with paired seeds, and a Linux network-namespace/TUN data
plane subject to `tc netem` loss.

## Predictions

| ID | Role | Claim |
|---|---|---|
| P1 | regression | compress/encrypt do not commute on size |
| P2 | regression | encrypt/fragment differ by exactly 28·(n−1) bytes but not in delivery |
| P3 | research | rewriting commutes with integrity protection only outside the authenticated scope |
| P4 | regression | fixed-overhead layers commute on size |
| P5 | regression | compress-then-fragment beats fragment-then-compress on delivery |
| P6 | research (core) | the visibility/reachability/integrity condition holds over a 54-case sweep |
| P7 | research (core) | integrity exclusion is not sufficient: structural fields break delivery |

P1–P5 keep the starter set from the draft goal, with numeric tolerances now
frozen. P2, P4 and P5 are explicitly regression tests. P3 is generalised by
P6 and extended by P7. Details, scenarios, stipulations and refutation
conditions are in the predictions file; that file is frozen and is not edited
after this commit.

## Milestones

| # | Deliverable | Done when |
|---|---|---|
| M1 | Layer type system and encap/decap library | Unit and property tests pass in CI |
| M2 | `docs/layering-predictions.md` finalized | Committed before experiment code; tolerances frozen |
| M3 | Executable model and SimPy implementations | Paired-seed CSVs generated and committed |
| M4 | Linux namespace data plane | Scenarios reproduce M3 within frozen tolerances, or discrepancies are logged |
| M5 | `docs/layering-results.md` | All predictions classified; refutations explained, not removed |
| M6 (stretch) | ns-3 cross-check of at least one prediction | Report appended to M5 |

## Observable set O (fixed before experiments)

- wire bytes per datagram;
- maximum application payload for a given path MTU;
- datagram delivery probability under stipulated i.i.d. fragment loss;
- in-order delivery fraction;
- duplicates delivered to the application;
- authentication acceptance rate.

Header visibility at a middlebox is recorded as a separate column and is
**not** part of O. Security properties are out of scope; the AEAD is a toy and
its only role is to make the integrity scope observable.

## Constraints

- Reuse `tools/validation_io.py`, the paired-seed methodology,
  `simulation/link_queue.py` and `simulation/rfmp.py`.
- Mark every stipulated parameter as stipulated. Never describe a stipulated
  value as measured. The only measured calibration value is the zlib ratio of
  the synthetic corpus, recorded in the predictions file.
- No new claims in `README.md` without a matching committed result.
- Do not modify existing benchmarks except to fix bugs, and note any such fix.
- If a prediction fails, stop and report it. Do not tune the model,
  tolerances or scenario until it passes.
- No external network dependencies beyond `requirements.txt`. Linux emulation
  runs as root in a container or WSL; the exact privileges are documented.

## Current status (3 November 2026)

- M1–M5 are complete. The frozen predictions are in
  [`docs/layering-predictions.md`](docs/layering-predictions.md); the
  classified results are in [`docs/layering-results.md`](docs/layering-results.md).
- Six predictions are confirmed. **P5 is refuted at the Linux fidelity** and
  is reported as a refutation, with the cause (a payload-normalisation
  fragment-count shift) explained. No prediction, tolerance or scenario was
  tuned to remove it.
- M6 (ns-3 cross-check) was not attempted because no ns-3 tree was available
  in the execution environment. It remains open.

## Out of scope

Wireless PHY/MAC effects, congestion control, role-selection policy,
CDN/cloud/quantum modules, and any claim about 6G/7G superiority. The testbed
does not evaluate cryptographic security, and no result here is evidence that
one layer ordering is a better protocol design.
