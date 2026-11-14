# Layering real-stack results, round 2 (P13-P16)

**Predictions frozen at commit:** `1b7e6ac964f6d27dd018da77a5fbf55576f7bb3e`
(`docs/layering-real-stack-predictions-round2.md`, committed before any round-2
harness code existed; never edited afterwards — the only record of a change is the
addendum at the end of this file).
**Harness:** `validation/round2/` (Python; four netns, AF_PACKET capture, ECN
mangler, ESP-in-UDP, fragment/SPI/sequence capture, depth gates, verdict CSV).
**Protocol: the frozen 20 runs per case** — 20 cases, **400 runs**, 5 800
observation rows.
**Raw output:** `validation/round2/results/observations.csv`, `verdicts.csv`,
`calibration.md`, `environment.txt`, `errors.txt` (empty).
**Verdict summary:** **17 of 18 scored predictions CONFIRMED, 1 REFUTED
(`P16d`)**; **Brier score 0.0833** over 18 scored predictions. No case is
INCONCLUSIVE, INVALID or NOT RUN. Every gate (warm-up, offload, ECN mutation,
SPI, fragment, depth) passed in all 400 runs.

## Status (20 runs per case)

| Prediction | Status | Evidence |
|---|---|---|
| P13a (IPIP, inner Not-ECT, outer CE) | **CONFIRMED** | 0 % delivery in 20/20; `ipip0` `rx_frame_errors` delta = 50 = datagrams sent in every run |
| P13b (IPIP, Not-ECT, outer ECT(0)) | **CONFIRMED** | 100 %, inner Not-ECT at the receiver |
| P13c (IPIP, ECT(0), outer CE) | **CONFIRMED** | 100 %, inner **CE** at the receiver |
| P13d (WireGuard, Not-ECT, CE) | **CONFIRMED** | 100 %, inner Not-ECT |
| P13e (WireGuard, ECT(0), CE) | **CONFIRMED** | 100 %, inner CE |
| P13f (ESP tunnel, Not-ECT, CE) | **CONFIRMED** | 100 %, inner Not-ECT |
| P13g (ESP tunnel, ECT(0), CE) | **CONFIRMED** | 100 %, inner CE |
| P13h (three controls, no mangler) | **CONFIRMED** | 100 % per stack, 25 Not-ECT + 25 ECT(0) delivered unchanged |
| P14a (ESP + NAT, client 1 first) | **CONFIRMED** | client 1 60/60, client 2 0/50, client 2 SPI never on the wire, one ESP conntrack entry |
| P14b (ESP + NAT, client 2 first) | **CONFIRMED** | roles exactly reversed |
| P14c (ESP-in-UDP + NAT) | **CONFIRMED** | both 100 %; client 2's translated source port differs from 4500 |
| P14d (ESP, no NAT) | **CONFIRMED** | both 100 % |
| P15 wire bytes | **CONFIRMED** | 2112 B (E→F) and 2180 B (F→E) per datagram in 20/20; difference exactly 68 B |
| P15 delivery equivalence | **CONFIRMED** | pooled 0.9003 / 0.9041 (predicted 0.9025 ± 0.015; difference 0.38 pp) |
| P16a (ESP, window 32, 100 ms) | **CONFIRMED** | delivered = reference count exactly in 20/20; `XfrmInStateSeqError` delta = sent − delivered |
| P16b (ESP, window 32, 4 ms) | **CONFIRMED** | 2000/2000 in 20/20; sequence-error delta 0 |
| P16c (WireGuard, 100 ms) | **CONFIRMED** | 2000/2000 in 20/20 at reordering depth ≈ 1995 |
| P16d (ESP, window 256, 100 ms) | **REFUTED** | 673–717 of 2000 delivered: the burst is ~2000 deep and a 256-packet window cannot span it |

## P13 — three decapsulators, one visible field, three answers

The mangler rewrites the **outer** ToS byte on `vN2` egress to CE (`0x03`) and
recomputes the IPv4 header checksum. The inner codepoint is set by the sender.
The mutation gate checks both ends of that statement in every run (all 50 test
packets carry the target outer codepoint with DSCP 0; none is CE at `vA1`
egress), so the table below is about decapsulation, not about mangling.

| Case | Stack | Inner | Outer | Delivery | Inner ToS at receiver |
|---|---|---|---|---|---|
| P13a | IPIP | Not-ECT | CE | **0 %** | — (nothing delivered) |
| P13b | IPIP | Not-ECT | ECT(0) | **100 %** | Not-ECT |
| P13c | IPIP | ECT(0) | CE | **100 %** | **CE** |
| P13d | WireGuard | Not-ECT | CE | **100 %** | Not-ECT |
| P13e | WireGuard | ECT(0) | CE | **100 %** | **CE** |
| P13f | ESP tunnel | Not-ECT | CE | **100 %** | Not-ECT |
| P13g | ESP tunnel | ECT(0) | CE | **100 %** | **CE** |

The IPIP case is the only stack that implements the RFC 6040 *drop* rule, and the
drop is booked exactly where assumption **A1** said: `ipip0`
`rx_frame_errors` rises by **50** per run and `rx_errors` by 50, while
`rx_dropped` stays 0 — a frame error, not a queue drop. With an ECT(0) inner,
IPIP instead propagates CE (P13c), so the stack implements both halves of the
rule. WireGuard and xfrm tunnel mode propagate CE into an ECN-capable inner and
ignore the outer-CE/inner-Not-ECT case (**A2**, **A3**).

**Consequence for the survival rule.** The same outer field, carrying the same
legitimate router marking, is inert on two stacks and fatal on the third. The
field cannot be classified by visibility alone: its effect is
**decapsulation-coupled**, and the rule has to name the decoder. This is the
`decapsulation-coupled` class promised in the frozen file §11, with a
per-implementation table:

| Decapsulator | outer CE + inner Not-ECT | outer CE + inner ECT(0) |
|---|---|---|
| IPIP (`ip_tunnel_rcv`) | **drop** (frame error) | deliver, inner CE |
| WireGuard | deliver, inner Not-ECT | deliver, inner CE |
| xfrm ESP tunnel | deliver, inner Not-ECT | deliver, inner CE |

## P14 — the middlebox's key, and what NAT-T actually buys

Two client namespaces, each with its own ESP tunnel-mode SA (distinct SPI and
key) to one server, behind one masquerade. Phase 1 sends 10 datagrams from one
client alone; phase 2 sends 50 from both, concurrently.

| Case | Client 1 | Client 2 | SPI on the wire (1 / 2) | ESP conntrack entries |
|---|---|---|---|---|
| P14a (client 1 first) | **60/60** | **0/50** | 60 / **0** | 1 |
| P14b (client 2 first) | **0/50** | **60/60** | **0** / 60 | 1 |
| P14c (ESP-in-UDP, NAT) | 60/60 | 50/50 | 60 / 50 | 0 (tracked as UDP) |
| P14d (no NAT) | 60/60 | 50/50 | 61 / 51 | 0 |

The loser's packets never reach `vN2` egress: the second ESP flow gets no
conntrack entry at all (one `unknown … 50` entry, not two), because the generic
tracker has no per-flow key for protocol 50 and the reply tuple of a second
inside host would collide with the first one's. This is a **lookup-key failure
at the middlebox**, and it is genuinely first-come-first-served: swapping which
client sends first swaps which client loses (**A4** confirmed).

NAT-T survives for two independent reasons, and the capture separates them.
First, the UDP ports give the nat table a usable key (**A5**): client 1's
translated source port stays 4500 in all 20 runs while client 2's is remapped to
a random value (1496 … 64424 across runs). Second — and this is an
implementation detail the frozen file did not assume — the receiving SA is
configured `encap espinudp 4500 4500`, yet it happily decapsulates packets whose
source port is no longer 4500. A receiver that enforced the configured source
port would have dropped client 2 even though the NAT did its job.

## P15 — fragment before or after the encryptor

One inner datagram of 2000 B UDP payload (inner IPv4 length 2028), measured at
`vA1` egress.

| Ordering | `wg0` MTU | Outer packets per datagram | Bytes |
|---|---|---|---|
| E→F (encrypt, then fragment) | 2100 | 1500 + 612 | **2112** |
| F→E (fragment, then encrypt) | 1420 | 1480 + 700 | **2180** |

Both totals are exact in **20/20 runs**; the predicted 68 B difference appears
every time, and the fragment gate confirms the shape (E→F: exactly one
more-fragments flag; F→E: two unfragmented packets). This confirms **both**
parts of assumption **A6**: the outer WireGuard packet is sent without DF (or
the 2092-byte packet could not have been fragmented at the underlay), and its
padding is capped at the interface MTU (`R(1420) = 1424 > 1420` is clamped to
1420, while the 628-byte fragment pads to 640).

Delivery under `loss 5%` at `vN2` egress, pooled over 20 × 500 datagrams per
ordering:

| Ordering | delivered / sent | pooled | predicted |
|---|---|---|---|
| E→F | 9003 / 10 000 | **0.9003** | 0.9025 ± 0.015 |
| F→E | 9041 / 10 000 | **0.9041** | 0.9025 ± 0.015 |

Both lie inside the stated band, they differ by 0.38 pp (limit 1.5 pp), and the
per-run spread (87.8–93.0 %) is the expected binomial spread of 500 samples at
`p = 0.9025`. The delivery *equivalence* survives a real fragmenter and a
quantising encryptor even though the wire cost differs by 68 B.

## P16 — the integrity window, not the path, sets the loss

Netem on `vN2` egress delays 75 % of a 2000-datagram burst by `D`; 25 % go
immediately. The reference filter is the frozen one: accept a packet iff it is a
new maximum, or `max_seq_seen − seq < window` and it was not already accepted.

| Case | Stack | Window | `D` | Depth | Delivered | Reference | Seq errors |
|---|---|---|---|---|---|---|---|
| P16a | ESP tunnel | 32 | 100 ms | 1992–1999 | **476–565** | identical | 2000 − delivered |
| P16b | ESP tunnel | 32 | 4 ms | 1 | 2000/2000 | 2000 | 0 |
| P16c | WireGuard | ~8k | 100 ms | 1985–1999 | 2000/2000 | 2000 | — |
| P16d | ESP tunnel | 256 (ESN) | 100 ms | 1991–1999 | **673–717** | identical | 2000 − delivered |

P16a is exact in the strongest sense the file asked for: in **20/20 runs** the
number of datagrams delivered equals the reference filter's count, and the
`XfrmInStateSeqError` delta equals `sent − delivered` to the packet. The
reordering had no loss on the wire — every run captured all 2000 ESP packets —
and about 74 % of them were discarded by the receiver purely for arriving too
late. Widening the window to 256 raises the accepted count (about 694 instead of
about 526) but does not restore delivery, because the depth of this burst is
~2000, not the ~500 the frozen file implicitly assumed: at the fastest rate the
sender sustains, 25 % of 2000 packets jumping ahead of a 100 ms queue puts
nearly the whole burst out of order.

So **P16d's prediction of 100 % is refuted**, but the mechanism it was meant to
demonstrate is confirmed: with the same impairment, the reference filter at
window 256 matches the kernel's `XfrmInStateSeqError` count exactly, run for
run. A 256-packet window is simply not wide enough for a 2000-deep burst. The
refutation is about the assumed rate × delay, not about replay semantics — the
frozen text's own reading ("the depth gate, not the nominal delay, defines the
case") is what the data supports.

Two caveats belong with this table. `replay-window 256` does not create a legacy
256-packet bitmap on this kernel and iproute2: it silently turns the SA into an
**ESN** SA (`anti-replay esn context`, bitmap-length 8), and both ends are
configured identically, so the tunnel still works. And the reference filter uses
the strict form `max − seq < window`; twenty runs at two windows matched
exactly, but no packet landed exactly on the boundary, so the inclusive/exclusive
edge is untested.

## Credence scoring and calibration

| Prediction | Credence | Outcome | Brier |
|---|---:|---:|---:|
| P13a, P13b, P13c | 0.90 | 1 | 0.0100 each |
| P13d, P13e | 0.70 | 1 | 0.0900 each |
| P13f, P13g | 0.60 | 1 | 0.1600 each |
| P13h (control set) | 0.95 | 1 | 0.0025 |
| P14a, P14b | 0.60 | 1 | 0.1600 each |
| P14c | 0.90 | 1 | 0.0100 |
| P14d | 0.95 | 1 | 0.0025 |
| P15 wire bytes | 0.80 | 1 | 0.0400 |
| P15 delivery | 0.75 | 1 | 0.0625 |
| P16a | 0.85 | 1 | 0.0225 |
| P16b, P16c | 0.90 | 1 | 0.0100 each |
| P16d | 0.70 | 0 | 0.4900 |
| **Total** | | **17 / 18** | **0.0833** |

Under the stated credences the expected score was **0.15** and the expected
number of refutations **3.8**. The observed score is 0.0833 and there was **one**
refutation. The gap is not a small-sample artifact: `P16d` alone contributes
0.49 of the 1.50 total, and the other seventeen predictions contribute 1.01
(mean 0.059) against an expected 2.49 (mean 0.147).

Read plainly: **the credences were too cautious**, exactly the failure mode the
frozen file warned about ("zero refutations would suggest the credences were
too low or the predictions too safe"). The hedges were attached to the
implementation-detail cases (0.6–0.7) and every one of those came in. What the
set did *not* anticipate was not an implementation detail at all but a
parameter: how deep a burst a 100 ms netem queue with a 33 kpps sender makes.
That is the one prediction written without a depth estimate, and it is the one
that failed.

## Assumption audit (frozen §2)

| # | Assumption | Verdict |
|---|---|---|
| A1 | `ip_tunnel_rcv` drops on outer CE + inner Not-ECT, counted as `rx_frame_errors` | **held**, to the packet (50/50 per run) |
| A2 | WireGuard ignores the decapsulation verdict, propagates CE, never drops | **held** (no drop in 20/20; CE propagated into ECT(0) inner) |
| A3 | xfrm tunnel-mode input only propagates CE, no RFC 6040 drop rule | **held** |
| A4 | Netfilter tracks ESP as a generic protocol with no per-flow key | **held**, with a direct observation: one ESP conntrack entry, never two |
| A5 | UDP ports disambiguate NAT-T flows | **held**, and the capture shows the second client's port remapped to a random value |
| A6 | WireGuard sends without DF and caps padding at the interface MTU | **held**, both parts, in the exact 2112/2180 totals |
| A7 | Legacy replay drops iff `max − seq ≥ window`, counted as `XfrmInStateSeqError` | **held**, exactly, in 20/20 runs |
| A8 | WireGuard's replay window is far above the depths used here | **held** (2000/2000 at depth ≈ 1995) |

Eight for eight. The one refuted prediction did not depend on a wrong assumption
about the kernel; it depended on a wrong assumption about the *experiment*.

## Environment

| Item | Value |
|---|---|
| Host | WSL2, Ubuntu 26.04.1 LTS |
| Kernel | `6.18.58.1-microsoft-standard-WSL2` (one kernel only — see limits) |
| Root | `wsl -u root` (`id -u` = 0) |
| Python | 3.14.4 |
| `ip` / `tc` | iproute2 6.19.0 |
| `wg` | wireguard-tools 1.0.20250521 |
| `nft` | nftables 1.1.6 |
| `ethtool` | 6.19 |
| Facilities | `ipip`, `wireguard`, `esp4`, `nft_masq`, `act_pedit`, `act_csum`, `sch_netem`, ESP-in-UDP encap, `replay-window` all present |
| Predictions commit | `1b7e6ac964f6d27dd018da77a5fbf55576f7bb3e` |

## Interpretation limits

- **One kernel.** The frozen replication clause asks for at least two kernels; this
  host has one (the WSL2 kernel). P13's per-stack table and P14's conntrack
  behaviour are the two results most likely to move on a distribution kernel or a
  different netfilter version. The clause says disagreement between kernels is a
  finding, not a harness failure; here there is simply no second kernel to
  disagree, so every result is a one-kernel result and is reported as such.
- netem produces reordering by delaying a queue, not by multipath; depth is a
  proxy, and the depth gate is what keeps the case honest (depth was measured on
  every run and gated at ≥ 64 for the high-depth cases and ≤ 16 for P16b).
- ECN behaviour reflects this kernel, not RFC 6040. The table in §P13 is a
  per-implementation observation, not a conformance test.
- Security is not evaluated: ECN and replay behaviour are measured as framing and
  survival effects. SPI values, keys and sequence numbers are read from captures
  only to attribute packets.
- Linux netfilter is the only NAT here; nothing is implied about pf, hardware
  CGNAT or consumer routers.
- The P16 boundary between "inside the window" and "outside it" was never hit
  exactly, so the strict/inclusive reading of `< window` is untested.

## Model consequences (frozen §11)

| Outcome | Model consequence | Status |
|---|---|---|
| P13a confirmed with P13d/P13f confirmed | add a **decapsulation-coupled** field class and a per-implementation rule table | **applies** — table in §P13 |
| P13 only IPIP drops | the class exists but is implementation-specific | **applies** (IPIP only) |
| P14a and P14b confirmed | extend `lookup-key` to **middlebox** state keys; add "a protocol without a middlebox-readable flow key cannot share a NAT" | **applies** |
| P14a refuted | record the key the kernel uses for ESP | not refuted (A4 held) |
| P15 confirmed | P2 equivalence holds on a real fragmenter; extend P9's padding rule to the F→E accounting | **applies** — 2112 / 2180 exact |
| P16a confirmed | add replay-window and reordering-depth parameters; delivery under multipath is `E`-window-limited | **applies** — with the depth estimate P16d got wrong |
| P16d refuted | no frozen consequence; the mechanism was confirmed and the predicted operating point was not | record the depth-vs-window arithmetic |

The substantive model changes this round forces:

1. **A decapsulation-coupled field class.** Outer ECN is unauthenticated and
   visible to every router; whether it kills the flow is decided inside the
   decapsulator, and Linux contains three different answers. A rule stated as a
   property of the field is therefore incomplete.
2. **Middlebox state keys.** The receiver's lookup key was round 1's subject; a
   NAT's own key is a second, independent place where a protocol with no ports
   (ESP) fails. NAT-T is not a workaround for integrity, it is a workaround for
   the *middlebox*: it manufactures the key the NAT needs.
3. **An integrity-window parameter and a depth estimate.** Delivery under
   reordering is `E`-window-limited, and the relevant depth is the sender's rate
   times the path delay difference — an operating point, not a property. A
   design that stripes across paths whose delay difference times rate exceeds the
   window drops valid packets with no loss on the wire.

## Addenda

- **2026-11-11 — round-2 harness implemented, run, and scored.** The frozen
  predictions file was committed first and has not been touched; this whole
  section is the record of harness work. Seven defects were found and fixed
  during harness development, all of them before the committed protocol run:
  1. the AEAD key was generated separately at each end, so every ESP case
     decrypted nothing (`XfrmInStateProtoError`); one key is now generated per
     SA pair;
  2. offload disabling reported failure when the second client's device (`vN3`)
     did not exist in single-client topologies, which would have invalidated the
     P13 controls;
  3. the P15 capture predicate matched UDP to the WireGuard port, which silently
     halves the fragment count because a non-first fragment carries no UDP
     header — the fixed predicate is "UDP to the port **or** a non-first
     fragment";
  4. ESP-in-UDP was delivered as plain UDP until the harness held a socket with
     `UDP_ENCAP_ESPINUDP` on port 4500 in the receiver (without it P14c showed
     0/0 and `UdpInNoPorts` climbed);
  5. the `AF_PACKET` tap buffer dropped 41 of 300 records in an early P16 burst;
     the sniffer now asks for 32 MB and the namespaces get `rmem_max = 64 MB`,
     after which all 2000 packets were captured in every P16 run;
  6. the calibration writer mapped neither `P15a`/`P15b` to their credence rows
     nor collapsed the three controls into one prediction, reporting 16 scored
     predictions and no P15 rows; fixed, and `run.py --recompute` can now rebuild
     verdicts from `observations.csv` without touching the kernel;
  7. `replay-window 256` was accepted but silently became an ESN SA; that is
     recorded as measured rather than worked around.
  Two pacing/stipulation decisions are documented rather than hidden: the
  `D = 4 ms` case is paced at 2 ms per datagram (at the maximum rate the depth
  would be ~80× the permitted 16), and the P15 sender clears DF so that the F→E
  ordering can fragment instead of failing with `EMSGSIZE`.
  Result: 17/18 confirmed, Brier 0.0833. No prediction text was changed.
