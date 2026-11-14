# Postmortem study: pre-registered rubric, sampling frame and predictions (E1-E8)

**Status:** DRAFT. Commit this file, then freeze the sampling frame (section 3), then
code. No edit after the frame freeze except a dated addendum. Record the commit hashes
of (1) this file, (2) the frame list, (3) the coder prompt, (4) the analysis script.

**Purpose.** Paper D argues from a simulator whose outcomes follow from its definitions
(the 90 % is the stipulated 0.9 efficiency; "100 % versus 0 %" is dependency-list
membership). This study replaces that with a question that real events can answer:

> In public provider postmortems, do large-blast-radius outages concentrate in shared
> control-plane dependencies, and do the remedies Paper D favours (tenant isolation,
> independent multipath, a tested fallback, local control) match what the postmortems
> say would and would not have helped?

A refutation here is a realistic outcome, and each prediction below says what it would
change in Paper D.

**What this study can show, and what it cannot.** It can estimate how often outage
classes occur in *published provider postmortems* and test the model's class system
against them. It cannot estimate the population of all outages (unpublished incidents,
other providers, ISP and telecom outages such as the FAA event are outside the frame),
and its counterfactual variable (V8) is a coder judgement from text, the weakest part of
the design. Those limits are reported with the results.

## 1. Provenance and contamination disclosure

- Written before any postmortem in the frame was coded and without reading the frame's
  postmortems for this purpose.
- The predictor already knows, from memory, several famous incidents that fall inside the
  window or just outside it (a large AWS us-east-1 event in October 2025 attributed to
  DNS, an Azure Front Door event in October 2025, a Cloudflare event in November 2025,
  a Google Cloud event in June 2025) and, from search on the day of writing, the
  3 September 2026 event in which ChatGPT, Claude and Grok were down together alongside
  Microsoft 365 disruption. Every incident gets a `known_before_freeze` flag (V10).
  **All results are reported twice: with and without flagged incidents.**
- The 13 November 2026 FAA and Microsoft events are outside the window (no postmortem yet)
  and serve as a later out-of-sample check (section 9), not as data.
- The author who wrote Paper D is also coder C1. This is not blind. Mitigations: a second
  coder who has not seen the predictions (C2), an adjudicator (C3), reliability gates
  (section 5), and publication of the full coding sheet.

## 2. Hypotheses and their link to Paper D

| ID | Claim (population level) | Paper D counterpart |
|---|---|---|
| E1 | Among multi-region or global incidents, most trace to a shared control-plane, identity, DNS, configuration-distribution or global dependency | H16, H20, the central framing |
| E2 | Changes (configuration pushes, software releases, capacity or network upgrades) are a large share of triggers | motivation, the Microsoft network-upgrade narrative |
| E3 | Tenant isolation would rarely have preserved service in multi-region or global incidents | H16 "wrong cut" |
| E4 | Independent multipath or multi-provider helps for path and physical failures much more than for control-plane failures | H17 "independence, not count" |
| E5 | Where a fallback, failover or rollback is mentioned, a substantial share fail, are slow, or were untested | H18 "tested fallback" |
| E6 | Incidents involving a central controller or global orchestrator have wider blast radius | H20 "controller is a dependency" |
| E7 | In multi-region or global incidents, redundancy customers relied on often failed together | H17, H19 |
| E8 | The model's classes cover the data: almost every incident can be assigned a plane and a trigger | taxonomy completeness |

## 3. Sampling frame (frozen before coding)

**Window:** 1 January 2023 to 31 October 2026 (publication date of the report).
**Providers:** AWS, Microsoft Azure (post incident reviews), Google Cloud (incident
reports), Cloudflare (postmortem blog posts). No provider may be added after the freeze.

**Eligibility (all must hold):**

1. An official provider-authored report exists (summary, post incident review, postmortem).
2. The report states a root cause or triggering event.
3. Customer-visible impact stated as at least 30 minutes.
4. The incident is not a single-customer event, a planned maintenance notice, or a
   security breach disclosure (attack-caused service outages are eligible).

**Selection:** build the list of all eligible reports per provider from the provider's
official index. If a provider has more than 40, take a random sample of 40 with
`random.Random(2026).sample(sorted_ids, 40)` over incident IDs sorted lexicographically.
Target total: 60 to 160. Commit the list with report URLs, dates and a SHA-256 of each
saved report text **before** coding starts (`study/frame.csv`). Reports with the same root
cause are merged into one incident and the choice recorded.

**Pilot:** up to 5 reports, taken from outside the frame, may be used to test the rubric
before the freeze; they never enter the analysis.

## 4. Codebook

One row per incident. Every non-trivial code needs an **evidence** pointer (section
heading or paragraph number in the saved report). "Unclear" is a valid and often correct
answer; it is never guessed away.

| Var | Name | Values | Decision rule |
|---|---|---|---|
| V1 | Trigger class | `config_change`, `software_release`, `capacity_or_network_upgrade`, `hardware_or_physical`, `overload_or_cascade`, `security_attack`, `third_party_or_upstream`, `other`, `unclear` | The first cause the report labels root cause or trigger. If several, the one it calls root cause; otherwise the earliest in its timeline. Secondary trigger optional (V1b). |
| V2 | Failed plane | `data_plane`, `control_plane`, `identity_auth`, `dns_naming`, `config_distribution_orchestration`, `network_backbone_physical`, `storage_or_database_service`, `other`, `unclear` | The component whose failure produced most customer impact, per the report. |
| V3 | Shared dependency | `shared_global`, `shared_regional`, `localized`, `unclear` | `shared_global` if the failed dependency served customers or regions across the provider (global control plane, identity, DNS, config system). `shared_regional` if shared inside one region. `localized` otherwise. |
| V4 | Blast radius | `single_zone`, `single_region`, `multi_region`, `global` | As stated in the report. If unstated, `unclear` is not allowed; use the widest scope the report names. |
| V5 | Independence breach | `yes`, `no`, `unclear` | `yes` if the report says redundancy that was supposed to be independent (zones, regions, paths, replicas) failed together or lost the same dependency. |
| V6 | Fallback outcome | `none_mentioned`, `worked`, `failed_or_not_triggered`, `slow_or_manual` | Any failover, rollback, bypass or manual workaround the report mentions. Time to mitigate recorded in V9. |
| V7 | Central controller involved | `yes`, `no`, `unclear` | `yes` if a centralised controller, orchestrator or global config system's failure or bad push drove the impact. |
| V8a | Tenant isolation would have retained service | `yes`, `no`, `unclear` | Counterfactual from the text: would a customer in an isolated tenant (own VPC/account/gateway) have retained service? |
| V8b | Independent multipath or multi-provider would have retained service | `yes`, `no`, `unclear` | Would a customer using independent paths or an independent second provider have retained service? |
| V8c | Tested local fallback would have retained service | `yes`, `no`, `unclear` | Would a customer with a pre-tested local fallback have retained service? |
| V9 | Duration | minutes (integer) | From the stated start to stated full recovery. |
| V10 | Known before freeze | `yes`, `no` | Predictor recognised the incident when the frame was built. |

**Counterfactual rule (V8).** Code `yes` or `no` only when the report text itself supports
it (for example, "customers with a second provider were unaffected"). Otherwise `unclear`.
Unclear is excluded from the denominator and its count is reported.

## 5. Coding protocol and gates

- **C1:** the author. **C2:** an independent coder who has the codebook and the reports but
  not this predictions file. If no human C2 exists, an LLM coder is allowed only if the
  model name, version and full prompt are committed beforehand; this is declared in the
  report as a limitation. **C3:** adjudicates every disagreement.
- Both coders work independently on all incidents. Disagreements go to C3; the final code
  is C3's, and the raw C1 and C2 codes are published.
- **Reliability gate (per variable):** Cohen's kappa (unweighted) between C1 and C2 on the
  raw codes. A variable with kappa below 0.60 is reported as unreliable and every
  prediction depending on it is **INVALID**, not refuted.
- **Size gate:** a prediction about a subset needs at least 30 eligible incidents in that
  subset; below that its verdict is **INCONCLUSIVE**.
- **Frame gate:** the SHA-256 list must match the saved reports at analysis time.
- **Duplicate gate:** merged duplicates are reported, and no root cause counts twice.

## 6. Predictions and verdict rules

Let `S_big` be the incidents with V4 in `{multi_region, global}`. Intervals are 95 % Wilson
for one proportion and 95 % Newcombe for a difference of two proportions. "Credence" is the
probability that the **claim holds in the population**; the verdict can still be
INCONCLUSIVE because of sample size.

| ID | Claim | Estimand | Rule | Credence |
|---|---|---|---|---:|
| E1 | Control-plane concentration | share of `S_big` with V3 = `shared_global` **or** V2 in `{control_plane, identity_auth, dns_naming, config_distribution_orchestration}` | claim: share >= 0.50. CONFIRMED if Wilson lower >= 0.50; REFUTED if Wilson upper < 0.50 | 80 % |
| E2 | Change-induced | share of all incidents with V1 in `{config_change, software_release, capacity_or_network_upgrade}` | claim: share >= 0.30. Same rule with 0.30 | 70 % |
| E3 | Isolation rarely helps | share of `S_big` with V8a = `yes` (excluding unclear) | claim: share <= 0.20. CONFIRMED if Wilson upper <= 0.20; REFUTED if Wilson lower > 0.20 | 80 % |
| E4 | Independence helps selectively | `p_P - p_C`, where `p_P` = share with V8b = `yes` among incidents with V1 = `hardware_or_physical` or V2 = `network_backbone_physical`, and `p_C` = same share among V2 in `{control_plane, identity_auth, dns_naming, config_distribution_orchestration}` | claim: difference >= 0.25. CONFIRMED if point >= 0.25 and Newcombe lower >= 0.10; REFUTED if Newcombe upper < 0.25 | 70 % |
| E5 | Fallback is the weak link | share with V6 in `{failed_or_not_triggered, slow_or_manual}` among incidents with V6 != `none_mentioned` | claim: share >= 0.20. Wilson rule with 0.20 | 55 % |
| E6 | Controllers widen blast radius | ordinal V4 (`single_zone` < `single_region` < `multi_region` < `global`) for V7 = `yes` versus V7 = `no` | one-sided Mann-Whitney. CONFIRMED if p < 0.05 and the `yes` group is wider; REFUTED if the `yes` median rank is not above the `no` group or p > 0.50; else INCONCLUSIVE | 60 % |
| E7 | Redundancy fails together | share of `S_big` with V5 = `yes` (excluding unclear) | claim: share >= 0.40. Wilson rule with 0.40 | 60 % |
| E8 | The classes cover the data | share of all incidents with V1 != `unclear`/`other` **and** V2 != `unclear`/`other` | claim: share >= 0.80. Wilson rule with 0.80 | 65 % |

All eight are tested on the full coded set and again without incidents flagged
`known_before_freeze`; both verdicts are reported, and a disagreement between them is
reported as a finding.

## 7. What each outcome means for Paper D

| Outcome | Consequence |
|---|---|
| E1 confirmed | The central framing (concentration in shared control planes) has empirical support in provider postmortems |
| E1 refuted | Paper D's thesis is weakened: most large outages are not control-plane concentration; the paper must say what they are |
| E2 confirmed | Change management, not hardware, is the dominant trigger; the model needs an explicit "change" event class |
| E3 confirmed, E4 confirmed | Matches H16 and H17 qualitatively; still a text-based judgement, so claim only "consistent with" |
| E3 refuted | Tenant isolation sometimes helps; soften the "wrong cut" claim to specific classes |
| E4 refuted | "Independence, not count" is not visible in postmortem text; do not claim it empirically |
| E5 confirmed | Supports H18: untested or slow fallbacks are common; quantify from V6 and V9 |
| E5 refuted | Fallbacks mostly work when present; the paper's emphasis on testing them needs a different argument |
| E6 confirmed | Supports H20; controllers widen scope |
| E7 confirmed | Redundancy that is not independent is common; supports the independence index idea |
| E8 refuted | The taxonomy is incomplete; the unlabeled share is the list of new classes to add |
| Many INVALID (low kappa) | The rubric is too subjective for text coding; report that and stop |

## 8. Analysis plan

1. `tools/analyze_postmortems.py` computes every table and verdict from `study/coded.csv`,
   `study/frame.csv` and the two raw coder files. Write it and test it on **synthetic**
   coded data **before** any real coding is read, so no analysis choice depends on results.
2. Outputs: the coding sheet, kappa per variable, each prediction's estimand with its interval,
   the with/without-known comparison, the `unclear` counts per variable, and a Brier score over
   the credences (INCONCLUSIVE and INVALID unscored).
3. No exploratory finding is reported as a result unless labelled exploratory.

## 9. Interpretation limits (fixed in advance)

- **Survivorship and disclosure bias:** only incidents the provider chose to explain; the four
  providers explain at very different depths and cadences.
- **Not a population of outages:** ISP, telecom, power and enterprise outages are outside the
  frame, including the FAA event of 13 November 2026.
- **Self-reported causes:** postmortems can omit contributing factors.
- **Counterfactuals are judgements:** V8 is weakest; its `unclear` share is reported and may
  be large.
- **Non-independence:** related incidents share causes; duplicates are merged, but clustering
  by provider is not modelled.
- **Author not blind:** mitigated, not removed.
- **Time effects:** disclosure norms changed over the window.
- **Out-of-sample check:** once Microsoft and the relevant AI providers publish postmortems for
  the November 2026 events, code them with the same codebook and report them separately,
  without adding them to the analysis set.

## 10. Credence table (for calibration scoring)

| Prediction | Credence |
|---|---:|
| E1 | 80 % |
| E2 | 70 % |
| E3 | 80 % |
| E4 | 70 % |
| E5 | 55 % |
| E6 | 60 % |
| E7 | 60 % |
| E8 | 65 % |

Sum of (1 - credence) is 2.6 expected refutations. If none occurs, the predictions were too
safe or the thresholds too loose; if INCONCLUSIVE dominates, the frame was too small.

## 11. Freeze procedure

1. Commit this file.
2. Build `study/frame.csv` and the saved reports; commit with hashes.
3. Commit the coder prompt (if an LLM is C2) and the analysis script with its synthetic test.
4. Code, adjudicate, analyse, report all dispositions.
5. Append addenda only.

## 12. Addenda

(none yet)
