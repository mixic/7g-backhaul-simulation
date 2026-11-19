# Release audit (0.2.0)

**Release candidate:** 14 November 2026. **Re-audited:** 16 November 2026 (M11:
P17 in Paper A, provenance sentence, reference check, contamination disclosure).
**Baseline:** `e394135`.
**Rule:** every headline claim is mapped to a committed file and a row or a
generated table. A claim that cannot be mapped is either removed or marked
`[unverified]` and listed at the bottom. The agent prepared this audit; the
human tags and submits.

## Test and gate status at the audit run

| Check | Command | Result |
|---|---|---|
| Full suite | `py -3 -m unittest discover -s tests -q` | **517 passed, 1 skipped** (was 511; 6 new M11 tamper tests) |
| Paper A invariants | `py -3 tools/make_paper_tables.py --check` | 0 FAIL (29 checks, incl. round 3) |
| Claims lint | `py -3 tools/lint_claims.py` | PASS |
| Round-3 tests | `py -3 -m unittest tests.test_round3 -q` | 7 OK |
| Postmortem tooling tests | `py -3.14 -m unittest tests.test_postmortems tests.test_build_postmortem_frame tests.test_collect_postmortem_frame -q` | 56 OK |

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
| P17: 6 of 6; total 34 of 36 | `validation/round3/results/verdicts.csv`; `docs/paper-tables/tables.md` | P17 table, headline counts; lint facts | reported (round-3 follow-up) |
| Round-3 Brier 0.0542 over 6 | `validation/round3/results/calibration.md` | round-3 calibration table; lint fact | reported |
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
| Empirical outage literature | refs 22-28 | gunawi 2016, Talluri 2025, Paladugu 2026, provider corpora | reported; preprint labelled; Paladugu DOI opened 16 Nov 2026 |

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
| Predictions E1-E8 frozen before real coding | `docs/postmortem-study-predictions.md` | frozen at `fc91471`, unchanged by M8 | freeze held |
| Frame built from the four official indexes | `study/frame.csv`, `study/indexes/MANIFEST.csv` | 88 incidents, 603 candidates in window, SHA-256 per report, frame gate passes | **DONE (M8b `434ee71`)** |
| Independent C2 coding, LLM declared | `study/coded_c2.csv`, `study/c2-packet/PROMPT.md` | model `deepseek-official/deepseek-flash`, prompt commit `7a3ec57`, 88/88 rows valid | **DONE (M8c `6061002`)** |
| Reliability measured | `study/analysis/m8-reliability.csv` | C2-vs-C2b kappa 0.58-0.93; V8c below the 0.60 gate | measured, same-model replicate |
| Author C1 and C3 adjudication | -- | absent | **NOT RUN (H)** |
| E1-E8 verdicts | `study/analysis/m8-verdicts.csv` | two labelled scenarios only | **UNADJUDICATED -- no verdict claimed** |
| Contamination disclosure includes a vendor figure at E2's threshold | `docs/postmortem-study-predictions.md` sections 1 and 12 | Control Plane 2026 report: 20 of 62 configuration-or-deployment changes (32 %) | disclosed pre-freeze |

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
release but no new claim depends on a changed version of them. The Paladugu 2026
preprint (ref 24, DOI [10.5281/zenodo.23585116](https://doi.org/10.5281/zenodo.23585116))
was opened on 16 November 2026 via its Zenodo record
(`https://zenodo.org/records/23585116`): the record exists, is dated 22 October
2026, is typed as a preprint, and its abstract states the 52/70, 28/52 and 10/11
figures that Paper D cites, so that reference is verified rather than unverified.
If a reviewer finds a source that cannot be fetched, add it here and mark the
claim `[unverified]`; do not silently drop it.

## Not run, and why

- **Second kernel (M3):** the host is one WSL2 kernel
  (`6.18.58.1-microsoft-standard-WSL2`); WSL root works, but a second kernel is
  not available. Runbook and comparison tool are ready.
- **Postmortem study verdicts (M8):** the frame and two blind LLM coding passes
  exist, but the protocol's reliability gate is defined between the author (C1)
  and an independent coder, and no C3 adjudicated. E1-E8 are therefore
  unadjudicated; the two labelled scenarios are not verdicts.
- **No external upload/submission:** by design.
