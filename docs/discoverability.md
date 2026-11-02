# Project Discovery Metadata

Suggested GitHub repository description:

> Research prototype and simulator for multi-medium backhaul continuity, multipath scheduling and self-scaling content delivery, with an ns-3 cross-validation of its transport model.

Suggested GitHub topics (lowercase, hyphenated):

- `network-simulation`
- `content-delivery-network`
- `cdn`
- `multi-access`
- `multipath-transport`
- `carrier-bonding`
- `ip-mobility`
- `handover`
- `congestion-control`
- `adaptive-mtu`
- `reinforcement-learning`
- `quantum-networking`
- `multi-cloud`
- `cooperative-networking`
- `edge-computing`
- `network-telemetry`
- `wireless-networks`
- `satellite-communications`
- `ns-3`
- `cross-validation`
- `mptcp`
- `reproducible-research`
- `python`

These are metadata suggestions; GitHub repository topics need to be set in repository settings. Prefer the most relevant subset rather than adding every tag if the project focus changes. The topics `ns-3`, `cross-validation`, `mptcp` and `reproducible-research` are supported by
[docs/external-validation.md](external-validation.md),
[`validation/`](../validation) and [`REPLICATION.md`](../REPLICATION.md).

## Historical network KPI data

The demo appends link snapshots and completed transfer KPIs to `output/network_history.csv`. The output directory is ignored by Git so experiment logs do not accidentally become source artifacts.

Rows use `record_type=link` for per-medium observations and `record_type=transfer` for session-level results. Fields include simulated timestamp, load, estimated latency and loss, pressure, current MTU, routing share, session identity, bytes, fragments, attempts, retries, elapsed time, goodput, continuity result, cache-hit flag, and cache-hit ratio.

The KPI definitions are:

- **Continuity success:** reconstructed transfer payload equals the input payload (per successful transfer).
- **Goodput:** delivered payload bits divided by simulated elapsed milliseconds, expressed in Mbps.
- **Retries:** attempted fragments not delivered on the first selected medium.
- **Cache hit ratio:** cache hits divided by cache hits plus misses observed so far.
- **Link routing share:** scheduler-assigned fraction for a medium at the sampled tick.

These are simulator estimates; they are not measurements from a live device or carrier network.
