# Review request: Paper A

**Paper:** *Which Rewrites Survive? Pre-registered Tests of a Field-Class Model
of Encapsulation, Middleboxes and Decapsulation on Linux.*
**Artifact:** https://github.com/mixic/7g-backhaul-simulation
**Review commit:** `[HUMAN: fill the release commit]`
**Time needed:** about 2-3 hours; the focused review below is about 90 minutes.
**Status:** not submitted. This note is a request for technical review, not a
venue submission.

## What the paper claims

A field-class rule: a rewrite is applied iff the field is visible at the wire and
reachable by the middlebox; it breaks delivery iff the field is authenticated or
structural. The rule is tested with predictions frozen before the harness at
three fidelities. The paper reports every refutation: P5 at Linux, and P16d
(the replay window / depth operating point). It adds four classes the rounds
forced: quantised, derived, lookup-key and decapsulation-coupled, plus the replay
window as a state parameter.

## What I would like reviewed

1. **The rule and its classes.** Are the four added classes genuinely distinct,
   or restatements of visibility/authenticity? Is the "visible, reachable,
   authenticated, structural" core still the right cut after P13 and P14?
2. **The P16d refutation.** Is the refutation correctly attributed to a
   mis-specified reordering depth rather than to replay semantics? Does the
   round-3 follow-up (P17: rate-limited depth, exact `window - 1` / `window`
   reinjection, legacy versus ESN) settle the boundary, or only move it?
3. **The P13/P14 novelty wording.** The prior-art log
   ([`prior-art-p13-p14.md`](prior-art-p13-p14.md)) says RFC 6040 and RFC 3948
   already document the rules. Is the paper's "conformance check, not discovery"
   wording accurate and sufficient? Is any sentence still overclaiming?
4. **The evidence chain.** Every results table comes from
   `docs/paper-tables/tables.md`; `tools/make_paper_tables.py --check` recomputes
   the invariants; `tools/lint_claims.py` fails on a key number that disagrees
   with the CSV. Is the chain complete? Where would a reviewer still have to
   trust the author?
5. **The limits.** One kernel series, veth links, one NAT, no security
   evaluation. Is the one-kernel shortfall stated plainly enough in the abstract
   and limits, or does the body still read as a cross-kernel result?

## What not to review

- The name fabric, T-NDN, DDMR, CRMR, bio-control and energy work are separate
  scopes in the repository; they are not part of Paper A.
- The common-mode testbed (Paper D) is a separate model-check study.
- The postmortem study is scaffolded only; no real coding has been done.

## How to check a number

```bash
git checkout <review-commit>
py -3 tools/make_paper_tables.py --check
py -3 tools/lint_claims.py
py -3 -m unittest discover -s tests -q
```

Then compare a table in `docs/paper-layering-testbed.md` with the same table in
`docs/paper-tables/tables.md` and with the raw rows under
`validation/*/results/`. A deliberate tamper test is in
`tests/test_make_paper_tables.py` and `tests/test_lint_claims.py`; the gate is
supposed to fail when the data changes.

## What I will do with the review

Fix wording and traceability defects, report every refutation the review finds,
and either run the second kernel or keep the one-kernel shortfall. I will not
edit a frozen predictions file; corrections go to dated addenda.

## Practical

- The PDF is `docs/paper-layering-testbed.pdf`; the Markdown source is
  `docs/paper-layering-testbed.md`.
- The raw observations are `validation/layering/results/`,
  `validation/real_stack/results/` and `validation/round2/results/`.
- If a command needs root, the runbook is in `REPLICATION.md`; do not run the
  kernel harness on a shared host without reading the privilege list.
- Please report the commit hash you reviewed and the exact command output, not
  only a verdict.
