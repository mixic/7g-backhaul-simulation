# TASKS-STATUS — GOAL-release baseline

**Baseline commit:** `e394135` (`Add Paper D: common-mode resilience testbed study`, 14 November 2026).
**Status date:** 16 November 2026.
**Rule:** this file records status, not new claims. A milestone may only be marked
fixed/closed with a commit hash and a test command.

## Environment actually observed

| Item | Value |
|---|---|
| Host | Windows 11 workstation (`ThinkStation`), PowerShell via the DSH harness |
| Python | 3.14.7 (`py -3.14`); 3.12 also installed |
| Plot stack | matplotlib 3.11.2, numpy 2.5.3 |
| Linux facility | WSL2 Ubuntu, kernel `6.18.58.1-microsoft-standard-WSL2`; uid 1000, passwordless `sudo` unavailable, but `wsl -u root` gives uid 0 (used for round 3) |
| Full suite at baseline | `py -3.14 -m unittest discover -s tests -q` → **Ran 433 tests, OK (skipped=1)** in 95.1 s |
| Full suite after M1 | **Ran 466 tests, OK (skipped=1)** in 93.2 s |
| Full suite after M6 | **Ran 477 tests, OK (skipped=1)** in 64.8 s |
| Full suite after M7 | **Ran 499 tests, OK (skipped=1)** in 65.3 s |
| Full suite after M4 | **Ran 511 tests, OK (skipped=1)** in 64.4 s |
| Full suite after M11 | **Ran 517 tests, OK (skipped=1)** in 92.8 s |
| Git state | `main...origin/main`, clean at `e394135`; no tags |

This is a **one-kernel** environment. The frozen round-2 replication clause asks
for a second kernel; the available WSL2 host cannot supply one, and no native
Linux host is available to the agent. That is F2, not a result.

## Current counts at baseline

| Quantity | Count | Source |
|---|---:|---|
| Unit tests | 517 passed, 1 skipped (after M11) | test run above |
| Paper A controlled predictions | P1–P7 (7), P8–P12 (12 cases), P13–P16 (18 scored), P17 (6 scored) | `docs/layering-*-predictions*.md` |
| Paper A round-2 outcome | 17/18 CONFIRMED, 1 REFUTED (P16d), Brier 0.0833 | `docs/layering-real-stack-results-round2.md` |
| Paper A round-3 outcome | 6/6 CONFIRMED, Brier 0.0542 | `docs/layering-real-stack-results-round3.md` |
| Paper A scored total | 34/36 | `docs/paper-tables/tables.md` headline counts |
| Paper D arms / events / seeds | 9 / 10 / 30 | `docs/common-mode-predictions.md` |
| Paper D runs | 2,700 | 9 × 10 × 30 |
| Paper D hypotheses | H16–H20, all PASS on the frozen scenario | `docs/common-mode-results.md` |
| Postmortem study predictions | E1–E8; **frame 88 incidents, C2 + C2b coded, no C1/C3, no verdict** | `docs/postmortem-study-status.md` |

## F-item table

| # | Finding | Status at baseline | Where |
|---|---|---|---|
| F1 | P16d delivered range written as 674–718; CSV gives **673–717** | **FIXED (M1)** — all four occurrences corrected; generator and lint now require 673–717 | `docs/layering-real-stack-results-round2.md`, `docs/paper-layering-testbed.md` |
| F2 | Replication clause (two kernels) unmet; one WSL2 kernel only | **BLOCKED (H)** — no second kernel/host; WSL root works but the kernel is the same 6.18.58.1. The shortfall is stated in Paper A's abstract and limits; runbook and compare tool are ready; status NOT RUN | round-2 results, Paper A §8, `validation/real_stack/RUNBOOK-second-kernel.md` |
| F3 | Table generator and tests not in repo; Paper A tables hand-copied | **FIXED (M1)** — generator, 16 tests, committed table snapshot; `--check` passes | `tools/make_paper_tables.py`, `tests/test_make_paper_tables.py`, `docs/paper-tables/` |
| F4 | P16d follow-up missing: depth gate has no upper bound; `replay-window 256` silently became ESN; boundary (`max − seq` equal to window) untested | **FIXED (M4)** — P17a depth 91-92 in [64,200], 600/600; P17b-e boundary exact; P17f mode recorded; all 6 confirmed, Brier 0.0542 | `docs/layering-real-stack-predictions-round3.md`, `docs/layering-real-stack-results-round3.md` |
| F5 | P13 (ECN decapsulation) and P14 (NAT/ESP conntrack) not checked against prior art | **FIXED (M5)** — search log and source audit; Paper A wording now calls P13/P14 conformance checks | `docs/prior-art-p13-p14.md`, Paper A §1/§7/§8 |
| F6 | Paper D results defined by stipulated constants; abstract says results "support three claims"; one "pre-registered results"; no break-even analysis | **FIXED (M6)** — abstract is model-check wording; `--sensitivity` mode, 25-point grid, break-even table, figures 4-5, short version; 477 tests OK | `docs/paper-common-mode.md`, `docs/paper-common-mode-short.md`, `docs/paper-tables/common-mode-break-even.md` |
| F7 | Paper D motivation merges 3 September 2026 and 13 November 2026 events | **FIXED (M6)** — events separated and dated, primary/verified sources, no common-cause claim | `docs/paper-common-mode.md` §1, §6.4, refs 15-21 |
| F8 | Paper D related work lacks empirical outage literature | **FIXED (M6)** — Gunawi 2016, Talluri 2025, Paladugu 2026 preprint, provider corpora | `docs/paper-common-mode.md` §2.5, refs 22-28 |
| F9 | Postmortem study only a draft predictions file; no frame, no analysis script | **FRAME AND TWO BLIND PASSES DONE (M8)** — 88-incident frame from the four official indexes, frozen at `434ee71` with report hashes; C2 codes at `6061002`; replicate C2b pass; C2-vs-C2b kappa 0.58-0.93 (V8c below 0.60); no C1 and no C3, so E1-E8 unadjudicated. Human: author C1, sign-off on agent eligibility, C3 | `study/frame.csv`, `study/coded_c2.csv`, `docs/postmortem-study-status.md` |
| F10 | No release metadata / review package; README statuses unchecked | **FIXED (M9)** — `.zenodo.json`, CITATION 0.2.0, release notes, review request, venue checklist, README status table | root, `docs/RELEASE-NOTES-0.2.0.md`, `docs/review-request-paperA.md`, `docs/venue-checklist.md` |
| F11 | Paper A did not mention P17 at all while the review request leans on it; headline counts still said 28 of 30 and Figure 2 stopped at P16 | **FIXED (M11)** — §6 P17 subsection with Table 6b, Table 7b credences, counts 34 of 36, Figure 2 redrawn with P17, generator and lint carry P17 | `docs/paper-layering-testbed.md` §2/§3/§6/§8/§9, `docs/paper-tables/tables.md`, `tools/make_paper_tables.py`, `tools/make_layering_figures.py` |
| F12 | Paper A's status line credited `make_layering_figures.py` for the tables, which come from `make_paper_tables.py` | **FIXED (M11)** — one sentence now names both tools for what each generates | `docs/paper-layering-testbed.md` status line |
| F13 | Paladugu 2026 preprint (ref 24) unverified by a reviewer | **VERIFIED 16 Nov 2026** — DOI 10.5281/zenodo.23585116 opened at `zenodo.org/records/23585116`: record present, dated 22 Oct 2026, abstract states the 52/70, 28/52 and 10/11 figures Paper D cites | `docs/RELEASE-AUDIT.md`, `docs/paper-common-mode.md` §2.5 |
| F14 | E2's 0.30 threshold sits on a published vendor figure (Control Plane 2026: 20 of 62 configuration-or-deployment changes, 32 %), seen before coding | **DISCLOSED (M11)** — contamination bullet in §1 with source, numbers and mitigations; dated addendum; no frame, prediction or threshold changed | `docs/postmortem-study-predictions.md` §1, §12 |

## What has not been done, and why

- **No author C1 and no C3 adjudication.** The frame and a blind LLM C2 exist, but
  the protocol's reliability gate is defined between the author and an independent
  coder. A same-model replicate (C2b) is reported as a reliability estimate for the
  model configuration only, never as C1. E1-E8 are therefore **unadjudicated**;
  the two labelled scenarios in `study/analysis/m8-verdicts.csv` are not verdicts.
- **No second kernel.** No native Linux host and no root in WSL; M3 is prepared,
  not executed.
- **No fabricated data.** Where a facility is missing, the disposition is NOT RUN
  or blocked, with the reason recorded here.

## Milestone log

| Milestone | Status | Commit | Evidence |
|---|---|---|---|
| M0 Baseline | **done** | `33aeb61` | this file; 433-test run |
| M1 Traceability | **done** | `0af7974` | `make_paper_tables.py --check` 0 FAIL; `lint_claims.py` PASS; 466 tests OK |
| M2 Paper A pass | **done** | `5a6feb7` | all results tables pasted from `docs/paper-tables/tables.md`; abstract counts 6/7, 5/5, 17/18, 28/30; P16d mis-specified depth stated; PDF rebuilt |
| M3 Second kernel | **prepared; execution NOT RUN (H)** | `0200064` | runbook, empty layout, `tools/compare_kernels.py` + 5 tests; no second kernel available |
| M4 P16 follow-up | **done** | freeze `285c8e9`; run `4efafe4` | 100 runs; P17a-f all CONFIRMED; Brier 0.0542; 511 tests OK |
| M5 Prior art P13/P14 | **done** | `22308de` | `docs/prior-art-p13-p14.md`; RFC 6040/3715/3948, WireGuard patch, strongSwan, Linux sources verified; Paper A wording aligned |
| M6 Paper D rework | **done** | `82415bf` | break-even table; sensitivity figure; per-seed figure; verified event sources; short 6-page version; lint passes; 477 tests OK at that commit |
| M7 Postmortem scaffold | **done** | `fc91471` | predictions/template/coder prompt; frame builder; analyser with Wilson/Newcombe/Mann-Whitney/kappa gates; 22 synthetic tests; no real coding |
| M8 Study execution | **frame + C2/C2b done; C1 and C3 human** | frame `434ee71`; C2 `6061002` | 88-incident frame, hashes verified; 88/88 rows assembled with 0 validation problems in both passes; kappa C2-vs-C2b 0.58-0.93; E1-E8 unadjudicated (no C1, no C3); see `docs/postmortem-study-status.md` |
| M9 Release package | **done** | `eeb2c11` | `.zenodo.json`, CITATION 0.2.0, release notes, review request, venue checklist |
| M10 Audit | **done** | `5ffc524` | `docs/RELEASE-AUDIT.md`; 511 tests OK; 0 FAIL; lint PASS; no `[unverified]` headline claim |
| M11 Review fixes | **done** | `7664050` | P17 in Paper A (§6, Table 6b/7b, 34 of 36); Figure 2 redrawn; table provenance corrected; ref 24 DOI opened; Control Plane contamination disclosed; 517 tests OK; `--check` 29/29 PASS; lint PASS; PDF rebuilt (21 pp) |
| M11b Status | **done** | this commit | M11 hash recorded here -- documentation only |
