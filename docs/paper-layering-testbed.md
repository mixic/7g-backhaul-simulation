# Empirical Commutation Rules for Protocol Layer Encapsulation in Heterogeneous Networks

**Milan Nikolic** · Independent Researcher · <m_nikolic@yahoo.com>

**Status:** focused paper. The real-stack extension (P8–P12) is complete: all
twelve cases are confirmed on one Linux kernel — see
[`layering-real-stack-results.md`](layering-real-stack-results.md). This paper is
Paper A of a two-paper split; Paper B is
[`paper-bio-control-limits.md`](paper-bio-control-limits.md).

## Abstract

Encapsulation layers — compression `C`, encryption/authentication `E`, tunnelling
`T`, fragmentation `F`, sequencing `S` — are usually studied one at a time. This
paper asks a narrower, testable question: **when the order changes, which rewrites
corrupt a datagram and which leave it intact?** It formalises a *survival rule*: a
middlebox can rewrite a field only if that field is **visible** at the wire and
**reachable** within its parse depth; delivery breaks exactly when the rewritten
field is **authenticated** (inside an integrity scope) or **structural** (length-
or offset-bearing). The rule is tested in three independent
implementations: a Python codec, a SimPy model, and a real Linux stack (kernel
WireGuard, IPsec AH/ESP, nftables NAT). The codec and model agree exactly on
P1–P7. Against the real stack, all twelve frozen cases are confirmed:
AH-in-tunnel dies through NAT while ESP and WireGuard survive (P8); WireGuard's
wire overhead is `60 + 16·⌈L/16⌉`, not the stipulated 56 B (P9); nested
IPIP/WireGuard orderings differ by `−4` or `+12` bytes because WireGuard
quantises size (P10); a rewritten outer UDP length is fatal while an inert ToS
rewrite is not (P11); and an inner UDP checksum derived from the outer address
breaks under NAT even without an integrity tag (P12). The contribution is the
**quantised** and **derived** field classes, which a fixed-overhead model lacks.
Everything here is about framing and survival, not cryptographic security; the
evidence is one kernel, veth links and one NAT implementation.

## 1. The question and the rule

A middlebox rewrites a header field. Two separate events follow, and the paper
keeps them apart:

- **The rewrite is applied** iff the field is **visible** at the wire *and*
  **reachable** within the middlebox's parse depth.
- **The receiver accepts the datagram** unless the rewritten field is
  **authenticated** (inside an integrity scope) or **structural** (length- or
  offset-bearing), which a rewrite invalidates.

So a field that is visible and reachable, but neither authenticated nor
structural, is silently rewritten and the datagram survives; a field that is
authenticated or structural breaks delivery when rewritten. The testbed freezes
this rule and then tests it, not the codec.

## 2. What was tested (P1–P7)

The predictions ([`layering-predictions.md`](layering-predictions.md)) cover
visible/mutation/acceptance for NAT and byte-mangling across six orderings of
`T`, `E`, `S`, plus the six-layer permutations with `C` and `F`. The codec
([`simulation/layering/`](../simulation/layering/)) and the SimPy model agree on
every case; the validator lives in
[`validation/layering/`](../validation/layering/). Notable outcomes:

- **P1** — encrypt-before-compress inflates a compressible payload (size effect).
- **P5** — fragment-before-compress raises the fragment count.
- **P3** — authenticating the NAT-rewritten outer source breaks acceptance.
- **P4** — fixed-overhead layers commute exactly; quantised layers do not (§4).

## 3. Real-stack extension (P8–P12)

Predictions frozen before the harness in
[`layering-real-stack-predictions.md`](layering-real-stack-predictions.md);
results in [`layering-real-stack-results.md`](layering-real-stack-results.md).
**Frozen protocol: 20 runs per case.**

| Prediction | Status | Evidence |
|---|---|---|
| P8a AH tunnel + NAT | **CONFIRMED** | 0 % delivery, `XfrmInStateProtoError` + datagrams |
| P8b ESP tunnel + NAT | **CONFIRMED** | 100 % delivery (outer src outside ESP scope) |
| P8c WireGuard + NAT | **CONFIRMED** | 100 % delivery; peer learns the NAT endpoint |
| P9 WireGuard overhead | **CONFIRMED** | `wire(L) = 60 + 16·⌈L/16⌉`, 9/9 lengths exact |
| P10a naive commutation | **CONFIRMED** | `d(L) ≠ 0` for every length |
| P10b quantised model | **CONFIRMED** | `d(L) = −4 / +12` exact |
| P11a UDP length, no csum | **CONFIRMED** | 0 % delivery, cause gate |
| P11b UDP length, recomputed csum | **CONFIRMED** | 0 % delivery, cause gate |
| P11c inert ToS control | **CONFIRMED** | 100 % delivery |
| P12a ESP transport + NAT, inner csum | **CONFIRMED** | 0 %, `UdpInCsumErrors` + datagrams |
| P12b inner csum zeroed | **CONFIRMED** | 100 % delivery |
| P12c control, no NAT | **CONFIRMED** | 100 % delivery |

Three consequences for the model follow from the confirmed cases:

1. **`W` is quantised.** P9 shows WireGuard pads to 16 B, so the stipulated
   56 B composite (`E = 28`, `T = 28`) is off by 4–16 B. The fixed-overhead
   assumption (P4) is amended for quantising layers.
2. **Fixed-overhead layers do not commute once one layer quantises size.** P10
   shows `d(L)` is never zero: swapping IPIP and WireGuard changes the wire
   length by −4 or +12 bytes.
3. **Fields can be derived across layers.** P12 shows an inner UDP checksum
   depending on the outer address is invalidated by a NAT rewrite without any
   integrity tag.

What that means for the rule: on this kernel, the rule held for the three
integrity-scope cases (AH, ESP, WireGuard), the two size effects (P9, P10), the
structural rewrite (P11) and the derived field (P12). That is evidence for the
rule against independent implementations; it does not establish it in general
(see §5).

## 4. Related work

- **Middlebox behaviour.** Honda et al. measured how widely deployed middleboxes
  drop or rewrite options and payloads, and concluded that new transport
  extensions are hard to deploy *because of* such boxes. The present paper is
  narrower: it does not measure middlebox prevalence, it tests a rule about which
  field classes break when rewritten, with independently implemented stacks.
- **IPsec and NAT.** RFC 3715 specifies the IPsec/NAT compatibility problem, RFC
  4302 defines the AH integrity scope (which covers the outer IP header) and RFC
  4303 defines ESP (which does not). P8 is a direct, executable restatement of
  that asymmetry; AH dying under NAT is the expected textbook outcome, so P8
  validates the harness rather than discovering a new fact.
- **Layering and recursion.** RINA and the "divide and repeat" style of recursive
  internetworking treat layering as a repeated composition problem. This paper
  contributes a small empirical constraint on that composition: layers with
  fixed size effects commute, layers that quantise size do not.
- **End-to-end.** The survival rule is a framing-level counterpart to the
  end-to-end argument of Saltzer, Reed and Clark: what a middlebox can touch is a
  property of the header scope, not of the protocol's intent.

## 5. What is still open

The `lookup-key` class (P8b's interpretation) is not isolated by the experiment:
P8b was confirmed as "ESP survives", consistent with a lookup not keyed on the
outer source, but the test does not separate that mechanism from the ESP scope
argument. The evidence is one kernel (WSL2), one NAT implementation (nftables
masquerade), veth links, no wireless and no congestion; other stacks may pad
differently or resolve SAs differently. The `tc pedit` result is a property of
iproute2 6.19 — the layered `udp len` field is rejected, so the harness uses the
raw-offset form.

## 6. Scope

Measures sizes, delivery and drop causes. It does not evaluate cryptographic
security; one kernel, one NAT implementation and veth links say nothing about
arbitrary middleboxes. The conclusions bound these cases, not "all middleboxes".

## Cross-references

- [`layering-predictions.md`](layering-predictions.md) — P1–P7 predictions.
- [`layering-results.md`](layering-results.md) — P1–P7 results.
- [`layering-real-stack-predictions.md`](layering-real-stack-predictions.md) — P8–P12 predictions (frozen).
- [`layering-real-stack-results.md`](layering-real-stack-results.md) — P8–P12 results.
- [`validation/real_stack/`](../validation/real_stack/) — the executable harness.
