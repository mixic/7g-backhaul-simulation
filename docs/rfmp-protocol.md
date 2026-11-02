# RFMP v0.1 — Role-Fluid Multipath Protocol specification

**Status:** draft, implementable, version 0.1.
**Companion implementations:** [`simulation/rfmp.py`](../simulation/rfmp.py) (Python
discrete-event reference) and
[`validation/ns3/rfmp-role-transition.cc`](../validation/ns3/rfmp-role-transition.cc)
(ns-3.49 packet-level reference), validated by
[`docs/rfmp-validation.md`](rfmp-validation.md).

This document specifies the protocol the role-fluid paradigm needs: a multipath
transport whose scheduling, path management, reordering and role/boundary
handoff are defined precisely enough that two independent implementations agree
on packet-level outcomes. It exists because the paradigm cannot be evaluated
against an external simulator until there is something to implement.

## 1. Scope and non-goals

In scope:

- a multipath data plane over heterogeneous links with per-path weights derived
  from a potential field;
- a path manager (add/remove, failure detection, re-probing);
- an ACK clock and RTT estimation;
- a receiver reordering buffer with a bounded deadline;
- a role-transition procedure that moves the content source between nodes
  without breaking the stream, and the medium-boundary fragmentation rule that
  it inherits.

Out of scope for v0.1 (and therefore not validated by the companion
implementations):

- TCP-like congestion control (a fixed offered rate is used; the window is not
  closed by loss);
- security, authentication and encryption;
- mobility of endpoints (the role transition moves the source, not the user);
- fairness across competing RFMP flows;
- cache capacity and hit-ratio semantics (the role transition assumes the
  serving node can answer, or must fill first).

## 2. Terms

- **Source node** — the node that currently originates content for a demand.
- **Serving node** — a node acting in the `serve` role; it is the source for its
  downstream demand.
- **Path** — one simple sequence of links from the source to the demand node.
- **Role epoch** — the interval during which a node keeps one role.
- **Handoff window** — the overlap interval during which the outgoing and
  incoming sources both emit, so that a transition never depends on a
  stop-and-wait message exchange.

## 3. Roles and the role/boundary interface

A node is in exactly one role per epoch: `forward`, `balance`, or `serve`.

| Role | Behaviour | Bound |
| --- | --- | --- |
| `forward` | relays packets toward the demand, no local termination | none |
| `balance` | relays and may split traffic across its downstream links | one overhead per epoch |
| `serve` | originates content locally for its downstream demand; also relays residual traffic | local service capacity |

A role change takes effect at an epoch boundary. The transition procedure
(§8) is identical for all role pairs; the implementation only needs to decide
whether the node becomes a source, stops being one, or both.

## 4. Packet formats

All fields are big-endian. A data packet carries a 24-byte RFMP header inside the
1200-byte application payload, so on-wire size is 1200 bytes plus the 28-byte
IPv4/UDP header where a real stack is used.

**DATA**

| Offset | Size | Field | Meaning |
| ---: | ---: | --- | --- |
| 0 | 8 | `seq` | global, monotonically increasing per content stream |
| 8 | 8 | `send_time` | seconds, sender clock, used for one-way delay |
| 16 | 1 | `source` | 0 = origin, 1 = serving node |
| 17 | 1 | `path` | path index at the source |
| 18 | 2 | `flags` | bit 0 = probe, bit 1 = retransmission (unused in v0.1) |
| 20 | 4 | `content_id` | stream identifier |

**ACK**

| Offset | Size | Field |
| ---: | ---: | --- |
| 0 | 8 | `cum_ack` — highest contiguous released sequence |
| 8 | 8 | `recv_time` — receiver clock |
| 16 | 8 | `echo_send_time` — send time of the packet that triggered this ACK |

ACKs are sent on the reverse path (the path the triggering packet used) and are
not retransmitted.

## 5. Sender

### 5.1 Emission

The offered load is a constant bit rate. Packet `k` is emitted at
`t_k = k · Δ`, `Δ = 0.8 ms`, for `k = 0 … N−1`, `N = 25000` over 20 s. The
**active source** for packet `k` is decided by the role epochs, not by the packet
stream: the origin is the source while it is in a sourcing role, the serving node
while it serves, and during a handoff window both emit (§8).

### 5.2 Scheduling

At every control interval of 100 ms the sender recomputes one weight per usable
path:

```
u_i   = bytes_sent_i(now − 500 ms … now) / (capacity_i · 0.5 s)
w_i   = max(ε, capacity_i / (latency_i + 1 ms) · (1 − min(1, u_i)))
```

and assigns each packet with **smooth weighted round robin**:

```
deficit_i += w_i / Σw
pick argmax_i deficit_i
deficit_pick −= 1
```

Ties break toward the lower path index. The same rule is specified in the
transport cross-validation (`validation/scenario_s1.py`), so implementations
already exist for it.

### 5.3 Path state

A path is `UP` until the failure detector (§7) marks it `DOWN`. `DOWN` paths
receive no traffic; their weight is zero. A path is re-probed every 500 ms with
a probe data packet (flag bit 0), which carries no payload semantics and is
acknowledged normally. Three successful probes restore `UP`; a failed probe
resets the counter.

### 5.4 Pacing and rate

The sender may not exceed `capacity_i` on any path in any 100 ms interval. If
the weighted assignment would exceed it, the excess is redistributed to paths
with residual capacity in weight order, at most twice. This is the "spill" rule.

## 6. Receiver

### 6.1 Reordering buffer

The receiver keeps `next_expected`, initially 0.

- On arrival of a DATA packet with `seq`:
  - if `seq < next_expected`, it is a **duplicate**: count it, discard it;
  - else if already buffered, count a duplicate, discard the later copy;
  - else buffer it with its arrival time.
- Release loop: while `next_expected` is buffered, release it (record
  `release_time`), increment `next_expected`, and continue.
- **Deadline:** if a buffered packet has waited longer than `REORDER_DEADLINE`
  (200 ms), the receiver declares `next_expected` lost, advances
  `next_expected` to the lowest buffered sequence, and releases. A packet waiting
  beyond `LATE_DROP` (400 ms) is discarded as late.
- `stall = release_time − arrival_time` per packet, reported as p95 and max.

### 6.2 ACK clock

An ACK is emitted every `ACK_INTERVAL` (10 ms) if at least one packet was
received since the previous ACK, and immediately on release of a packet that
fills a hole. `cum_ack` is `next_expected − 1`. `echo_send_time` is the send
time of the most recently released packet.

### 6.3 RTT estimation

`srtt ← 7/8·srtt + 1/8·(recv_time − echo_send_time)`; `rto = 3·srtt` with a floor
of 50 ms. RTT is reported per path and is not used for congestion control in
v0.1.

## 7. Failure detection and path management

A path is marked `DOWN` when either condition holds:

- no ACK has arrived for that path for `3 · srtt` (or 150 ms before the first
  sample), while the path carried traffic; or
- three consecutive probe packets on the path go unacknowledged.

A `DOWN` path is re-probed every 500 ms. Removal from the candidate set is
immediate; re-addition requires three successful probes. `add` and `remove`
events are logged with timestamps so role-transition behaviour can be attributed
to scheduling rather than to path churn.

## 8. Role transition procedure

For a transition at epoch boundary `T`:

1. The incoming source starts emitting at `T − HANDOFF_HEADSTART`
   (`HANDOFF_HEADSTART = 50 ms`) and continues.
2. The outgoing source stops emitting at `T + HANDOFF_TAIL`
   (`HANDOFF_TAIL = 50 ms`).
3. Both emit the *same* packet sequence numbers during the overlap
   (`T − 50 ms ≤ t_k < T + 50 ms`), so the receiver sees duplicates and
   suppresses them by `seq` (§6.1). Sequence numbers are derived from the packet
   index (`seq = k`), never from a counter exchanged between nodes.
4. No handshake, no stop-and-wait, no sequence reset is permitted. A transition
   is therefore *always* completed in bounded time; the only observable effect is
   a short duplicate burst and a possible reordering stall while the old path
   drains.
5. Reported transition metrics: duplicate rate in the window, maximum stall in
   the window, and the **in-order release gap** — the interval between the last
   release before `T` and the first release at or after `T`.

The in-order release gap is the paradigm's continuity claim in measurable form.
A protocol that resets on transition has a gap of one RTT or more; RFMP predicts
zero gap whenever the incoming path is no slower than the old path's worst-case
drain.

## 9. Boundary rule

When a packet crosses a medium boundary with smaller MTU, the transmitted
fraction of a packet is `T = mtu_next / mtu_prev` (capped at 1) and the
reflected fraction `1 − T` is requeued on the same path after
`REFLECTION_DELAY = 2 ms`, with the same `seq`. In the v0.1 implementations a
packet is not split; the rule is applied as a per-path serialization overhead
`1 + max(0, 1500/mtu − 1)`, which is the same first-order effect and is what the
Python role-fluid model uses. True packet splitting is deferred to v0.2 and is
explicitly **not** validated by the current comparison.

## 10. Constants

| Constant | Value |
| --- | --- |
| `PAYLOAD_BYTES` | 1200 |
| `HEADER_BYTES` | 24 (inside the payload); 28 IPv4/UDP where a stack exists |
| `DEMAND_MBPS` | 12 |
| `PACKET_INTERVAL` | 0.8 ms |
| `DURATION` | 20 s |
| `CONTROL_INTERVAL` | 100 ms |
| `UTILIZATION_WINDOW` | 500 ms |
| `HANDOFF_HEADSTART`, `HANDOFF_TAIL` | 50 ms each |
| `REORDER_DEADLINE` | 200 ms |
| `LATE_DROP` | 400 ms |
| `ACK_INTERVAL` | 10 ms |
| `RTO` | `3·srtt`, floor 50 ms |
| `PROBE_INTERVAL` | 500 ms |
| `QUEUE_LIMIT` | 100 packets per link (drop-tail) |

## 11. Validation scenario RT1

Topology: origin `O`, role-fluid node `X`, demand node `D`.

| Link | Capacity | One-way latency | MTU |
| --- | ---: | ---: | ---: |
| `O–X` path 0 (fibre) | 20 Mbit/s | 4 ms | 9000 |
| `O–X` path 1 (satellite) | 8 Mbit/s | 20 ms | 1200 |
| `X–D` (edge) | 30 Mbit/s | 2 ms | 1500 |

Phases: `forward` on `[0, 6)`, `serve` on `[6, 12)`, `forward` on `[12, 20)`.

**Cache rule (RT2).** In RT2 the serving node starts with a cold cache. During
the serve epoch its hit ratio is

```
hit(t) = min(1, (t − 6 s) / WARM_SECONDS)
```

with `WARM_SECONDS = 8 s`. Packet `k` in the serve epoch is served by `X` when
`hash_unit(seed, k) < hit(t_k)` and by `O` otherwise, where `hash_unit` is the
same deterministic uniform used for the jitter. The assignment is **exclusive**:
exactly one node sources each sequence number, so RT2 produces no duplicates and
does not need the overlap window of RT1. Misses keep using the RT1 paths, so a
cold-cache transition is a *gradual* handover rather than a switch.

**Scenarios.** RT1 (`warm cache`, overlap handoff) validates the transition
mechanics; RT2 (`cold cache`, hit-based split) validates the cache-aware
transition, where serving capacity ramps up while the demand stream is already
live.

Metrics, reported per replicate and as paired differences between
implementations: in-order delivery, duplicate rate, served fraction, transition
gaps, p95 and max stall, mean one-way delay, and late drops.

## 12. Acceptance criteria (fixed before running)

The Python and ns-3 implementations are expected to agree on:

1. in-order delivery within **0.5 percentage points**;
2. duplicate rate within **0.1 percentage points**;
3. served fraction within **0.5 percentage points** (RT2);
4. p95 reorder stall within **15 %** relative;
5. transition gap within **5 ms**;
6. predicted transition behaviour: RT1 shows **zero in-order gap** with a stall
   spike of at most the old path's drain time (≈20 ms); RT2 shows a
   **gradual** handover whose served fraction equals the mean hit ratio
   (3/8 of the epoch for the 6 s epoch and 8 s warm-up above).

A failure of any criterion is reported as a discrepancy, not as a tuning target.
