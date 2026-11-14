# Postmortem coder prompt (C2)

**Status:** prepared, not yet instantiated. If C2 is an LLM, the model name,
version and this prompt must be committed **before** any report is coded, and
the C2 session must receive only this prompt, the codebook and one report. It
must not receive the predictions file, the hypotheses, or the other coder's
codes.

## Frozen header (fill before use)

| Field | Value |
|---|---|
| Coder ID | C2 |
| Model name | `[HUMAN: fill exact model name]` |
| Model version / API snapshot | `[HUMAN: fill exact version or snapshot date]` |
| Prompt commit | `[HUMAN: fill git commit of this file]` |
| Codebook commit | `[HUMAN: fill git commit of docs/postmortem-study-predictions.md]` |
| Date coding started | `[HUMAN: YYYY-MM-DD]` |

If the model name or version is not recorded, the run is not a valid C2 and the
kappa gate cannot be interpreted.

## What you receive

You receive:

1. The codebook in `docs/postmortem-study-predictions.md`, section 4.
2. Exactly one saved report text, identified by `incident_id`.
3. This prompt.

You do **not** receive the predictions (E1-E8), the hypotheses, the other
coder's codes, or any summary of the expected result.

## Task

Read the report and assign the variables in the codebook. One row per incident.
Every non-trivial code needs an evidence pointer: a section heading, paragraph
number, or short quoted phrase from the report. "Unclear" is a valid answer and
must not be guessed away. Do not use outside knowledge of the incident; code
only what the report says. If the report does not state a fact, code `unclear`
where the codebook allows it.

Return one CSV row with exactly these fields:

```text
incident_id,provider,report_url,report_sha256,publication_date,coder,V1_trigger,V1b_secondary_trigger,V2_failed_plane,V3_shared_dependency,V4_blast_radius,V5_independence_breach,V6_fallback_outcome,V7_central_controller,V8a_tenant_isolation_retained,V8b_multipath_or_multiprovider_retained,V8c_tested_local_fallback_retained,V9_duration_minutes,V10_known_before_freeze,evidence_V1,evidence_V2,evidence_V3,evidence_V4,evidence_V5,evidence_V6,evidence_V7,evidence_V8,notes
```

Set `coder=C2`. Leave `V10_known_before_freeze` at `no` unless the frame builder
already marked it; do not infer it from the incident's fame.

## Values

- **V1** `config_change|software_release|capacity_or_network_upgrade|hardware_or_physical|overload_or_cascade|security_attack|third_party_or_upstream|other|unclear`
- **V1b** same set, or blank.
- **V2** `data_plane|control_plane|identity_auth|dns_naming|config_distribution_orchestration|network_backbone_physical|storage_or_database_service|other|unclear`
- **V3** `shared_global|shared_regional|localized|unclear`
- **V4** `single_zone|single_region|multi_region|global` (no `unclear`; use the widest scope the report names)
- **V5, V7, V8a, V8b, V8c** `yes|no|unclear`
- **V6** `none_mentioned|worked|failed_or_not_triggered|slow_or_manual`
- **V9** integer minutes from stated start to stated full recovery.
- **V10** `yes|no`.

## Decision rules to apply

- **V1:** the first cause the report calls root cause or trigger. If several,
  the one it calls root cause; otherwise the earliest in its timeline.
- **V2:** the component whose failure produced most customer impact, per the
  report.
- **V3:** `shared_global` if the failed dependency served customers or regions
  across the provider; `shared_regional` if shared inside one region;
  `localized` otherwise.
- **V4:** as stated. If unstated, use the widest scope the report names; do not
  code `unclear`.
- **V5:** `yes` if redundancy that was supposed to be independent (zones,
  regions, paths, replicas) failed together or lost the same dependency.
- **V6:** any failover, rollback, bypass or manual workaround the report
  mentions. Record the time to mitigate in V9.
- **V7:** `yes` if a centralised controller, orchestrator or global config
  system's failure or bad push drove the impact.
- **V8a/V8b/V8c:** counterfactuals from the text only. Code `yes` or `no` only
  when the report text itself supports it; otherwise `unclear`. Examples:
  "customers with a second provider were unaffected" supports V8b=`yes`;
  "the second region failed with the first" supports V8b=`no`. Do not reason
  from what a well-designed system would have done.

## Evidence pointers

For each of V1, V2, V3, V4, V5, V6, V7 and V8, give one pointer:

- a section heading, e.g. `What happened?`;
- a paragraph number, e.g. `p. 3, para 2`;
- or a short quoted phrase, e.g. `"the configuration change was rolled back"`.

If the evidence is absent, write `unclear` in the variable and `no statement
found` in the evidence field. Do not fabricate a pointer.

## Output discipline

- One row per incident; do not merge incidents.
- Do not read or use the predictions file.
- Do not change the report text or the codebook.
- If the report is ambiguous, prefer `unclear` and explain in `notes`.
- Return only the CSV row and, if needed, a short note. Do not return a
  narrative verdict.

## Single-report template

```text
incident_id: <ID>
report_sha256: <hash from frame.csv>
provider: <AWS|Microsoft Azure|Google Cloud|Cloudflare>
publication_date: <YYYY-MM-DD>

<report text>

Apply the codebook and return the CSV row described above.
```
