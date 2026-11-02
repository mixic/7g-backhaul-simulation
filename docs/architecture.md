# Seamless Multi-Medium Delivery and Self-Scaling CDN

## Thesis connection

This design takes inspiration from Milan Nikolic's University of Bern master's thesis, *Gezora: A Self-Scalable Content Distribution Network* (2010), included in this repository as [`Ni10.pdf`](../Ni10.pdf). The simulator uses the thesis's self-scaling CDN goal as a foundation: learn regional content demand, improve request placement, and add cache capacity where demand is growing. The implementation here is a new educational model, not a reproduction of Gezora.

The design also emphasizes request routing, service discovery, measurement, and simulation. In this repository, per-region popularity is learned from requests, telemetry exposes transport conditions, and deterministic trend estimation gives cache placement a measurable trigger.

## Continuity and radio mobility models

An application session has a stable session ID and byte stream. The stream is split into fragments, and each fragment may use a different physical transport:

- Microwave / directional radio
- HF
- LEO satellite
- Mobile
- Wi-Fi
- Drone relay

`Mixed` describes a session using several of these media concurrently; it is not modeled as a separate physical link. The bonded-carrier scheduler allocates bytes across active media using available pacing rate, loss, pressure, and latency. It distributes fragments over those paths and retries a lost fragment on another path. A receiver reassembles by session ID, byte offset, and total message length, so fragments may arrive out of order or use different MTUs without changing the application payload.

`RadioHandoverController` models signal-strength measurements, hysteresis, a time-to-trigger counter, and a make-before-break transition. `MobileIpAnchor` keeps a stable simulated virtual IP while changing the access locator. These state machines model protocol concepts; they do not interoperate with cellular base stations, Wi-Fi controllers, carrier infrastructure, or real IP tunnels.

## Variable MTU and adaptation

Each medium advertises its own network-layer MTU and encapsulation overhead. Available application payload size is:

```text
payload_mtu = current_link_mtu - encapsulation_overhead
```

The modeled link MTU can shrink as load increases. `AdaptiveMTULearner` explores supported payload sizes per medium and updates an online reward estimate from delivery feedback. Successful larger payloads are more efficient; a loss penalizes that size and triggers retransmission on another medium.

## Congestion control and routing policy

`AIMDCongestionController` applies a Reno-inspired additive-increase/multiplicative-decrease congestion window to each modeled medium. Acknowledgements grow the window; simulated losses reduce it. Its pacing rate feeds the bonded carrier scheduler, which can move subsequent fragments onto other paths.

`CoupledCongestionGroup` adds multipath coupling options over the same window abstraction: uncoupled per-path Reno, LIA per RFC 6356, and OLIA using the published Khalili et al. increase rule. It is a window-level model with no ACK packets, slow start, retransmission or scheduler, used for the comparison in §10.4 of the paper; it is not an MPTCP implementation and its numbers are not conformance evidence.

`RoleFluidSimulation` in [`simulation/role_fluid.py`](../simulation/role_fluid.py) models the role-fluid paradigm: every node may act as router, load balancer or server, role selection is co-optimised with path selection through a potential field, and medium boundaries contribute MTU-based transmission/reflection coefficients. It is a control model, not a protocol, and it is not cross-validated. The model, its controllers and the first measured (partly negative) results are documented in [role-fluid-paradigm.md](role-fluid-paradigm.md).

`TabularQRoutingAgent` is a small online Q-learning policy over quantized load and pressure state. It uses a safety mask to avoid unavailable links and adjusts the carrier allocation weights from observed delivery reward. This is genuine tabular RL in the simulated environment, but it is not deployment-grade: the state/action space, reward, training duration, and safety model are intentionally small and require validation before any real-world use.

## Link queue model

`DropTailQueue` in [`simulation/link_queue.py`](../simulation/link_queue.py) is a single-server, finite-buffer FIFO queue driven by caller-supplied time. It was added after external cross-validation showed that the queue-free transport abstraction is optimistic under overload: when a handover moved 12 Mbit/s onto an 8 Mbit/s path, the queue-free model over-reported delivery by 6.5 percentage points and under-reported p95 delay by a factor of 5.7 relative to an ns-3 reference. With the queue model the same scenario matches the reference to 0.01 points of delivery and 1.8 % of p95 delay. See [external-validation.md](external-validation.md) for the experiment, the shared scenario definition and the remaining gaps.

The queue model is opt-in and time-driven by the caller, so tick-based benchmarks and the validation harness can use the same code path as the event-driven simulator.

## Session authentication model

`SessionAuthenticator` issues short-lived HMAC-SHA256 signed session credentials and verifies their session binding, expiry, and signature before transmission when the transport is configured with an authenticator. The demo creates a random ephemeral key for the process. This authenticates simulator requests only; it is not subscriber authentication, key management, replay protection, TLS, or a replacement for operator-grade identity systems.

## Demand velocity and acceleration

Cache scaling uses request arrivals to estimate request-rate velocity and acceleration. A general metric forecast uses equally spaced samples:

```text
v(t) = (x(t) - x(t - Δt)) / Δt
a(t) = (x(t) - 2x(t - Δt) + x(t - 2Δt)) / Δt²
x̂(t + H) = x(t) + v(t)H + 0.5a(t)H²
```

The same estimator can be applied to request rate, throughput, or latency. `RequestDemandLearner` currently computes the request-rate signal from recent arrival windows; the CDN forecasts demand over a configurable horizon and creates a regional cache when observed or forecast demand crosses its scaling threshold. Per-region object popularity then guides cache warming and eviction.

This is a deliberately transparent baseline. Real CDN scaling should include forecast uncertainty, cache-fill cost, origin capacity, network price, and latency SLOs before taking an action.

## Multicloud AI datacenters and Kubernetes edge

The orchestration model adds two educational abstractions. `KEDAInspiredScaler`
translates observed and forecast request rates into a bounded desired replica
count for an edge cache cluster. `MultiCloudAIScheduler` ranks eligible AI
datacenters using configured latency, estimated billable egress, accelerator
load, and hardware availability, while respecting an optional latency SLO.
The demo exercises both decisions.

These are not live cluster or cloud integrations. The scaler does not call
Kubernetes/KEDA, and placement does not reserve GPUs, execute inference, fetch
model artifacts, or provision a provider. Egress estimates use operator-supplied
rates and omit charges not represented in those inputs. See
[`multicloud-kubernetes.md`](multicloud-kubernetes.md) for formulas,
assumptions, AI datacenter context, and future integration points.

## Peer mesh and congestion-aware cache decisions

`PeerMesh` models peers with independent caches connected by undirected links.
Each link reports utilization, queue delay, loss, and a second-order predicted
pressure score. Congestion hysteresis feeds a path cost that can select an
alternate route; when the lowest-latency route is predicted congested, repeated
content requests may trigger a local replica if the cache-admission guard
approves it.

The cache guard rejects content without a trusted manifest or with a
SHA-256 mismatch. A small NPU-inspired anomaly score uses request reuse and
cache footprint to limit one-off/high-novelty admissions. The score is a
transparent heuristic, not a trained AI model or actual NPU execution.
Publisher trust is configured out-of-band; manifests are not signed or
distributed by a production trust service. See [`peer-mesh.md`](peer-mesh.md)
for the model and security boundaries.

## Quantum-assisted cooperative backhaul

Quantum links are modeled as a separate resource for bounded qubit frames and
simulated key-material generation; they do not carry the mesh's classical
content bytes. Classical payload MTU is the minimum usable MTU across the
selected classical route after per-link encapsulation overhead. Quantum frame
capacity is measured in qubits and is not an IP MTU. The cooperative coordinator
combines congestion-aware classical path selection, demand-driven cache
replication, and optional key-resource reservations. It is an educational
policy model, not distributed multi-agent learning or a QKD implementation.
See [`quantum-cooperative-backhaul.md`](quantum-cooperative-backhaul.md).

## How to exercise it

The test suite checks:

- The original bytes reconstruct after fragments use multiple media and MTUs.
- A receiver can reassemble out-of-order fragments.
- Radio handover applies hysteresis/TTT and preserves the stable simulated IP.
- Carrier bonding respects availability and conserves allocated bytes.
- Congestion feedback changes the AIMD window and stays within the link rate.
- Authenticated transport rejects missing, expired, and wrong-session credentials.
- Routing Q-values update while unavailable links remain masked.
- The second-order forecast computes velocity, acceleration, and projected demand.
- Accelerating regional requests trigger cache placement and warming.
- Forecasted demand drives bounded Kubernetes-inspired edge replica decisions.
- AI workload placement respects datacenter availability, accelerator capacity, and latency SLOs.
- Congestion forecasts reroute mesh requests and trigger guarded peer-cache replication.
- Mesh cache admission rejects untrusted or corrupted content and resists one-off cache pollution.
- Quantum key-resource frames remain separate from per-route classical MTUs and fragmentation.
- Cooperative requests use demand forecasts for guarded replication and reserve quantum resource only for remote responses.
- Network snapshots and transfer KPIs are appended as CSV.

Run the interactive simulation with `python main.py`; generated dashboard frames are saved in [`../figures/`](../figures/).

## Next research steps

- Replace the fixed finite-difference predictor with a validated online forecast and confidence interval.
- Add throughput and latency histories to the route reward and trigger proactive path/capacity changes.
- Model cache-fill traffic and compare request latency against an origin-only baseline.
- Test correlated outages, reordered/lost fragments, and realistic per-medium rate limits.
- Implement standards-based access-network control, real IP tunneling/mobility, cryptographic session protocols, and congestion algorithms in a network simulator or controlled testbed.
