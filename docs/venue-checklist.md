# Venue checklist (fill when the ANRW 2027 call is published)

**Status:** placeholder. The agent does not choose a venue or submit. Fill this
table with the actual call text, then keep it with the review package.

| Item | Value | Source / date |
|---|---|---|
| Venue and track | `[HUMAN]` | `[HUMAN]` |
| Call published | `[HUMAN]` | `[HUMAN]` |
| Submission deadline | `[HUMAN]` | `[HUMAN]` |
| Notification / camera-ready | `[HUMAN]` | `[HUMAN]` |
| Page limit (review / camera) | `[HUMAN]` | `[HUMAN]` |
| Format / template | `[HUMAN]` | `[HUMAN]` |
| Anonymisation | `[HUMAN]` | `[HUMAN]` |
| Artifact policy | `[HUMAN]` | `[HUMAN]` |
| arXiv / prepublication policy | `[HUMAN]` | `[HUMAN]` |
| Ethics / human-subjects | `[HUMAN]` | `[HUMAN]` |
| Dual submission rule | `[HUMAN]` | `[HUMAN]` |
| Travel / registration | `[HUMAN]` | `[HUMAN]` |
| Paper to submit (A / D / short D) | `[HUMAN]` | `[HUMAN]` |
| Review package prepared | yes | `docs/review-request-paperA.md` |
| Archive metadata prepared | yes | `.zenodo.json`, `CITATION.cff` |

## Pre-submission checks

- [ ] The call text is saved and dated.
- [ ] Page limit and anonymisation are checked against the actual PDF.
- [ ] `py -3 tools/lint_claims.py` passes on the submitted files.
- [ ] `py -3 tools/make_paper_tables.py --check` reports 0 FAIL.
- [ ] The abstract states the one-kernel shortfall and the model-check scope.
- [ ] No `[unverified]` item remains in a load-bearing claim.
- [ ] The artifact link is public and points at the reviewed commit.
- [ ] A human, not the agent, clicks submit.

## Notes

ANRW is a workshop; the Paper A review request is written for a technical
reviewer, not a venue. If the venue requires a shorter paper, the Paper D short
version is a separate document, not a substitute for Paper A.
