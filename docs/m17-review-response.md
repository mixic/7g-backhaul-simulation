# M17: response to the peer review of Papers A and B

**Note on labels.** The review names Paper A as the layering study and Paper B as
the fair-queueing study. The request that accompanied it labelled them the other
way round; this response follows the review's own subject matter:
`docs/paper-layering-testbed.md` is Paper A and `docs/paper-bio-control-limits.md`
is Paper B.

Every change below is textual. No number, verdict, refutation or figure changed,
and no data were re-run.

## Paper A — layering study

| Weakness | Action | Where |
|---|---|---|
| **W1** Single WSL2 kernel; the abstract over-claims. | The abstract now says that all kernel evidence comes from one WSL2 kernel series, veth links and one nftables implementation, that the frozen two-kernel replication clause is unmet, and that the paper does not claim transfer to another kernel series, NAT implementation or physical NIC. | Abstract, paragraph 1 |
| **W2** The three fidelities are not independent. | The abstract now states that the Python model, the SimPy simulator and the Linux leg are three engines of which at most one is independent, and that round 1's Linux leg runs the harness's own user-space codec. §2.7 adds that "confirmed at three fidelities" means three engines, not three independent replications, and that the kernel leg decides. | Abstract; §2.7 |
| **W3** Tamper tests are not external replication. | §4.8 now states the scope: a tamper test proves the *pipeline* is sensitive to corruption, not that the *model* is right; it is orthogonal to a corrupted model, and it does not substitute for a second implementation, a second kernel, or an independent re-derivation. The independent re-derivation is named as the role of Figures 3 and 7. | §4.8, final paragraph |
| **W4** Length and density. | Two raw size tables (P9, P10) moved to a new **Appendix A. Detail tables** as Table A1/A2, with both in-text references updated. A one-paragraph reading guide at the head of the contributions tells a workshop reader which four sections carry the method and the result. | §1; Appendix A |

## Paper B — fair-queueing study

| Weakness | Action | Where |
|---|---|---|
| **W1** Tests one reading of the analogy, not the analogy. | The abstract now states that the paper tests the *mechanism* the analogy proposes — a continuous compensation signal driving a discrete actuator — and not the metaphor of homeostasis. §2.2 adds that the claim is about the shared mechanism, that a different set-point law would still act through the same discrete edit, and that this is an argument about the actuator rather than a measurement of every possible controller. | Abstract; §2.2 |
| **W2** The LLM arm is a mock. | A new paragraph, **"What the mock can and cannot represent"**, states what the mock is (a policy table with three guardrails), that it is bit-identical to the greedy heuristic (2,673.9 B, 30/30 seeds) so the oracle contributes nothing to the saving, that a real model could only win by proposing an order better than compression-first, and that 2,673.9 B is therefore a *ceiling* for this workload, not a floor. The instant/free decision is named as the one place the mock is optimistic. | §5.4 |
| **W3** The 42 % wire saving is unexplained. | A new paragraph, **"Where the 42 % comes from"**, gives the mechanism: 1,400-byte payloads over fiber–microwave–satellite, compressible except on microwave; the static convention fragments → encrypts → compresses, so compression meets ciphertext and saves nothing (4,650 B); the compiler installs compress → encrypt → fragment, so the payloads compress before encryption (2,673.9 B, 42.5 %, 1,976.1 B). It states that the saving is a compression-placement effect, not a property of the oracle. | §4.2(f) |
| **W4** No mechanism for the peak-burst failure. | A new paragraph, **"Why the trigger cannot cap the burst"**, gives the measured mechanism: the 1-D limiter and the extraction arm report the *same* peak (222.04 ± 31.70) because both issue the identical edit; the edit's magnitude is fixed by the actuator (12 % byte limit, 0.05 weight) across ~15 routers per tick, so no trigger issuing that edit can reduce it. The only freedom is *when* to fire, and the campaign shows it is worth nothing: 49.8 ± 9.97 edits against 45.3 ± 6.51, false positives exactly zero, and a worse tail (worst seed 402.6 against 256.2) because firing less often means each firing meets a larger accumulated state. Capping the peak would require changing the edit, which no arm does. | §5.2 |

## What this revision does not do

- **External replication (the review's central residual risk).** Paper A still has
  one kernel, one NAT and one encryptor; Paper B still has one simulator. Both
  papers now say so in the abstract and in the threats sections. Replication is a
  new experiment, not a revision, and inventing it would be the failure mode the
  review warns about.
- **A workshop-length cut of Paper A.** The body was tightened by moving two data
  tables out and adding a reading guide, but the paper remains a full version
  (40 pages). A workshop submission would need a separate cut, not a rewrite of
  this document.
- **A real LLM in Paper B.** The mock remains a mock; the paper now states exactly
  what that means for the EROI number and why the break-even is the transferable
  result.

## Verification

- `tools/lint_claims.py`: PASS (Paper A and Paper D claims still agree with the
  committed evidence; the P16d range, the 12.35 pp P5 difference, the 2,112/2,180 B
  P15 totals, both Brier scores and the 34/36 count are all still present).
- Both PDFs rebuilt with pandoc + XeLaTeX: Paper A 40 pages, Paper B 35 pages,
  zero missing characters in Paper B (Paper A keeps its earlier glyph fixes).
- No table, figure or number was edited; the only structural change is the
  appendix move in Paper A, and every affected cross-reference was updated
  (`Table 2c → A1`, `Table 2d → A2`).
