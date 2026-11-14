# Release audit (0.2.0)

**Release candidate:** 14 November 2026.
**Baseline:** `e394135`.
**Rule:** every headline claim is mapped to a committed file and a row or a
generated table. A claim that cannot be mapped is either removed or marked
`[unverified]` and listed at the bottom. The agent prepared this audit; the
human tags and submits.

## Test and gate status at the audit run

| Check | Command | Result |
|---|---|---|
| Full suite | `py -3 -m unittest discover -s tests -q` | **511 passed, 1 skipped** |
| Paper A invariants | `py -3 tools/make_paper_tables.py --check` | 0 FAIL |
| Claims lint | `py -3 tools/lint_claims.py` | PASS |
| Round-3 tests | `py -3 -m unittest tests.test_round3 -q` | 7 OK |
| Postmortem scaffold tests | `py -3 -m unittest tests.test_postmortems tests.test_build_postmortem_frame -q` | 22 OK |

## Paper A

| Headline claim | Source file | Row / evidence | Disposition |
|---|---|---|---|
| P1-P7: 6 of 7 confirmed | `validation/layering/results/verdicts.csv`; `docs/paper-tables/tables.md` | P1-P7 table; `make_paper_tables.py --check` | reported |
| P5 refuted at Linux, +12.35 pp | `validation/layering/results/linux_observations.csv` | P5 delivery rows; lint fact 12.35 | reported |
| P8-P12: 5 of 5 predictions, 12 cases | `validation/real_stack/results/verdicts.csv`; `docs/paper-tables/tables.md` | real-stack table | reported |
| P9/P10 formulas exact | `validation/real_stack/results/observations.csv` | generator checks P9/P10 | reported |
| P13/P14 results | `validation/round2/results/observations.csv` | P13/P14 tables in `tables.md` | reported as conformance checks |
| P15: 2112 / 2180 B, delivery 0.9003 / 0.9041 | `validation/round2/results/observations.csv` | P15 wire and delivery rows | reported |
| P16d: 673-717 delivered, REFUTED | `validation/round2/results/observations.csv` | P16d delivered rows; lint fact 673-717 | reported as mis-specified depth |
| Brier 0.0833 over 18 | `validation/round2/results/calibration.md` | calibration table; lint fact | reported |
| One-kernel shortfall | `docs/layering-real-stack-results-round2.md` Environment; `docs/paper-layering-testbed.md` abstract/limits | explicit statement | carried as limit |
| P13/P14 are prior art, not discoveries | `docs/prior-art-p13-p14.md` | RFC 6040/3715/3948, WireGuard thread, strongSwan, Linux source | disposition recorded |

## Paper D

| Headline claim | Source file | Row / evidence | Disposition |
|---|---|---|---|
| 9 arms x 10 events x 30 seeds = 2,700 runs | `docs/paper-tables/common-mode-per-seed.csv` | 2,700 rows | reported |
| H16: A4-A3 tenant gateway 100; identity 0 | `docs/paper-tables/common-mode-summary.csv`; `common-mode-verdicts.csv` | H16 rows | model check |
| H17: A3-A2 conduit 100; A2-A1 link 100 | same | H17 rows | model check |
| H18: A6-A5 AI 90; A6 90; normal cost 10 | same | H18 rows | model check |
| H19: interaction 44.38 | same | H19 row; summary A1/A3/A6/A9 | model check |
| H20: A5-A8 controller+link 100; normal 0 | same | H20 rows | model check |
| Tested fallback gap 34.5 | `common-mode-summary.csv` | A6 minus A7 under `backhaul_cut` | model check |
| H18 break-even 0.85 efficiency | `docs/paper-tables/common-mode-break-even.csv` | H18_normal_cost row | model check |
| Fallback break-evens 0.222 / 18.166 / 0.12172 | `common-mode-break-even.csv` | fallback_gap rows | model check |
| H19 capacity boundary 0.767 | `common-mode-break-even.csv` | H19_interaction row | model check |
| Per-seed pass fraction 1.000 | `common-mode-verdicts.csv`; `common-mode-per-seed.csv` | verdict rows | reported |
| 3 Sep and 13 Nov events separate, verified | `docs/paper-common-mode.md` refs 15-21 | URLs fetched 14 Nov 2026 | reported |
| Empirical outage literature | refs 22-28 | gunawi 2016, Talluri 2025, Paladugu 2026, provider corpora | reported; preprint labelled |

## Round 3 (P17)

| Headline claim | Source file | Row / evidence | Disposition |
|---|---|---|---|
| P17a depth 91-92 in [64,200], 600/600 delivered | `validation/round3/results/observations.csv`; `verdicts.csv` | P17a rows | **CONFIRMED** |
| P17b legacy boundary 32 rejected | same | P17b delivered/reference 1/1 | **CONFIRMED** |
| P17c legacy boundary 31 accepted | same | P17c delivered/reference 2/2 | **CONFIRMED** |
| P17d ESN boundary 256 rejected | same | P17d delivered/reference 1/1 | **CONFIRMED** |
| P17e ESN boundary 255 accepted | same | P17e delivered/reference 2/2 | **CONFIRMED** |
| P17f mode mapping | same | `anti_replay_esn` 20/20 legacy for 32, 20/20 ESN for 256 | **CONFIRMED** |

## Postmortem study

| Claim | Source | Evidence | Disposition |
|---|---|---|---|
| Predictions E1-E8 frozen before real coding | `docs/postmortem-study-predictions.md` | committed with template | scaffold only |
| Frame builder and analyser exist | `tools/build_postmortem_frame.py`, `tools/analyze_postmortems.py` | 22 synthetic tests | scaffold only |
| No real coding by the agent | `study/README.md`; this audit | M8 is human | **NOT RUN (H)** |
| C2 prompt committed | `docs/postmortem-coder-prompt.md` | model/version fields to fill | prepared, not used |

## Release package

| Item | File | Status |
|---|---|---|
| Citation metadata | `CITATION.cff` | version 0.2.0, 14 Nov 2026 |
| Archive metadata | `.zenodo.json` | valid JSON; no DOI |
| Release notes | `docs/RELEASE-NOTES-0.2.0.md` | prepared |
| Paper A review request | `docs/review-request-paperA.md` | prepared |
| Venue checklist | `docs/venue-checklist.md` | placeholder for ANRW 2027 call |
| Second-kernel runbook | `validation/real_stack/RUNBOOK-second-kernel.md` | prepared, **NOT RUN** |
| Status file | `docs/TASKS-STATUS.md` | F-table and milestone log |

## `[unverified]` items

None in the claims above. The 2026 event sources (refs 15-21) were fetched on
14 November 2026; the pre-2026 references 1-14 were not re-fetched for this
release but no new claim depends on a changed version of them. If a reviewer
finds a source that cannot be fetched, add it here and mark the claim
`[unverified]`; do not silently drop it.

## Not run, and why

- **Second kernel (M3):** the host is one WSL2 kernel
  (`6.18.58.1-microsoft-standard-WSL2`); WSL root works, but a second kernel is
  not available. Runbook and comparison tool are ready.
- **Real postmortem frame and coding (M8):** human-only; the agent has read the
  predictions and is not a blind coder.
- **No external upload/submission:** by design.
