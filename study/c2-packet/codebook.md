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

