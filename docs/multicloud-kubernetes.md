# Multicloud, Kubernetes Edge, and AI Datacenters

This design extends the self-scaling CDN and heterogeneous backhaul model with
forecast-driven edge capacity and workload placement across configured cloud
and AI datacenter sites. It is an educational simulation; it does not provision
cloud resources, start Kubernetes pods, or program network hardware.

## Reference architecture

```text
                         +------------------------------+
                         | Multi-cloud AI datacenters   |
                         | inference / training / models |
                         +---------------+--------------+
                                         |
                    model and content replication
                     over costed backhaul paths
                                         |
  clients -- multi-medium backhaul -- regional edge clusters
                                         |
                              Kubernetes cache pods
                                         ^
                                         |
          telemetry -> demand forecast -> scaling policy
```

The control loop separates three decisions:

1. **Where to run AI work:** `MultiCloudAIScheduler` ranks available AI
   datacenters by configured network latency, estimated egress cost, accelerator
   load, accelerator capacity, availability, and an optional latency SLO.
2. **How much edge capacity to request:** `KEDAInspiredScaler` compares observed
   request rate with the forecast request rate and computes a bounded desired
   cache replica count for a simulated Kubernetes edge cluster.
3. **How traffic uses transport:** the existing transport scheduler selects
   among simulated wireless and backhaul media. A future real deployment would
   connect orchestration policy to supported networking APIs; the simulator
   does not push routes or configure NPUs.

## AI datacenter placement

An `AIWorkload` can represent inference, training, or model distribution. Each
configured `AIDataCenter` provides its provider and region, measured/assumed
latency, available accelerator count, accelerator load, and an operator-supplied
egress price. Candidate sites that are unavailable, short of accelerators, or
outside a workload's latency SLO are excluded.

For remaining candidates, the scheduler minimizes a transparent weighted score:

```text
score =
  (latency_weight * normalized_latency
   + egress_weight * normalized_estimated_egress
   + accelerator_load_weight * accelerator_load)
  / sum(weights)

estimated_egress_cost =
  billable_egress_bytes / 1,000,000,000 * configured_egress_cost_per_GB
```

Weights are simulation policy inputs, not learned or provider-prescribed values.
The estimated cost covers only the configured egress component; it excludes
ingress, inter-region charges, compute, storage, committed-use discounts, taxes,
and private-interconnect pricing unless those are added to the model. Prices in
examples must be supplied from current contracts before making cost claims.

The placement result is a recommendation, not a reservation: the caller remains
responsible for updating capacity telemetry and handling job lifecycle. The
current model does not execute inference, move model weights, or emulate GPU
performance.

## Kubernetes-inspired edge scaling

`KubernetesEdgeCluster` represents a regional edge cluster with a configured
requests-per-second target per cache pod and min/max replica bounds.
`KEDAInspiredScaler` computes the replica target from the larger of current and
forecast request rates:

```text
desired_replicas =
  clamp(ceil(max(observed_rps, forecast_rps) / target_rps_per_pod),
        min_replicas, max_replicas)
```

The scaler reports when the modeled demand exceeds the maximum replica
capacity. This resembles an event-driven autoscaling policy, but it does not
implement KEDA's metrics adapters, Kubernetes readiness, cooldowns, resource
requests, persistent volumes, or pod scheduling. It is not a KEDA replacement.

The existing CDN model learns regional content popularity and warms caches.
Together, that model and the replica scaler illustrate a path to forecast-based
content placement and cache capacity. Real Open Caching deployments require
content-owner authorization, cache interoperability, and operator-specific
integration; no third-party content is fetched by this project.

## Multicloud and traffic engineering

The topology can represent public-cloud and private AI datacenters alongside
regional edge clusters. A future deployment could combine object/model
replication, private interconnects, and network-aware placement, with routing
and service discovery handled by their respective systems. BGP Anycast,
service-mesh routing, SDN control, and provider-specific networking are
integration points, not behavior implemented by this simulator.

Predictive replication should account for the forecast confidence, object size,
cache capacity, backhaul utilization, transfer deadline, data residency, and
the cost of a miss. Background transfers can be modeled as lower priority than
interactive traffic, but strict isolation and service-level guarantees require
real QoS mechanisms and measurements.

## AI-aware networking and safety boundaries

NPU/SmartNIC telemetry, flowlet scheduling, queue occupancy, DDoS signals, and
AI training/inference traffic are useful future inputs for the routing and
capacity policies. The current simulator uses abstract link load, latency,
loss, and pressure values; it does not model line-rate packet inspection,
nanosecond queue control, autonomous hardware route changes, or attack
classification. Defensive mitigation would need explicit rate limits, audit
logs, false-positive controls, and a safe policy boundary before any hardware
actions.

Likewise, AI datacenter accelerator counts and utilization are abstract
capacity signals. The current implementation does not model GPU/NPU
interconnects, distributed training collectives, power/cooling constraints, or
inference throughput.

## Running and testing the model

The main demo includes a sample forecast-driven edge scaling decision and a
latency/egress-aware AI workload placement decision. Focused tests cover replica
bounds, saturation reporting, placement objectives, resource constraints, and
no-eligible-site errors:

```bash
python -m unittest discover -s tests -v
```

The next step toward a deployable prototype would be a separate adapter layer
for a local Kubernetes distribution (such as K3s), a real custom/external
metrics source for KEDA, and provider-specific cost and networking data. Those
adapters should remain outside the simulator core so tests can continue to run
without cloud credentials or cluster access.
