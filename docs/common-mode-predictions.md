# Common-mode resilience predictions (H16-H20) — frozen before the run

**Status: FROZEN.** This file is committed before `simulation/common_mode.py`
exists. Constants below are the scenario definition and the pre-registered
thresholds. Results go in [`common-mode-results.md`](common-mode-results.md);
this file is not edited afterwards. The freeze commit is recorded there.

The experiment is a **flow-level simulation testbed**, not a measurement of a
production network. The scenario is a stipulated 7G cooperative AI backhaul; the
links, capacities, failure times and fallback probabilities are design choices,
not observations. The point is to test the structural claims, not to estimate an
operator's availability.

## 1. Principles the model encodes

1. **Availability is a conjunction, not a path property.** A tenant is served
   only if its data path, its control plane, its tenant boundary and (where
   required) its fallback are available at the same time.
2. **Multipath counts only across independent failure domains.** Paths that share
   a conduit, a provider control plane or a shared control service are one path
   with extra steps.
3. **Isolation trades capability for containment.** A cut that removes a shared
   dependency can also remove the capability that dependency provided. A boundary
   without local capacity is a partition, not a mitigation.
4. **A fallback is a tested state.** It has an activation probability, a delay and
   a capacity fraction. An untested fallback is a control arm.
5. **The controller is a dependency.** Self-scaling through a global cooperative
   controller concentrates the very service it is meant to diversify.
6. **Common-mode events are sampled once per event, not per tenant.** A shared
   node fails for everyone at once; that is what makes it common-mode.

## 2. Hypotheses and frozen thresholds

All deltas are **percentage points of tenant demand**, averaged over tenants and
the event window. Each hypothesis is evaluated on the 30-seed mean; per-seed pass
fractions are reported as well.

### H16 — the isolation mismatch

> Tenant isolation reduces the blast radius of a tenant-shared fault but not the
> blast radius of a shared control-plane fault.

- Under `tenant_gw`: `A4 − A3 ≥ 50` points.
- Under `idp`: `|A4 − A3| ≤ 5` points.
- **Refuted** if either condition fails.

### H17 — the multipath disjointness condition

> Multipath gain tracks path independence, not path count.

- Under `srlg`: `A3 − A2 ≥ 20` points.
- Under `link`: `A2 − A1 ≥ 50` points.
- **Refuted** if either condition fails.

### H18 — the isolation-alone condition

> A one-way boundary with a tested local fallback preserves service when the
> shared control plane fails; a boundary without fallback does not.

- Under `ai`: `A6 − A5 ≥ 50` points and `A6 ≥ 80` points.
- Under `none`: `A5 − A6 ≤ 15` points (the normal-operation cost of isolation).
- **Refuted** if the AI gain is below 50 points, A6 is below 80, or the normal
  cost exceeds 15 points.

### H19 — the interaction

> Isolation and multipath are super-additive under a combined control-plane and
> path failure.

- Under `ai_link`, interaction
  `(A6 − A3) − (A9 − A1) ≥ 20` points.
- `A6 ≥ 80` points and `A3 ≤ 20` points.
- **Refuted** if the interaction is below 20 points or the absolute levels fail.

### H20 — the cooperative-controller trap

> A global cooperative controller is a new common-mode carrier; local
> reallocation is not.

- Under `controller_link`: `A5 − A8 ≥ 50` points.
- Under `none`: `|A5 − A8| ≤ 5` points.
- **Refuted** if the controller failure costs less than 50 points or the
  controller changes normal operation by more than 5 points.

## 3. Scenario: cooperative AI backhaul (stipulated)

Six edge tenants, three aggregation sites, three providers, two cloud regions,
one shared identity service, one shared DNS service, one shared AI control
endpoint, one shared tenant gateway, one global cooperative controller and six
local fallbacks.

### Nodes

| Node | Kind | Role |
|---|---|---|
| `e1`…`e6` | edge | tenant sites |
| `a1`…`a3` | aggregation | backhaul aggregation |
| `p1`…`p3` | provider | provider data plane |
| `p1-cp`…`p3-cp` | provider control | per-provider control plane |
| `c1`, `c2` | cloud | service regions |
| `idp` | shared control | global identity |
| `dns` | shared control | global name resolution |
| `ai` | shared control | AI policy/optimisation endpoint |
| `mt-gw` | shared tenant | multi-tenant gateway |
| `coop` | controller | global cooperative reallocation |
| `fb1`…`fb6` | fallback | local degraded-mode service |

### Data links (symmetric, both directions)

| Link set | Capacity | Latency | SRLG |
|---|---:|---:|---|
| `e_i → a_j` (18 links) | 1.05 Gbps | 1.0 + 0.25·(j−1) ms | `edge-i-j` (unique) |
| `a1 → p_k` (3 links) | 1.20 Gbps | 4.0 + 0.5·(k−1) ms | `agg-1` |
| `a2 → p_k` (3 links) | 1.20 Gbps | 5.0 + 0.5·(k−1) ms | `agg-2` |
| `a3 → p_k` (3 links) | 1.20 Gbps | 6.0 + 0.5·(k−1) ms | `agg-3` |
| `p1 → c1` | 1.50 Gbps | 8.0 ms | `prov-1-cloud-1` |
| `p2 → c1` | 1.50 Gbps | 8.5 ms | `prov-2-cloud-1` |
| `p3 → c2` | 1.50 Gbps | 9.0 ms | `prov-3-cloud-2` |

Only the listed provider→cloud links exist. A path is
`e_i → a_j → p_k → c_l`; its capacity is the minimum link capacity (1.05 Gbps),
its latency is the sum, and its SRLG set is the union of the link SRLGs.

All `a_j → p_k` links of one aggregation site share the SRLG `agg-j`: one conduit
failure at an aggregation site takes all of that site's provider links. This is
what makes a non-disjoint three-path set fail together.

### Tenants and demand

Six tenants, one per edge. Each tenant's offered demand is
`1.0 Gbps × U(0.95, 1.05)` per seed, drawn once and shared by all arms. A
tenant's paths all start at its edge and end at `c1` or `c2`.

### Shared dependencies

- **Shared control** (A1-A4): `idp`, `dns` and `ai` must all be up. If any is
  down, the tenant serves 0.
- **Independent control** (A5-A9): `idp` and `dns` are local; only `ai` is
  required unless the arm is one-way.
- **One-way boundary** (A6, A7, A9): `ai` is not on the availability path; the
  tenant runs local policy. Path-based service is multiplied by 0.9 (local
  policy efficiency); fallback service is not.
- **Tenant isolation** (A4-A9): `mt-gw` is not on the availability path. Without
  it, `mt-gw` failure is a total tenant outage.
- **Provider control** (`p_k-cp`): a path via provider `k` is unavailable when
  `p_k-cp` is down.
- **Global controller** (`coop`, A8 only): when `coop` is down, only the first
  path is used; local controller arms keep all paths.

## 4. Arms (frozen)

| Arm | Paths | Tenant isolation | Control | One-way | Fallback | Controller |
|---|---|---|---|---|---|---|
| A1 | 1 shortest | no | shared | no | none | none |
| A2 | 3 shortest | no | shared | no | none | local |
| A3 | 3 SRLG-disjoint | no | shared | no | none | local |
| A4 | 3 SRLG-disjoint | **yes** | shared | no | none | local |
| A5 | 3 SRLG-disjoint | yes | **independent** | no | none | local |
| A6 | 3 SRLG-disjoint | yes | independent | **yes** | **tested** | local |
| A7 | 3 SRLG-disjoint | yes | independent | yes | **untested** | local |
| A8 | 3 SRLG-disjoint | yes | independent | no | none | **global** |
| A9 | 1 shortest | yes | independent | yes | tested | none |

Path selection is fixed by the arm, not by the event:

- **1 shortest**: minimum latency; ties by path tuple.
- **3 shortest**: the three lowest-latency paths, overlap allowed.
- **3 SRLG-disjoint**: greedy by latency, each next path must not share an SRLG
  with an already selected path; if fewer than three exist, use what exists.

A1 and A9 use the same single path. A2's three paths are expected to share
`agg-1` because the `a1` links are the fastest. A3's paths are expected to use
one aggregation site each.

## 5. Fallback model

| Arm | Tested | Activation probability | Delay | Capacity |
|---|---|---|---|---|
| A6, A8, A9 | yes | 0.98 | 2 s | 0.50 Gbps |
| A7 | no | 0.60 | 8 s | 0.30 Gbps |

For each seed and tenant, `u ~ U(0,1)` is drawn once. A fallback activates when
its control plane or all of its paths are unavailable, and only if `u` is below
the arm's activation probability. The same `u` is used by every arm with a
fallback, so the comparison is paired. The fallback serves its capacity fraction
of demand; it is released 2 s after the primary path or control plane returns.

## 6. Events

All events start at `15 + U(0,10) s` and last `20 + U(0,10) s`; the run is 60 s.
The start and duration are drawn once per seed and shared by all arms.

| Event | Failure |
|---|---|
| `none` | no failure |
| `link` | `a1 → p1` down |
| `srlg` | all `a1 → p*` links down (`agg-1` conduit) |
| `backhaul_cut` | all `a* → p*` links down |
| `provider_cp` | `p1-cp` down |
| `idp` | `idp` down |
| `ai` | `ai` down |
| `tenant_gw` | `mt-gw` down |
| `controller_link` | `coop` down and `a1 → p1` down |
| `ai_link` | `ai` down and `a1 → p1` down |

`link` and `ai_link` use the link on A1's shortest path, so A1 is affected in
every seed. `controller_link` uses the same link, on A5's and A8's first path.

## 7. Metrics

For each arm, event and seed:

| Metric | Definition |
|---|---|
| `availability_event` | mean served/offered over tenants and ticks in the event window |
| `availability_overall` | mean served/offered over tenants and the whole 60 s |
| `recovery_s` | mean time from event start until a tenant first reaches 90 % for 3 consecutive ticks; event duration if never |
| `blast_radius` | fraction of tenants with event availability below 50 % |
| `path_independence` | largest subset of the arm's paths with distinct aggregation SRLG and distinct provider, divided by the number of paths |
| `fallback_rate` | fraction of tenants whose fallback activated |
| `cost_index` | `0.5·paths + 0.1·tenant_isolation + 0.1·independent_control + 0.1·one_way + 0.05·global_controller` |

`cost_index` is a stipulated accounting device, not a price.

## 8. Seeds and pairing

30 seeds, base 2026. For each seed the scenario, demand factors, event start and
duration, and fallback draws are generated once and used by all nine arms and all
ten events. The network, tenants, paths and failure model are identical across
arms; only the arm's mechanisms differ.

## 9. Expected outcome (stated in advance)

- A1 normal availability is 100 %; A2-A5 and A8 are 100 %; A6, A7 and A9 are
  about 90 % because the one-way boundary uses local policy without the AI
  capacity factor.
- Under `tenant_gw`, A3 is 0 and A4 is 100; under `idp`, A3 and A4 are both 0.
- Under `srlg`, A2 is 0 and A3 is 100; under `link`, A1 is 0 and A2 is 100.
- Under `ai`, A5 is 0 and A6 is about 90; under `none`, the A5-A6 gap is about
  10 points.
- Under `ai_link`, A6 is about 90, A3 is 0, A9 is about 50 and A1 is 0; the
  interaction is about 40 points.
- Under `controller_link`, A5 is 100 and A8 is 0.
- Under `backhaul_cut`, A6 is about 50 and A7 is about 18 (0.30 × 0.60).

These are predictions, not results. Any deviation is reported with its cause.

## 10. Refutation and reporting

Each hypothesis is scored on the 30-seed mean and on the per-seed pass fraction.
A refutation is reported as a result, not suppressed. In particular:

- if tenant isolation reduces the `idp` blast radius, H16 is refuted;
- if A2 keeps its advantage under `srlg`, H17 is refuted;
- if A6 does not preserve service under `ai`, H18 is refuted;
- if the interaction under `ai_link` is below 20 points, H19 is refuted;
- if the global controller costs nothing under `controller_link`, H20 is refuted.

The simulator and the benchmark are deterministic given a seed. The benchmark
writes per-seed rows and a per-event summary; the results document interprets
them.

## 11. What this does not test

- Packet-level behaviour, congestion control, queueing or TCP dynamics.
- Cryptographic security, key management or the data diode as a security control.
- Real providers, real identity services or real AI endpoints.
- The cost of operating a data diode or the update path behind it.
- Political, regulatory or capital-market claims.

The scenario is a testbed for the structural hypotheses, not a prediction of any
specific operator's outage.
