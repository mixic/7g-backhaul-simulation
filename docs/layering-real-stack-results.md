# Layering real-stack results (P8-P12)

**Predictions frozen at commit:** `46c7b40` (`docs/layering-real-stack-predictions.md`,
committed before any harness code; never edited).
**Harness:** `validation/real_stack/` (Python; three netns, AF_PACKET capture,
mutation/cause gates, verdict CSV). **Protocol: the frozen 20 runs per case.**
**Raw output:** `validation/real_stack/results/observations.csv` and `verdicts.csv`.
**Verdict summary:** **all five predictions (twelve cases) CONFIRMED**
(P8a, P8b, P8c and their controls; P9; P10a and P10b; P11a, P11b, P11c; P12a,
P12b, P12c). No case is INCONCLUSIVE or NOT RUN on this host.

> **History.** An earlier version of this file reported "P11 INCONCLUSIVE, six
> confirmed" from ad-hoc bash scripts. That was wrong for two reasons, both now
> corrected: the scripts used an `ip tos` mangler on a `root prio` qdisc whose
> inert control failed, and the scripts were never committed. The committed
> Python harness uses a `clsact` qdisc with `pedit … csum ip4h`, and its inert
> ToS control delivers 100 %. See §P11.

## Status (20 runs per case)

| Prediction | Status | Evidence |
|---|---|---|
| P8a (AH tunnel through NAT) | **CONFIRMED** | control 100 %, NAT 0 %; `XfrmInStateProtoError` rises by the datagram count |
| P8b (ESP tunnel through NAT) | **CONFIRMED** | control 100 %, NAT 100 % |
| P8c (WireGuard through NAT) | **CONFIRMED** | control 100 %, NAT 100 %; peer endpoint learns the NAT address |
| P9 (WireGuard wire overhead) | **CONFIRMED** | 9/9 lengths exact: 92, 108, 124, 124, 140, 172, 1068, 1084, 1468 B |
| P10a (naive commutation) | **CONFIRMED** | `d(L) ≠ 0` for every length |
| P10b (quantised model) | **CONFIRMED** | `d(L) = R(L+20) − R(L) − 20 ∈ {−4, +12}` for every length |
| P11a (UDP length 9, checksum untouched) | **CONFIRMED** | 0 % delivery, cause confirmed |
| P11b (UDP length 9, checksum recomputed) | **CONFIRMED** | 0 % delivery, cause confirmed |
| P11c (inert ToS rewrite) | **CONFIRMED** | 100 % delivery — the control that validates the mangler |
| P12a (ESP transport + NAT, inner checksum) | **CONFIRMED** | 0 % delivery; `UdpInCsumErrors` rises by the datagram count |
| P12b (same, checksum zeroed) | **CONFIRMED** | 100 % delivery |
| P12c (control, no NAT) | **CONFIRMED** | 100 % delivery |

## P8 — NAT against real integrity scopes

Three-namespace topology, `nftables masquerade` on the router egress, controls
without NAT. AH's integrity scope covers the outer source address, so the
masquerade rewrite invalidates the ICV (P8a). ESP does not cover the outer IP
header (P8b), and WireGuard authenticates only its own payload (P8c), so both
survive. AH dying under NAT is textbook (RFC 3715); the experiment confirms the
harness, not a new fact.

## P9 — WireGuard wire overhead

For an inner IPv4 packet of length `L`, the outer IP total length is exactly
`wire(L) = 60 + 16·⌈L/16⌉`:

| L | 29 | 44 | 60 | 61 | 76 | 100 | 1000 | 1024 | 1400 |
|---|---|---|---|---|---|---|---|---|---|
| predicted | 92 | 108 | 124 | 124 | 140 | 172 | 1068 | 1084 | 1468 |
| measured | 92 | 108 | 124 | 124 | 140 | 172 | 1068 | 1084 | 1468 |

The stipulated 56 B composite (`E = 28`, `T = 28`, no padding) is low by
`4 + (16·⌈L/16⌉ − L)` bytes (4–16 B depending on `L mod 16`). This is a
calibration: WireGuard is **quantised**.

## P10 — quantisation breaks commutation

`Y→W` (IPIP then WireGuard) versus `W→Y` (WireGuard then IPIP):

| L | 64 | 65 | 76 | 77 | 79 | 100 | 1000 | 1008 |
|---|---|---|---|---|---|---|---|---|
| wire(Y→W) | 156 | 156 | 156 | 172 | 172 | 188 | 1084 | 1100 |
| wire(W→Y) | 144 | 160 | 160 | 160 | 160 | 192 | 1088 | 1088 |
| d(L) | +12 | −4 | −4 | +12 | +12 | −4 | −4 | +12 |

\* In an earlier exploratory capture the first `Y→W` L = 64 sample landed on the
WireGuard handshake-init packet (20 IP + 8 UDP + 148 WG = 176 B). The harness now
attributes sweep packets by capture timestamp, and all 20 committed runs record
the 156 B data packet, so the committed table has no artifact.

`d(L) = R(L+20) − R(L) − 20` exactly. **P10a is false** (fixed-overhead layers
do *not* commute when one layer quantises) and **P10b is exact**.

## P11 — confirmed, and the bisect that explains the old failure

| Case | Mangler | Delivery | Predicted |
|---|---|---|---|
| P11a | outer UDP length → 9, checksum untouched | **0 %** | 0 % |
| P11b | outer UDP length → 9, checksum recomputed | **0 %** | 0 % |
| P11c | outer IPv4 ToS byte rewritten (inert) + IP checksum | **100 %** | 100 % |

The mangler uses the **raw-offset** form because iproute2 6.19 rejects the
layered `udp len` field ("bad pedit parsing"):

```text
tc filter add dev vN2 egress protocol ip prio 1 u32 \
  match ip protocol 17 0xff match ip dport 51820 0xffff \
  action pedit ex munge offset 24 u16 set 0x0009 pipe action csum udp
```

The outer UDP length is at IPv4-header offset 24 (20 IP + 4 UDP). The inert
control rewrites the IPv4 ToS byte (offset 1) and recomputes the header
checksum (`csum ip4h`); because it delivers 100 %, the mangler path itself is
sound and the P11a/P11b 0 % results are attributable to the length rewrite.

**Why the old bash result was "INCONCLUSIVE".** The old scripts used a
`root prio` qdisc and a `csum ip` action, and their ToS control delivered 0/50.
That was a mangler-setup defect, not a kernel effect. The bisect that resolved
it (also recorded as a checklist below): (1) `tc -s filter show dev vN2 egress`
shows whether the filter matched; (2) a capture on `vB2` shows whether the
packets left the router; (3) a **no-op** pedit (`ip tos set 0`) separates "the
filter is wrong" from "the rewrite is destructive". With a `clsact` qdisc and
`csum ip4h`, all three checks pass.

## P12 — derived inner checksum

| Case | Delivery | Predicted | Cause gate |
|---|---|---|---|
| control (no NAT) | 100 % | 100 % | — |
| NAT + computed inner UDP checksum | **0 %** | 0 % | `UdpInCsumErrors` + datagrams |
| NAT + zeroed inner checksum (`SO_NO_CHECK`) | **100 %** | 100 % | — |

ESP transport mode does not authenticate the outer IP header, so NAT passes the
ESP check; the inner UDP checksum covers a pseudo-header containing the rewritten
outer address, so it fails. This is the **derived** field class: a field in one
layer is invalidated by a rewrite in another, with no integrity tag involved.

## Environment

| Item | Value |
|---|---|
| Host | WSL2, Ubuntu 26.04.1 LTS |
| Kernel | `6.18.58.1-microsoft-standard-WSL2` |
| Root | `wsl -u root` (`id -u` = 0) |
| `ip` | iproute2 6.19.0 |
| `wg` | wireguard-tools 1.0.20250521 |
| `nft` | nftables 1.1.6 |
| `ethtool` | 6.19 |
| Kernel modules | `wireguard`, `ipip`, `esp4`, `ah4`, `act_pedit`, `act_csum`, `nft_masq` all present |

`tc_pedit_csum` is available in the **raw-offset** form, not the layered
`udp len` form; the probe tests the raw form (see §P11).

## Model consequences (from `layering-real-stack-predictions.md` §9)

| Outcome | Model consequence | Status here |
|---|---|---|
| P8a, P8c, P11 confirmed | survival rule holds against independent implementations | **confirmed** |
| P8b refuted | add a lookup-key field class | not refuted (P8b confirmed) |
| P9 confirmed | replace the 56 B composite by `60 + R(L)`; mark `W` quantised | **confirmed** |
| P10b confirmed | amend P4: commutation needs fixed (non-quantised) size effects | **confirmed** |
| P12a confirmed | add derived dependency edges between layers | **confirmed** |
| any INCONCLUSIVE or NOT RUN | report as such; do not infer a verdict | none on this host |

## P11 bisect checklist (for a future kernel)

1. `tc -s filter show dev vN2 egress` — the filter's `packets` counter must rise.
2. `tcpdump -i vB2 -n 'udp dst port 51820'` — the mangled packets must leave the
   router; compare the captured ToS/length with the filter intent.
3. No-op pedit (`ip tos set 0`) — if delivery stays 100 %, the filter is sound
   and a failing rewrite is the rewrite's effect, not a setup defect.
4. Offload: verify with `ethtool -k` that TX **and** RX checksumming are off on
   all four veth ends (veth marks RX as verified when RX checksumming is on).
5. Do not trust the exit code of `ethtool -K`; trust `ethtool -k`.

## Addenda

- **2026-11-10 — the frozen 20-run protocol (Python harness).** All twelve cases
  confirmed; P11 recovered by the raw-offset mangler and a `clsact` qdisc. The
  earlier "six confirmed / P11 INCONCLUSIVE / P10-P12 not attempted" text was
  from uncommitted bash scripts and is withdrawn. Predictions unchanged.
