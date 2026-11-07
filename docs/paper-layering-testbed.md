# The Layering Survival Rule: A Testbed for Encapsulation Ordering in Heterogeneous Backhaul

**Milan Nikolic** · Independent Researcher · <m_nikolic@yahoo.com>

**Status:** focused paper (excerpted from the larger vision document; the
real-stack extension is complete for P8a/P8b/P8c/P9, with P10–P12 open — see
[`layering-real-stack-results.md`](layering-real-stack-results.md)).

## Abstract

Encapsulation layers — compression `C`, encryption/authentication `E`, tunnelling
`T`, fragmentation `F`, sequencing `S` — are usually studied one at a time. This
paper asks a narrower, testable question: **when the order changes, which layers
survive and which break?** It formalises a *survival rule* (a field survives a
rewrite iff it is visible, reachable and authenticated or structural) and tests it
in three independent implementations: a Python codec, a SimPy model, and a real
Linux stack (kernel WireGuard, IPsec AH/ESP, nftables NAT). The codec and model
agree exactly on P1–P7. The real-stack extension confirms the two integrity-scope
predictions (AH dies through NAT, ESP survives), the WireGuard-through-NAT case,
and measures the WireGuard wire overhead as `60 + 16·⌈L/16⌉` rather than the
stipulated 56 B. The `tc pedit` structural-rewrite case is inconclusive (the inert
control failed), and the quantised/derived-field cases (P10, P12) remain open.
Everything here is about *framing and survival*, not cryptographic security.

## 1. The question and the rule

A middlebox rewrites a header field. The receiver accepts the datagram iff every
layer that authenticates or structures the field can still do so. The testbed
freezes a rule — a field survives iff it is **visible** (at the wire),
**reachable** (within the middlebox's parse depth), and either **authenticated**
(in an integrity scope) or **structural** (length/offset-bearing) — and then
tests the rule, not the codec.

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

The predictions were frozen before the harness and are in
[`layering-real-stack-predictions.md`](layering-real-stack-predictions.md); results
in [`layering-real-stack-results.md`](layering-real-stack-results.md).

| Prediction | Status | Evidence |
|---|---|---|
| P8a AH tunnel + NAT | **CONFIRMED** | 0 % delivery, `XfrmInStateProtoError` +50 |
| P8b ESP tunnel + NAT | **CONFIRMED** | 100 % delivery (outer src outside ESP scope) |
| P8c WireGuard + NAT | **CONFIRMED** | 100 % delivery; peer learns the NAT endpoint |
| P9 WireGuard overhead | **CONFIRMED** | `wire(L) = 60 + 16·⌈L/16⌉`, 9/9 lengths exact |
| P10 nested IPIP/WG | NOT RUN | — |
| P11 `tc pedit` UDP length | INCONCLUSIVE | inert ToS control failed (setup, not rule) |
| P12 ESP transport + NAT checksum | NOT RUN | — |

Two consequences for the model follow directly from the confirmed cases:

1. **`W` is quantised.** P9 shows WireGuard pads to 16 B, so the stipulated
   56 B composite (`E = 28`, `T = 28`) is off by 4–16 B. The model's fixed-overhead
   assumption (P4) must be amended for quantising layers.
2. **The survival rule holds against independent implementations** for AH, ESP and
   WireGuard through NAT (P8a–c), which is the strongest available evidence for
   the rule short of a production deployment.

## 4. What is still open

P10 (nested `Y→W` vs `W→Y`) and P12 (ESP transport + inner checksum) are not run;
P11 needs a clean checksum-offload path before its inert control passes. `derived`
and `lookup-key` field classes remain unproven extensions of the model — the paper
does **not** claim they are needed or unnecessary until those cases run.

## 5. Scope

One kernel, one NAT implementation, veth links, no wireless, no congestion, no
cross traffic; security strength is not evaluated; `AH` is used only as the
clearest real case of an integrity scope covering the outer address. The
conclusions bound these cases, not "all middleboxes".

## Cross-references

- [`layering-predictions.md`](layering-predictions.md) — P1–P7 predictions.
- [`layering-results.md`](layering-results.md) — P1–P7 results.
- [`layering-real-stack-predictions.md`](layering-real-stack-predictions.md) — P8–P12 predictions (frozen).
- [`layering-real-stack-results.md`](layering-real-stack-results.md) — P8–P12 results.
- [`validation/layering/`](../validation/layering/) — codec/model validator and harness.
