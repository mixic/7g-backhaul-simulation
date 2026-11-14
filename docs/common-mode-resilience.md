# Research note: isolation and multipath as the two resilience axes for cooperative AI-dependent backhaul

**Status: proposal only.** This note defines the research question, a two-axis
model and five falsifiable hypotheses. It contains no implementation, no
simulation and no results. Nothing here should be cited as a measurement.

The topic comes from a simple structural observation about recent outages: a
legacy router failure and a cloud/identity failure have different triggers but
the same propagation signature — a shared dependency with no independent failure
domain behind it. The engineering response has two halves, and they are not
substitutes:

- **Multipath and diversity** keep service running while a path, link or provider
  degrades.
- **Isolation** stops a fault from propagating across a boundary at all.

Concentration without both is not scale; it is a single point of failure with a
business model. This note turns that sentence into a model that can be tested.

## 1. The two axes, and the third leg

| Axis | Question it answers | Failure it addresses | What it cannot do |
|---|---|---|---|
| **Multipath / diversity** | Can service continue when one path or provider degrades? | Independent link, path and provider failures | Cannot survive a fault shared by every path (common control plane, shared identity/API, shared SRLG) |
| **Isolation** | Can a fault be prevented from crossing a boundary? | Propagation across tenants, providers, IT/OT, control planes | Cannot by itself preserve service when the isolated side has no autonomous fallback |

**Tested fallback** is the third leg, but it is a test condition rather than a
third axis: an isolation boundary that leaves the protected side without capacity
converts a provider outage into a local outage, and an unexercised fallback is a
control arm, not a solution.

### The biological parallel, used carefully

The brain tolerates damage through **distributed representation and parallel
pathways** — the analogue of multipath and diversity — while the blood–brain
barrier and compartmentalisation provide **selective isolation**, and shared
perfusion is a dependency no local boundary can cut. The analogy is useful for
generating hypotheses, not as evidence that a bio-inspired network control will
work: the repository's Paper B is a reminder that continuous bio-inspired control
did not beat static per-flow isolation in the packet testbed.

## 2. Isolation as graph cuts

Isolation categories are different cuts in a dependency graph:

| Isolation | Cuts | Leaves uncut |
|---|---|---|
| Tenant isolation (VPC/IAM/hypervisor) | tenant → tenant | tenant → provider control plane, shared DNS/identity/API |
| Hardware isolation (TEE, per-workload VM) | workload → host/other workloads | workload → provider control plane |
| Provider diversity | provider A → provider B | shared identity/API/client stack, global dependencies |
| Control-plane independence | a shared identity/API plane | local dependencies |
| Physical one-way (data diode) | inbound paths into the protected side | outbound telemetry; the need for a local autonomous fallback |

The **data-diode** row is the category cloud generally lacks: direction is
enforced in hardware, not configuration, so the inbound connection cannot be used
to reach the protected side. The consequence is architectural, not cosmetic: the
protected side can no longer receive control from the cloud and must run a local
fallback. The rail signalling example in the discussion is motivating context, not
a validated case study; its product claims are not independently verified here.

## 3. Multipath as path diversity and self-scaling

Multipath is only as good as the independence of its paths. Three properties
matter, and they are often conflated:

1. **Path multiplicity** — the number of candidate paths.
2. **Disjointness** — whether paths share links, nodes or a shared-risk link
   group (SRLG). Multiple paths over the same conduit are one failure domain.
3. **Control independence** — whether all paths depend on the same identity, DNS,
   API gateway or AI endpoint.

Self-scaling cooperative backhaul adds a fourth property:

4. **Controller locality** — whether capacity reallocation is decided locally or
   by a shared cooperative controller. A global controller is a new common-mode
   carrier: if it fails, the multipath advantage disappears.

A useful composite metric is the **path independence index**: the fraction of
candidate paths that fail independently under the tested event set. It is the
multipath analogue of blast radius.

## 4. The interaction: a 2×2 of regimes

| | **Low isolation** | **High isolation** |
|---|---|---|
| **Low multipath** | Concentration: one provider, one path. Maximum efficiency, maximum common-mode exposure. | Compartmentalised: a boundary protects, but the protected side is a hard partition with only local capacity. |
| **High multipath** | Survivable to independent failures, exposed to shared control-plane/API faults; multipath can amplify a correlated failure because every path fails together. | Resilient fabric: independent paths across boundaries, with a tested local fallback. Higher cost and operational complexity. |

The two axes are orthogonal: adding paths does not cut the control-plane edge,
and adding a boundary does not create capacity on the protected side. The
hypothesis is that tail availability requires both, plus the tested fallback.

## 5. Hypotheses (draft; thresholds to be frozen before code)

**H16 — the isolation mismatch.** In a dependency model with a shared provider
control plane, tenant-level logical isolation does not reduce the blast radius of
a control-plane failure by more than a small frozen margin, because the shared
node lies outside the tenant boundary. *Refuted if* tenant isolation reduces the
blast radius by at least the threshold.

**H17 — the multipath disjointness condition.** Multipath reduces goodput loss
under independent link/path failures, but its advantage over a single path
vanishes for a common-mode event that affects every candidate path (shared SRLG,
shared control plane, shared AI endpoint). The gain is predicted to scale with the
path independence index, not with the number of paths. *Refuted if* multipath
retains a large advantage under a shared-fate event, or if path count alone
predicts the gain.

**H18 — the isolation-alone condition.** A physical one-way boundary (or an
equivalent hard cut) prevents propagation across the boundary but leaves the
protected side as a hard partition; its availability is bounded by local fallback
capacity. *Refuted if* an isolated side without a local fallback maintains
service at the same level as the multipath arm.

**H19 — the interaction.** Multipath, isolation and a tested fallback together
produce higher tail availability than any single-axis arm, and the joint gain is
super-additive: the combined arm outperforms the sum of the individual
improvements. *Refuted if* the combined arm is no better than the best single
axis, or if the gains add without interaction.

**H20 — the cooperative-controller trap.** Self-scaling that pools capacity
through a shared cooperative controller introduces a new common-mode dependency:
a controller failure erases the multipath gain. Partition-tolerant, local
reallocation restores it. *Refuted if* a centralized controller is no more fragile
than a local one under the tested events.

## 6. Model sketch

A deployment is a graph `G = (V, E)` with

- **tenants** with path sets `P_t` (not a single path),
- **backhaul links** with capacities, latencies and SRLG memberships,
- **provider/control-plane nodes** (identity, DNS, API gateway, AI endpoint),
- **shared dependencies** (client SDK/identity configuration, public DNS, the AI
  API contract, the network path),
- **local fallback** nodes (`F`) that run without the provider,
- **a cooperative controller** (local or global) that reallocates capacity.

An edge `u → v` means `v` cannot meet its function when `u` is down. A tenant is
served when at least one path in `P_t` reaches a working serving path, or when a
working fallback is active. Multipath is k-disjoint routing over `P_t` with
capacity splitting and self-scaling to surviving paths. Isolation is a cut set on
`E`; a data diode removes inbound edges across the boundary.

Failure events have an independent component (per link/node) and a common-mode
component (shared SRLG, identity plane, AI API, controller). The common-mode
process is sampled once per event, not per tenant — that is what makes it
common-mode.

Fallback has an activation time, a capacity fraction, a staleness bound and a
correct-activation probability that depends on the test interval. An untested
fallback is the control arm.

## 7. Experiment design (not run)

- **Topology:** the repository's 100-node heterogeneous backhaul (fibre,
  microwave, satellite), with k candidate paths per tenant and explicit SRLG
  memberships.
- **Arms:** A1 single path/single provider; A2 multipath over a shared control
  plane; A3 multipath with disjoint paths, shared control plane; A4 A3 plus
  independent control planes; A5 A4 plus a one-way boundary and a tested local
  fallback; A6 A5 with an untested fallback; A7 A5 with a global cooperative
  controller (to test H20).
- **Scenarios:** independent link failure; shared-risk link-group failure;
  provider control-plane/identity outage; AI API outage; correlated multi-provider
  event; controller failure.
- **Seeds:** 30 paired seeds; one scenario realisation per seed, shared by all
  arms.
- **Metrics:** goodput ratio under the event, per-tenant availability, recovery
  time, blast radius, path independence index, fallback activation time and
  staleness, cost, controller dependency.
- **Gates:** a failure must be observable and must propagate through the declared
  edges; an arm that cannot reach its fallback is INVALID, not a negative result.

## 8. Refutation and reporting

Each hypothesis has a frozen threshold before any code. Refutations are results
and are reported with their cause. In particular:

- if tenant isolation does reduce control-plane blast radius, H16 is refuted and
  the “wrong category” argument is weakened;
- if path count alone predicts multipath gain, H17 is refuted and the SRLG
  condition is not needed;
- if a hard boundary without local capacity keeps service, H18 is refuted;
- if the combined arm does not beat the best single axis, H19 is refuted;
- if a centralized cooperative controller is as robust as a local one, H20 is
  refuted.

## 9. Limits

- This is a **model**, not a measurement of any cloud, AI provider or rail
  system. The motivating outages are external anecdotes; root causes are not
  independently verified here and no result depends on them.
- Security is not evaluated. A data diode is treated as an availability and
  attack-surface boundary, not a cryptographic control.
- The vendor example from the discussion is context, not a validated case study.
- Political, regulatory and capital-market claims are out of scope.
- Failure distributions, SRLG memberships, fallback capacities and test intervals
  are stipulated and must be reported as such.
- The biological parallel is a hypothesis generator; it is not evidence that a
  bio-inspired controller will work in a network.

## 10. Relation to the existing project

Papers A (layering and middleboxes), B (bio-inspired control) and C (CRMR) study
how fields, controllers and metrics survive faults. This note adds the two-axis
resilience question — **isolation and multipath** — and ties it to the
repository's cooperative-backhaul and self-scaling modules rather than to the
name-fabric work.

If the hypotheses survive, the natural Paper D is *Isolation and Multipath:
Common-Mode Resilience for Cooperative AI-Dependent Backhaul*. The 7G backhaul
prototype is the instantiation: an AI-assisted control plane that depends on a
cloud model service, with a local degraded mode as the fallback and a cooperative
controller whose own centrality is part of the experiment.

## 11. Next steps

1. Freeze `docs/common-mode-predictions.md` with the thresholds, arms, scenarios
   and SRLG definitions before writing code.
2. Implement `simulation/common_mode.py` (multipath graph, SRLG failures, isolation
   cuts, fallback, controller locality) and `tools/benchmark_common_mode.py`.
3. Report paired-seed results, including refutations, and decide whether Paper D
   is warranted.

No part of this has been implemented or measured yet.
