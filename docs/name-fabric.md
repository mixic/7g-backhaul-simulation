# The name fabric: resolution collapsed into forwarding

This document specifies and evaluates the strongest version of the
DNS-independence claim: not "no lookup", but **resolution and forwarding are one
operation**. A request carries its name, and the same potential field that
allocates flow and selects roles decides where the request goes. Nothing has to
complete before the first packet moves, so no TTL sits between a role change and
the requests that should follow it.

Implementation: [`simulation/name_fabric.py`](../simulation/name_fabric.py).
Experiments: [`tools/benchmark_name_fabric.py`](../tools/benchmark_name_fabric.py).
Results: [`figures/name_fabric_*.csv`](../figures).

## 1. Why this is the thesis and not a slogan

The earlier work tested scheduling, then role transitions. Both are consequences
of a control plane. This one tests the control plane itself: if the request's
name is enough to route it, then resolution, routing, role selection and cache
location are the same optimisation. The water analogy becomes exact — water does
not consult a map before flowing, the terrain is the map — and the seismic
analogy becomes exact too, because the boundary coefficients are what a request
sees at each medium and role transition.

That is what makes the earlier criticism ("you benchmarked the wrong thing")
dissolve: there is now one mechanism to test, once.

## 2. Mechanism choice

Of the four candidates, the model implements **name-based forwarding (NDN/ICN
style) with self-certifying names for immutable content**, plus a second name
class for dynamic services. Justification:

- The pending-request table *is* the reordering/reflection buffer already
  modelled in RFMP, and the content store *is* the cache role already modelled.
  Resolution and forwarding are literally the same packet operation.
- Self-certifying names make poisoning structurally impossible for immutable
  content. This is the only one of the four options that removes the attack
  rather than mitigating it.
- A DHT would have been slower on the tail (Section 4.4 measures why) and an
  identifier/locator split would have reintroduced a mapping system under
  another name.

## 3. What breaks, stated before the results

1. **Bootstrap.** Nothing resolves in an empty network. A node must learn the
   gradient toward a name before any cache or server is reachable. In ICN this
   is name-based routing, and name-based routing is a naming-distribution layer.
   The function is not eliminated, it is co-located with forwarding: no separate
   serial step, no hierarchical root to poison. This model assumes the gradient
   exists and does not model its bootstrap.
2. **Dynamic content cannot be self-certified.** A hash names bytes; a
   role-fluid service has no fixed bytes. The service class therefore needs
   signed descriptors, and that class reintroduces forgery risk — measured in
   Section 4.2, where the acceptance probability falls from 95 % to 0.18 % as
   attestation strengthens.
3. **The attack surface relocates.** Interest flooding replaces query flooding,
   cache pollution replaces cache poisoning, pending-table exhaustion is a new
   resource attack with no DNS analogue. Section 4.3 reports where each side
   fails, and one regime where the new fabric is *worse* is stated if found.
4. **Interoperability is bounded.** External names require a DNS-speaking
   gateway. Section 4.5 models that seam rather than leaving it implicit.
5. **Name-table scalability is not modelled.** Route-by-name tables grow with
   namespace, not topology. This model treats the name table as free; that is a
   limit, not a result.

## 4. Results

Model: an eight-node fabric (producer, two cores, three edges, a gateway and a
legacy resolver) over ten links with capacities from 50 to 1000 Mbit/s and
latencies from 2 to 20 ms. Requests carry names; path latency comes from the
topology, queueing from a utilisation curve, the resolver from an M/M/1 queue,
poisoning from a Monte Carlo. It is a resolution-latency and security-exposure
model, **not** a packet simulator.

### 4.1 The floor that was removed

A service instance moves from `E2` to `E3` at t = 0. DNS clients keep the old
mapping until their cached entry expires; gradient clients have no mapping to
expire.

| Strategy | TTL | p95 time to first success | Mean | Failed requests per client |
| --- | ---: | ---: | ---: | ---: |
| DNS | 30 s | 28 677 ms | 15 130 ms | 150 |
| DNS | 60 s | 58 285 ms | 29 748 ms | 297 |
| DNS | 300 s | 280 717 ms | 147 970 ms | 1 479 |
| gradient | any | 35.4–36.0 ms | 32.5 ms | 0 |

The floor moves from `min(link adaptation, DNS convergence)` to link-limited, as
the programme predicted: the gradient's observation time is the path plus
queueing to the new instance, and it does not depend on the TTL at all.

**Pre-registered check: FAIL, and it is reported as such.** The threshold was
"gradient p95 below 10 ms". The measured value is 35.7 ms, because the new
instance sits behind a saturated 80 Mbit/s link whose queue delay alone is
20 ms. The ratio check (at least 5×) passes by 800–7 800×, but the absolute
number depends on the topology and the pre-registration was written without
deriving it. The correct reading is: the floor is link-limited, and a
topology-derived bound should be pre-registered next time. Moving the threshold
after seeing the result would have destroyed the point of pre-registering it.

### 4.2 Poisoning: success rate by name class

| Name class | Variant | Acceptance | 95 % CI |
| --- | --- | ---: | ---: |
| immutable | self-certifying digest (128-bit) | 0.000 % | ±0.000 |
| service | descriptor, strength 0 (no check) | 95.385 % | ±0.291 |
| service | strength 1 (origin signature) | 14.935 % | ±0.494 |
| service | strength 2 (+ epoch freshness) | 1.965 % | ±0.192 |
| service | strength 3 (+ threshold witness) | 0.180 % | ±0.059 |
| external | DNS cache, no DNSSEC | 3.250 % | ±0.246 |
| external | DNS cache, DNSSEC | 0.000 % | ±0.000 |

Immutable names are unpoisonable by construction, which is the structural win.
The service curve is the honest residual: role-fluid service naming inherits a
forgery risk that only attestation reduces, and the price of each step is
visible. **Caveat that must not be buried:** these acceptance probabilities are
*stipulated*, so the table measures the model's exposure curve, not the security
of any real signature scheme.

### 4.3 Interest flooding versus query flooding

| Offered load | Resolver failure | Resolver queue | Pending-table failure | PIT occupancy |
| ---: | ---: | ---: | ---: | ---: |
| 2 000 rps | 0.0 % | 0 ms | 0.0 % | 400 |
| 5 000 rps | 100.0 % | saturated | 0.0 % | 1 000 |
| 50 000 rps | 100.0 % | saturated | 0.0 % | 10 000 |
| 100 000 rps | 100.0 % | saturated | 50.0 % | 20 000 |

Sustainable rate (<1 % failure): **DNS 2 000 rps, pending table 50 000 rps per
node**. Under these defaults the name fabric is roughly 25× more flood-resistant
per node, which *contradicts* a simple "the 13 roots are the weak point"
narrative — here the resolver's query capacity is the bottleneck, not the root
tier.

That is not a victory. The result is dominated by the stipulated capacities: a
10 000-entry pending table with a 200 ms lifetime yields 50 000 rps by Little's
law, and a resolver at 5 000 QPS yields 5 000 rps. A targeted attack on a single
node, the memory cost of pending entries, and a resolver with a larger capacity
all move this number, and the model does not include the first two.

### 4.4 Latency distributions (nominal load)

| Strategy | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: |
| DNS, cached | 19.05 ms | 21.07 ms | 22.52 ms | 28.33 ms |
| DNS, uncached | 45.13 ms | 50.30 ms | 54.29 ms | 64.09 ms |
| DHT | 34.63 ms | 92.83 ms | 217.16 ms | 280.44 ms |
| gradient | 19.04 ms | 21.21 ms | 22.67 ms | 26.25 ms |

The gradient matches a *cached* DNS answer and beats an uncached one, but the
point is the tail: the DHT's p99 is 217 ms, an order of magnitude worse than the
gradient's 22.7 ms. This is the programme's warning confirmed — a DHT can lower
the mean and still raise the floor for role transitions.

### 4.5 The gateway seam

| External share | Gateway utilisation | Internal p95 | External p95 |
| ---: | ---: | ---: | ---: |
| 0 % | 0.0 % | 21.28 ms | 42.28 ms |
| 5 % | 6.4 % | 21.27 ms | 42.58 ms |
| 20 % | 25.6 % | 21.15 ms | 44.88 ms |
| 50 % | 64.0 % | 21.16 ms | 71.44 ms |

External requests cost roughly twice an internal request even with an idle
gateway, because they pay an uncached DNS lookup and the gateway path. At a 50 %
external share the gateway is at 64 % utilisation and its p95 has grown to
71 ms. This is the seam the architecture cannot remove, and it is reported
rather than hidden.

## 5. What this establishes

- Resolution can be collapsed into forwarding: the transition floor is
  link-limited rather than TTL-limited, measured at 35.7 ms versus 28.7 s at a
  30 s TTL.
- Poisoning is structurally zero for immutable content and a measurable function
  of attestation for service names (95 % → 0.18 %).
- Tail latency favours gradient forwarding over a DHT by an order of magnitude
  at p99.
- The flood resistance of the pending table is better than a 5 000 QPS resolver
  per node under these defaults, and the number is a direct function of
  stipulated capacities.

## 6. What it does not establish

- **No packet-level cross-validation.** The RFMP harness is the obvious vehicle
  (carry a name in the header, verify it at the receiver) and it has not been
  done. Until then this is a model, not a validated mechanism.
- **No bootstrap.** The gradient is assumed to exist.
- **No name-table memory model.** The scalability objection is unanswered.
- **Stipulated security parameters.** The acceptance curve is an input, not a
  measurement of real signature schemes.
- **One topology and one load point.** No sensitivity analysis of the
  transition floor to topology or of the flood thresholds to table size.

## 7. Next steps, in order

1. Cross-validate the name-carrying request path in ns-3: extend the RFMP
   program with a name field, self-certifying verification, and a forged-name
   attacker, then compare verified delivery and rejection between the Python and
   ns-3 implementations.
2. Model the name table as a bounded resource, so the scalability objection has
   a number attached to it.
3. Model bootstrap explicitly: what a node must learn, from whom, and at what
   cost before the first request can move.
4. Pre-register a topology-derived bound for the transition floor, replacing the
   failed absolute threshold.
5. Extend to mobility and churn, where the gradient has to track a moving
   instance rather than a single move.
