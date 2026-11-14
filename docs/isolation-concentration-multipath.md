# Concentration, Isolation, Multipath

## One risk and two independent mitigations

**Status: position and analysis draft, 14 November 2026.** This document makes
no new measurements. External events are cited as reported; their root causes are
not independently verified here, and no claim below depends on a particular root
cause being correct.

## Abstract

On 13 November 2026 the US Federal Aviation Administration halted departures
nationally after a telecommunications failure. The same week, a Microsoft cloud
outage — reported as a failed network capacity upgrade — coincided with
disruptions to AI services including Claude, ChatGPT and Grok. The triggers were
different. The signature was the same: a shared dependency with no independent
failure domain behind it, so a local fault reached every consumer at once.

The risk is **concentration**. The mitigations are **isolation**, which stops a
fault from crossing a boundary, and **multipath**, which keeps service running
across independent failure domains. They are independent: isolation does not
create capacity, and multipath does not cut a shared control plane. Cloud
isolation is the wrong category — tenant isolation and confidential computing
solve tenant-to-tenant, not tenant-to-provider or consumer-to-control-plane.
Physical one-way isolation is the category cloud lacks, and rail signalling shows
it is buildable: commercial off-the-shelf servers with hardware-enforced one-way
flow at the IT/OT boundary. Neither mitigation substitutes for the other, and both
need a tested fallback.

## 1. Two days, one signature

The FAA event is reported as a nationwide ground stop on Friday 13 November 2026,
lifted after a telecommunications outage; commentary attributed the proximate
constraint to legacy capacity that "got overloaded"
([UPI](https://www.upi.com/Top_News/US/2026/11/13/faa-grounds-all-flights/9251794604658/),
[TPR](https://www.tpr.org/news/2026-11-13/old-tech-blamed-for-the-ground-stop-that-caused-flight-chaos-it-got-overloaded)).
The Microsoft event began the previous day, lasted roughly eighteen hours and
spread from the Americas to global users, affecting Microsoft 365, Outlook, Teams,
OneDrive, Copilot, Defender and the Intune admin console. Microsoft reported a
faulty network capacity upgrade, no evidence of malicious activity, and a resolved
root cause with residual recovery
([DigitalToday, citing TechCrunch](https://www.digitaltoday.co.kr/cn/view/125685/microsoft-massive-service-outage-cause-still-unclear-no-evidence-of-malicious-activity)).
AI services were reported to be disrupted in the same window, with an Azure link
suspected rather than established
([Business Insider](https://www.businessinsider.es/big-tech/chatgpt-claude-caidos-apagon-microsoft-arrastra-ia_7060706_0.html),
[Mathrubhumi](https://english.mathrubhumi.com/technology/azure-outage-chatgpt-claude-grok-down-fij8a1wm)).

The two events do not share a mechanism. One is a telecommunications capacity
failure in a legacy-adjacent chain; the other is a network change in a modern cloud
control plane. That is the point. "Legacy" is not an explanation of the category,
because the modern stack reproduced the category without the legacy. Different
vintages, same propagation: a shared node fails, and every consumer behind it fails
together.

Whether the AI disruptions share the Microsoft root cause is a reported causal
chain, not a verified one. The structural claim does not need it: a shared cloud
network can carry many services at once, and that is exactly what makes it a
common-mode carrier.

## 2. Three keywords, two roles

The three words are not peers. **Concentration is the diagnosis; isolation and
multipath are the treatment.** The third leg, a tested fallback, is the condition
under which either treatment works.

### 2.1 Concentration is the risk

Let a service depend on a shared node `d` and on an independent part `i`. Its
availability is bounded by

```
A_service  ≤  A_d · A_i
```

Adding consumers to `d` increases scale, utilization and blast radius at the same
time. It does not add an independent failure domain; it widens the one that
already exists. That is why concentration is economically rational and
structurally dangerous: the same decision that lowers unit cost raises correlated
exposure. Stated in engineering terms, the political-economy diagnosis is a
dependency graph with one shared node and no independent failure domain behind it
— a single point of failure with a business model. The political-economy reading
is out of scope here; the graph is not.

### 2.2 Isolation is a cut

Isolation removes edges between failure domains. It answers: *can this fault cross
that boundary?* It does not answer: *is there capacity on the other side?* A cut
that leaves the protected side without a fallback converts a provider outage into a
local outage; a cut with a tested local fallback contains the fault. This is why
isolation is a boundary property, not an availability property.

### 2.3 Multipath is diversity

Multipath maintains service across independent failure domains. Its value is not
the number of paths but their independence: shared links, shared-risk link groups,
shared identity/DNS/API gateways and shared AI endpoints all collapse the path set
back into one failure domain. Under independent failures, availability improves
roughly as

```
A_paths  =  1 − Π (1 − a_i)
```

but under a common-mode event the same expression is capped by the shared
dependency's availability. Multipath cannot exceed the availability of what all
paths share. Paths that reconverge on the same control plane are one path with
extra steps.

### 2.4 Tested fallback is the condition

A fallback has an activation time, a capacity fraction, a staleness bound and a
correct-activation probability that depends on how often it is exercised. An
untested fallback is a control arm, not a mitigation. This is the difference
between an isolation boundary that contains a fault and one that merely relocates
it.

## 3. The category error in cloud isolation

Cloud isolation is real, and it solves the problem it was designed for:

| Isolation | Cuts | Leaves uncut |
|---|---|---|
| Logical tenant isolation (VPC, IAM, hypervisor) | tenant → tenant | tenant → provider control plane; shared DNS, identity and API |
| Confidential computing / TEEs | workload → host and other workloads | workload → provider control plane and shared dependencies |
| Region isolation | region → region | the global control plane; deployment concentration in one region |
| Provider diversity | provider A → provider B | the shared client stack, identity provider and API contract |

Tenant isolation was never the weak point. The shared control plane was. Public
postmortems repeatedly show the same shape: regions are isolated, yet deployments
concentrate in one of them; identity is global; a control-plane fault crosses
regional boundaries. The specific incidents — us-east-1 concentration, global
identity services, global propagation — are widely reported illustrations, not
evidence for the model. The model's claim is narrower: a cut that does not include
the shared node does not bound the blast radius.

## 4. The missing category: physical one-way isolation

A data diode enforces direction in hardware. The inbound path is absent, not
filtered, so a compromised or faulty control plane cannot reach across the
boundary. That is a different category from logical isolation, and it is the one
cloud architecture generally does not offer, because inbound control is the
management model.

Rail signalling provides an existence proof. Siemens Mobility describes
Signaling X as commercial off-the-shelf servers with the CoreShield data capture
unit enforcing one-way transfer at the IT/OT boundary, with safety logic decoupled
from any single vendor stack
([Siemens Mobility](https://www.mobility.siemens.com/global/en/portfolio/digital-solutions-software/cybersecurity/cybersecurity-rail-infrastructure/protection-of-ot-systems.html),
[CoreShield DCU](https://www.dex.siemens.com/industrial-iot/step-4-book-apps-and-extras/coreshield-data-capture-unit)).
This is a vendor-described architecture, not an independently evaluated result; it
establishes that the category is buildable, not that it is cheap or universally
applicable.

The engineering consequences are architectural:

- the protected side can no longer receive inbound control, so it must run a local
  autonomous fallback;
- telemetry can still flow out, so observability survives the cut;
- updates must take an out-of-band path, which becomes a new operational dependency
  to test;
- the boundary's availability is the fallback's availability, not the diode's.

A data diode is an availability and attack-surface boundary, not a cryptographic
control. Security is not evaluated here.

## 5. Multipath is diversity, not redundancy theatre

Three properties are routinely conflated:

1. **multiplicity** — how many candidate paths exist;
2. **disjointness** — whether paths share links, nodes or an SRLG;
3. **control independence** — whether all paths depend on the same identity, DNS,
   API gateway or AI endpoint.

A useful composite is the **path independence index**: the size of the largest
subset of candidate paths with pairwise independent failures, divided by the number
of candidate paths. It is the multipath analogue of blast radius.

Self-scaling cooperative backhaul adds a fourth property: **controller locality**.
Pooling capacity across paths and tenants increases utilization, but a global
cooperative controller is itself a shared dependency. If it fails, the multipath
advantage disappears at the moment it is needed. Partition-tolerant local
reallocation is the design that keeps the mitigation from becoming the next
common-mode carrier. This is the cooperative-controller trap: the mechanism that
makes multipath self-scaling is also the mechanism that can concentrate it. In the
7G backhaul setting, self-scaling means pooling capacity across heterogeneous links
and cooperative peers; it is precisely the mechanism that raises utilization and
the one that can centralize control.

## 6. Neither substitutes for the other

| | **Low isolation** | **High isolation** |
|---|---|---|
| **Low multipath** | Concentration: one provider, one path. Maximum efficiency, maximum common-mode exposure. | Compartmentalised: the boundary contains the fault, but the protected side is a hard partition bounded by local capacity. |
| **High multipath** | Survivable to independent failures, exposed to shared control-plane and API faults; every path can fail together. | Resilient fabric: independent paths across boundaries with a tested local fallback. Higher cost and operational complexity. |

The axes are orthogonal. Adding paths does not cut the control-plane edge; adding
a boundary does not create capacity on the protected side. The combined arm should
therefore be super-additive, not merely additive: the interaction is the claim. If
it is not, the "neither substitutes" thesis is false and one axis is doing the
work.

## 7. The biological parallel, used carefully

The brain tolerates damage through **distributed representation and parallel
pathways** — the analogue of multipath and diversity — and it contains damage
through the blood–brain barrier, compartmentalisation and glial boundaries — the
analogue of isolation. Shared perfusion is a dependency no local boundary can cut,
which is why a boundary alone does not guarantee function. Compensation and
rehabilitation are the tested-fallback analogue: unused pathways degrade, and a
backup that is never exercised is not a backup.

The analogy is useful because it separates the two mechanisms. A lesion is not
survived because the brain is isolated; it is survived because function is
distributed. Excitotoxicity is not stopped because function is distributed; it is
stopped because a boundary contains it. The brain needs both, and so does a
network.

The analogy is not evidence. The repository's Paper B is the standing caution: a
continuous bio-inspired controller did not beat static per-flow isolation in the
packet testbed. Biology generates the hypothesis; the testbed decides.

## 8. What would falsify the argument

The argument is testable, and the protocol is in
[`docs/common-mode-resilience.md`](common-mode-resilience.md):

- **H16** — tenant isolation does not meaningfully reduce control-plane blast
  radius. Refuted if it does.
- **H17** — multipath gain tracks path independence, not path count, and vanishes
  under a shared-fate event. Refuted if multiplicity alone predicts the gain, or if
  multipath survives a shared control-plane failure.
- **H18** — isolation without local fallback capacity cannot preserve service.
  Refuted if a hard partition alone maintains availability.
- **H19** — isolation plus multipath plus a tested fallback is super-additive over
  the best single axis. Refuted if the combined arm is no better than that axis, or
  if the gains merely add.
- **H20** — a centralized cooperative controller is a new common-mode carrier.
  Refuted if it is no more fragile than local reallocation under the tested events.

If the combined arm does not beat the best single axis, the central claim of this
document — that neither substitutes for the other — fails. That is the intended
risk.

## 9. Limits

- This is a position and analysis document, not a measurement of any cloud, AI
  provider, aviation system or rail deployment.
- Outage causes are reported, not verified. The structural comparison is
  mechanism-independent; no hypothesis depends on a reported root cause.
- The Siemens architecture is vendor-described, not independently evaluated.
- Security is out of scope: the data diode is treated as an availability and
  attack-surface boundary, not a cryptographic control.
- Political, regulatory and capital-market claims are out of scope. The
  "techno-feudalism" framing describes an incentive; the engineering claim is
  narrower and testable.
- Failure distributions, SRLG memberships, fallback capacities and test intervals
  are stipulated and must be reported as such.

## 10. Conclusion

Concentration is the risk. Isolation and multipath are the two independent
mitigations, and neither substitutes for the other. A tested fallback is the
condition that makes either one real.

The engineering translation of the closing line is exact: concentration without
independent failure domains is a single point of failure with a business model.
The remedy is structural — hard boundaries that stop propagation, independent
paths that keep serving when one degrades, and a fallback that has been tested
before it is needed. Tenant isolation, region isolation and confidential computing
are necessary but belong to a different boundary. The shared control plane is the
one that has to be cut, and multipath is the one that has to be disjoint. Until
both are true, the next trigger will have a different name and the same signature.
