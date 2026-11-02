# Community Engagement

This document records the project's community-engagement status and the
collaboration it is seeking. It is a statement of current state and intent, not
evidence that anyone outside the project has used, reviewed, or cited the work.

## Current status (version 0.1.0)

As of version 0.1.0 (2 November 2026):

| Signal | Status |
|---|---|
| External issues | None recorded |
| External pull requests | None recorded |
| Fork or third-party code contributions | None recorded |
| Citations | None known |
| Cross-simulator validation | One transport scenario (S1) compared with ns-3.49 by the author; see [external-validation.md](external-validation.md) |
| Independent replications | None published; see [REPLICATION.md](../REPLICATION.md) |
| Peer review | None; neither the software nor the paper has been peer reviewed |
| Workshop submission | None submitted |
| Review outcomes | None exist |

The project is a single-author research prototype. The absence of external
engagement limits the evidence base; this document cannot substitute for
independent scrutiny, and it does not claim any.

## Why this document exists

Feedback on the project identified it as a single-author effort without
community engagement and recommended three things: publish replication and
validation material, invite external collaboration explicitly, and prepare for
workshop submission. The repository now contains that infrastructure:

- [REPLICATION.md](../REPLICATION.md) — install, test, benchmark, and
  cross-simulator comparison commands, plus an honestly empty table of
  published external validations.
- [Validation challenge template](../.github/ISSUE_TEMPLATE/validation_challenge.yml)
  — for a specific, technically grounded challenge to a submodel.
- [Replication report template](../.github/ISSUE_TEMPLATE/replication_report.yml)
  — for independent replication attempts, including partial and failed ones.
- [CITATION.cff](../CITATION.cff) — citation metadata for the software.

Publishing this infrastructure does not create engagement. It only makes
engagement possible and auditable.

## Most valuable contributions

1. **Independent validation evidence (highest priority).** A cross-simulator
   check, a testbed comparison, or a trace-calibrated model that confirms or
   contradicts a claim. Negative and partial results are valuable when reported
   honestly.
2. **Trace-calibrated models.** Replace stipulated link, traffic, queue, or
   failure parameters with documented measurements, and record provenance and
   preprocessing.
3. **MPTCP LIA/OLIA comparison.** The repository now has a window-level coupled
   congestion-control model (uncoupled Reno, LIA and OLIA) and a comparison
   benchmark, but no TCP implementation: no acknowledgements, retransmissions or
   schedulers. A comparison against a real MPTCP stack or a compatible simulator
   module is therefore still open, and LIA/OLIA outputs must not be presented as
   a protocol conformance test.
4. **Independent review of the paper.** Methodological critique, related-work
   corrections, and checks of the claims against the cited literature.
5. **Replication reports.** Running the documented commands at a recorded
   commit and reporting matches, deviations, or failures.
6. **Code, tests, and documentation.** Useful, but lower priority than
   evidence about whether the models are right.

## Collaboration offer

The maintainer is willing to:

- scope one bounded validation with a collaborator (a single handover or
  link-impairment scenario is the recommended first target);
- share scenario definitions and review a metric mapping before an external run
  starts;
- review a proposed protocol and acceptance criterion in advance;
- list completed replications, including failed or partial ones, with the
  collaborator's permission and with the outcome stated plainly;
- discuss authorship for substantive joint work according to actual
  contribution. Authorship is not promised in advance.

Responses are best-effort. There is no service-level commitment, funded
support, or guaranteed turnaround.

## Workshop-submission readiness checklist

This checklist tracks preparation. An unchecked item is not done, and no
workshop submission has been made.

| Item | Status | Notes |
|---|---|---|
| Reproducible command guide | Done | [REPLICATION.md](../REPLICATION.md) |
| Citation metadata | Done | [CITATION.cff](../CITATION.cff) |
| Validation and replication issue forms | Done | `.github/ISSUE_TEMPLATE/` |
| Explicit limitations statement | Done | README and paper, Section 15 |
| Honest engagement statement | Done | This document |
| Author-performed cross-simulator validation | Done | Scenario S1 in ns-3.49, see [external-validation.md](external-validation.md) |
| Independent third-party validation | Not done | No external validation by anyone outside the project exists |
| Published independent replication | Not done | Table in `REPLICATION.md` is empty |
| Peer review of the paper | Not done | No review outcome exists |
| Target workshop and deadline selected | Not done | No venue has been chosen |
| Artifact-evaluation package | Partial | A `Dockerfile` exists but has not been validated as an artifact image |
| Reproducibility appendix with expected outputs | Partial | Commands exist; expected output values are not pinned |
| Data-availability and ethics statement | Not done | Needed before submission |
| Conflict-of-interest statement | Not done | Needed before submission |
| Author affiliation and contact metadata | Partial | Author is known; affiliation is not stated |
| Response plan for reviews and artifact evaluation | Not done | Needed before submission |
| Community evidence (issues, PRs, citations) | None | Nothing external to report |

The project is not workshop-ready until at least one independent validation or
replication exists, the paper has had independent review, and the artifact
package is reproducible from a clean environment. Those are prerequisites, not
formalities.

## What this document does not claim

- It does not claim that the project has been peer reviewed.
- It does not claim any external issue, pull request, fork contribution, or
  citation.
- It does not claim that anyone has validated, adopted, or endorsed the
  software.
- It does not claim that a workshop will accept the work. No submission has
  been made.

## Getting involved

- Read [REPLICATION.md](../REPLICATION.md) and run the documented commands at a
  recorded commit.
- Open a
  [replication report](https://github.com/mixic/7g-backhaul-simulation/issues/new?template=replication_report.yml)
  for a full attempt, or a
  [validation challenge](https://github.com/mixic/7g-backhaul-simulation/issues/new?template=validation_challenge.yml)
  for a specific model-fidelity discrepancy.
- Follow the general workflow in [CONTRIBUTING.md](../CONTRIBUTING.md).
