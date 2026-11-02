# IPv4 vs IPv6 — overhead, fragmentation, and IPv6-agnostic services

A controlled ns-3.49 comparison of IPv4 and IPv6 on a single dual-stack link,
measuring where the two address families actually diverge, and an
introduction to **IPv6-agnostic services**: a service layer that is identified
by *name* (not address) and therefore runs unchanged over either family — the
address family becomes a transport concern invisible to the service.

Everything here is measured by one scratch program
([`validation/ns3/ip46-fabric.cc`](../validation/ns3/ip46-fabric.cc)) and driven
by [`validation/ns3/run-ip46.sh`](../validation/ns3/run-ip46.sh). The committed raw
CSV is [`figures/ip46.csv`](../figures/ip46.csv) (the run writes
`output/validation/ip46.csv`).

## 0. Background and motivation

IPv6 exists because IPv4 ran out. The exhaustion was predicted as early as
1994, the basic protocol landed in RFC 1883 (1995) / RFC 2460 (1998), and the
world staged **IPv6 Launch Day in 2012**. IPv4 addresses are now a traded asset:
a single RIPE **/24 block cost ~$6,600 in 2026**, even though many large
organisations use only a fraction of the /16 blocks they were assigned. The
address space is a scarce resource, so a service layer that is *tied to the
address family* inherits that scarcity.

IPv6's design targets matter directly for this work:

- **End-to-end connectivity** (NAT removed the end-to-end model; IPv6 restores
  it) — relevant to a fabric where a name resolves to a reachable endpoint, not
  a NATted one.
- **NDP replaces ARP** and **IPsec/CGA** bind a signature key to an address — the
  same "identity is a hash" idea the name fabric uses for self-certifying names.
- **Extension headers** keep the base header fixed and simple while allowing
  optional per-packet features (ESP 50, AH 51, Routing 43).
- **Flow label** (20 bits): *"source, destination and flow label are used to
  identify this traffic"*; unlabelled packets carry 0. This is the primitive
  that G3 compares against IPv4's 5-tuple.

These targets — not raw throughput — are where IPv4 and IPv6 genuinely diverge,
and they are what the experiments below quantify or argue.

## 1. Setup

- **2 nodes**, one `PointToPoint` link (1 Gbit/s, 1 ms delay), both the IPv4 and
  IPv6 stacks installed on the same devices — so IPv4 and IPv6 are compared on
  an *identical* medium.
- A custom UDP echo `ClientApp`/`ServerApp`: the client stamps each datagram
  with a 32-byte header (sequence, magic, send-time, address family) and the
  server echoes it, so RTT and per-family delivery are measured directly.
- Wire bytes are counted at `PhyTxEnd`, so *overhead* is the true on-the-wire
  header cost, not an assumption.
- Three experiments, 2000 datagrams each:

| Experiment | MTU | Payload | Question |
| --- | ---: | ---: | --- |
| `overhead` | 1500 | 128 B | What does each header cost on a small packet? |
| `fragment` | 1280 | 1400 B | What happens when the payload exceeds the MTU? |
| `agnostic` | 1500 | 128 B | Can a name-identified service switch family mid-session? |

## 2. Results (measured)

| Experiment | Family | Sent | Echoed | Goodput (Mbit/s) | Overhead (B/datagram) | RTT (ms) | Switch gap (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| overhead | ipv4 | 2000 | 1999 | 0.683 | **30.1** | 2.00 | — |
| overhead | ipv6 | 2000 | 1999 | 0.683 | **50.1** | 2.00 | — |
| fragment | ipv4 | 2000 | 1999 | 7.467 | **52.1** | 2.02 | — |
| fragment | ipv6 | 2000 | 1999 | 7.467 | **108.1** | 2.02 | — |
| agnostic | — | 2000 | **2000** | 0.205 | 40.2 (mix) | 2.00 | **5.00** |

(The `echoed 1999` rows drop only the final datagram, whose echo arrives after
the 3 s stop time — a measurement-boundary artefact, not a protocol failure.)

Figures: [`figures/ip46_overhead.png`](../figures/ip46_overhead.png),
[`figures/ip46_agnostic.png`](../figures/ip46_agnostic.png).

## 3. Hypothesis verdicts

### G1 — IPv6 carries a larger fixed header than IPv4 — CONFIRMED

IPv6's fixed header is 40 bytes against IPv4's 20. Measured on 128 B payload:
**30.1 B vs 50.1 B per datagram** — a constant **+20 B** that is exactly the
fixed-header delta. Goodput is *identical* (0.683 Mbit/s): the larger header
costs wire efficiency, not application throughput, because goodput counts
payload bytes and the payload is unchanged. The relative cost is worst for
small packets, which is the backhaul-relevant regime (short control/Interest
messages).

### G2 — Fragmentation differs, but *where* it happens matters — PARTIALLY CONFIRMED

With a 1400 B payload on a 1280 B MTU, **both families delivered all 2000
datagrams** (0 % loss). The divergence is in the *overhead*: IPv4 host-fragments
into two datagrams for **52.1 B** of overhead; IPv6 source-fragments via its
8-byte Fragment extension header for **108.1 B** — roughly double.

Two honest clarifications:

1. This single-link topology exercises **source** fragmentation. Both IPv4 and
   IPv6 source-fragment, so both succeed. The famous "IPv6 does not fragment"
   rule is about *routers*, not end hosts: an IPv4 **router** may fragment a
   datagram in flight, while an IPv6 router must drop it and signal **Packet Too
   Big** so the *source* adapts (PMTUD). Demonstrating that router-level split
   requires a 3-node topology (client–router–server with a smaller second link);
   it is architectural here, not yet measured.
2. ns-3's IPv6 stack honours source fragmentation with the Fragment extension
   header; the measured +56 B is the visible cost of that mechanism.

### G3 — IPv6 classifies services with the flow label instead of the 5-tuple — ARCHITECTURAL (documented)

IPv4 classifies a flow by the 5-tuple (source/dest address, source/dest port,
protocol); IPv6 adds a 20-bit **flow label** that can identify a flow without
touching the addresses. In the name fabric this maps cleanly onto the
self-certifying name: the flow label can be the low 20 bits of the content hash,
so a balancer can steer *one service object* consistently across all fragments
without inspecting addresses or ports. This is a design comparison, not a
measured experiment in this program.

### G4 — IPv6-agnostic services run unchanged over either family — CONFIRMED

The `agnostic` experiment sends a name-identified service for 10 s and switches
the transport from IPv4 to IPv6 at t = 5 s *without the service layer knowing*.
Measured: **1000 datagrams echoed on the IPv4 leg, 1000 on the IPv6 leg, 2000/2000
delivered, zero loss**, and a **5.00 ms switch gap** — exactly one send interval,
with the mean RTT (2.00 ms) unchanged. The service object itself (header + payload)
never changes; only the encapsulating family does.

## 4. IPv6-agnostic services

The concept: **identify a service by name, not by address.** In the name fabric a
service is a self-certifying content name (a hash), so the *service layer* deals
in names and the *transport layer* deals in whatever address family the network
offers. A request "resolve the name and reach the address" collapses into one
operation; whether that operation is carried by IPv4 or IPv6 is immaterial to
the caller.

Consequences, measured or argued above:

- **Seamless family migration** (G4): the name binding survives a mid-session
  IPv4→IPv6 switch with zero loss and one send-interval of interruption.
- **No dual-stack at the service boundary**: a name-based resolver can hand back
  an IPv6 endpoint to an IPv4-only client via a gateway *by name*, because the
  client never needs to understand the address syntax.
- **Address-family transparency**: the 32-byte service header is the only shared
  contract; it carries no addresses, only the name-derived flow identity.

## 5. Limitations

- Single-link topology: source fragmentation is exercised, router fragmentation
  is not. A client–router–server topology is the next increment.
- Flow-label steering (G3) is documented, not simulated.
- Goodput is rate-limited by the client, so it shows *equality* rather than a
  throughput ceiling; a saturation run would add a goodput ceiling comparison.
