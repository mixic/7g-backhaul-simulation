# Layering predictions, real-stack extension (P8-P12)

**Status:** FROZEN. This file was committed before any harness code and is not
edited afterwards; corrections go in a dated addendum at the end, never as
edits. The freeze commit hash is recorded in
[`layering-real-stack-results.md`](layering-real-stack-results.md).

**Provenance.** Every prediction below was derived from protocol specifications
(WireGuard whitepaper, RFC 4302, RFC 4303, RFC 3948, RFC 3715, RFC 768) and from
the documented behaviour of the Linux kernel. None was checked against a running
system when it was written. A confidence label is attached to each prediction; a
wrong low-confidence prediction is an expected, informative outcome, not an
embarrassment.

**Relationship to P1-P7.** `layering-predictions.md` tested the survival
condition (visible, reachable, authenticated, structural) against a codec and
middlebox that share one implementation. This file replaces both with
independent implementations: kernel WireGuard, kernel IPsec (xfrm), and kernel
NAT (nftables). Agreement here is evidence about the rule, not only about the
codec.

**Scope note.** As before, this does not evaluate cryptographic security.
WireGuard, ESP and AH are used as real framing and integrity-scope
implementations. No claim is made about their strength.

## 1. Layers and middleboxes under test

| Symbol | Meaning | Real implementation |
|---|---|---|
| `W` | WireGuard: AEAD plus its own outer IPv4/UDP | kernel wireguard, `wg0` |
| `Y` | IPv4-in-IPv4 tunnel, 20 B fixed | `ip link add type ipip` |
| `AH` | IPsec AH, tunnel mode, HMAC-SHA256 | `ip xfrm`, `proto ah` |
| `ESP` | IPsec ESP, tunnel or transport mode | `ip xfrm`, `proto esp` |
| `N` | NAT middlebox (source NAT of the outer header) | nftables `masquerade` in a router namespace |
| `M` | byte mangler (structural rewrite) | `tc pedit` plus `csum` action, egress on the router |

## 2. Topology

Three network namespaces on one host, connected by two veth pairs:

```text
 cA 10.200.1.2/24 ---- vA1 == vN1 ---- cN ---- vN2 == vB2 ---- cB 10.200.2.2/24
                          10.200.1.1      10.200.2.1
                          (router: ip_forward=1, nft masquerade on vN2 egress)
```

`cA` sends one-way UDP to `cB`; no application-level reply is needed.
Veth MTU 1500, WireGuard MTU 1420, IPIP MTU 1480. No netem loss anywhere.
Capture the outermost IP packet at `vA1` egress (before NAT) and at `vN2` egress
(after NAT and after any mangler). Parse with an `AF_PACKET` socket or
`tcpdump -w`; wire size is always the IP total length, Ethernet excluded.
Each run builds fresh namespaces and fresh keys.

## 3. Observable set and validity gates

The observable set O of `layering-predictions.md` §2 is used unchanged: wire
bytes, maximum payload, delivery, in-order fraction, duplicates, authentication
acceptance. Delivery is "datagram received by the cB application". Two
additions:

- **Mutation gate.** For every case that involves `N` or `M`, the capture at
  `vN2` egress must show that the targeted field changed (for `N`: outer source
  address differs from `10.200.1.2`; for `M`: UDP length or source port differs
  from the `vA1` capture). A case whose mutation gate fails is **INVALID**, not
  refuted.
- **Cause gate.** A predicted drop only counts if the kernel confirms the
  predicted cause by a counter delta in the named statistic. A drop with a
  different or no cause is **INCONCLUSIVE**. This prevents being right for the
  wrong reason.
- **NOT RUN.** If a required kernel facility is missing (for example `ah4`,
  `act_pedit`, `act_csum`, `wireguard`), the case is recorded NOT RUN with the
  missing module named. NOT RUN is neither confirmed nor refuted.

## 4. Field classes the cases probe

| Field class | Meaning | Probed by |
|---|---|---|
| authenticated | covered by an integrity tag | P8 (AH), P8 (WireGuard control) |
| structural | length- or offset-bearing | P11 |
| derived | value computed from a field in another layer | P12 |
| lookup-key | selects a state entry (SA, policy, conntrack) | P8b |
| quantised | size rounded by a layer | P9, P10 |

`derived`, `lookup-key` and `quantised` are not in the current model
(`layering-predictions.md` §3 has only visible, reachable, authenticated,
structural). The point of P8b, P10 and P12 is to find out whether the model
needs them. A refutation there is a model extension, not a failure.

## 5. Stipulated parameters

| Parameter | Value |
|---|---|
| Runs per case | 20 |
| Datagrams per run (after warm-up) | 50 |
| Application payload (P8, P11, P12) | 200 B UDP payload |
| Warm-up | up to 10 s of probe packets until the first delivery, then discard 5 |
| Mangler/NAT rewrite value (P11) | outer UDP length set to `0x0009` |
| WireGuard MTU | 1420 |
| Packet lengths in P9 | 29, 44, 60, 61, 76, 100, 1000, 1024, 1400 B (inner IPv4) |
| Packet lengths in P10 | 64, 65, 76, 77, 79, 100, 1000, 1008 B (inner IPv4) |

Environment to record for the results file: kernel version, `wg` and wireguard
version, `nft`, `ip` (iproute2), `tc` versions, container or WSL2.

## 6. Predictions

### P8: NAT against real integrity scopes (research, core)

Maps to: P3 cases (a) and (b), now with real implementations. Flow: one-way UDP
cA to cB through `N`. Each case has a no-NAT control (same stack, cN forwards
without masquerade).

| Case | Stack | What N rewrites | Predicted delivery | Cause gate | Confidence |
|---|---|---|---|---|---|
| a | AH tunnel | outer source address (inside AH integrity scope, RFC 4302 §3.3.3.1.1) | 0 % | `/proc/net/xfrm_stat` shows an increase in an `XfrmIn*Error` counter | high |
| b | ESP tunnel | outer source address (outside ESP scope, RFC 4303) | 100 % | none | medium |
| c | W | outer source address and UDP source port | 100 % | none; additionally `wg show wg0 endpoints` on cB must list the NAT address and translated port after the first authenticated packet | high |

Controls (no NAT) must deliver 100 % in all three cases.

Tolerance: zero. In every one of the 20 runs, the 50 post-warm-up datagrams must
all arrive (100 %) or none must arrive (0 %).

Refuted if any case delivers outside its predicted extreme with a valid mutation
gate. Case b is the lookup-key probe: Linux resolves an inbound ESP SA by
destination, SPI and protocol, and the policy template is compared with the
state's own addresses, not the packet's. If a lookup keyed on the outer source
rejects the packet, the model's rule "visible and unauthenticated means
survives" needs a lookup-key class.

### P9: Real wire overhead versus the stipulated overhead (calibration)

Purpose: convert a stipulated number into a measured one. The repo stipulates
E = 28 B and T = 28 B, a 56 B composite with no padding.

Prediction (WireGuard, IPv4 underlay): the IP total length of the outer packet
for an inner IPv4 packet of length L is exactly

```text
wire(L) = 60 + R(L),   R(x) = 16 * ceil(x / 16)       (valid while R(L) <= 1420)
```

(20 IPv4 + 8 UDP + 16 WireGuard header + padded plaintext + 16 tag, with the
plaintext padded to a multiple of 16 up to the interface MTU, per the WireGuard
whitepaper.)

| L | 29 | 44 | 60 | 61 | 76 | 100 | 1000 | 1024 | 1400 |
|---|---|---|---|---|---|---|---|---|---|
| R(L) | 32 | 48 | 64 | 64 | 80 | 112 | 1008 | 1024 | 1408 |
| predicted wire(L) | 92 | 108 | 124 | 124 | 140 | 172 | 1068 | 1084 | 1468 |
| measured minus stipulated (wire - L - 56) | 7 | 8 | 8 | 7 | 8 | 16 | 12 | 4 | 12 |

An inner packet of length L is produced by sending a UDP payload of `L - 28`
bytes from the cA application.

Tolerance: zero. Confidence: high for the 60 B base, medium-high for the padding
rule at the listed lengths.

Refuted if any `wire(L)` differs from the formula. A confirmed result also
refutes the stipulated 56 B composite as an exact model: it is off by 4 to 19 B
depending on `L mod 16`. That is reported as a calibration finding, not as a
failure of P9.

### P10: Fixed-overhead layers do not commute when one layer quantises size (research)

Extends: P4 (all six orderings of `T`, `E`, `S` commute exactly). P4 assumed
every layer adds a fixed overhead. WireGuard pads to 16 B, so that assumption
fails for it.

Stacks: `Y -> W` (inner packet enters IPIP, then WireGuard; WireGuard is
outermost) versus `W -> Y` (inner packet enters WireGuard, then IPIP is
outermost). `Y` adds a fixed 20 B.

Prediction: for inner IPv4 packet length L

```text
wire(Y -> W) = 60 + R(L + 20)
wire(W -> Y) = 80 + R(L)
d(L) = wire(Y -> W) - wire(W -> Y) = R(L + 20) - R(L) - 20
     = -4   if 1 <= (L mod 16) <= 12
     = +12  if (L mod 16) in {0, 13, 14, 15}
```

| L | 64 | 65 | 76 | 77 | 79 | 100 | 1000 | 1008 |
|---|---|---|---|---|---|---|---|---|
| L mod 16 | 0 | 1 | 12 | 13 | 15 | 4 | 8 | 0 |
| wire(Y -> W) | 156 | 156 | 156 | 172 | 172 | 188 | 1084 | 1100 |
| wire(W -> Y) | 144 | 160 | 160 | 160 | 160 | 192 | 1088 | 1088 |
| predicted d(L) | +12 | -4 | -4 | +12 | +12 | -4 | -4 | +12 |

Two verdicts are reported:

- **P10a (naive P4 on a real stack):** the exact-commutation prediction
  `d(L) = 0` is predicted false for every listed L.
- **P10b (quantised model):** the formula above is predicted exact for every
  listed L, zero tolerance.

Delivery must be 100 % in both orderings (no fragmentation; all outer packets
are at most 1500 B).

Confidence: medium-high for the arithmetic; medium for building the nested
topologies (see §7). Refuted if any measured `d(L)` differs from the formula
(P10b), or if any `d(L)` is zero (P10a would be confirmed instead).

### P11: Structural rewrite of the outer UDP length on a real kernel (research)

Extends: P7 (rewriting a length field breaks delivery even though no integrity
scope covers it). Setup: tunnel `W` is established first (probe packets), then a
`tc pedit` filter is installed on `vN2` egress, so handshake packets are never
mangled. Test runs finish well inside the first rekey interval.

| Case | M action on data packets | Predicted delivery | Cause gate | Confidence |
|---|---|---|---|---|
| a | outer UDP length set to 9, UDP checksum untouched | 0 % | `nstat` shows an increase in `UdpInCsumErrors` or the cB WireGuard receive counter does not advance | high |
| b | outer UDP length set to 9, UDP checksum recomputed (`csum` action) | 0 % | cB WireGuard receive counter does not advance | high |
| c | outer IP ToS rewritten, IP header checksum recomputed (inert field) | 100 % | none | medium |

Case b exercises the length field itself: a nine-byte UDP datagram carries a
one-byte payload, far below the 32-byte minimum WireGuard message.

Tolerance: zero. Refuted if a structural rewrite delivers any datagram with a
valid mutation gate, or the inert rewrite (c) fails to deliver all 50.

### P12: Derived fields across layers: the inner checksum depends on the outer address (research)

Extends: P7, with a derived field, which the model does not yet have.
Background: RFC 3715 §2.2 describes the problem. In ESP transport mode the inner
TCP or UDP checksum covers a pseudo-header that includes the IP source and
destination. A NAT that rewrites the outer address cannot fix the encrypted
inner checksum.

Stack: ESP transport mode carrying UDP. The inbound policy selector must not
constrain the source address (wildcard source); otherwise the case measures the
selector, not the checksum.

| Case | Inner UDP checksum | N rewrites outer source | Predicted delivery | Cause gate | Confidence |
|---|---|---|---|---|---|
| a | computed (default) | yes | 0 % | `nstat UdpInCsumErrors` increases by at least the number of sent datagrams | medium |
| b | zero (`SO_NO_CHECK`, IPv4) | yes | 100 % | none | medium |
| c | computed | no (control) | 100 % | none | high |

Tolerance: zero. Refuted if case a delivers any datagram, case b loses any, or
the cause gate in (a) names a different drop reason.

A pass shows that a field in one layer can be invalidated by a rewrite in
another layer without any integrity tag, so the model needs a dependency edge
(`derived`), not only a field table. A fail in case a with the cause gate
pointing elsewhere (for example an xfrm policy mismatch) means the setup, not
the rule, decided the outcome; report it as INCONCLUSIVE and fix the selector in
an addendum without changing the prediction.

## 7. Implementation notes (not predictions)

- **P10 topologies.** `Y -> W`: route inner traffic into `ipip0` whose outer
  endpoints are the WireGuard overlay addresses (`10.99.0.1`, `10.99.0.2`);
  those outer packets are routed into `wg0` with `AllowedIPs` covering the peer
  overlay address. `W -> Y`: inner traffic is routed into `wg0`; the WireGuard
  endpoint address is reachable only through an `ipip1` tunnel built on the
  underlay addresses. Keep the underlay and overlay prefixes disjoint to avoid
  routing loops.
- **NAT in the router namespace:** `nft add rule ip nat postrouting oifname vN2
  masquerade`. NAT of protocols 50 and 51 translates the address only, which is
  the intended behaviour for P8a and P8b.
- **Mangler:** `tc qdisc add dev vN2 root handle 1: prio` plus a `u32` or
  `flower` filter selecting UDP to the tunnel port, with `pedit munge` and a
  `csum` action where the case calls for a recomputed checksum.
- **Counters:** `nstat -az UdpInCsumErrors` in the receiving namespace;
  `cat /proc/net/xfrm_stat`; `wg show wg0 transfer`; `wg show wg0 endpoints`.
- **Kernel modules to check first:** `wireguard`, `ipip`, `esp4`, `ah4`,
  `xfrm_user`, `act_pedit`, `act_csum`, `nft_masq`. A WSL2 kernel may lack some;
  the result is then NOT RUN for the affected case.
- Repeat the P1-P7 hygiene: pair runs where meaningful, store raw observations as
  CSV in the existing `validation_io` format, never overwrite a refutation
  narrative in a hand-maintained results file.

## 8. Interpretation limits (fixed in advance)

- One kernel, one NAT implementation, veth links, no wireless, no congestion, no
  cross traffic. Honda et al.'s measurements of real-world middleboxes are
  context, not something this file reproduces.
- AH is deprecated; it is used because it is the clearest real case of an
  integrity scope covering the outer address.
- Security properties are not evaluated.
- P9 and P10 test Linux WireGuard padding. Other stacks may pad differently (or
  not at all); the result then calibrates one layer, not all.
- Passing P8 to P12 would show that the survival rule and its two extensions
  hold against independent implementations for these cases. It would not show
  that the rule holds for arbitrary protocols or middleboxes.
- Failing any of them is a result: it names a field class the model lacks.

## 9. How outcomes feed back into the model

| Outcome | Model consequence |
|---|---|
| P8a, P8c, P11 confirmed | survival rule holds against independent implementations |
| P8b refuted | add a lookup-key field class |
| P9 confirmed | replace the stipulated 56 B composite by `60 + R(L)` and mark `W` as quantised |
| P10b confirmed | amend P4: commutation requires fixed (non-quantised) size effects |
| P12a confirmed | add derived dependency edges between layers |
| any INCONCLUSIVE or NOT RUN | report as such; do not infer a verdict |

## 10. Addenda

(none yet)
