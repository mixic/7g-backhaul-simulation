# Quantum-Assisted Cooperative Multi-Backhaul

This concept extends the self-scaling CDN mesh with cooperative classical
backhauls and a separately modeled quantum resource link. The intent is to
coordinate route selection, congestion avoidance, cache placement, and optional
quantum key-material allocation while keeping each function's limits explicit.

## Do not treat quantum links as byte links

A quantum channel does not carry an ordinary IP byte stream. This simulator
therefore does not add quantum links to the classical packet-bonding list and
does not fragment application data into qubits.

`QuantumResourceLink` models a constrained quantum resource used for abstract
key-material generation. Its `max_qubits_per_frame` is a **quantum frame
capacity**, measured in qubits; it is not an Ethernet/IP MTU and must not be
compared to byte counts. The model translates qubit attempts and a configured
fidelity factor into a simulated key-bit buffer. This is only a capacity
abstraction—not a QKD protocol, entanglement-distribution protocol, security
proof, or real random-key generator.

When classical content traverses a multi-link mesh route, each `MeshLink`
contributes its classical MTU and encapsulation overhead. The usable payload
MTU for that selected route is:

```text
classical_path_payload_mtu =
  min(link.classical_mtu_bytes - link.encapsulation_overhead_bytes
      for each link in the route)
```

The content is sized into a modeled fragment count using this path MTU. Quantum
frame capacity has no effect on that calculation. A deployed QKD system's
classical coordination messages would also use classical links and their own
classical MTUs.

## Cooperative policy loop

`CooperativeBackhaulCoordinator` composes existing mesh behaviors:

1. Peer links share local telemetry and second-order pressure forecasts.
2. The mesh keeps multiple classical paths active and allocates traffic using
   link capacity, cost, latency, and forecast congestion speed/acceleration.
3. Regional request-rate forecasting can trigger cache replication; the
   pollution guard still requires reuse and the content must pass its trusted
   manifest digest check.
4. If a remote response requires quantum-assisted key material, the coordinator
   reserves buffered bits from an available quantum resource link connecting
   the requesting and serving peers. A local cache hit does not consume remote
   key resources.

This is a cooperative **decision model**, not distributed consensus or
independent agents learning together. The congestion forecaster, weighted path
cost, demand predictor, and cache admission rules are transparent heuristics.
The existing small tabular Q-learning agent is not connected to the quantum
resource manager and this coordinator does not claim deployment-grade AI.

## Running the demo

`python main.py` builds a three-peer mesh with a congested direct classical
route, an alternate route with a smaller end-to-end MTU, and a separate
quantum-resource link. The output shows:

- predicted congestion, active-active classical route shares, and
  congestion-acceleration response;
- route payload MTU and fragment count;
- modeled qubit frame count and key-material buffer;
- key-bit reservation for remote content responses;
- demand-driven cache replication and subsequent local cache hit.

## Deployment and safety boundaries

- The key-buffer arithmetic is illustrative and does not model quantum
  measurement, error correction, privacy amplification, authenticated
  classical channels, device calibration, or composable security.
- A reserved key-bit count is not used to encrypt the simulated content. Real
  deployments must integrate reviewed cryptographic protocols and key lifecycle
  management; do not treat this model as providing confidentiality.
- Quantum resource links are direct peer-pair abstractions; there is no
  entanglement routing, repeater model, key relay, or quantum network control
  plane.
- Cache and path actions run in one process. Peers do not exchange signed
  telemetry, resolve conflicting policies, or execute hardware forwarding
  changes.
- Classical route MTUs, encapsulation, fragmentation, and packet loss are
  independent of quantum qubit-frame limits.

The next research phase should validate predictive path/cache decisions on
recorded classical telemetry and model quantum resource capacity from an
explicit protocol/provider profile before considering hardware integration.
