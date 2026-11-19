# Postmortem study (M8): status after two blind LLM coding passes

**This is not the protocol's verdict.** The frozen protocol requires an author-coded C1, a kappa gate between C1 and C2, and C3 adjudication. This run has two independent blind passes by the same model configuration (`C2` and the replicate `C2b`) and no C1 and no C3, so E1-E8 stay unadjudicated. Every kappa below is C2-vs-C2b, not C1-vs-C2.

## Frame

- incidents in the frozen frame: **88**
- eligible and not a duplicate: **87**
- coded by C2: **87**

## Coder reliability, C2 vs C2b (unweighted Cohen's kappa)

| Variable | n | kappa | raw agreement | gate >= 0.60 |
|---|---:|---:|---:|---|
| V1_trigger | 88 | 0.926063 | 0.943182 | PASS |
| V1b_secondary_trigger | 88 | 0.681489 | 0.840909 | PASS |
| V2_failed_plane | 88 | 0.7942 | 0.829545 | PASS |
| V3_shared_dependency | 88 | 0.788969 | 0.863636 | PASS |
| V4_blast_radius | 88 | 0.882195 | 0.920455 | PASS |
| V5_independence_breach | 88 | 0.65282 | 0.806818 | PASS |
| V6_fallback_outcome | 88 | 0.675144 | 0.795455 | PASS |
| V7_central_controller | 88 | 0.724731 | 0.818182 | PASS |
| V8a_tenant_isolation_retained | 88 | 0.691499 | 0.954545 | PASS |
| V8b_multipath_or_multiprovider_retained | 88 | 0.705122 | 0.920455 | PASS |
| V8c_tested_local_fallback_retained | 88 | 0.582444 | 0.954545 | BELOW 0.60 |
| V9_duration_minutes | 88 | 0.930799 | 0.931818 | PASS |
| V10_known_before_freeze | 88 | 1.0 | 1.0 | PASS |

Disagreeing cells across all variables: **125** over 88 incidents.

## Unclear counts (C2 codes)

| Variable | n | unclear |
|---|---:|---:|
| V1_trigger | 88 | 28 |
| V1b_secondary_trigger | 88 | 0 |
| V2_failed_plane | 88 | 8 |
| V3_shared_dependency | 88 | 14 |
| V4_blast_radius | 88 | 0 |
| V5_independence_breach | 88 | 45 |
| V6_fallback_outcome | 88 | 0 |
| V7_central_controller | 88 | 33 |
| V8a_tenant_isolation_retained | 88 | 81 |
| V8b_multipath_or_multiprovider_retained | 88 | 74 |
| V8c_tested_local_fallback_retained | 88 | 83 |
| V9_duration_minutes | 88 | 4 |
| V10_known_before_freeze | 88 | 0 |

## Verdicts, scenario `replicate-kappa` (scored on C2 codes)

| ID | n | estimate | 95% interval | verdict | reason |
|---|---:|---:|---|---|---|
| E1 | 56 | 0.786 | [0.662, 0.873] | **CONFIRMED** | Wilson [0.6618, 0.8729] vs threshold 0.5 |
| E2 | 87 | 0.414 | [0.316, 0.519] | **CONFIRMED** | Wilson [0.3161, 0.5188] vs threshold 0.3 |
| E3 | 6 | 0.000 |  | **INCONCLUSIVE** | size gate: n=6 < 30 |
| E4 | 10 |  |  | **INCONCLUSIVE** | size gate: path n=5, control n=5 |
| E5 | 59 | 0.864 | [0.755, 0.930] | **CONFIRMED** | Wilson [0.7546, 0.9297] vs threshold 0.2 |
| E6 | 54 |  |  | **INCONCLUSIVE** | size gate: yes n=32, no n=22 |
| E7 | 24 | 0.958 |  | **INCONCLUSIVE** | size gate: n=24 < 30 |
| E8 | 87 | 0.598 | [0.493, 0.694] | **REFUTED** | Wilson [0.4926, 0.6945] vs threshold 0.8 |

## Verdicts, scenario `no-reliability` (scored on C2 codes)

| ID | n | estimate | 95% interval | verdict | reason |
|---|---:|---:|---|---|---|
| E1 | 56 | 0.786 |  | **INVALID** | kappa unavailable or below 0.60: V3_shared_dependency, V2_failed_plane, V4_blast_radius |
| E2 | 87 | 0.414 |  | **INVALID** | kappa unavailable or below 0.60: V1_trigger |
| E3 | 6 | 0.000 |  | **INVALID** | kappa unavailable or below 0.60: V4_blast_radius, V8a_tenant_isolation_retained |
| E4 | 10 |  |  | **INVALID** | kappa unavailable or below 0.60: V1_trigger, V2_failed_plane, V8b_multipath_or_multiprovider_retained |
| E5 | 59 | 0.864 |  | **INVALID** | kappa unavailable or below 0.60: V6_fallback_outcome |
| E6 | 54 |  |  | **INVALID** | kappa unavailable or below 0.60: V4_blast_radius, V7_central_controller |
| E7 | 24 | 0.958 |  | **INVALID** | kappa unavailable or below 0.60: V4_blast_radius, V5_independence_breach |
| E8 | 87 | 0.598 |  | **INVALID** | kappa unavailable or below 0.60: V1_trigger, V2_failed_plane |

## How to read the scenarios

- `replicate-kappa` applies the measured C2-vs-C2b kappa to the frozen gate: a variable below 0.60 turns its predictions into INVALID, which is the protocol's own treatment of an unreliable variable.
- `no-reliability` is the strict protocol position when no independent human coder exists: kappa unavailable, so every prediction is INVALID.
- Neither scenario is a finding about providers. The author's C1 and a C3 remain the missing inputs.
