# Release notes: 0.2.0 (release candidate for external review)

**Date:** 14 November 2026.
**Baseline:** `e394135` (Paper D testbed study).
**Status:** release candidate. Not submitted, not peer reviewed, not archived by
the agent. A human tags, archives and submits.

## What this release is for

Paper A should be sendable to outside reviewers with every number traceable to
a committed CSV. Paper D should be scoped honestly: a flow-level model-check
study with a one-factor break-even analysis, and a separate empirical
postmortem study that is scaffolded but not yet executed.

## Verification commands

```bash
py -3 tools/make_paper_tables.py --check
py -3 tools/lint_claims.py
py -3 -m unittest discover -s tests -q
```

`make_paper_tables.py --check` recomputes the Paper A invariants and regenerates
`docs/paper-tables/`. `lint_claims.py` fails on banned phrases and on a key number
that disagrees with the CSVs. The full suite result is recorded in
[`TASKS-STATUS.md`](TASKS-STATUS.md) and [`RELEASE-AUDIT.md`](RELEASE-AUDIT.md).

## Changes in this release

| Area | Change |
|---|---|
| Paper A | Table generator + 16 tests; P16d range corrected to 673-717; all results tables pasted from `docs/paper-tables/tables.md`; abstract states the one-kernel shortfall; PDF rebuilt |
| Paper A | Claims lint (`tools/lint_claims.py`) + 17 tests; banned phrases, title/abstract vocabulary, old rule wording and key CSV numbers are gated |
| Paper D | `--sensitivity` mode in `tools/benchmark_common_mode.py`; 25-value one-factor grid, break-even CSV/Markdown, 11 tests; two new figures (per-seed distributions, sensitivity) |
| Paper D | Motivation separated into the 2-3 September and 13 November 2026 events with verified sources; empirical outage literature added; abstract and discussion use model-check wording; 6-page short version |
| Prior art | `docs/prior-art-p13-p14.md`: RFC 6040, RFC 3715, RFC 3948, WireGuard patch, strongSwan and Linux source audit; Paper A wording aligned |
| Postmortem study | Frozen predictions/template added; frame builder and analyser with Wilson/Newcombe/Mann-Whitney/kappa gates; 22 synthetic tests; C2 prompt; `study/README.md` |
| Round 3 | P17 predictions frozen before harness; rate-limited depth, captured/reinjected ESP boundary, legacy/ESN mode; 20 runs per case; results in `docs/layering-real-stack-results-round3.md` |
| Release | `.zenodo.json`, release notes, Paper A review request, venue checklist, audit |

## What is not included

- **Second-kernel replication (NOT RUN).** The host has one WSL2 kernel
  (`6.18.58.1-microsoft-standard-WSL2`). The runbook and comparison tool are
  ready; a human with a native Linux VM must run them. Paper A says one kernel.
- **Real postmortem frame and coding (H, M8).** The agent read the predictions
  and is not a blind coder. The frame builder, analyser and prompt are committed;
  the human builds the frame, finds C2, and codes.
- **No external contact, upload or submission.** The agent prepared materials
  only.

## Known limits carried into the release

- Paper A is one kernel series (two WSL2 builds), veth links, one NAT; no
  wireless, congestion or cross traffic; security is not evaluated.
- Paper D is flow-level and stipulated; its break-even values are one-factor
  interpolations, not confidence intervals; the empirical anchor is the separate
  postmortem study.
- The postmortem study's counterfactual variable (V8) is the weakest part of the
  design; its `unclear` share is reported.
- The repository remains a single-author prototype with one author-performed
  ns-3 cross-check and no independent replication.
