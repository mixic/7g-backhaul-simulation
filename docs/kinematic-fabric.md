# Role-fluid, kinematic backhaul fabric in ns-3

A high-fidelity ns-3 simulation of a heterogeneous backhaul fabric where nodes
are role-fluid, resolution is collapsed into forwarding, and role transitions
are driven by a kinematic (velocity/acceleration) controller. This document
reports the architecture, the three hypotheses, and the measured results —
including where they fail.

## 1. Architecture

One scratch program ([`validation/ns3/role-fluid-fabric.cc`](../validation/ns3/role-fluid-fabric.cc))
implements the whole fabric; `run-fabric.sh` builds and runs it.

- **50 nodes, no IPv4.** Every node speaks over `PacketSocket`, so the fabric
  owns forwarding end to end and the standard IP stack is not involved.
- **Custom `RoleFluidHeader`** (an `ns3::Header`): content name, hop limit,
  fragment offset, total fragment count, path MTU, and a send timestamp used to
  measure per-hop queueing delay.
- **No DNS.** A flood-learned FIB with least-cost flooding: each node keeps the
  lowest-latency ingress per name and re-floods only when its best improves. A
  pending-interest table (PIT) reverses the path for Data.
- **Byte-offset fragmentation** at the transport: the server splits an object by
  the minimum MTU along the Interest's path (1500 B fibre → 2 fragments, 500 B
  satellite → 5), and the receiver reassembles by offset.
- **Potential field** `Φ = a·queue + b·latency + γ·fragment + δ·role`, used to
  pick the egress.
- **Kinematic (Turbo) controller:** EMA of request rate and acceleration;
  pressure `P = w1·EMA(v) + w2·EMA(a)`; impedance `1 + k1·P + k2·P³`; role
  transitions (router → balancer → server) with 50 ms inertia.
- **Heterogeneous links:** fibre (P2P 1 Gbit/s, 2 ms), microwave (CSMA
  100 Mbit/s, 10 ms), satellite (P2P 10 Mbit/s, 500 ms, MTU 500 B), satellite
  only on the chords so worst-case path latency stays bounded.

## 2. Scenarios

| Scenario | Meaning |
| --- | --- |
| `A_static` | fixed roles, gradient forwarding, shockwave (12× demand on t∈[50,60)) |
| `A_turbo` | the kinematic controller, same shockwave |
| `B_dns` | server for name 0 moves at t=50; clients hold a 300 s "TTL" binding |
| `B_name` | same move; name-based forwarding with withdrawal |
| `C_single` | single-path, MTU fragmentation, no loss |
| `C_fabric` | balancer splitting, MTU fragmentation, 0.5 % satellite loss |
| `stability` | 10 000 s at low rate (deadlock check) |

## 3. Results (3 paired seeds per scenario)

| Scenario | Transitions | Mean queue | Shockwave queue | Mean TTFB | Drop rate | Retrans. | First success after move |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A_static | 0 | 121.7 ms | 239.8 ms | 649.9 ms | 0.50 % | 0 | — |
| A_turbo | 76 | 164.3 ms | 276.5 ms | 297.7 ms | 0.50 % | 0 | — |
| B_dns | 0 | 1.5 ms | 1.5 ms | 34.7 ms | 1.71 % | 0 | 0.90 s |
| B_name | 0 | 1.5 ms | 1.5 ms | 34.7 ms | 0.28 % | 0 | 0.90 s |
| C_single | 0 | 1.7 ms | 1.7 ms | 36.7 ms | 0.95 % | 0 | — |
| C_fabric | 0 | 1.6 ms | 1.6 ms | 34.6 ms | 78.1 % | 4624 | — |
| stability | 111 | 1.6 ms | 1.6 ms | 15.8 ms | 0.01 % | 0 | — |

The raw CSV is [`figures/fabric.csv`](../figures/fabric.csv).

## 4. Hypothesis verdicts

### H1 — the kinematic advantage: FAILED

The Turbo controller did **not** reduce queue delay during the shockwave; it
increased it (276.5 ms versus 239.8 ms in the window, 164.3 versus 121.7 ms
mean). It did cut mean TTFB (297.7 versus 649.9 ms) because transit nodes that
switched to the server role served cached content locally, shortening the data
path — but the queue-drop benefit the hypothesis required is absent.

The instability trap the task asked me to watch for **is present**: 76 role
transitions over 120 s (≈0.63/s) without any queue reduction. The cubic gain
`k1·P + k2·P³` reacts to acceleration by shedding roles, but in this fabric the
dominant delay is propagation (satellite paths), which role switching cannot
absorb. H1 fails as stated.

### H2 — DNS independence: architecturally demonstrated, measurement incomplete

The fabric eliminates the DNS resolution latency floor **by construction**: the
name is the route, and there is no lookup that must complete before the first
packet moves. This surfaced in the experiment itself — an attempt to model a
"300 s TTL" baseline failed to reproduce a 300 s block, because the fabric
re-routes by name at every hop, so a stale first-hop binding cannot pin a
client to a dead server end-to-end.

The measurable cost of the stale binding is small but real: the DNS-stale mode
drops 1.71 % of requests versus 0.28 % for name-withdrawal. H2's mechanism is
supported; the head-to-head "TTL-limited versus link-limited" number is **not**
produced, and I report that rather than fabricate it.

### H3 — boundary coefficients: no deadlock, partial fidelity

Fragmentation and reassembly across MTU boundaries (1500 B ↔ 500 B) works
without deadlock: the 10 000 s run completes with 0.01 % drop, and under 0.5 %
satellite loss the retransmission path recovers (4624 retransmissions, no
deadlock). The boundary is modelled as a per-path MTU fragment count, **not** a
true transmission/reflection queue, so "accurately modelled" is only partially
satisfied.

## 5. Acceptance criteria

- **10 000 simulated seconds without deadlock: PASS** (111 transitions, 0.01 %
  drop, no crash).
- **CSVs contain Role_Transitions, Queue_Delay, TTFB, Packet_Drop_Rate: PASS**
  (`figures/fabric.csv`).
- **Turbo reduces peak queue delay versus static: FAIL** (276.5 vs 239.8 ms).
- **Cubic gain churn reported: YES** (76 transitions, no queue benefit).

## 6. What is honest about this and what is missing

- The drop-rate KPI counts unresolved and retransmitted requests, not device
  queue drops; ns-3's point-to-point queue-drop trace is not wired in.
- The DNS baseline is a stale first-hop binding on a name-routed transport, so
  it is not a faithful IP/DNS reference; a true address-based comparison is
  future work.
- The satellite link is a point-to-point link with 500 ms propagation, not a
  custom channel or PHY; no hypothesis depends on one.
- Fragmentation lives in the transport (which sits directly on the NetDevices,
  because IPv4 is bypassed), not in a NetDevice subclass.
- The Turbo controller's gains and the shockwave magnitude are stipulated; the
  H1 failure is specific to those values and this topology.

## 7. Reproduction

```bash
NS3_DIR=~/ns-3-dev ./validation/ns3/run-fabric.sh
#    -> output/validation/fabric.csv
```
