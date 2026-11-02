# Predictive Peer Mesh and Cache Protection

`PeerMesh` models a small undirected overlay in which every peer can have its
own cache, serve requests, and forward traffic. It is an educational simulator,
not a P2P protocol implementation, router dataplane, NPU control stack, or
production cache.

## Peer and link model

Each `MeshPeer` has an independent byte-limited cache and may be configured to
serve or forward. Each `MeshLink` records utilization, queue delay, loss, base
latency, and capacity. A bounded three-sample history feeds the existing
second-order trend estimator:

```text
pressure = 0.70 * utilization
         + 0.20 * queue_delay / (base_latency + queue_delay + 1)
         + 0.10 * loss_rate

predicted_pressure = clamp(second_order_forecast(pressure_samples), 0, 1)
```

The congestion state turns on when predicted pressure crosses a configured
threshold and clears only after two consecutive samples fall below the
hysteresis boundary. Link telemetry snapshots expose both current and predicted
pressure.

For content available at multiple peers, the mesh compares the lowest-latency
path with a congestion-aware path cost. Congested links carry a penalty; when
an alternate path is preferable, the request uses it. If the unconstrained
lowest-latency route was congested, the requesting peer may cache a replica
after it receives the content, subject to integrity and cache-admission checks.
Subsequent requests can then be served locally.

## Poisoning and pollution defenses

### Content integrity and publisher authorization

Before publication, an operator registers a content manifest containing a
content ID, trusted publisher ID, and expected SHA-256 digest. `PeerMesh.publish`
only inserts content when the publisher is in the configured trusted set and
the payload digest matches the manifest. Cached entries are verified again
before serving; a missing manifest or digest mismatch causes the entry to be
evicted and the request to fail explicitly if no verified copy is available.

This is an integrity check against the configured manifest, not a signature
scheme. The simulator assumes the trusted-publisher set and manifest are
provisioned through a trusted channel. A real system needs signed manifests,
key rotation, revocation, secure peer identity, and audit trails.

### NPU-inspired pollution admission

`NPUInspiredCacheGuard` scores a candidate using observations for that
requesting peer and content ID:

```text
novelty          = 1 / observations
reuse_deficit    = max(0, 1 - observations / minimum_reuse_observations)
cache_footprint  = min(1, content_bytes / cache_capacity_bytes)
anomaly_score    = 0.55 * novelty
                 + 0.35 * reuse_deficit
                 + 0.10 * cache_footprint
```

By default, an object must be requested at least three times and have a score
at or below 0.30 before congestion-triggered replication is admitted. This
resists one-off, high-cardinality content pollution and avoids filling a peer
cache with oversized objects. The weights and threshold are a transparent
hand-authored heuristic: no model is trained, and no NPU actually runs it.
False positives, adaptive attackers, workload diversity, and cache fairness
are not evaluated.

## Limits and next steps

- The mesh uses a single-process graph and deterministic path costs; it does not
  implement peer discovery, consensus, route advertisements, or packet forwarding.
- The pressure forecast is a simple second-order extrapolation, not a validated
  congestion predictor. Hysteresis reduces oscillation but does not guarantee
  stable behavior under real traffic.
- Replication does not model cache-fill bytes, transfer time, storage I/O,
  privacy/data-residency restrictions, or origin licensing.
- No Open Caching, BGP Anycast, Kubernetes, DHT, or NPU API is contacted.

The next realism step is to replay recorded per-link and per-content traces,
measure forecast errors and cache hit/cost tradeoffs, and test competing peers
before connecting to a controlled network testbed.
