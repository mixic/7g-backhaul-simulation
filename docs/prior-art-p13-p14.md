# Prior art for P13 (ECN decapsulation) and P14 (NAT / ESP conntrack)

**Status:** complete, 14 November 2026. **Scope:** what was already documented
before Paper A's round 2, and the wording Paper A may therefore use. This note
does not report new experiments; it is a search log and a source audit.

**Why it matters.** P13 and P14 are the two round-2 results most likely to be
mistaken for discoveries. The rules they exercise are older than the harness.
The honest claim is an executable, per-implementation check, not a new field
class or a new NAT behaviour.

## Search log

| Date | Query / source route | Purpose |
|---|---|---|
| 2026-11-14 | `RFC 6040 ECN tunnelling IPIP drop outer CE inner Not-ECT` | find the decapsulation rule |
| 2026-11-14 | `Linux kernel inet_ecn_decapsulate IPIP source` | find the kernel helper and IPIP call site |
| 2026-11-14 | `WireGuard ECN decapsulation outer CE inner Not-ECT` | find the WireGuard implementation history |
| 2026-11-14 | `RFC 3715 IPsec NAT compatibility ESP no ports` | find the IPsec/NAT requirements |
| 2026-11-14 | `RFC 3948 UDP encapsulation ESP multiple clients NAT` | find the NAT-T specification |
| 2026-11-14 | `Linux nf_conntrack ESP no ports NAT RFC 3948` | find the conntrack/protocol-50 behaviour |

All sources below were fetched on 2026-11-14. Kernel source was checked in the
Linux v6.18 tree through the Bootlin Elixir cross-referencer; the pages were
fetched successfully, but the relevant functions were not line-audited from the
HTML because the pages are large. The experiment's own observations are in
`validation/round2/results/observations.csv`.

## P13: one outer ECN mark, three decapsulators

### What is documented

1. **RFC 6040** defines the decapsulation rule. It says a decapsulator must drop
   an outer CE mark when the inner header is Not-ECT, and must propagate CE when
   the inner header is ECT(0); the rule is stated in §4 and motivated in §5.3.2.
   The relevant sentence is that a decapsulator "must drop a combination of
   Not-ECT inner and CE outer headers" ([RFC 6040](https://datatracker.ietf.org/doc/html/rfc6040)).
2. **Linux** implements the rule in the shared `INET_ECN_decapsulate` helper
   (`include/net/inet_ecn.h`), which returns "drop" for the outer-CE/inner-Not-ECT
   case. IPIP reaches that helper from `ip_tunnel_rcv`
   ([`include/net/inet_ecn.h`](https://elixir.bootlin.com/linux/v6.18/source/include/net/inet_ecn.h),
   [`net/ipv4/ip_tunnel.c`](https://elixir.bootlin.com/linux/v6.18/source/net/ipv4/ip_tunnel.c)).
3. **WireGuard** originally propagated only the CE bit, following the older
   RFC 3168 behaviour. A 2020 patch switched it to the common decapsulation
   helper; the thread then records a decision **not** to drop on outer
   CE/inner Not-ECT, to stay robust to mis-marked traffic
   ([patch thread](https://lore.kernel.org/all/87zhawvuuk.fsf@toke.dk/t/#u)).
   That is consistent with the observed WireGuard result (100 % delivery,
   inner Not-ECT) and with the ESP tunnel result.
4. **RFC 9601** later updates RFC 6040 for tunnel headers separated by a shim;
   it is not needed for P13's two-header case, but it confirms that the ECN
   tunnelling rule is a maintained standard, not an open question.

### What P13 adds, and what it does not

P13 does **not** discover the drop rule. It measures whether three Linux
decapsulators follow it under one identical outer marking: IPIP does
(0 % delivery, 50 frame errors per run); WireGuard and ESP tunnel mode do not
(100 % delivery, inner Not-ECT). The useful artifact is the **per-decapsulator
table under one mangler**, plus the fact that the same visible, unauthenticated
field is fatal on one stack and inert on two. This is a conformance observation
about this kernel and these decapsulators, not a new protocol requirement. It is
also not a claim that WireGuard or ESP are "wrong": the WireGuard thread shows a
deliberate robustness trade-off.

### Wording Paper A may use

> P13 is an executable, per-decapsulator check of RFC 6040. IPIP follows the
> outer-CE/inner-Not-ECT drop rule; WireGuard and ESP tunnel mode deliver the
> same packet with the inner mark unchanged. The result is a conformance
> observation on one kernel, not a new field class or a new rule.

Do **not** write "we discover that outer ECN is handled differently", "first
measurement of ECN decapsulation", or "the RFC leaves this open". RFC 6040 does
not leave it open; the implementations differ.

## P14: two ESP clients behind one NAT

### What is documented

1. **RFC 3715** lists the intrinsic IPsec/NAT incompatibilities. Item (f) says a
   NAT must demultiplex ESP by destination IP, security protocol and SPI, and
   that two hosts behind the same NAT can collide; item (j) notes that many NATs
   cannot handle non-UDP/TCP traffic such as ESP (protocol 50)
   ([RFC 3715](https://datatracker.ietf.org/doc/html/rfc3715)).
2. **RFC 3948** specifies UDP encapsulation of ESP (NAT-T) precisely because ESP
   has no ports; §1 and §5.2 describe the multiple-client conflict, and
   Appendix A lists implementation choices ([RFC 3948](https://datatracker.ietf.org/doc/html/rfc3948)).
3. **strongSwan's NAT Traversal documentation** states it plainly: ESP protocol
   50 "doesn't have any ports, *per se* it is not suited for Port Address
   Translation"; a single client behind a NAT may work with an IPsec-passthrough
   helper, but multiple clients behind the same NAT do not; the solution is
   ESP-in-UDP on port 4500 ([strongSwan](https://docs.strongswan.org/docs/5.9/features/natTraversal.html)).
4. **Linux's generic conntrack** handles protocols without a dedicated tracker
   through `nf_conntrack_proto_generic.c`; there is no port key for protocol 50
   ([`nf_conntrack_proto_generic.c`](https://elixir.bootlin.com/linux/v6.18/source/net/netfilter/nf_conntrack_proto_generic.c)).

### What P14 adds, and what it does not

P14 is an executable reproduction of the documented limitation, not a new
requirement. The **first-come-first-served conntrack entry** and the observation
that the receiver accepts a NAT-T packet whose source port is no longer 4500 are
implementation observations on this kernel and this strongSwan-style receiver
configuration. The RFCs predict the conflict; P14 shows its concrete failure
mode (one ESP conntrack entry, the second client's SPI never on the wire,
swapping the send order swaps the loser). The ESP-in-UDP control shows the
documented workaround, not a new one.

### Wording Paper A may use

> P14 is an executable check of the documented ESP/NAT limitation (RFC 3715,
> RFC 3948). Plain ESP has no port key; with two clients behind one masquerade,
> the second client's packets never reach the wire. ESP-in-UDP restores
> multiplexing. The first-come-first-served conntrack entry and the receiver's
> acceptance of a translated source port are implementation observations on this
> kernel, not new protocol requirements.

Do **not** write "we discover that ESP does not traverse NAT", "first
demonstration of NAT-T", or "NAT-T is broken". NAT-T is the documented
workaround; P14 confirms it and records one receiver behaviour.

## Verification table

| Source | URL | Fetched | What was verified |
|---|---|---|---|
| RFC 6040 | https://datatracker.ietf.org/doc/html/rfc6040 | 200 | drop rule for outer CE/inner Not-ECT; CE propagation for ECT inner |
| Linux `inet_ecn.h` | https://elixir.bootlin.com/linux/v6.18/source/include/net/inet_ecn.h | 200 | helper exists in v6.18 |
| Linux `ip_tunnel.c` | https://elixir.bootlin.com/linux/v6.18/source/net/ipv4/ip_tunnel.c | 200 | IPIP receive path exists in v6.18 |
| WireGuard ECN patch | https://lore.kernel.org/all/87zhawvuuk.fsf@toke.dk/t/#u | 200 | old CE-only behaviour; switch to helper; decision not to drop |
| RFC 3715 | https://datatracker.ietf.org/doc/html/rfc3715 | 200 | ESP/NAT incompatibilities, items (f) and (j) |
| RFC 3948 | https://datatracker.ietf.org/doc/html/rfc3948 | 200 | ESP-in-UDP; multiple-client conflict in §5.2 |
| strongSwan NAT-T | https://docs.strongswan.org/docs/5.9/features/natTraversal.html | 200 | ESP has no ports; multiple clients behind one NAT; port 4500 workaround |
| Linux generic conntrack | https://elixir.bootlin.com/linux/v6.18/source/net/netfilter/nf_conntrack_proto_generic.c | 200 | protocol-50 path exists in v6.18 |

## Caveats

- **Kernel pages were not line-audited.** The URLs and files are verified; the
  exact call graph in Linux v6.18 was not read line by line. Paper A should cite
  the files, not claim a source-level proof.
- **One kernel and one receiver configuration.** P13 and P14 are one-kernel
  observations. The RFCs are the general rule; the implementation details can
  move.
- **WireGuard's decision not to drop** is a thread-level record, not a
  specification. The observed behaviour is what matters for P13.
- **RFC 9601** was located through the RFC 6040 page but not read in full; it is
  mentioned only to show the rule is maintained, not as a P13 source.
