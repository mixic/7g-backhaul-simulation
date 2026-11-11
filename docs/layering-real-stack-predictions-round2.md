# Layering predictions, round 2 (P13-P16): predictions that can fail

**Status:** DRAFT. Commit this file **before any harness change**, record the
commit hash, and never edit it afterwards; corrections go in a dated addendum.

**Why a second round.** Round 1 (`layering-real-stack-predictions.md`, P8-P12)
ended 15/15 confirmed. Those predictions were derived from specifications that
the author and the reviewer both knew, so the result shows the harness and the
understanding are sound; it does not show that the model can find anything.
Round 2 asks questions where the answer depends on **implementation behaviour
that the specifications leave open**, so a refutation is a realistic outcome
and teaches something about the model whichever way it goes.

**Provenance and honesty.** Every prediction was written without running
anything. The "assumed code path" column in section 2 is recalled from memory
of mainline Linux source and is **unverified**; if a recollection is wrong, the
prediction is wrong, and that is a legitimate result. Each sub-prediction
carries a **credence** (my probability that it holds) so calibration can be
scored afterwards (section 9).

**Relationship to earlier files.** Same observable set, dispositions
(CONFIRMED, REFUTED, INCONCLUSIVE, INVALID, NOT RUN), mutation-gate and
cause-gate philosophy, topology, and harness as `layering-real-stack-predictions.md`.
Security properties are out of scope.

## 1. Replication clause (new)

Run the whole file on **at least two kernels** (for example the WSL2 kernel and a
native distribution kernel) and record both in `environment.txt`. P13 and P14
depend on kernel versions. **Disagreement between kernels is reported as a
finding for that prediction, not averaged away, and not a failure of the
harness.** Predictions are made for mainline kernels 6.1 and later.

## 2. Assumed implementation behaviour (unverified, from memory)

| # | Assumption | Used by | Credence |
|---|---|---|---:|
| A1 | `ip_tunnel_rcv` (ipip) calls `IP_ECN_decapsulate` and **drops** when it returns 2 (outer CE, inner Not-ECT), counting `rx_frame_errors` | P13a-c | 90 % |
| A2 | WireGuard calls `INET_ECN_decapsulate` on receive but **ignores its return value** (propagates CE into an ECT inner, never drops) | P13d-e | 70 % |
| A3 | xfrm tunnel-mode input only **propagates** CE (`ipip_ecn_decapsulate`), with no RFC 6040 drop rule | P13f-g | 60 % |
| A4 | Netfilter has **no ESP tracker** in mainline; ESP is tracked as a generic protocol keyed on addresses only, so two inside hosts sending ESP to one server cannot get distinct translated tuples | P14 | 60 % |
| A5 | UDP ports disambiguate NAT-T (ESP-in-UDP) flows, so masquerade handles two clients | P14c | 90 % |
| A6 | WireGuard sends outer IPv4 packets **without DF** and caps padding at the interface MTU: `padded = min(mtu, 16*ceil(len/16))` | P15 | 80 % |
| A7 | xfrm legacy replay check rejects a packet iff `max_seq - seq >= replay_window` and counts it as `XfrmInStateSeqError` | P16 | 85 % |
| A8 | WireGuard's receive replay window is thousands of packets (8128 in the mainline constant), far above any depth used here | P16c | 90 % |

## 3. Gates (additions to round 1)

A gate failure makes a case INVALID (mutation, depth, fragment, SPI gates) or
INCONCLUSIVE (cause gates); never a refutation.

| Gate | Needed by | Rule |
|---|---|---|
| ECN mutation gate | P13 | every test packet at `vN2` egress carries the target outer ECN codepoint and DSCP 0; at `vA1` egress none carries CE |
| SPI gate | P14 | the ESP SPI of each client is read from the capture; a client's "dropped" verdict needs its SPI to be absent at `vN2` egress |
| Fragment gate | P15 | each datagram yields exactly 2 captured outer packets at `vA1` egress; in E->F ordering exactly one has the more-fragments flag |
| Depth gate | P16 | observed reordering depth at `vN2` egress (ESP sequence number or WireGuard counter, in capture order) is at least 64 for the high-depth cases and at most 16 for the low-depth case |
| Warm-up gate | all | tunnel established and carrying traffic before any impairment is installed |

Capture additions needed in the harness (implementation, not predictions): IPv4
flags/fragment offset, ESP SPI and sequence number, WireGuard counter (little-endian,
bytes 8-15 of the UDP payload), and `IP_RECVTOS` in the receiver.

## 4. Stipulated parameters

| Parameter | Value |
|---|---|
| Runs per case | 20, fresh namespaces and keys per run |
| Delivery cases (P13, P14) | 50 datagrams per run, 228 inner bytes, 10 ms apart |
| P14 | second client namespace `rsA2` (10.200.3.2/24 via `vN3`), inner prefixes 10.201.0.0/30 and 10.202.0.0/30, distinct SPIs |
| P15 payload | 2000 B UDP payload (inner IPv4 length 2028), 500 datagrams per run, 50 ms apart |
| P15 loss | netem `loss 5%` on `vN2` egress, installed after warm-up, for the delivery part only |
| P16 traffic | 2000 datagrams of 228 inner bytes per run at the fastest rate the sender sustains |
| P16 impairment | `tc qdisc add dev vN2 root netem delay D reorder 25%`, with `D = 100ms` (high depth) and `D = 4ms` (low depth) |
| Underlay MTU | 1500; WireGuard MTU 1420 unless a case says otherwise |

---

## 5. P13: outer ECN is a visible, unauthenticated field that some decapsulators act on (research)

**Question.** RFC 6040 combines the outer ECN codepoint with the inner one at
decapsulation. A middlebox that marks Congestion Experienced (CE) on the *outer*
header is doing something every router may legitimately do. Does the tunnel
survive? Round 1 treated the outer ToS as inert (P11c, DSCP only). This is the
case where an outer field the model calls "visible and unauthenticated" can
still affect delivery through the decapsulation rule.

**Setup.** One-way UDP `cA` to `cB`. The mangler on `vN2` egress sets the outer
ToS byte: `0x03` (CE) or `0x02` (ECT(0)) with the IPv4 header checksum recomputed.
The inner ToS is set by the sender: `0x00` (Not-ECT) or `0x02` (ECT(0)). The
receiver reads the inner ToS via `IP_RECVTOS`. Controls: same stack, no mangler.

| Case | Stack | Inner ECN | Outer ECN set to | Predicted delivery | Inner ECN at receiver | Cause gate | Credence |
|---|---|---|---|---:|---|---|---:|
| a | IPIP | Not-ECT | CE | **0 %** | n/a | `ipip0` `rx_frame_errors` delta equals datagrams sent | 90 % |
| b | IPIP | Not-ECT | ECT(0) | **100 %** | Not-ECT | none | 90 % |
| c | IPIP | ECT(0) | CE | **100 %** | CE | none | 90 % |
| d | WireGuard | Not-ECT | CE | **100 %** | Not-ECT | none | 70 % |
| e | WireGuard | ECT(0) | CE | **100 %** | CE | none | 70 % |
| f | ESP tunnel | Not-ECT | CE | **100 %** | Not-ECT | none | 60 % |
| g | ESP tunnel | ECT(0) | CE | **100 %** | CE | none | 60 % |
| h | each stack | both | none (control) | **100 %** | unchanged | none | 95 % |

**Tolerance:** zero; delivery is exactly 0 % or 100 % in every one of the 20
runs, and the inner ECN column must match in every delivered datagram.

**Refuted if** any cell differs. Each of cases d to g is a separate bet on an
implementation detail, so a mixed outcome is expected to be informative: it
maps which stacks implement the RFC 6040 drop rule.

**If it holds / fails.** If a is confirmed and d, f are confirmed too, three
stacks disagree on the **same** visible, unauthenticated field. The survival rule
then needs a per-implementation **decapsulation-coupled** field class (a field
whose outer value is combined with an inner value on the way out) and cannot be
stated as a property of the field alone. If d or f also drops, the class is
common; if nothing but IPIP drops, it is implementation-specific.

## 6. P14: a middlebox's own state key decides whether a protocol can share a NAT (research)

**Question.** Round 1 tested the *receiver's* lookup key (P8b: ESP survives
NAT). This tests the *middlebox's* key. ESP has no ports. Two inside hosts that
each run an ESP tunnel to the same server share one translated address, so
netfilter has nothing to tell their flows apart unless it reads the SPI.

**Setup.** Two client namespaces behind the same masquerade, each with its own
ESP tunnel-mode SA to `cB` (distinct SPI, key, inner prefix). Phase 1: client 1
sends 10 datagrams alone. Phase 2: both send 50 interleaved.

| Case | Setup | Predicted | Credence |
|---|---|---|---:|
| a | ESP tunnel, NAT, client 1 first | client 1: **100 %**, client 2: **0 %**; client 2's SPI never appears at `vN2` egress | 60 % |
| b | same, client 2 first | roles reverse: client 2 **100 %**, client 1 **0 %** | 60 % |
| c | ESP-in-UDP (`encap espinudp 4500 4500`), NAT | both **100 %** | 90 % |
| d | ESP tunnel, **no** NAT (control) | both **100 %** | 95 % |

b is the prediction that distinguishes "first come, first served" from a fixed
property of one client. Tolerance zero.

**Refuted if** in a both clients deliver 100 % (the kernel disambiguates by SPI
or by another key; assumption A4 is false). If client 1 delivers less than
100 %, or client 2 delivers a nonzero fraction below 100 %, the case is
INCONCLUSIVE and the cause is investigated with `conntrack -S` and
`/proc/net/stat/nf_conntrack` before any verdict.

**If it holds / fails.** If a and b hold, a protocol with no field a middlebox can
use as a flow key is a **lookup-key failure at the middlebox**, a class the
model currently only has at the receiver. If a fails, the same experiment shows
that the model must say which fields a given NAT *can* read as keys.

## 7. P15: placement of fragmentation relative to encryption on a real stack (research)

**Question.** The codec and SimPy agreed with the model on `E->F` versus `F->E`
(P2). Here the fragmenter is the kernel's IP layer, and the encryptor is
WireGuard with its own padding rule, so the two orderings can differ in a way the
fixed-overhead model could not predict.

**Setup.** One WireGuard tunnel, one inner UDP datagram of 2000 B payload
(inner IPv4 length 2028), underlay MTU 1500.

- **E->F** (encrypt, then fragment): `wg0` MTU 2100 (inner not fragmented); the
  outer WireGuard packet exceeds the underlay MTU and is fragmented by IP.
- **F->E** (fragment, then encrypt): `wg0` MTU 1420; the sender fragments the
  inner datagram first, and each fragment is encrypted separately.

**Predicted wire bytes per datagram (IP total lengths at `vA1` egress):**

| Ordering | Outer packets | Calculation | Total |
|---|---|---|---:|
| E->F | 2 fragments | WG packet `20+8+16+R(2028)+16 = 2092`; fragments of 1480 + 592 data bytes give 1500 + 612 | **2112 B** |
| F->E | 2 packets | inner fragments 1420 and 628 B; `60+min(1420,R(1420))=1480` and `60+R(628)=700` | **2180 B** |

(`R(x) = 16*ceil(x/16)`; padding is capped at the interface MTU, assumption A6.)
The orderings differ by exactly **68 B**, with F->E larger. Tolerance zero.
**Credence 80 %.**

**Predicted delivery under iid loss `p = 5 %` per outer packet:** both orderings
deliver a datagram iff both outer packets arrive, so both are `(1-p)^2 = 0.9025`.
Over 20 runs x 500 datagrams each ordering's pooled delivery lies within
**+/- 1.5 percentage points** of 0.9025, and the two differ by no more than
1.5 points. **Credence 75 %.**

**Refuted if** any measured byte total differs, or if the 68 B difference does
not appear (which would mean WireGuard sets DF, or pads differently, or that the
kernel fragments differently from assumed).

**If it holds / fails.** A hold shows that the byte-accounting and delivery
equivalence from P2 survives a real fragmenter and a quantising encryptor, with
the quantisation producing a calculable extra cost. A failure shows which
assumption about how a real stack places fragmentation was wrong.

## 8. P16: reordering tolerance is set by the integrity layer's replay window (research)

**Question.** The project's central use case is multipath striping, which
reorders packets between encryption and decryption. The model has a sequencing
layer `S` but no concept of the replay window of `E`. If `E` drops anything that
arrives more than a window late, then *delivery under reordering is a property of
`E`'s window*, independent of where `S` sits.

**Setup.** One-way traffic through the tunnel; netem on `vN2` egress sends 25 %
of packets immediately and delays the rest by `D`, producing reordering depth of
about the sending rate times `D`. ESP tunnel mode with `replay-window 32`.

**Reference model (zero tolerance).** From the capture at `vN2` egress, in
wire order, take each packet's sequence number (ESP sequence, or WireGuard
counter). A reference replay filter accepts a packet iff
`max_seq_seen - seq < window` (or it is a new maximum) and it is not a repeat.
The prediction is that the **number of datagrams delivered equals the number the
reference filter accepts**, exactly.

| Case | Stack | Window | Impairment | Predicted | Cause gate | Credence |
|---|---|---|---|---|---|---:|
| a | ESP tunnel | 32 | `D = 100 ms` (depth gate >= 64) | delivered = reference count (expected well under half of the datagrams) | `XfrmInStateSeqError` delta = sent - delivered | 85 % |
| b | ESP tunnel | 32 | `D = 4 ms` (depth gate <= 16) | **100 %** delivered | `XfrmInStateSeqError` delta = 0 | 90 % |
| c | WireGuard | default | `D = 100 ms` | **100 %** delivered | none | 90 % |
| d | ESP tunnel | 256 | `D = 100 ms` (optional; NOT RUN if iproute2/kernel rejects it) | **100 %** delivered | none | 70 % |

Case d, with the same reordering as a, shows the window size is the
discriminator. The depth gate, not the nominal delay, defines the case: if the
sender cannot reach the needed rate, the case is INVALID, not refuted.

**Refuted if** delivered differs from the reference count in a, or if b, c or d
lose any datagram with a valid depth gate.

**If it holds / fails.** A hold means a multipath design that stripes across
paths whose delay difference times rate exceeds the replay window loses valid
packets with no loss on the wire, so the model needs an integrity-window
parameter on `E` and a reordering-depth parameter on the path. A failure in a
means the kernel's window semantics differ from assumption A7 and the reference
filter is the thing to fix.

---

## 9. Credence table (for scoring calibration)

| Prediction | Credence |
|---|---:|
| P13a, P13b, P13c | 90 % each |
| P13d, P13e | 70 % each |
| P13f, P13g | 60 % each |
| P13h (controls) | 95 % |
| P14a, P14b | 60 % each |
| P14c | 90 % |
| P14d | 95 % |
| P15 wire bytes (2112, 2180, 68 B difference) | 80 % |
| P15 delivery equivalence | 75 % |
| P16a | 85 % |
| P16b, P16c | 90 % each |
| P16d | 70 % |

After the run, record each as 1 (confirmed) or 0 (refuted) and report the Brier
score. Treat INCONCLUSIVE, INVALID and NOT RUN as unscored. A well-calibrated
set at these credences should have several refutations; zero refutations would
suggest the credences were too low or the predictions too safe.

## 10. Interpretation limits (fixed in advance)

- One or two kernels, veth links, Linux netfilter as the only NAT. Results about
  other middleboxes (pf, hardware CGNAT, consumer routers) are not implied.
- netem produces reordering by delaying, not by multipath, so depth is a proxy;
  the depth gate keeps the case honest.
- ECN behaviour reflects the kernel versions recorded, not the RFC.
- Security is not evaluated; ECN and replay behaviour are measured as framing
  and survival effects.

## 11. How outcomes feed back into the model

| Outcome | Model consequence |
|---|---|
| P13a confirmed with d or f confirmed | add a **decapsulation-coupled** field class and a per-implementation rule table |
| P13 only IPIP drops | the class exists but is implementation-specific; record which stacks follow RFC 6040 |
| P13 all deliver | the outer ECN field is inert; keep it out of the rule |
| P14a and P14b confirmed | extend `lookup-key` to **middlebox** state keys; add the rule "a protocol without a middlebox-readable flow key cannot share a NAT" |
| P14a refuted | record which key the kernel uses for ESP and amend A4 |
| P15 confirmed | P2 equivalence holds on a real fragmenter; extend P9's padding rule to the F->E accounting |
| P15 refuted | find which of A6's two parts (DF, padding cap) failed; amend the stack model |
| P16a confirmed | add replay-window and reordering-depth parameters; delivery under multipath is `E`-window-limited |
| any INCONCLUSIVE, INVALID or NOT RUN | report as such; infer nothing |

## 12. Addenda

(none yet)
