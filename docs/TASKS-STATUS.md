# TASKS-STATUS — GOAL-release baseline

**Baseline commit:** `e394135` (`Add Paper D: common-mode resilience testbed study`, 14 November 2026).
**Status date:** 14 November 2026.
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
| Git state | `main...origin/main`, clean at `e394135`; no tags |

This is a **one-kernel** environment. The frozen round-2 replication clause asks
for a second kernel; the available WSL2 host cannot supply one, and no native
Linux host is available to the agent. That is F2, not a result.

## Current counts at baseline

| Quantity | Count | Source |
|---|---:|---|
| Unit tests | 511 passed, 1 skipped (after M4) | test run above |
| Paper A controlled predictions | P1–P7 (7), P8–P12 (12 cases), P13–P16 (18 scored) | `docs/layering-*-predictions*.md` |
| Paper A round-2 outcome | 17/18 CONFIRMED, 1 REFUTED (P16d), Brier 0.0833 | `docs/layering-real-stack-results-round2.md` |
| Paper D arms / events / seeds | 9 / 10 / 30 | `docs/common-mode-predictions.md` |
| Paper D runs | 2,700 | 9 × 10 × 30 |
| Paper D hypotheses | H16–H20, all PASS on the frozen scenario | `docs/common-mode-results.md` |
| Postmortem study predictions | E1–E8, draft, no frame, no analyser | `postmortem-study-predictions.md` (outside repo at baseline) |

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
| F9 | Postmortem study only a draft predictions file; no frame, no analysis script | **SCAFFOLD FIXED (M7)** — predictions + template committed, frame builder and analyser with synthetic tests, C2 prompt; real frame and coding remain **H (M8)** | `docs/postmortem-study-predictions.md`, `tools/build_postmortem_frame.py`, `tools/analyze_postmortems.py`, `study/README.md` |
| F10 | No release metadata / review package; README statuses unchecked | **OPEN** | no `.zenodo.json`, no review note |

## What has not been done, and why

- **No real postmortem coding.** The agent has read the predictions; it is not a
  blind coder. M8 remains human.
- **No second kernel.** No native Linux host and no root in WSL; M3 is prepared,
  not executed.
- **No fabricated data.** Where a facility is missing, the disposition is NOT RUN
  or blocked, with the reason recorded here.

## Milestone log

| Milestone | Status | Commit | Evidence |
|---|---|---|---|
| M0 Baseline | **done** | `33aeb61` | this file; 433-test run |
| M1 Traceability | **done** (this commit) | see `git log --grep '^M1:'` | `make_paper_tables.py --check` 0 FAIL; `lint_claims.py` PASS; 466 tests OK |
| M2 Paper A pass | **done** (this commit) | see `git log --grep '^M2:'` | all results tables pasted from `docs/paper-tables/tables.md`; abstract counts 6/7, 5/5, 17/18, 28/30; P16d mis-specified depth stated; PDF rebuilt |
| M3 Second kernel | **prepared; execution NOT RUN (H)** | see `git log --grep '^M3:'` | runbook, empty layout, `tools/compare_kernels.py` + 5 tests; no second kernel available |
| M4 P16 follow-up | **done** (this commit) | see `git log --grep '^M4:'` | P17 frozen at `285c8e9` before harness; 100 runs; P17a-f all CONFIRMED; Brier 0.0542; 511 tests OK |
| M5 Prior art P13/P14 | **done** (this commit) | see `git log --grep '^M5:'` | `docs/prior-art-p13-p14.md`; RFC 6040/3715/3948, WireGuard patch, strongSwan, Linux sources verified; Paper A wording aligned |
| M6 Paper D rework | **done** (this commit) | see `git log --grep '^M6:'` | break-even table; sensitivity figure; per-seed figure; verified event sources; short 6-page version; lint passes; 477 tests OK |
| M7 Postmortem scaffold | **done** (this commit) | see `git log --grep '^M7:'` | predictions/template/coder prompt; frame builder; analyser with Wilson/Newcombe/Mann-Whitney/kappa gates; 22 synthetic tests; no real coding |
| M8 Study execution | human | — | out of agent scope |
| M9 Release package | not started | — | — |
| M10 Audit | not started | — | — |
