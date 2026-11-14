# Research note: common-mode resilience and isolation categories for AI-dependent backhaul

**Status: proposal only.** This note defines a research question, four falsifiable
hypotheses and an experiment design. It contains no implementation, no simulation
and no results. Nothing here should be cited as a measurement.

The note exists because two discussions in the same week made the same structural
point from different directions: an FAA ground stop attributed to aging telecom
routers, and a cloud/identity outage that took down a hosted AI service and its
API. The root causes are different and are not independently verified here. The
question this note formalises is whether the *propagation mechanism* is the same:
a shared dependency with no independent failure domain behind it.

## 1. The claim under test

The motivating discussion argues three things:

1. **Tenant isolation is real but is the wrong category.** Hypervisors, VPCs,
   namespaces and IAM isolate tenants from each other; confidential computing
   isolates data from the host. None of them isolates a tenant from the provider,
   from the provider's control plane, or from the shared dependencies every
   tenant uses.
2. **The shared control plane is the common-mode carrier.** Identity, DNS, API
   gateways, model-serving endpoints and the network paths to them are shared by
   construction; a fault in one of them reaches every tenant at once.
3. **Physical one-way isolation and tested fallback are a separate category.**
   A hardware data diode enforces a direction in hardware, not configuration, so
   the inbound path cannot be used to reach the protected side. Resilience then
   depends on diversity, isolation and a fallback that has actually been tested.

These are engineering claims, and they are testable as a model. The discussion
also contains commercial, regulatory and capital-market commentary. That material
is motivation, not evidence, and it is deliberately outside the scope of this
note.

## 2. What needs to be separated

| Term | What it isolates | What it does not isolate |
|---|---|---|
| Tenant isolation (logical) | tenant → tenant | tenant → provider control plane, shared DNS/identity/API, the provider's own failure domain |
| Hardware isolation (TEE, per-workload VM) | workload → host/other workloads | workload → provider control plane, shared services |
| Provider diversity | provider A → provider B failure domain | shared identity/DNS/API standards, shared client stack, correlated global dependencies |
| Control-plane independence | a provider's identity/API plane | the tenant's own local dependencies |
| Physical one-way (data diode) | inbound paths into the protected side | outbound telemetry; the need for a local autonomous fallback |
| Tested fallback | a provider outage at the tenant | correctness of the fallback if it is never exercised |

The hypothesis is that these are *different cuts* in a dependency graph, and that
a deployment can have all of the first two and still have an uncut edge from a
shared control plane to every tenant. If that is true, "we have tenant
isolation" is not evidence of common-mode resilience.

## 3. Research questions

- **RQ1.** Does tenant-level logical isolation reduce the blast radius of a
  provider control-plane failure?
- **RQ2.** Does multi-provider diversity eliminate common-mode correlation, or
  does a shared client/identity/API layer preserve it?
- **RQ3.** What does a physically one-way boundary plus a tested local fallback
  buy in availability and recovery time, and what does it cost in staleness,
  throughput and operational effort?
- **RQ4.** Under a fixed budget and a given common-mode correlation, when is
  concentration the rational choice and when is diversity?

## 4. Hypotheses (draft; thresholds to be frozen before code)

**H16 — the isolation mismatch.** In a dependency model with a shared provider
control plane, adding tenant-level logical isolation does not reduce the blast
radius of a control-plane failure by more than a small margin (threshold to be
frozen, e.g. 5 percentage points of affected tenants), because the shared node is
outside the tenant boundary. *Refuted if* tenant isolation does reduce the blast
radius by at least the frozen threshold.

**H17 — diversity without independence.** Multi-provider deployment reduces the
probability of a simultaneous outage but does not make it the product of the
independent provider failure probabilities; a shared identity/API/client layer
leaves a residual correlation, so the observed joint-outage probability exceeds
the independent-product prediction by a factor to be frozen. *Refuted if* the
joint outage is statistically indistinguishable from the product.

**H18 — one-way isolation plus tested fallback.** A hardware one-way boundary
with a local, exercised fallback reduces tenant downtime under a provider outage
by at least a frozen margin, at a bounded cost in staleness/throughput, and the
benefit degrades as the fallback test interval grows. An untested fallback is
predicted to be worse than a tested one and may be worse than no fallback if it
fails on activation. *Refuted if* the one-way/fallback arm does not beat logical
isolation on downtime, or if the cost exceeds the frozen bound.

**H19 — the concentration threshold.** For a fixed budget and availability
target, there is a common-mode correlation threshold above which concentration
is cheaper than diversity, and below which diversity is cheaper. *Refuted if* one
architecture dominates for every correlation in the tested range.

These are model hypotheses. They are not claims about any named provider, and
they are not a security evaluation.

## 5. Model sketch

### 5.1 Dependency graph

A deployment is a directed graph `G = (V, E)`:

- **Tenants** `T`: application workloads with an availability SLO.
- **Provider regions/control planes** `P`: compute, identity, DNS, API gateway,
  model-serving endpoint.
- **Shared dependencies** `S`: client SDK/identity configuration, public DNS,
  the AI API contract, the network path.
- **Local fallback** `F`: a degraded mode that runs without the provider
  (cached model, static policy, local control loop).

An edge `u → v` means `v` cannot meet its function when `u` is down. The graph is
the object that isolation categories cut.

### 5.2 Isolation as cuts

- **Tenant isolation** removes edges between tenants; it does not remove
  `provider → tenant` edges.
- **Provider diversity** adds a second provider and its edges; it does not remove
  shared `S` edges.
- **Control-plane independence** removes shared identity/API edges by
  construction (separate credentials, DNS, gateways).
- **Physical one-way** removes *inbound* edges across the boundary; telemetry may
  still leave. The protected side must therefore have a local fallback, because
  the provider can no longer send control inward.
- **Tested fallback** is not a graph cut; it is a probability that the fallback
  activates correctly, improved by exercises.

### 5.3 Failure process

Each node has an independent failure process and a common-mode process shared by
a set of nodes (for example, a global identity service). A failure event marks a
node unavailable for a duration drawn from a scenario distribution. Availability
of a tenant is computed by reachability from its entry point to a functioning
serving path, or to a working fallback. Correlated events are injected by
sampling the shared process once per event, not per tenant.

### 5.4 Fallback

A fallback has an activation time, a capacity (fraction of load it can carry), a
staleness bound, and a probability of correct activation that depends on the test
interval. The model treats an untested fallback as a control arm, not as a
strawman: it is the common real deployment.

### 5.5 Metrics

- **Blast radius:** fraction of tenants below their availability SLO during an
  event.
- **Availability:** per-tenant time-based availability over the run.
- **Recovery time:** time from event start to the tenant's SLO being met again.
- **Staleness/throughput cost** of the fallback.
- **Operational cost:** extra providers, control-plane separation, test cadence.

## 6. Experiment design (not run)

- **Arms:** (A1) single provider, no isolation; (A2) single provider, tenant
  isolation; (A3) two providers, shared identity/API; (A4) two providers,
  independent control planes; (A5) A4 plus a one-way boundary and a tested local
  fallback; (A6) A5 with an untested fallback (control).
- **Scenarios:** single-region outage; identity/control-plane outage; AI API
  outage; correlated multi-provider event; injection through the shared client
  stack.
- **Seeds:** 30 paired seeds; one scenario realisation per seed, shared by all
  arms.
- **Analysis:** paired differences in blast radius and recovery; joint-outage
  probability against the independent-product baseline; a correlation sweep for
  H19; sensitivity to fallback test interval and capacity.
- **Gates:** a failure must be observable in the model and must propagate through
  the declared edge; an arm that cannot reach the fallback is INVALID, not a
  negative result.

## 7. Refutation and reporting

Each hypothesis has a frozen threshold before any code. A refutation is a result
and is reported with its cause. In particular, if tenant isolation does reduce
control-plane blast radius in the model, H16 is refuted and the
"wrong category" argument is weakened; if one-way isolation does not pay for its
operational cost, H18 is refuted.

## 8. Limits

- This is a **model**, not a measurement of any cloud or AI provider. The
  motivating outages are external anecdotes; their root causes are not
  independently verified here and no result will depend on them.
- Security is not evaluated. A data diode is treated as an availability and
  attack-surface boundary, not as a cryptographic control.
- The vendor example from the discussion (a rail signalling deployment with a
  hardware diode) is motivating context, not a validated case study.
- Political, regulatory and capital-market claims are out of scope.
- The model's failure distributions and correlations are stipulated and must be
  reported as such.

## 9. Relation to the existing project

Papers A (layering and middleboxes), B (bio-inspired control) and C (CRMR) study
how fields, controllers and metrics survive faults. This note adds a different
axis: **shared dependency structure**. It does not extend the name fabric or the
metric-space work; it asks whether the isolation a deployment claims is the
isolation its failure model needs.

If the hypotheses survive, the natural Paper D is *Concentration Without
Isolation: Common-Mode Failure and the Isolation Mismatch in AI-Dependent
Backhaul*. The 7G backhaul prototype is the instantiation: an AI-assisted
control plane that depends on a cloud model service, with a local degraded mode
as the fallback.

## 10. Next steps

1. Freeze `docs/common-mode-predictions.md` with the thresholds, arms and
   scenarios before writing code.
2. Implement `simulation/common_mode.py` (dependency graph, correlated failures,
   fallback) and `tools/benchmark_common_mode.py`.
3. Report paired-seed results, including refutations, and decide whether Paper D
   is warranted.

No part of this has been implemented or measured yet.
