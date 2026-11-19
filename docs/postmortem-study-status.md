# Postmortem study (M8): execution record

**Date:** 19 November 2026.
**Owner of the frozen protocol:** the author. **Protocol:** [`postmortem-study-predictions.md`](postmortem-study-predictions.md), frozen at `fc91471` (M7), unchanged here.
**Status:** the frame exists and is frozen; two independent blind LLM coding passes exist; **no C1 (author) and no C3 adjudication exist**, so no protocol verdict is available and none is claimed.

This document records what was done, by what, and where it departs from the frozen
protocol. It records status, not new claims.

## 1. What the protocol asks for, and what this run supplied

| Protocol element | Supplied here | Who / how |
|---|---|---|
| Frame from the four official indexes, publication window 2023-01-01 to 2026-10-31, seeded sample of 40 per provider (seed 2026) | **Yes** | agent, `tools/collect_postmortem_frame.py`, network-fetched 19 Nov 2026 |
| Eligibility decisions (`study/eligibility.csv`) written by a human | **Partly** | agent applied the frozen rules mechanically; five Cloudflare rows decided by hand and recorded with reasons; **human sign-off still owed** |
| `frame.csv` + saved reports committed before any coding | **Yes** | commit `434ee71` (M8b) |
| C1 = the author | **No** | the author has not coded. The agent cannot be C1: C1 must be the author, and the agent built the frame |
| C2 = an independent blind coder; if an LLM, model name, version and prompt committed first | **Yes** | `study/c2-packet/PROMPT.md` (header filled), prompt commit `7a3ec57`, codebook commit `434ee71`, model `deepseek-official/deepseek-flash` |
| C3 adjudicates every disagreement | **No** | no adjudicator exists for this run |
| Kappa gate C1-C2 per variable; below 0.60 the dependent predictions are INVALID | **Substituted** | kappa is measured **C2 vs C2b**, a replicate blind pass by the same model configuration. This is a reliability estimate for the model configuration, **not** the protocol's gate |
| Size gate (>= 30 per subset), frame gate (hash match), duplicate gate | **Yes** | enforced; the frame gate is checked on every analysis run |

## 2. The frame

| Provider | Official source used | In window | Eligible | In the frozen frame |
|---|---|---:|---:|---:|
| AWS | `aws.amazon.com/premiumsupport/technology/pes/` (`/message/<id>/` archive) | 3 | 3 | 3 |
| Cloudflare | `blog.cloudflare.com/tag/post-mortem/` | 18 | 14 | 13 |
| Google Cloud | `status.cloud.google.com/summary` -> each product's `products/<key>/history` table (238 product pages) | 545 | 509 | 40 |
| Microsoft Azure | `azure.status.microsoft/en-us/status/history/`, recovered from 44 Internet Archive snapshots (one per month, when the live page is pinned to the last 90 days) | 37 | 32 | 32 |
| **Total** | | **603** | **558** | **88** |

The frame is [`study/frame.csv`](../study/frame.csv); every row carries the
SHA-256 of its saved text in `study/reports/`. `study/frame-candidates.csv`
holds all 603 in-window candidates with the eligibility reason for each,
`study/frame-dropped.csv` the one row removed after the post-fetch check, and
`study/indexes/MANIFEST.csv` the URL and SHA-256 of every raw page used.

### Why the sample is not 40 everywhere

- **AWS publishes 18 Post-Event Summaries in total**, three inside the window.
  A sample of 40 is impossible without leaving the official index, which the
  protocol forbids, so the AWS arm is n=3.
- **Cloudflare's post-mortem tag** yields 18 in-window posts, 14 eligible, 13
  after the duplicate merge (the 18 November 2025 outage is published twice and
  is counted once).
- Google and Azure exceed 40 and were sampled with the frozen function and seed.

An imbalance this large is a frame limitation, not a result: any pooled estimate
is dominated by Google Cloud (40 of 88).

### Eligibility decisions made by the agent, not the author

The frozen rules are: official report, root cause stated, customer-visible impact
of at least 30 minutes, not single-customer, not planned maintenance, not a
security-breach disclosure. The tool applies them mechanically in this order:

1. planned/deprecation, breach and single-customer patterns in title and text;
2. impact duration from the index when the index states it (Google Cloud
   durations come from the status page itself), otherwise from an explicit
   duration claim in the report text ("failed for 47 minutes");
3. a span between two clock times is recorded as information but is **not** used
   to exclude a row, because it can be a diagnostic timeline rather than the
   customer-impact window;
4. rows with no verifiable duration stay in the frame with a note naming that.

**Five Cloudflare rows were decided by hand** and are listed in
[`study/eligibility.csv`](../study/eligibility.csv) with reasons: four posts on
that tag are not incident reports (a programme completion announcement, a
resilience plan, an engineering redesign, and a third-party breach response) and
are excluded; one (the 1.1.1.1 CNAME-order incident) is kept.

**Known gap:** the "root cause stated" rule cannot be checked mechanically before
coding. Some frame rows are status stubs that never state a cause; they carry
`V1 = unclear` in the codes and appear in the unclear counts. They were not
removed afterwards, because removing rows after sampling would make the sample
selective. The author can overrule any row through `study/eligibility.csv`.

## 3. The two coding passes

| Pass | What it is | Where |
|---|---|---|
| **C2** | the protocol's independent coder: one fresh LLM session per report, receiving only `PROMPT.md`, `codebook.md` (section 4 of the frozen protocol) and one item file | `study/coded_c2.csv`, raw rows in `study/c2-rows/` |
| **C2b** | a replicate blind pass, same model configuration, separate packet, same restrictions | `study/coded_c2b.csv` |

Both passes covered all 88 frame incidents. The packet the coders saw is archived
in [`study/c2-packet/`](../study/c2-packet/) with a manifest; no coder session was
given the predictions file, the hypotheses, the other pass's codes, or the
repository. Isolation was enforced by the packet living outside the repository
and by instructing every session to read exactly three files and nothing else --
**not** by a filesystem sandbox. A session that ignored the instruction could have
read the repository; nothing in the raw rows suggests that any did, and each pass
was assembled from the report metadata it was given.

Assembly and validation are mechanical: `tools/assemble_coded_rows.py` checks
field order, the frozen allowed values, the frame metadata and the report hash
against `frame.csv`, and refuses to write a row that fails. Both assemblies
reported **0 problems** for 88 of 88 rows.

## 4. Reliability, measured C2 vs C2b

Unweighted Cohen's kappa over the 88 incidents: V1 0.93, V1b 0.68, V2 0.79,
V3 0.79, V4 0.88, V5 0.65, V6 0.68, V7 0.72, V8a 0.69, V8b 0.71, V8c 0.58,
V9 0.93, V10 1.00. Twelve of thirteen variables clear 0.60; **V8c is below**
(0.58) and 125 cells disagree across the two passes.

This is a same-model replicate: it measures how stable this model configuration
is on this codebook. It does **not** substitute for agreement between the author
and an independent human coder, and a high same-model kappa can overstate the
reliability of an author-C1 comparison.

## 5. What the codes say, under two labelled scenarios

Full tables: [`study/analysis/m8-verdicts.csv`](../study/analysis/m8-verdicts.csv),
per-incident disagreements in
[`study/analysis/m8-disagreements.csv`](../study/analysis/m8-disagreements.csv),
report in [`study/analysis/m8-status.md`](../study/analysis/m8-status.md).

**Scenario `no-reliability`** -- the strict protocol position when no independent
human coder exists: kappa unavailable, so **all eight predictions are INVALID**.

**Scenario `replicate-kappa`** -- the measured C2-vs-C2b kappa applied to the
frozen gate, scored on C2's codes:

| ID | n | estimate | 95% interval | outcome |
|---|---:|---:|---|---|
| E1 control-plane concentration | 56 | 0.786 | [0.662, 0.873] | CONFIRMED |
| E2 change-induced | 87 | 0.414 | [0.316, 0.519] | CONFIRMED |
| E3 isolation rarely helps | 6 | 0.000 | -- | INCONCLUSIVE (size gate) |
| E4 independence helps selectively | 10 | -- | -- | INCONCLUSIVE (size gate) |
| E5 fallback is the weak link | 59 | 0.864 | [0.755, 0.930] | CONFIRMED |
| E6 controllers widen blast radius | 54 | -- | -- | INCONCLUSIVE (size gate) |
| E7 redundancy fails together | 24 | 0.958 | -- | INCONCLUSIVE (size gate) |
| E8 the classes cover the data | 87 | 0.598 | [0.493, 0.694] | REFUTED |

Neither scenario is a finding about providers. The `replicate-kappa` row is what
the frozen rules produce if the measured replicate kappa is accepted as the
reliability gate; the strict position invalidates everything. Reporting one of
them as "the result" would be the error this table is written to prevent.

Two things in it are worth the author's attention because they do not depend on
the gate:

- **E8 is refuted on these codes by a wide margin** (0.598 against a 0.80 floor).
  It is driven by 28 incidents with `V1 = unclear` and 8 with
  `V2 in {other, unclear}`: the frozen class list does not cover status-stub
  reports. If the author's C1 codes the same way, E8's failure is a statement
  about the class list, not about providers.
- **E3/E4/E6/E7 are small-cell problems** (n = 6, 10, 54, 24). E3 in particular
  has only six incidents with any counterfactual statement, so the frozen
  counterfactual rule ("code only what the text states") starves it.

## 6. What remains human

1. **C1**: the author codes the 88 frame incidents. The packet builder and the
   assembler are ready; `tools/build_c2_packet.py` writes the same packet for the
   author, and `tools/assemble_coded_rows.py --coder C1` validates and writes
   `study/coded_c1.csv`.
2. **Kappa gate**: computed C1-vs-C2 by the frozen analyser
   (`tools/analyze_postmortems.py`, which requires both files).
3. **C3**: adjudicate the disagreements; write `study/coded_final.csv`.
4. **Sign-off on the frame**: review `study/frame-candidates.csv` eligibility
   column and `study/eligibility.csv`, and overrule any row.
5. **Then**, and only then, E1-E8 verdicts on `coded_final.csv`.

## 7. Deviations, listed plainly

- The frame and the eligibility screening were done by the agent, not the human
  owner. The protocol assumed a human does both. Every decision is recorded with
  its reason so it can be reversed.
- C1 and C3 do not exist; a same-model replicate (C2b) replaces the kappa gate
  for this run only, and is never described as C1.
- The Azure arm comes from Internet Archive snapshots of the official page,
  because the live page is pinned to the last 90 days. Snapshots are recorded in
  the manifest.
- Google's incident universe comes from the per-product history tables linked
  from the summary page, because the summary page itself lists only recent
  incidents.
- The AWS and Cloudflare arms are far below the planned 40 per provider.
- Two Cloudflare rows carry an impact duration read from a clock-time pair
  (`major-data-center-power-failure...`, `route-leak-incident-january-22-2026`)
  that may not be the full customer-impact window; the notes name both.
