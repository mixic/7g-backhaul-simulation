# Empirical Commutation Rules for Protocol Layer Encapsulation in Heterogeneous Networks

**Milan Nikolic** · Independent Researcher · <m_nikolic@yahoo.com>

**Status:** focused paper. The real-stack extension (P8–P12) is complete: all
twelve cases are confirmed on one Linux kernel — see
[`layering-real-stack-results.md`](layering-real-stack-results.md). This paper is
Paper A of a two-paper split; Paper B is
[`paper-bio-control-limits.md`](paper-bio-control-limits.md). Section 3 adds the
DNS-free name fabric the rule implies and the migration-convergence comparison
that motivates it; those figures are model outputs, not packet traces. The
epilogue is a future-work proposal and is explicitly untested.

## Abstract

Encapsulation layers — compression `C`, encryption/authentication `E`, tunnelling
`T`, fragmentation `F`, sequencing `S` — are usually studied one at a time. This
paper asks a narrower, testable question: **when the order changes, which rewrites
corrupt a datagram and which leave it intact?** It formalises a *survival rule*: a
middlebox can rewrite a field only if that field is **visible** at the wire and
**reachable** within its parse depth; delivery breaks exactly when the rewritten
field is **authenticated** (inside an integrity scope) or **structural** (length-
or offset-bearing). The rule is tested in three independent
implementations: a Python codec, a SimPy model, and a real Linux stack (kernel
WireGuard, IPsec AH/ESP, nftables NAT). The codec and model agree exactly on
P1–P7. Against the real stack, all twelve frozen cases are confirmed:
AH-in-tunnel dies through NAT while ESP and WireGuard survive (P8); WireGuard's
wire overhead is `60 + 16·⌈L/16⌉`, not the stipulated 56 B (P9); nested
IPIP/WireGuard orderings differ by `−4` or `+12` bytes because WireGuard
quantises size (P10); a rewritten outer UDP length is fatal while an inert ToS
rewrite is not (P11); and an inner UDP checksum derived from the outer address
breaks under NAT even without an integrity tag (P12). The contribution is the
**quantised** and **derived** field classes, which a fixed-overhead model lacks.
Everything here is about framing and survival, not cryptographic security; the
evidence is one kernel, veth links and one NAT implementation.

The same rule decides whether a DNS-free name fabric can work at all, because a
name carried in the packet header is a field any middlebox may rewrite (§3).

While the architectural principle of merging name resolution with forwarding is the foundation of Information-Centric Networking (ICN) and Named Data Networking (NDN), our contribution is empirical and quantitative. We do not claim to invent a new naming architecture. Instead, we provide the first direct, apples-to-apples measurement of service migration convergence latency between an NDN-style name fabric and a conventional DNS-based system with a standard TTL. Our results demonstrate that the TTL-bounded convergence of DNS (28.7 seconds) imposes a fundamental limit on dynamic service migration, whereas the name-based fabric achieves convergence in 35.7 milliseconds—a reduction of nearly three orders of magnitude. This quantifies a critical architectural advantage for future 7G networks where service instances must migrate rapidly.

## 1. Introduction

A middlebox rewrites a header field. Two separate events follow, and the paper
keeps them apart:

- **The rewrite is applied** iff the field is **visible** at the wire *and*
  **reachable** within the middlebox's parse depth.
- **The receiver accepts the datagram** unless the rewritten field is
  **authenticated** (inside an integrity scope) or **structural** (length- or
  offset-bearing), which a rewrite invalidates.

So a field that is visible and reachable, but neither authenticated nor
structural, is silently rewritten and the datagram survives; a field that is
authenticated or structural breaks delivery when rewritten. The testbed freezes
this rule and then tests it, not the codec.

The rule is not only a catalogue of middlebox failures. It also decides whether
a network can route on a name carried in the packet header, and therefore
whether a DNS-free name fabric is possible at all (§3). The fabric in this paper
is not a new architecture — it is the ICN/NDN design, applied and measured:

While the architectural principle of merging name resolution with forwarding is the foundation of Information-Centric Networking (ICN) and Named Data Networking (NDN), our contribution is empirical and quantitative. We do not claim to invent a new naming architecture. Instead, we provide the first direct, apples-to-apples measurement of service migration convergence latency between an NDN-style name fabric and a conventional DNS-based system with a standard TTL. Our results demonstrate that the TTL-bounded convergence of DNS (28.7 seconds) imposes a fundamental limit on dynamic service migration, whereas the name-based fabric achieves convergence in 35.7 milliseconds—a reduction of nearly three orders of magnitude. This quantifies a critical architectural advantage for future 7G networks where service instances must migrate rapidly.

Sections 2 and 4 report the frozen layering cases (P1–P7) and the real-stack
extension (P8–P12); §3 specifies the fabric and the one measurement this paper
makes with it; §5 credits the prior art.

## 2. What was tested (P1–P7)

The predictions ([`layering-predictions.md`](layering-predictions.md)) cover
visible/mutation/acceptance for NAT and byte-mangling across six orderings of
`T`, `E`, `S`, plus the six-layer permutations with `C` and `F`. The codec
([`simulation/layering/`](../simulation/layering/)) and the SimPy model agree on
every case; the validator lives in
[`validation/layering/`](../validation/layering/). Notable outcomes:

- **P1** — encrypt-before-compress inflates a compressible payload (size effect).
- **P5** — fragment-before-compress raises the fragment count.
- **P3** — authenticating the NAT-rewritten outer source breaks acceptance. The
  same scope rule governs a rewritten name field (§3.3).
- **P4** — fixed-overhead layers commute exactly; quantised layers do not (§4).

## 3. Name Fabric Architecture

The rule of §1 is usually read as a warning about middleboxes. It is also a
design constraint: if a network routes on a name carried in the packet header,
then the name is a field, and every rewrite of it is governed by the same
visible / reachable / authenticated / structural test. This section specifies
the DNS-free fabric the rule permits, the way nodes learn where a name lives,
the cryptographic binding the fabric needs, and the seam through which it must
speak to the legacy Internet. It is an architecture section; the one
quantitative result it carries is the migration-convergence comparison of §3.2.

### 3.1 Name structure

The fabric's names are hierarchical, in the NDN idiom, with the service at the
root and the object below it:

```
/service/<service-id>/<content-id>
```

- `<service-id>` identifies a role-fluid service, not a host. It is the unit a
  client asks for and the unit the fabric routes on.
- `<content-id>` is a self-certifying digest of the bytes for immutable content,
  and a signed descriptor bound to an epoch for a dynamic service (the
  `IMMUTABLE` and `SERVICE` name classes of
  [`simulation/name_fabric.py`](../simulation/name_fabric.py)). A digest names
  bytes; a role-fluid service has no fixed bytes, so its name must be a signed
  claim about which instance currently serves it.

The instance is deliberately not a component of the requested name. A
deployment that wants to pin a replica can extend the hierarchy to
`/service/<service-id>/<instance>/<content-id>`, but a name that contains the
instance must be rewritten on every move — the exact coupling the fabric exists
to remove. The prototype keeps instance selection below the name layer, in the
FIB (§3.2).

The ns-3 prototype encodes only the service level on the wire: the custom
`RoleFluidHeader` carries a 64-bit `name` field, alongside `seq`, fragment
offset, `total`, `mtu`, hop limit, a send timestamp and an accumulated path
cost; `name = node index / 5`, so 50 nodes expose 10 names. That is a prototype simplification — a flat 64-bit
identifier for a 10-name space — not a claim that a production fabric should use
flat names; route-by-name table size is unmodelled (see §6 and
[`name-fabric.md`](name-fabric.md) §6).

This structure replaces the DNS A/AAAA record. An A/AAAA record is a binding from
a name to a locator, cached with a TTL; a client that holds a stale record sends
to the old locator until the TTL expires. In the fabric the name is the
forwarding key itself: a request carries `/service/svc-3`, and each node's FIB
maps that name to an egress device and a cost. There is no name→address binding
to cache, so no TTL sits between an instance move and the next request.

### 3.2 FIB update mechanism

Nodes do not query a directory. They learn the gradient that points at a name. In
the ns-3 prototype
([`validation/ns3/role-fluid-fabric.cc`](../validation/ns3/role-fluid-fabric.cc))
the mechanism is:

1. A server announces its name with a `HELLO` control packet. The packet
   accumulates a path cost (`costAccum`) as it is flooded.
2. A node keeps, per name, the lowest-latency ingress it has seen
   (`FibEntry{device, latencyMs, mtu}`). A `HELLO` that does not improve the best
   known cost is dropped; one that improves it updates the FIB and is
   re-flooded. Duplicates are suppressed by a seen-`HELLO` set.
3. When the instance moves, the old server sends a `WITHDRAW` for the name and
   the new server sends a `HELLO`; the gradient re-forms around the new
   location. A pending-interest table (PIT) reverses the data path, so data
   follows the reverse of the interest that created it.
4. Data is served from the instance or from an on-path cache. No name lookup is
   performed anywhere in this path.

The analytic model abstracts one step further: `gradient_resolution()` computes
the lowest-latency path from the client to the instance (Dijkstra, with the
bottleneck capacity of that path), adds a utilisation-dependent queue delay and
an exponential jitter term. It *assumes* the gradient exists; bootstrap is not
modelled (stated in advance in [`name-fabric.md`](name-fabric.md) §3).

Contrast this with DNS. DNS resolution requires a (usually centralized)
authoritative server and a recursive resolver, and correctness after a move
depends on cache invalidation: clients keep the old answer until the TTL
expires. Under the model's defaults, a 30 s TTL produces a p95 time to first
success of **28 677 ms** (28.7 s) and 150 failed requests per client. Name-based
forwarding has no mapping to expire, and its p95 is **35.7 ms** — the path plus
the queue to the new instance. The 10 ms absolute threshold pre-registered for
the gradient **failed** (the new instance sits behind a saturated 80 Mbit/s
link); the measured 35.4–36.0 ms band and the failure are reported in
[`name-fabric.md`](name-fabric.md) §4.1 rather than moved.

### 3.3 Security and AAD linkage

Because the name is in the header and is what routing acts on, its integrity is
not optional. Two distinct requirements follow.

First, the scope rule of P3 (§2) applies to the name exactly as it applies to
any other field. If the fabric does not rewrite the name, the name belongs
inside the integrity scope: it is the field that binds a request to the object
or service it asks for, and leaving it unauthenticated lets an on-path attacker
steer the request by rewriting it. If an element on the path does rewrite the
name — a gateway translating to DNS, or an anycast point selecting an instance —
that field must be kept outside the AEAD's additional-authenticated-data (AAD)
scope. When the name is inside the AAD and a middlebox rewrites it, the receiver
computes a different tag and drops the packet: P3 measures exactly this, and
acceptance is 0 % at all three fidelities. Rewriting an authenticated name does
not degrade the fabric, it stops it.

Second, where the name is not rewritten, it must be cryptographically bound to
what it names. An unsigned name in a header is a routing hint that any on-path
attacker can rewrite, which would let the attacker steer requests to a forged
instance. The fabric therefore verifies at the edge:

- an `IMMUTABLE` name is a 128-bit digest checked against the payload, so a
  forged name cannot match the bytes (structural, not probabilistic);
- a `SERVICE` name is a signed descriptor bound to an epoch, verified with an
  attestation strength chosen by the operator. The model measures the exposure
  curve — forgery acceptance falls from 95.4 % at strength 0 to 0.18 % at
  strength 3 — but those probabilities are **stipulated inputs**, not a
  measurement of a real signature scheme ([`name-fabric.md`](name-fabric.md)
  §4.2).

The residual is stated rather than hidden: self-certifying names remove
poisoning for immutable content; dynamic service names can only reduce it, and
the fabric's security therefore depends on an attestation design this paper does
not evaluate.

### 3.4 The gateway seam

A name fabric cannot be the whole Internet. Requests for external names must
still become DNS queries and IP packets, and the component that does that is a
gateway. The model includes one (node `G` in
[`simulation/name_fabric.py`](../simulation/name_fabric.py)): internal requests
are resolved by the gradient; external requests traverse `G`, pay an uncached
DNS lookup (25 ms resolver RTT plus M/M/1 queueing at 5 000 QPS) and a gateway
queue at 100 Mbit/s.

The measured seam, at 2 000 requests/s with an 8 kB payload:

| External share | Gateway utilisation | Internal p95 | External p95 |
| ---: | ---: | ---: | ---: |
| 0 % | 0.0 % | 21.28 ms | 42.28 ms |
| 5 % | 6.4 % | 21.27 ms | 42.58 ms |
| 20 % | 25.6 % | 21.15 ms | 44.88 ms |
| 50 % | 64.0 % | 21.16 ms | 71.44 ms |

An external request costs roughly twice an internal one even at an idle gateway,
because it pays the uncached lookup and the gateway path; at a 50 % external
share the gateway is at 64 % utilisation and its p95 has grown to 71 ms. This
gateway is a centralization point, a potential bottleneck and an attack target:
in this model, a DDoS on it takes the fabric's entire legacy reachability with
it. Its performance and security are outside the scope of this measurement —
one gateway, no protection and no failover is modelled. It is a critical area
for future deployment and is stated here as a seam, not a solved component.

### 3.5 What this measurement is, and what it is not

The 28.7 s and 35.7 ms figures are produced by the same model
([`simulation/name_fabric.py`](../simulation/name_fabric.py)) on the same
eight-node topology, at the same 2 000 requests/s and 8 kB payload, under one
seed. That is what makes them apples-to-apples: the comparison differs in the
resolution mechanism (a DNS cache with a TTL versus gradient forwarding) and in
nothing else. The 35.7 ms is link-limited — the path latency plus the queue of a
saturated 80 Mbit/s link — and is not a claim that 35.7 ms is achievable on any
topology.

It is not packet-level. The ns-3 prototype carries names in a header and
forwards on them, but it does not produce the TTL-versus-gradient head-to-head
number; that comparison comes from the analytic/stochastic model, and the model
assumes the gradient exists. Packet-level cross-validation of the name path, the
name-table memory bound, and an explicit bootstrap model are future work
([`name-fabric.md`](name-fabric.md) §6). The security numbers in §3.3 are
stipulated, the gateway in §3.4 is not defended, and the migration floor is one
topology at one load point.

## 4. Real-stack extension (P8–P12)

Predictions frozen before the harness in
[`layering-real-stack-predictions.md`](layering-real-stack-predictions.md);
results in [`layering-real-stack-results.md`](layering-real-stack-results.md).
**Frozen protocol: 20 runs per case.**

| Prediction | Status | Evidence |
|---|---|---|
| P8a AH tunnel + NAT | **CONFIRMED** | 0 % delivery, `XfrmInStateProtoError` + datagrams |
| P8b ESP tunnel + NAT | **CONFIRMED** | 100 % delivery (outer src outside ESP scope) |
| P8c WireGuard + NAT | **CONFIRMED** | 100 % delivery; peer learns the NAT endpoint |
| P9 WireGuard overhead | **CONFIRMED** | `wire(L) = 60 + 16·⌈L/16⌉`, 9/9 lengths exact |
| P10a naive commutation | **CONFIRMED** | `d(L) ≠ 0` for every length |
| P10b quantised model | **CONFIRMED** | `d(L) = −4 / +12` exact |
| P11a UDP length, no csum | **CONFIRMED** | 0 % delivery, cause gate |
| P11b UDP length, recomputed csum | **CONFIRMED** | 0 % delivery, cause gate |
| P11c inert ToS control | **CONFIRMED** | 100 % delivery |
| P12a ESP transport + NAT, inner csum | **CONFIRMED** | 0 %, `UdpInCsumErrors` + datagrams |
| P12b inner csum zeroed | **CONFIRMED** | 100 % delivery |
| P12c control, no NAT | **CONFIRMED** | 100 % delivery |

Three consequences for the model follow from the confirmed cases:

1. **`W` is quantised.** P9 shows WireGuard pads to 16 B, so the stipulated
   56 B composite (`E = 28`, `T = 28`) is off by 4–16 B. The fixed-overhead
   assumption (P4) is amended for quantising layers.
2. **Fixed-overhead layers do not commute once one layer quantises size.** P10
   shows `d(L)` is never zero: swapping IPIP and WireGuard changes the wire
   length by −4 or +12 bytes.
3. **Fields can be derived across layers.** P12 shows an inner UDP checksum
   depending on the outer address is invalidated by a NAT rewrite without any
   integrity tag.

What that means for the rule: on this kernel, the rule held for the three
integrity-scope cases (AH, ESP, WireGuard), the two size effects (P9, P10), the
structural rewrite (P11) and the derived field (P12). That is evidence for the
rule against independent implementations; it does not establish it in general
(see §6).

## 5. Related work

- **Named Data Networking and ICN.** Named Data Networking makes the name the
  forwarding key: an Interest carries a name, a router forwards it toward a
  producer or a cache, and a Data packet is signed over its name and content
  (Zhang et al., "Named Data Networking", *ACM SIGCOMM Computer Communication
  Review* 44(3):66–73, 2014, DOI
  [10.1145/2656877.2656887](https://doi.org/10.1145/2656877.2656887); the earlier
  content-centric design is Jacobson et al., "Networking Named Content",
  *CoNEXT* 2009, DOI
  [10.1145/1658939.1658941](https://doi.org/10.1145/1658939.1658941)). The fabric
  in §3 is that architecture, not a new one. What this paper adds is the
  comparison in §3.2, not the design: name-based forwarding is prior art, and
  the P3 AAD rule is the layering constraint that decides when it can be
  deployed safely.
- **Standardisation of name-based forwarding.** RFC 8677 defines a Name-Based
  Service Function Forwarder (nSFF) inside the SFC framework: the logical service
  path stays stable while the execution endpoint is selected by name, so moving
  an instance does not require a rechain (Trossen, Purkayastha and Rahman,
  "Name-Based Service Function Forwarder (nSFF) Component within a Service
  Function Chaining (SFC) Framework", RFC 8677, November 2019, DOI
  [10.17487/RFC8677](https://doi.org/10.17487/RFC8677); an Independent
  Submission, informational, not IETF consensus). It shows that the operational
  problem measured here — instance movement without a reconfiguration cycle — is
  recognised in standards work. It does not report the TTL-versus-name
  convergence comparison; that is the gap §3.2 fills.
- **Service migration in ICN.** Karimzadeh, Satria and Karagiannis, "Utilizing
  ICN/CCN for Service and VM Migration Support in Virtualized LTE Systems"
  (*CLOSER* 2014, pp. 633–638, DOI
  [10.5220/0004945606330638](https://doi.org/10.5220/0004945606330638)), and
  Satria, Karimzadeh and Karagiannis, "Performance evaluation of ICN/CCN based
  service migration approach in virtualized LTE systems" (*IEEE CloudNet* 2014,
  pp. 461–467, DOI
  [10.1109/CloudNet.2014.6969038](https://doi.org/10.1109/CloudNet.2014.6969038)),
  apply ICN to service and VM migration and evaluate it in virtualized LTE. They
  make the architectural case this paper takes as given. The contribution here is
  different in kind: a like-for-like convergence-latency comparison against a
  DNS baseline with a standard TTL — 28.7 s against 35.7 ms — rather than another
  migration architecture.
- **Middlebox behaviour.** Honda et al. measured how widely deployed middleboxes
  drop or rewrite options and payloads, and concluded that new transport
  extensions are hard to deploy *because of* such boxes. The present paper is
  narrower: it does not measure middlebox prevalence, it tests a rule about which
  field classes break when rewritten, with independently implemented stacks.
- **IPsec and NAT.** RFC 3715 specifies the IPsec/NAT compatibility problem, RFC
  4302 defines the AH integrity scope (which covers the outer IP header) and RFC
  4303 defines ESP (which does not). P8 is a direct, executable restatement of
  that asymmetry; AH dying under NAT is the expected textbook outcome, so P8
  validates the harness rather than discovering a new fact.
- **Layering and recursion.** RINA and the "divide and repeat" style of recursive
  internetworking treat layering as a repeated composition problem. This paper
  contributes a small empirical constraint on that composition: layers with
  fixed size effects commute, layers that quantise size do not.
- **End-to-end.** The survival rule is a framing-level counterpart to the
  end-to-end argument of Saltzer, Reed and Clark: what a middlebox can touch is a
  property of the header scope, not of the protocol's intent.

## 6. What is still open

The `lookup-key` class (P8b's interpretation) is not isolated by the experiment:
P8b was confirmed as "ESP survives", consistent with a lookup not keyed on the
outer source, but the test does not separate that mechanism from the ESP scope
argument. The evidence is one kernel (WSL2), one NAT implementation (nftables
masquerade), veth links, no wireless and no congestion; other stacks may pad
differently or resolve SAs differently. The `tc pedit` result is a property of
iproute2 6.19 — the layered `udp len` field is rejected, so the harness uses the
raw-offset form.

The name-fabric figures in §3 come from the resolution-latency model, not from
the kernel harness: 28.7 s and 35.7 ms are model outputs under one topology and
one load point. Packet-level cross-validation of a name-carrying header is
future work; the ns-3 prototype exists but does not produce that head-to-head
comparison ([`kinematic-fabric.md`](kinematic-fabric.md) §6). The gateway is
modelled as one undefended hop, not as a component with failover or DDoS
protection.

## 7. Scope

Measures sizes, delivery and drop causes. It does not evaluate cryptographic
security; one kernel, one NAT implementation and veth links say nothing about
arbitrary middleboxes. The conclusions bound these cases, not "all middleboxes".
The name-fabric comparison in §3 is a resolution-latency measurement of named
forwarding against a DNS baseline; it does not measure a deployed fabric, the
name-table memory cost, or the security of a real signature scheme.

## Epilogue: complex-rotation manifolds (not tested)

The name fabric in §3 routes on a static metric space. Its follow-up work
extends that space dynamically: the Topological NDN plan of
[`tndn.md`](tndn.md) keeps the metric fixed, and the Dynamic Dimensionality
Manifold Routing of [`ddmr.md`](ddmr.md) expands it from one to four dimensions
in a discrete step with hysteresis. A discrete step is still a switch, and the
M11 results show its cost — a detection window that keeps the fabric in the
defensive state for seconds after the attack ends, and a threshold controller
that needs hysteresis precisely to avoid chatter.

We therefore record, as future work only, a continuous alternative:
**Complex-Rotation Manifold Routing (CRMR)**, in which the network state is a
phasor

```
ψ(t) = R(t) · e^{i θ(t)}
```

whose phase `θ ∈ [0, π/2]` rotates the metric continuously from the prefix-only
axis (calm) to the full defensive axes (attack), and whose amplitude `R(t)`
scales the forwarding phase penalty. The hypothesis H15 is that a phase-
continuous rotation reduces control-state churn and CDR variance under a
*flapping* attack relative to the discrete jump, at no more than 2 points of CDR
and within the same energy budget. No implementation, simulation or measurement
accompanies this proposal; it is deliberately deferred until this paper and
paper B are final. The full sketch and the falsification criteria are in
[`future-work-complex-rotation.md`](future-work-complex-rotation.md).

## Cross-references

- [`layering-predictions.md`](layering-predictions.md) — P1–P7 predictions.
- [`layering-results.md`](layering-results.md) — P1–P7 results.
- [`layering-real-stack-predictions.md`](layering-real-stack-predictions.md) — P8–P12 predictions (frozen).
- [`layering-real-stack-results.md`](layering-real-stack-results.md) — P8–P12 results.
- [`name-fabric.md`](name-fabric.md) — the name fabric: mechanism, results, limitations.
- [`tndn.md`](tndn.md) — Topological NDN (M10) and its three baselines.
- [`ddmr.md`](ddmr.md) — Dynamic Dimensionality Manifold Routing (M11).
- [`future-work-complex-rotation.md`](future-work-complex-rotation.md) — CRMR proposal (H15, not tested).
- [`validation/real_stack/`](../validation/real_stack/) — the executable harness.
- [`validation/ns3/role-fluid-fabric.cc`](../validation/ns3/role-fluid-fabric.cc) — the name-carrying ns-3 prototype.
