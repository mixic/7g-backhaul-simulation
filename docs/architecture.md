# Seamless Multi-Medium Delivery and Self-Scaling CDN

## Thesis connection

This design takes inspiration from Milan Nikolic's University of Bern master's thesis, *Gezora: A Self-Scalable Content Distribution Network* (2010), included in this repository as [`Ni10.pdf`](../Ni10.pdf). The simulator uses the thesis's self-scaling CDN goal as a foundation: learn regional content demand, improve request placement, and add cache capacity where demand is growing. The implementation here is a new educational model, not a reproduction of Gezora.

The design also emphasizes request routing, service discovery, measurement, and simulation. In this repository, per-region popularity is learned from requests, telemetry exposes transport conditions, and deterministic trend estimation gives cache placement a measurable trigger.

## Continuity model

An application session has a stable session ID and byte stream. The stream is split into fragments, and each fragment may use a different physical transport:

- Microwave / directional radio
- HF
- LEO satellite
- Mobile
- Wi-Fi
- Drone relay

`Mixed` describes a session using several of these media concurrently; it is not modeled as a separate physical link. The transport policy distributes fragments across available paths and retries a lost fragment on another path. A receiver reassembles by session ID, byte offset, and total message length, so fragments may arrive out of order or use different MTUs without changing the application payload.

This is a simulator abstraction for continuity, not a claim that arbitrary real networks can provide zero interruption. It does not implement radio access handover, carrier integration, a common IP mobility anchor, congestion control, cryptographic framing, or real-time scheduling. A real deployment would need those mechanisms and end-to-end testing.

## Variable MTU and adaptation

Each medium advertises its own network-layer MTU and encapsulation overhead. Available application payload size is:

```text
payload_mtu = current_link_mtu - encapsulation_overhead
```

The modeled link MTU can shrink as load increases. `AdaptiveMTULearner` explores supported payload sizes per medium and updates an online reward estimate from delivery feedback. Successful larger payloads are more efficient; a loss penalizes that size and triggers retransmission on another medium. This is a lightweight online bandit-style policy, not a trained neural network or production-grade reinforcement-learning agent.

## Demand velocity and acceleration

Cache scaling uses request arrivals to estimate request-rate velocity and acceleration. A general metric forecast uses equally spaced samples:

```text
v(t) = (x(t) - x(t - Δt)) / Δt
a(t) = (x(t) - 2x(t - Δt) + x(t - 2Δt)) / Δt²
x̂(t + H) = x(t) + v(t)H + 0.5a(t)H²
```

The same estimator can be applied to request rate, throughput, or latency. `RequestDemandLearner` currently computes the request-rate signal from recent arrival windows; the CDN forecasts demand over a configurable horizon and creates a regional cache when observed or forecast demand crosses its scaling threshold. Per-region object popularity then guides cache warming and eviction.

This is a deliberately transparent baseline. Real CDN scaling should include forecast uncertainty, cache-fill cost, origin capacity, network price, and latency SLOs before taking an action.

## How to exercise it

The test suite checks:

- The original bytes reconstruct after fragments use multiple media and MTUs.
- A receiver can reassemble out-of-order fragments.
- The second-order forecast computes velocity, acceleration, and projected demand.
- Accelerating regional requests trigger cache placement and warming.

Run the interactive simulation with `python main.py`; generated dashboard frames are saved in [`../figures/`](../figures/).

## Next research steps

- Replace the fixed finite-difference predictor with a validated online forecast and confidence interval.
- Add throughput and latency histories to the route reward and trigger proactive path/capacity changes.
- Model cache-fill traffic and compare request latency against an origin-only baseline.
- Test correlated outages, reordered/lost fragments, and realistic per-medium rate limits.
- Define the receiver/session protocol and experiment against real multi-access networks.
