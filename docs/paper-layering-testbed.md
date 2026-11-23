# When Do Protocol Layers Commute? A Pre-Registered, Cross-Fidelity Study of Encapsulation Ordering

**Milan Nikolic** · Independent Researcher · <m_nikolic@yahoo.com>

**Comments:** 17 tables, 7 figures. Part of a three-paper series on topological
routing (arXiv:XXXX.XXXXX), protocol layering (this paper), and bio-inspired
control limits (arXiv:YYYY.YYYYY).
**Primary:** cs.NI · **Cross-list:** cs.CR.

**Series note.** This paper is part of a three-paper series. The companion papers
are *Complex-Rotation Manifold Routing* (arXiv:XXXX.XXXXX) and *Why Fair-Queueing
Beats the Fick Principle* (arXiv:YYYY.YYYYY). The identifiers are placeholders
until the companion papers are posted.

**Status.** Focused measurement paper. Predictions were written down and locked in
four batches, each before the harness that could test it existed; §4.2 dates them
and §4.8 states what each round records and how the records are reduced. Every
table and every figure in this paper is computed from those records — no number is
transcribed by hand — and the same checks that compute them also refuse a
corrupted value (§4.8).

## Abstract

Protocol stacks are composed by convention — compress before encrypt, fragment
before tunnel, rewrite headers at middleboxes — yet these orderings are rarely
justified empirically. A wrong ordering is invisible until it manifests as
authentication failure, delivery collapse, or silent byte inflation. We report a
pre-registered evaluation of layer commutation at three fidelities, only one of
which is independent: the Python model, the SimPy simulator and the Linux
namespace leg are three engines, but the first two share an author and a
specification with the predictions, and the Linux leg of the first round runs the
harness's own user-space codec. We state a
field-class rule — a rewrite is applied iff the field is visible at the wire and
reachable by the middlebox, and breaks delivery iff the field is authenticated or
structural — and test it with sixteen prediction categories (34 sub-cases in the
real-stack rounds) plus a six-case replay-window follow-up. Together they expand
into 36 scored predictions about compression, encryption, fragmentation,
tunnelling and header rewriting. The predictions run in an executable Python
model, a SimPy event-driven simulator, and Linux network namespaces, across four
rounds, each frozen before the harness that tested it existed. All kernel evidence
comes from one WSL2 kernel series, veth links and one nftables implementation; the
frozen two-kernel replication clause is unmet, and the paper does not claim that
the rule transfers to another kernel series, another NAT implementation or a
physical NIC.

Of seven initial predictions, six are confirmed and P5 is refuted at the Linux
fidelity; the real-stack round confirms five further predictions; a deliberately
failure-prone round confirms 17 of 18 (Brier 0.0833) and refutes P16d; a
replay-window follow-up confirms six of six (Brier 0.0542). In total, **34 of 36
scored predictions are confirmed**.

Four findings. First, commutation is exact when every layer has fixed size effects
(P4: all six orderings of tunnelling, encryption and sequencing give 1104 B) and
fails when a layer quantises size (P10: IPIP and WireGuard orderings differ by −4
or +12 B by `L mod 16`). Fragmentation placement (P2) changes the wire bytes by
exactly 224 B (12,100 vs 12,324), i.e. 28 B per affected fragment. Second,
integrity boundaries are fragile under rewriting: AH through NAT delivers 0 %
(P8a), an outer CE mark is fatal on IPIP but inert on WireGuard and ESP (P13),
and the ESP replay window bounds delivery under reordering (P16, P17). Third,
reproducibility is checked rather than asserted: every table is rebuilt from the
per-run records by one reduction and re-checked against its invariants, and 27
injected faults — in the data and in the prose — each make that check fail. Fourth,
the refutations are reported, not removed: P5 (12.35 pp at Linux against
19.76 pp predicted) and P16d (673–717 of 2000 delivered at window 256).

All kernel evidence comes from one WSL2 kernel series, veth links and one nftables
NAT; the frozen two-kernel replication clause is **unmet**, and security is not
evaluated. The predictions, the harness and the per-run records are what a reader
needs to repeat the study, and §4.8 says exactly what each contains.

## 1. Introduction

A packet in the wild is rarely sent as built. It is compressed, encrypted,
tunnelled, fragmented and sequenced, in an order set by whoever configured the
stack, and then crosses devices that rewrite its headers (NAT), mark its
congestion bits (routers), and look up state keyed on fields they can read.
Whether the datagram arrives depends on which fields each device touches and which
fields the receiver treats as authenticated or structural. This knowledge exists,
but scattered across RFCs, middlebox measurement studies and kernel source; it is
rarely stated as one testable rule, and rarely tested against more than one
implementation.

We state such a rule and test it. A rewrite is **applied** iff the targeted field
is **visible** at the wire and **reachable** within the middlebox's parse depth.
It **breaks delivery** iff the field is **authenticated** (inside an integrity
scope) or **structural** (length- or offset-bearing). We test the rule with
predictions that were written down and dated before any experiment code existed, at
three fidelities of increasing realism, and we report every refutation rather than
removing it.

The rule survives, but is incomplete in four specific ways. Fields can be
**quantised** (WireGuard rounds sizes up, so layer order changes wire bytes);
**derived** (an inner UDP checksum depends on the outer address, so a rewrite
breaks delivery without any integrity tag); **keys to a middlebox's own state**
(two ESP clients cannot share a NAT address); and **decapsulation-coupled** (one
outer ECN mark is fatal under IPIP and harmless under WireGuard and ESP).
Reordering adds a state parameter: the integrity layer's replay window decides how
much delay the stack tolerates.

**Why this is worth measuring.** Three costs motivate the study. *Silent byte
inflation*: a size-quantising encryptor can add 12 bytes per datagram without any
error, and a compressor placed inside a tunnel can add an order of magnitude in
wire cost (P1 in §5.2: 32,815 B against 17,253 B for the same payload). *Silent
delivery collapse*: an authenticated field rewritten in flight produces a
receiver-side drop that looks like loss to the transport layer, which then
retransmits into the same failure (P3, P8). *Configuration coupling*: the same
middlebox behaviour is harmless on one decapsulator and fatal on another (P13), so
an operator cannot infer safety from the field alone. None of the three is
discoverable from the specification, because in all three the behaviour is left to
the implementation.

**Reading guide for a workshop audience.** The paper is long because it reports
every scored case. A reader who wants the method and the result can read §3.1–3.2
(the rule and the field classes, Table 1), §5.2–5.6 (the mechanism results) and
§5.3 (the verdict map); §4 and §5.1 give the protocol and the arithmetic, and the
per-case tables and the two raw size tables are in the appendix and are not needed
to follow any verdict.

**Contributions.**

1. A compact field-class model — visible, reachable, authenticated, structural,
   quantised, derived, lookup-key, decapsulation-coupled — plus one state
   parameter (the replay window), stated as a decision rule in §3 and derived from
   the cases rather than from first principles.
2. A method: predictions frozen before the harness that tested them existed, three
   fidelities, mutation and cause gates, explicit dispositions (CONFIRMED,
   REFUTED, INCONCLUSIVE, INVALID, NOT RUN), and credences scored with a Brier
   score; the method is reusable and its cost is stated.
3. A reproducible Linux testbed and the measured facts it produced,
   including the per-decapsulator ECN table and the first-come-first-served
   ESP-through-NAT behaviour. P13 and P14 check documented rules; the
   per-implementation table is the contribution, not the rule.
4. A negative result and a reproducibility audit: two refutations that stand
   (P5, P16d), a reduction whose every number is re-derived and mutation-tested
   against its records, and a cross-fidelity comparison
   that says where a Python model is *sufficient* (fixed-size arithmetic) and
   where it is *not* (quantised lengths, parser depths, replay state).

**What we do not claim.** We do not claim a first measurement of anything; the
middlebox literature and the RFCs are older than this work. We do not claim the
rule generalises to arbitrary middleboxes, kernels or stacks. We do not evaluate
cryptographic security. AH failing under NAT, the RFC 6040 decapsulation drop
rule and the ESP/NAT limitation are documented behaviours: confirming them
validates the method and the harness, not a discovery. P13 and P14 are executable
conformance checks on one kernel, not new field classes or new NAT requirements.
The informative results are the cases where the specification leaves behaviour to
the implementation (P10, P12, P16) and the per-decapsulator differences that the
RFCs do not settle, together with the measured first-come-first-served conntrack
behaviour.

## 2. Background and Related Work

### 2.1 The middlebox interaction

Honda et al. measured how widely deployed middleboxes drop or rewrite transport
options and payloads, and concluded that new transport extensions are hard to
deploy because of such boxes ("Is it still possible to extend TCP?", IMC 2011,
DOI [10.1145/2068816.2068834](https://doi.org/10.1145/2068816.2068834)). Their
finding is an *incentive* argument: middleboxes make deployment risky. Ours is a
*mechanism* argument: given a rewrite, the outcome is decided by the field's class
and the middlebox's parse depth. The two are complementary, and we do not measure
middlebox prevalence. The operational counterpart — middleboxes as a
first-class, outsourced service with their own failure modes — is argued by Sherry
et al. (SIGCOMM 2012, DOI
[10.1145/2377677.2377710](https://doi.org/10.1145/2377677.2377710)); our P14 result
is a small, concrete instance of that failure mode in conntrack state.

### 2.2 IPsec, NAT traversal and ECN: the RFC record

RFC 3022 defines traditional NAT; RFC 4787 states the UDP behavioural
requirements that a NAT must meet. RFC 3715 specifies the IPsec/NAT compatibility
problem. RFC 4302 defines AH, whose integrity scope covers the immutable part of
the outer IP header; RFC 4303 defines ESP, which in tunnel mode does not. RFC 3948
defines ESP-in-UDP for NAT traversal. RFC 3168 defines ECN itself, and RFC 6040 defines ECN tunnelling and the
outer-CE/inner-Not-ECT decapsulation rule.

P8 is therefore an executable restatement of the AH/ESP asymmetry, and we say so:
confirming it validates the harness. P13 is an executable check of the RFC 6040
rule per implementation, not a new rule; the WireGuard patch discussion records a
deliberate decision not to drop the outer-CE/inner-Not-ECT case, so the
three-answer table in §5.5 is a conformance observation on this kernel. P14 is the
same kind of check for the documented ESP/NAT limitation. Both were audited against
the patch history before the run rather than after: the WireGuard outer-CE handling
and the conntrack ESP limitation are kernel behaviours, not RFC requirements, and
§6.2.3 states what that costs.

WireGuard's design is documented by Donenfeld (NDSS 2017, DOI
[10.14722/ndss.2017.23160](https://doi.org/10.14722/ndss.2017.23160)); its
`16·ceil(L/16)` padding is exactly the size-quantising behaviour that P9 and P10
measure, and the reason P4's exact commutation does not survive a real encryptor.

### 2.3 Fragmentation, MTU and offload

IP fragmentation has been discouraged for two decades: RFC 1191 introduced path
MTU discovery, RFC 8899 restates packetization-layer PMTUD for datagram
transports, and RFC 8900 ("IP Fragmentation Considered Fragile") collects the
operational reasons. Measurement work has shown that fragmentation is also an
*attack* surface — Herzberg and Shulman use fragmented DNS responses to poison
resolvers ("Fragmentation Considered Poisonous", IEEE CNS 2013). The layering
question in P2 and P15 is upstream of that literature: before asking whether a
fragment is safe, one must know whether the encryptor saw one datagram or many.
Our P2 result (a fixed 28 B per affected fragment) and our P15 result (fragment
counts and delivery are equal, wire cost is not) give the size accounting those
arguments assume.

### 2.4 Encapsulation and recursive composition

NDN (Zhang et al., *ACM SIGCOMM Computer Communication Review* 44(3), 2014, DOI
[10.1145/2656877.2656887](https://doi.org/10.1145/2656877.2656887)) composes
forwarding state above a name layer; NLSR (Hoque et al., ICN 2013, DOI
[10.1145/2491224.2491231](https://doi.org/10.1145/2491224.2491231)) and FSR (Pei,
Gerla and Chen, IEEE ICC 2000, DOI
[10.1109/ICC.2000.853066](https://doi.org/10.1109/ICC.2000.853066)) compose routing
state on top of it; the fisheye overlay of Milić and Braun (IEEE LCN 2009, DOI
[10.1109/LCN.2009.5355168](https://doi.org/10.1109/LCN.2009.5355168)) composes a
peer view above the transport layer. All four put one layer's state inside another
layer's payload, which is precisely the operation P4, P9 and P10 test. RINA and the
"divide and repeat" formulation of recursive internetworking (Day, *Patterns in
Network Architecture*, Prentice Hall, 2008) treat layering itself as a repeated
composition problem; this paper contributes a small empirical constraint on that
composition: layers with fixed size effects commute, layers that quantise size do
not, and a field's survival can depend on the decapsulator rather than on the field
alone.

### 2.5 End-to-end reasoning

The survival rule is a framing-level counterpart to the end-to-end argument of
Saltzer, Reed and Clark (*ACM TOCS* 2(4), 1984, DOI
[10.1145/357401.357402](https://doi.org/10.1145/357401.357402)): what a middlebox
can touch is a property of the header scope and the path, not of the protocol's
intent. The end-to-end argument says where a function *should* live; the
field-class rule says what happens to a field that lives in the wrong place.

### 2.6 Pre-registration in systems measurement

Pre-registration is standard in psychology and medicine and rare in networking.
Nosek et al. ("The preregistration revolution", *PNAS* 115(11), 2018, DOI
[10.1073/pnas.1708274114](https://doi.org/10.1073/pnas.1708274114)) describe the
mechanism we adopt: freeze the prediction, then test it. Our adaptation for an
instrumented measurement paper is to freeze each prediction *before the harness that
could test it exists*, so that the freeze is a dated record rather than a claim made
afterwards, and to score credences with a Brier score so that a cautious prediction
set cannot pass as insight. A frozen prediction is never edited; corrections go to a
dated addendum of the results, never to the prediction itself.

### 2.7 The gap

The literature tests these layers one at a time — AH and NAT in one paper, ECN
decapsulation in another, fragmentation in a third, and each against a single
implementation. What is missing is a systematic, pre-registered, cross-fidelity
comparison of the *orderings*, scored on predictions frozen before the experiments,
with the refutations left in. To our knowledge no prior study freezes the
predictions and then tests the same ordering rules at model, simulator and kernel
fidelity; that is the gap this paper fills.

The claim is bounded, and the bound is part of the claim. The three fidelities are
one Python model, one SimPy model and one kernel; the first two were written by the
same author from the same specification as the predictions, so they are a
consistency check rather than an independent replication (§6.2.1), and the kernel
evidence is one series, one NAT, one encryptor, IPv4 only (§6.2.3, §6.3). When the
paper says a prediction is "confirmed at three fidelities" it means three engines
of which at most one is independent, and the kernel leg is the one that decides. What is
new is the *method* — a pre-run freeze plus a scored credence — and the table of
measured facts it produced, not a priority claim over the RFCs or the middlebox
literature.

## 3. Problem Statement: The Encapsulation Commutation Problem

### 3.1 Layers as functions on a byte stream

Let a layer be a function $L: B \to B$ on finite byte strings, consuming an input
datagram and producing a wire representation. A stack of two layers applied in
order is the composition $L_2 \circ L_1$; the reversed stack is $L_1 \circ L_2$. Write
$\lvert\cdot\rvert$ for the wire length of the output and $D(\cdot)$ for the end-to-end
delivery probability of the result over a fixed path.

**Definition 1 (exact commutation).** Layers $L_1$ and $L_2$ *commute exactly* on
input $x$ iff $L_2(L_1(x)) = L_1(L_2(x))$ as byte strings.

**Definition 2 (size commutation).** They *commute in size* iff
$\lvert L_2(L_1(x))\rvert = \lvert L_1(L_2(x))\rvert$ for all $x$ in the workload,
without requiring byte equality. P4 is a size-commutation claim; P10 is its
refutation on a real stack.

**Definition 3 (delivery commutation).** They *commute in delivery* iff
$D(L_2 \circ L_1) = D(L_1 \circ L_2)$ within the pre-registered margin. P2 and P15
are delivery-commutation claims under seeded loss.

Three regimes follow, and the paper's results are a map of which layer pairs fall
in which:

- **Fixed-size regime.** If every layer adds a constant $c_i$ bytes and removes
  nothing, then $\lvert L_2(L_1(x))\rvert = \lvert x\rvert + c_1 + c_2 =
  \lvert L_1(L_2(x))\rvert$: size commutation holds
  exactly, and byte equality holds for the header-producing layers tested. P4.
- **Quantising regime.** If a layer's output size is a step function of its input
  size, $L_2$ with $\lvert L_2(y)\rvert = R(\lvert y\rvert)$ for a staircase $R$,
  then the difference $d(L) = R(L + c) - R(L) - c$ is generally non-zero and depends
  on $L \bmod k$ for block size $k$. WireGuard gives $k = 16$ and
  $d(L) \in \{-4, +12\}$ (P9, P10).
- **Rewriting regime.** A middlebox applies `M` to fields visible at the wire.
  Commutation of `M` with the stack is decided not by size but by the field class
  of §3.2.

**The margin.** Definitions 2 and 3 need a tolerance to be testable, and the
tolerance is part of the prediction, not of the analysis. P2 and P15 use a 1.5 pp
margin on the delivery difference; P5 uses 4.0 pp on a difference it expected to be
19.76 pp. A difference inside its margin is a **non-rejection at that margin**, not
an equivalence result; §6.2.5 says what the design can and cannot conclude from
either.

### 3.2 Field classes and the decision rule

Table 1 lists the classes the rounds forced. Each is traceable to a test that
found it; none is introduced by definition alone. Figure 4 shows the two integrity
scopes side by side and the field that NAT rewrites.

**Table 1. Field classes.**

| Class | Definition | Found by | Effect on a rewrite |
|---|---|---|---|
| visible | readable at the wire (not inside an encryption layer) | P3, P4 | rewrite possible |
| reachable | within the middlebox's parse depth | P6 | rewrite possible |
| authenticated | covered by an integrity tag | P3, P8 | receiver rejects |
| structural | length- or offset-bearing | P7, P11 | receiver rejects or mis-parses |
| quantised | size rounded by a layer | P9, P10 | order changes wire bytes; layers no longer commute exactly |
| derived | value computed from a field in another layer | P12 | rewrite elsewhere invalidates it without a tag |
| lookup-key | selects state at the receiver (SA, policy) or the middlebox (conntrack) | P14 (middlebox key); P8b motivates the receiver-side variant | wrong or colliding key drops or merges flows |
| decapsulation-coupled | outer value combined with an inner value on the way out | P13 | outcome depends on the decapsulator implementation |

A state parameter accompanies the classes: the **replay window** of the integrity
layer (P16). With reordering depth at or above the window, valid packets are
dropped though none was lost on the wire. The edge is strict and was measured
directly (P17): a packet whose displacement equals the window is rejected, one at
`window − 1` is accepted, and the same pair of answers holds in a legacy 32-packet
window and in an ESN 256-packet window.

**The rule, stated once.** For a datagram produced by stack `S`, a middlebox `M`
rewriting field `f`, and a receiver `R`:

1. `M` applies the rewrite iff `f` is visible at the wire and within `M`'s parse
   depth (§3.3).
2. `R` rejects the datagram iff `f` is authenticated by an integrity scope `R`
   will check, or structural (length- or offset-bearing).
3. If `R` accepts, delivery still fails when `f` is a lookup key that collides, or
   when a value `R` recomputes depends on `f` (derived), or when the decapsulator
   combines `f` with an inner value in an implementation-defined way
   (decapsulation-coupled).
4. Independently of `f`, a datagram can be dropped by `R`'s replay window when the
   reordering depth reaches the window.

### 3.3 Middlebox model

`M` has a parse depth measured in bytes from the start of the outer IP header, an
ordered set of fields it may rewrite, and no knowledge of layers it cannot see.
This is the operational shape of NAT, of a TTL decrementer, of an ECN marker and
of a tunnel decapsulator. The model is deliberately weak: it does not assume `M`
recomputes any checksum it is not required to, and where `M`'s behaviour is
implementation-defined the model says so instead of guessing (that is the content
of the decapsulation-coupled class).

### 3.4 Out of scope

Keys, nonces and tags; replay as an attack (our P17 reinjects packets the harness
itself generated); fragmentation reassembly attacks; cross-traffic and congestion;
and any middlebox that reconstructs fields rather than rewriting them.

**IPv4 only.** Every experiment in this paper is IPv4. This matters for three of
the field classes and it is stated here rather than left to the reader: the IPv4
header this paper rewrites does not exist in IPv6, where fragmentation moved to a
fragment header that end hosts add and routers do not fragment (RFC 8200), where
path-MTU discovery is mandatory and fragmentation is a receiver-side exception
(RFC 8201), and where the AAD layout of an integrity scope differs field by field.
A reader who wants the IPv6 analogue should read the classes as *hypotheses* and
re-run P3, P8, P9 and P10 on an IPv6 harness; we do not claim the numbers transfer.

## 4. Methodology

### 4.1 Three fidelities

P1–P7 were run in an executable Python model, in a SimPy model with a finite
drop-tail queue, and on Linux network namespaces with a veth pair, TUN devices and
seeded `tc netem` loss. The real-stack rounds run four Linux namespaces with
kernel WireGuard, IPsec AH/ESP, IPIP and nftables masquerade; round 2 adds an ECN
mangler, ESP-in-UDP, a second client namespace, fragment / SPI / sequence capture
and depth gates.

**What "Linux fidelity" means in each round.** This distinction matters for every
claim about agreement, so it is stated here rather than in a footnote. In the P1–P7
round the Linux leg is a namespace data plane — netns, a veth pair, a TUN device
and seeded `tc netem` loss — driven by the harness's *user-space* codec: the
compressor, the AEAD and the fragmenter are the harness's own Python implementations
of zlib, a toy AEAD and RFC-style fragmentation, so this leg tests the kernel's
routing, queueing, MTU handling and checksum behaviour, **not** kernel crypto. From
P8 onward the encryption, tunnelling and fragmentation are the kernel's (WireGuard,
AH, ESP, IPIP, nftables), and those are the only rounds in which a number is a
statement about kernel cryptography.

The three tiers are chosen so that a disagreement is *informative*: the model is
byte-exact and has no queue; SimPy adds a finite queue and seeded drop; the Linux
leg adds a real data plane — the kernel's routing, MTU handling and parser in P1–P7,
plus its own crypto in P8–P17. When all three agree, the arithmetic is confirmed at
engine level; when they disagree, the disagreement localises the
implementation-defined part. §5.3 shows the pattern.

### 4.2 Pre-registration

Predictions were frozen in four batches, each before the harness that could test it
existed:

**Table 1b. The four freeze points.** Each batch was written down, dated and closed
before the corresponding harness was built.

| Batch | Predictions | Frozen before |
|---|---|---|
| 1 | P1–P7 | the first (Python-model) harness was written |
| 2 | P8–P12 | the real-stack (kernel) harness existed |
| 3 | P13–P16 | the round-2 harness existed |
| 4 | P17 | the round-3 harness existed |

A frozen batch is never edited; corrections go to a dated addendum of the *results*,
never to the prediction. Because the freeze is a dated record, a refutation can be
checked against what was actually predicted rather than against a description
written afterwards, and this paper quotes the frozen text verbatim in the two places
where that matters: P5's `n1 = 3` / `n2 = 6` fragment counts (§5.4) and P16d's
prediction of full delivery at window 256 (§5.6).

The paper states every expectation that it scores, with its threshold, in the
sections that test it. Nothing in §5 depends on a prediction the reader cannot read
here: Table 2 and Table 2b give the P1–P7 claims and their outcomes, §5.5–§5.6 give
P8–P17, and the thresholds (4.0 pp for P5, 1.5 pp for P15, full delivery for P16)
are quoted where they are used.

### 4.3 Paired-run protocol and n

Each case is executed as a **paired block**: the orderings being compared run with
the same seed and the same traffic trace, so that a difference between orderings
cannot be attributed to the draw. The frozen protocol is 20 runs per case (round 2:
20 cases, 400 runs, 5,800 observation rows; round 3: five traffic cases plus a mode
check scored from the same runs, 100 runs). Delivery quantities are pooled within a
case and reported as a mean with a paired 95 % confidence interval; the arithmetic
quantities (wire bytes, fragment counts) are deterministic per ordering and are
reported as identical in every run, which is itself a tested invariant.

*On n.* This paper does not use the 30-seed protocol of the companion paper
(arXiv:YYYY.YYYYY). With 20 paired runs, the resolution of a delivery difference is
about 1 percentage point after pooling; P5's pre-registered margin is 4.0 pp, so
the design has margin for its own claim and none to spare. §6.2.5 states what that
costs.

### 4.4 Gates and dispositions

A case is scored only when its gates pass: warm-up, checksum offload, ECN
mutation, SPI, fragment shape and reordering depth. Every case receives one
disposition: CONFIRMED, REFUTED, INCONCLUSIVE (a cause gate failed), INVALID
(another gate failed or setup error) or NOT RUN (facility missing). Only CONFIRMED
and REFUTED are evidence; the Brier score ignores the rest. No case in the reported
runs is INCONCLUSIVE, INVALID or NOT RUN. Gates are checked on captured packets,
not on the script's intent: a rewrite that the harness *believes* it applied but
that the capture does not show is a failed gate, and a case whose rewrite is absent
cannot be scored as a confirmation of anything.

### 4.5 Credence scoring

Round 2 recorded a credence per prediction before the run and scores each outcome
with the Brier term `(credence − outcome)`$^2$. The purpose is to make "the prediction
was easy" visible: a cautious set scores well only if the cases really were easy.
Round 3 does the same for the replay-window boundary.

### 4.6 Metrics

| Metric | Definition | Used by |
|---|---|---|
| wire bytes | bytes on the wire per datagram, summed over the datagram's fragments | P1, P2, P4, P9, P10, P15 |
| fragment count | datagrams produced by the fragmenter | P2, P5, P7, P15 |
| delivery % | received datagrams / sent datagrams, pooled per case | P2, P5, P7, P8, P13–P17 |
| acceptance % | received datagrams that pass the integrity check | P3, P8, P11, P12 |
| inner ECN at receiver | the ECN codepoint observed inside the tunnel | P13 |
| delivered count | datagrams delivered to the application, compared with a reference replayer | P16, P17 |
| reorder depth | maximum displacement of a delivered datagram | P16, P17 |

Every metric is obtained by the same reduction from the per-run records, and no
number in §5 is transcribed by hand. Delivery and acceptance are pooled per case and
reported as a percentage with a paired 95 % confidence interval over the 20 runs;
wire bytes and fragment counts are reported per ordering, where they are identical
in every run — a property that is itself checked, because a value that moves between
runs would silently invalidate the arithmetic claims. §4.8 describes what a run
records and what the checks are.

### 4.7 Environment

WSL2 Ubuntu 26.04.1 LTS; kernel `6.18.54.1-microsoft-standard-WSL2` for P1–P7 and
`6.18.58.1-microsoft-standard-WSL2` for P8–P17; iproute2 6.19.0; wireguard-tools
1.0.20250521; nftables 1.1.6; `ipip`, `wireguard`, `esp4`, `ah4`, `act_pedit`,
`act_csum`, `nft_masq` and `sch_netem` present. The Linux application payload is
normalised to `model_payload − 28` bytes so the codec sees a `model_payload`-byte
IP/UDP datagram; this normalisation was fixed in the frozen P1–P7 prediction and is
the direct cause of the P5 refutation.

### 4.8 What a run records, and how the records are checked

A run is one execution of one case at one fidelity with one seed. It writes one row
per observed quantity, in a fixed schema: the case, the ordering, the seed, the
metric, the value and the unit. Six families of quantity are recorded, and every
number in §5 is a reduction of one of them:

- **size** — wire bytes per datagram (minimum and maximum over the datagram's
  packets), packets per datagram, and the expected packet count;
- **delivery** — datagrams sent and delivered, the delivered percentage, and, where
  a reference replayer exists, the count the anti-replay filter should have accepted;
- **integrity** — datagrams accepted after the receiver's authentication check;
- **fields** — the ECN codepoint observed inside the tunnel, and the outer length and
  checksum values after the rewrite;
- **state** — reorder depth, sequence-error deltas, conntrack entry counts, and the
  effective anti-replay mode read back from the kernel;
- **gates** — warm-up, checksum offload, ECN mutation, SPI, fragment shape,
  reordering depth, capture and cause flags, each recorded as a boolean per run.

Three checks stand between those rows and a number in the paper. The first is
*determinism*: a quantity that the arithmetic fixes — a wire size, a fragment count —
must be identical in every run of the same case, and the reduction fails loudly if it
is not. The second is *gating*: a case is scored only when every gate it needs is
true, and the gate is read from the captured packets rather than from the harness's
intent. The third is *re-derivation*: each table and figure is rebuilt from the rows
by the reduction the caption states, and each value is asserted against the claim the
text makes about it, so a table cannot drift from its data without the check failing.

Those checks are themselves tested. Twenty-seven faults are injected into a copy of
the data and into the prose — a corrupted wire size, a flipped verdict, a wrong
Brier term, a stale gate flag, a number edited in a sentence, a broken
cross-reference — and each one must make the corresponding check fail. A check that
still passes after its input is corrupted is a check that proves nothing, which is
why the count (27) is reported rather than the assertion that the checks exist.

The scope of that evidence is narrow and is stated so a referee can weigh it. A
tamper test proves that the *pipeline* is sensitive to corruption; it proves
nothing about whether the *model* is right, and it is orthogonal to a corrupted
model. Three things it does not substitute for: a second implementation of the
same predictions by a different author, a second kernel series, and an independent
re-derivation of a verdict from the published numbers alone. The first two are
absent from this paper (§6.2.1, §6.2.3); the third is what Figures 3 and 7 are
for, since every plotted number is recomputed from the per-run rows rather than
transcribed.

**Repeating the study.** The four rounds are independent setups, and each is
repeatable from this description alone: the scenario of §4.1 and the environment
above fix the topology and the kernel; §4.3 fixes the pairing and the run count; the
frozen claims quoted in §5 fix what is being measured. Concretely, a repetition is
five steps per round: build the two namespaces and the middlebox on the path; enable
the gates and capture on both sides; run the case 20 times with the same seed and the
same traffic trace for both orderings; reduce the rows with the metric definitions of
§4.6; and compare the outcome with the frozen prediction before looking at any other
case. The P1–P7 round additionally runs the Python model and the SimPy model, which
are the same reduction over the same schema, so the three fidelities are compared
row for row rather than paragraph for paragraph.

## 5. Results

### 5.1 Overview

Table 2 gives the dispositions for P1–P7. The model and the SimPy implementation
agree on all seven; Linux agrees on six and refutes P5.

**Table 2. P1–P7 verdicts by fidelity.** One cell per prediction × fidelity; a
prediction is confirmed overall only when every fidelity that tested it confirms.
Each cell is the reduction of that case's 20 paired runs in that round.

| Prediction | Model | SimPy | Linux | Overall |
|---|---|---|---|---|
| P1: compress/encrypt size | CONFIRMED | CONFIRMED | CONFIRMED | CONFIRMED |
| P2: encrypt/fragment overhead | CONFIRMED | CONFIRMED | CONFIRMED | CONFIRMED |
| P3: integrity scope | CONFIRMED | CONFIRMED | CONFIRMED | CONFIRMED |
| P4: fixed-overhead commutation | CONFIRMED | CONFIRMED | CONFIRMED | CONFIRMED |
| P5: compress/fragment delivery | CONFIRMED | CONFIRMED | REFUTED | REFUTED |
| P6: survival sweep | CONFIRMED | CONFIRMED | CONFIRMED | CONFIRMED |
| P7: structural inertness | CONFIRMED | CONFIRMED | CONFIRMED | CONFIRMED |

**Table 2b. P1–P7 key quantities by fidelity.** The same reduction, one row per
quantity. A quantity that the arithmetic fixes — a wire size, a fragment count — is
identical in every run of a case and is therefore reported as a single number;
delivery is a pooled percentage over the runs.

| Quantity | Model | SimPy | Linux |
|---|---|---|---|
| P1 text wire bytes, E→C / C→E (ratio) | 1.902 | 1.902 | 1.878 |
| P2 wire bytes, E→F / F→E | 12100 / 12324 | 12100 / 12324 | 12100 / 12324 |
| P2 byte difference (F→E − E→F) | 224 | 224 | 224 |
| P2 delivery E→F / F→E (%) | 39.35 / 39.35 | 39.35 / 39.35 | 37.98 / 38.17 |
| P4 wire bytes over the six orderings | 1104 (all equal) | 1104 (all equal) | 1104 (all equal) |
| P5 fragments C→F / F→C | 3.0 / 6.0 | 3.0 / 6.0 | 4.0 / 6.0 |
| P5 delivery C→F / F→C (%) | 73.75 / 53.50 | 73.75 / 53.50 | 64.28 / 51.92 |
| P5 delivery difference (pp) | +20.25 | +20.25 | +12.35 |
| P6 cases checked | 54 | 54 | 54 |

P1, P2, P4 and P5 are arithmetic regression tests: confirming them shows that the
three implementations reproduce the specified arithmetic, not that a deployed
network behaves this way. P3, P6 and P7 are the research content of this round.

### 5.2 The fixed-size regime commutes; the quantising regime does not

Figure 1 draws the two orderings that the rest of the section quantifies, and
Figure 2 gives the bytes.

![Figure 1](../figures/paperA_fig1_stack_comparison.pdf){width=100%}

**Figure 1.** Layer orderings and their measured cost. This is a diagram of
*ordering*, not a measurement: it defines the `C→E` / `E→C` / `E→F` / `F→E` notation
the rest of the paper uses and ties it to the byte counts that Figure 2 plots. (a)
Compression before and after encryption (P1, model fidelity): the reversed order
costs +90 % wire bytes because ciphertext does not compress. (b) Encryption before
and after fragmentation (P2, Linux fidelity): 12,100 B against 12,324 B, a
difference of 224 B. Arrows are the order in which each layer consumes the byte
stream; the values are the measured bytes of Figure 2, and nothing is drawn to
scale.

Panel (a) of Figure 2 is P2: the same 2,000-byte UDP payload, fragmented before
or after the encryptor, differs by 224 B — 28 B on each of the eight affected
fragments — and the value is identical at all three fidelities. Panel (b) is P4:
the six fixed-overhead orderings of tunnelling `T`, encryption `E` and sequencing
`S` all produce 1,104 B at every leg — and, per §4.1, the P1–P7 Linux leg runs the
harness's user-space codec, so this is agreement between two models and one
data-plane harness on the same codec, not agreement with kernel cryptography. The
kernel's own encryptor enters at P8, and §5.2's quantisation result (P9, P10) is
where it disagrees.

![Figure 2](../figures/paperA_fig2_wire_bytes.pdf){width=100%}

**Figure 2.** Wire bytes per ordering. (a) P2, fragmentation around the encryptor.
(The P1–P7 Linux leg uses the harness's user-space codec, §4.1; kernel crypto is
exercised from P8 on, not here.) The y-axis starts at 11,850 B because a zero-based
axis renders the paper's own finding — a 224 B difference, 1.8 % of the value —
literally invisible; the axis start is printed in the label, the exact values are
printed at the points, and the difference is annotated with its decomposition
(28 B × eight affected fragments). No visual proportion is used to argue any claim:
the numbers are the claim. Points rather than bars are used so that the truncated
axis is not read as a magnitude. (b) P4, the six fixed-overhead orderings: all six
are identical to the byte, which is what size commutation means. Data: wire bytes
per ordering, identical in every run of the case at all three fidelities.

P1, P4 and P9–P10 are the size-accounting core of the paper. P9 is a calibration:
the stipulated 56-byte composite (`E = 28`, `T = 28`, no padding) is low by
`4 + (16*ceil(L/16) - L)` bytes. WireGuard is **quantised**. P10 makes that visible
as a commutation failure: swapping IPIP and WireGuard changes the wire length by
−4 or +12 bytes depending on `L mod 16`, and the quantised model
`d(L) = R(L+20) − R(L) − 20` is exact. Figure 5 draws both: the staircase against the
nine measured sizes, and `d(L)` against `L mod 16`.

### 5.3 The verdict map

Figure 3 collects every scored prediction at every fidelity that tested it. The
point of the figure is the two red cells: a pre-registered study that reports no
refutation is not reporting a measurement, it is reporting a preference.

![Figure 3](../figures/paperA_fig3_verdict_heatmap.pdf){width=100%}

**Figure 3.** Pre-registered dispositions. A cell is one prediction × one fidelity,
not one sub-case: P16 is a single red cell although three of its four sub-cases are
confirmed, which is why the figure counts 28 of 30 cells while the paper counts
34 of 36 scored predictions. Green = CONFIRMED, red = REFUTED, grey = not tested at
that fidelity. P1–P7 were run at all three fidelities; the real-stack rounds
(P8–P16) were run on Linux only, so the model and SimPy cells are empty by design,
not by omission. P16 is scored REFUTED because P16d is (three of its four sub-cases
confirmed). Built from the per-case verdicts of the four rounds.

### 5.4 Fragmentation placement and the P5 refutation

P2 is the size claim (Figure 1b, Figure 2a). P5 is the *delivery* claim on the same
pair of orderings, and it is the round's refutation. The frozen prediction was
`n1 = 3` fragments for compress-then-fragment and `n2 = 6` for
fragment-then-compress, a delivery difference of `0.9^3 - 0.9^6 = 19.76`
percentage points. The model and SimPy produce that difference (+20.25 pp on their
draws); Linux produces **+12.35 pp**, outside the frozen 4.0 pp margin. The cause
is measured, not guessed: the Linux `C→F` datagram has **four** fragments because
the compressor saw the real 28-byte IP/UDP header, and with stock zlib 1.3.1 the
packet compressed to about 4507 B, above the three-fragment boundary of 4476 B.
Recomputing with the observed count gives `0.9^4 - 0.9^6 = 12.47` pp, which Linux
reproduces. The frozen prediction stands as refuted; it is reported as it was
written, not restated to match the outcome.

This is the clearest cross-fidelity lesson in the paper. The model and the kernel
agree exactly on *bytes* and disagree by 7.4 pp on *delivery*, because the number of
fragments is a discrete function of a compressed length that the model stipulated
and the kernel measured. A cross-fidelity prediction with compressible data near a
fragment boundary must state the encoded input, not only the application payload.

### 5.5 Integrity boundaries: P3, P8, P11, P12

**P3 (integrity scope).** Three cases: `E→T` with the target inside the AEAD's
AAD, `E→T` with no AAD, and `T→E` where the target is invisible. Acceptance is
exactly 0 %, 100 % and 100 % at every fidelity, with no intermediate value. Case
(a) is the operational shape of the known NAT/IPsec failure; it is confirmed here
for a toy AEAD and a scripted rewriter, which is narrower than the real-world
claim. Figure 4 shows the field layout that produces the 0 %, and the same layout
that lets ESP and WireGuard survive the rewrite.

![Figure 4](../figures/paperA_fig4_integrity_scope.pdf){width=100%}

**Figure 4.** What the integrity scope covers, and what NAT rewrites. (a) AH
(RFC 4302) authenticates the immutable part of the *outer* IPv4 header, so the
source-address rewrite invalidates the ICV: 0 % delivery for AH through NAT, 100 %
without NAT, and the toy-AEAD control (P3) gives 0 % / 100 % / 100 % for "inside the
AAD" / "excluded from the AAD" / "invisible". (b) ESP tunnel mode (RFC 4303) leaves
the outer header outside its scope, so the rewrite passes: 100 % for ESP and
WireGuard through NAT. The inner UDP checksum is nonetheless *derived* from the
rewritten address, so it fails (0 %) unless zeroed (100 %) — P12. Fields are drawn to
scale in bytes; the source address is the field this testbed's SNAT rewrites (DNAT
would rewrite the destination instead). Data: delivery percentages pooled over 20
runs per case, from the round-1 real-stack records and the toy-AEAD control of the
P1–P7 round.

Round 1 of the real-stack testbed confirms all twelve cases of the five
predictions (Table 3). The cases are executed 20 times each.

**Table 3. P8, P11 and P12 on the Linux stack.** The predicted column is the frozen
text; the observed column is the mean of 20 runs with its min–max range; the gates are
read from the captured packets rather than from the harness's intent.

| Case | Stack / middlebox | Predicted delivery | Observed % mean (min–max) | Runs | Gates | Verdict |
|---|---|---|---|---|---|---|
| P8a | AH tunnel + NAT | 0 % | 0.0 (0) | 20 | mutation yes, cause yes | CONFIRMED |
| P8a_control | AH tunnel, no NAT | 100 % | 100.0 (100) | 20 | mutation yes, cause yes | CONFIRMED |
| P8b | ESP tunnel + NAT | 100 % | 100.0 (100) | 20 | mutation yes, cause yes | CONFIRMED |
| P8b_control | ESP tunnel, no NAT | 100 % | 100.0 (100) | 20 | mutation yes, cause yes | CONFIRMED |
| P8c | WireGuard + NAT | 100 % | 100.0 (100) | 20 | mutation yes, cause yes, endpoint yes | CONFIRMED |
| P8c_control | WireGuard, no NAT | 100 % | 100.0 (100) | 20 | mutation yes, cause yes | CONFIRMED |
| P11a | WireGuard, UDP length 9, checksum untouched | 0 % | 0.0 (0) | 20 | mutation yes, cause yes | CONFIRMED |
| P11b | WireGuard, UDP length 9, checksum recomputed | 0 % | 0.0 (0) | 20 | mutation yes, cause yes | CONFIRMED |
| P11c | WireGuard, inert ToS rewrite | 100 % | 100.0 (100) | 20 | mutation yes, cause yes | CONFIRMED |
| P12a | ESP transport + NAT, inner UDP checksum | 0 % | 0.0 (0) | 20 | mutation yes, cause yes | CONFIRMED |
| P12b | ESP transport + NAT, inner checksum zero | 100 % | 100.0 (100) | 20 | mutation yes, cause yes | CONFIRMED |
| P12c | ESP transport, no NAT | 100 % | 100.0 (100) | 20 | mutation yes, cause yes | CONFIRMED |

AH dies under NAT while ESP and WireGuard survive (P8). This is textbook
asymmetry — RFC 3715 describes the compatibility problem, RFC 4302 puts the outer
IP header in AH's integrity scope and RFC 4303 does not for ESP — and the run
validates the harness rather than discovering a fact. Figure 4 is the same result
drawn as field layout, and it is the figure a reader should keep in mind for P12:
the fact that the inner packet is authenticated does not protect it, because the
value that fails is *derived* from the field that was rewritten.

P11 separates a structural rewrite from a broken mangler. Rewriting the outer UDP
length to 9 breaks delivery whether the checksum is left untouched (0 %) or
recomputed (0 %), while an inert ToS rewrite with a recomputed IP checksum
delivers 100 %. The raw-offset `pedit` form is used because iproute2 6.19 rejects
the layered `udp len` field.

P12 is the **derived** class: ESP transport does not authenticate the outer IP
header, so NAT passes the ESP check, but the inner UDP checksum covers a
pseudo-header containing the rewritten outer address, so it fails (0 %); zeroing
the inner checksum restores delivery (100 %), and the no-NAT control delivers
100 %.

### 5.6 Results III: P13–P17

Round 2 is deliberately failure-prone: credences were recorded before the run,
and the protocol was designed so that some predictions were expected to fail. Of
18 scored predictions, **17 are confirmed and one (P16d) is refuted**; the Brier
score is **0.0833**.

**Table 4. P13: outer ECN codepoint set to CE or ECT(0) after NAT, by
decapsulator.** Ten cases, 20 runs of 50 datagrams each. Delivery, the inner ECN
codepoint observed at the receiver and the IPIP frame-error counter are read from the
round-2 records; the counter is a frame error, not a queue drop.

| Case | Decapsulator | Inner ECN | Outer ECN set to | Delivery | Inner ECN at receiver | Cause counter | Verdict |
|---|---|---|---|---|---|---|---|
| P13a | IPIP | Not-ECT | CE | 0 % | — | rx_frame_errors 50/run | CONFIRMED |
| P13b | IPIP | Not-ECT | ECT(0) | 100 % | Not-ECT 100 % | rx_frame_errors 0/run | CONFIRMED |
| P13c | IPIP | ECT(0) | CE | 100 % | CE 100 % | rx_frame_errors 0/run | CONFIRMED |
| P13d | WireGuard | Not-ECT | CE | 100 % | Not-ECT 100 % | — | CONFIRMED |
| P13e | WireGuard | ECT(0) | CE | 100 % | CE 100 % | — | CONFIRMED |
| P13f | ESP tunnel | Not-ECT | CE | 100 % | Not-ECT 100 % | — | CONFIRMED |
| P13g | ESP tunnel | ECT(0) | CE | 100 % | CE 100 % | — | CONFIRMED |
| P13h_ipip | IPIP | both | none (control) | 100 % | ECT(0) 50 % / Not-ECT 50 % | rx_frame_errors 0/run | CONFIRMED |
| P13h_wg | WireGuard | both | none (control) | 100 % | ECT(0) 50 % / Not-ECT 50 % | — | CONFIRMED |
| P13h_esp | ESP tunnel | both | none (control) | 100 % | ECT(0) 50 % / Not-ECT 50 % | — | CONFIRMED |

**Table 4b. Decapsulation of an outer CE mark.** The same visible,
unauthenticated field is fatal on one stack and inert on two.

| Decapsulator | Outer CE, inner Not-ECT | Outer CE, inner ECT(0) |
|---|---|---|
| IPIP | drop (50 frame errors/run) | deliver, inner CE |
| WireGuard | deliver, inner Not-ECT | deliver, inner CE |
| ESP tunnel | deliver, inner Not-ECT | deliver, inner CE |

**One field, three answers.** A router marking Congestion Experienced on the
outer header is legitimate behaviour. Under RFC 6040's decapsulation rule an
outer CE over an inner Not-ECT packet should be dropped. We rewrote the outer ECN
codepoint to CE after the NAT and recorded delivery per decapsulator over 20 runs
of 50 datagrams. IPIP dropped every packet (`ipip0` `rx_frame_errors` rose by 50
per run, a frame error rather than a queue drop). WireGuard and ESP tunnel mode
delivered every packet and left the inner field Not-ECT; with an ECT(0) inner,
all three delivered and propagated CE. The same visible, unauthenticated field is
inert on two stacks and fatal on the third, so the rule cannot classify it by
visibility alone: it has to name the decapsulator. This is the
**decapsulation-coupled** class, with a per-implementation table rather than a
field property. Figure 6(a) draws the three-by-three matrix that Table 4 reports.

**Two ESP clients and one NAT.** Two client namespaces, each with its own ESP
tunnel-mode SA (distinct SPI and key) to one server behind one masquerade; one
client warms up, then both send concurrently.

**Table 5. P14: two ESP clients behind one NAT.** Counts are per run; the SPI values
are read from the capture and the conntrack entries from the kernel's table.

| Case | Setup | Client 1 delivered/sent | Client 2 delivered/sent | ESP SPI on wire (1 / 2) | ESP conntrack entries | Client 2 translated src port | Verdict |
|---|---|---|---|---|---|---|---|
| P14a | ESP tunnel + NAT, client 1 first | 60/60 | 0/50 | 60 / 0 | 1 | — | CONFIRMED |
| P14b | ESP tunnel + NAT, client 2 first | 0/50 | 60/60 | 0 / 60 | 1 | — | CONFIRMED |
| P14c | ESP-in-UDP (NAT-T) + NAT | 60/60 | 50/50 | 60 / 50 | 0 | 1496–64424 | CONFIRMED |
| P14d | ESP tunnel, no NAT | 60/60 | 50/50 | 61 / 51 | 0 | — | CONFIRMED |

The loser's packets never reach the router's egress: the second ESP flow gets no
conntrack entry (one `unknown … 50` entry, not two), because the generic tracker
has no per-flow key for protocol 50 and the reply tuple of a second inside host
collides with the first. This is a lookup-key failure **at the middlebox**, and it
is first-come-first-served: swapping which client sends first swaps the loser.
With ESP-in-UDP both clients succeed, for two separate reasons the capture
distinguishes: the UDP ports give the NAT a usable key (client 2's translated
source port is remapped to a random value in 1496–64424 across runs), and the
receiver, configured with `encap espinudp 4500 4500`, happily decapsulates
packets whose source port is no longer 4500. Figure 6(b) plots the delivered counts
and the conntrack entries of Table 5 side by side.

**Fragmentation before or after the encryptor.** One inner datagram of 2000 B UDP
payload: encrypt-then-fragment yields **2112 B** per datagram (1500 + 612), and
fragment-then-encrypt yields **2180 B** (1480 + 700), a difference of exactly 68 B
in 20/20 runs. Delivery under 5 % loss is 0.9003 and 0.9041 against a predicted
0.9025 ± 0.015; the difference between orderings is 0.38 pp against the 1.5 pp margin
fixed in the frozen prediction, so delivery *does not separate* under a real
fragmenter and a quantising encryptor even though the wire cost differs. That is a
non-rejection at the stated margin, not an equivalence result (§6.2.5).

**Table 5b. P15: fragmentation placement around WireGuard.** The predicted columns
are the frozen values; the observed wire bytes are identical in all 20 runs, and
delivery is pooled over them.

| Ordering | Wire bytes per datagram | Predicted (frozen) | Packets per datagram | Pooled delivery | Predicted delivery (frozen) |
|---|---|---|---|---|---|
| E→F (encrypt, then fragment) | 2112 (all equal) | 2112 | 2 | 0.9003 | 0.9025 ± 0.015 |
| F→E (fragment, then encrypt) | 2180 (all equal) | 2180 | 2 | 0.9041 | 0.9025 ± 0.015 |

**The replay window, not the path, sets the loss.** Netem delays 75 % of a
2000-datagram burst by 100 ms; 25 % go immediately, so the reordering depth is
~2000. Table 6 gives the result, and Figure 7(a) plots it: the 20 per-run delivered
counts of each case against the 2,000 sent.

**Table 6. P16: replay window against reordering.** 20 runs of 2,000 datagrams per
case. "Equals reference filter" means the kernel's delivered count equals the count a
strict anti-replay filter should have accepted, in every run.

| Case | Stack / window / reorder | Observed reorder depth | Delivered (min–max) | Equals reference filter | Sequence errors | Verdict |
|---|---|---|---|---|---|---|
| P16a | ESP, window 32, 100 ms reorder | 1992–1999 | 476–565 of 2000 | yes | 1435–1524 | CONFIRMED |
| P16b | ESP, window 32, 4 ms reorder | 1 | 2000 of 2000 | yes | 0 | CONFIRMED |
| P16c | WireGuard, 100 ms reorder | 1985–1999 | 2000 of 2000 | yes | 0 | CONFIRMED |
| P16d | ESP, window 256, 100 ms reorder | 1991–1999 | 673–717 of 2000 | yes | 1283–1327 | REFUTED |

P16a is exact in the strongest sense the protocol asked for: in 20/20 runs the
delivered count equals the reference filter's count and the
`XfrmInStateSeqError` delta equals `sent − delivered` to the packet. No packet
was lost on the wire; about 74 % were discarded by the receiver for arriving too
late. P16d predicted 100 % at window 256 and is **refuted**: the burst is ~2000
deep, and a 256-packet window cannot span it (673–717 delivered). The mechanism
was confirmed — the reference filter at window 256 matches the kernel exactly —
but the depth was mis-specified: the frozen text assumed a shallower burst than
the sender actually produced. Two caveats: on this kernel/iproute2
`replay-window 256` silently turns the SA into an ESN SA, and the strict/inclusive
boundary of `< window` was never hit exactly, so that edge is untested.

**P17: the boundary itself.** Both caveats were testable, so a fourth batch of
predictions was frozen before a round-3 harness existed: a rate-limited sender whose
reordering depth falls inside a pre-registered band, and captured-and-reinjected ESP
packets placed at an exact displacement, in each anti-replay mode. P17 is a follow-up
on the replay semantics, not a new field
class. Table 6b gives the result.

**Table 6b. P17: the replay-window boundary, exactly.** Five traffic cases × 20
runs, plus the mode check scored from the same runs. The reinjection cases place two
captured packets at an exact displacement from the highest sequence number seen.

| Case | Stack / window / displacement | Delivered (min–max) | Reference filter | Effective mode | Verdict |
|---|---|---|---|---|---|
| P17a | ESP, ESN window 256, 1 ms pacing, depth gate [64, 200] | 600 of 600 | matches | ESN | CONFIRMED |
| P17b | ESP, legacy window 32, displacement = window | 1 of 2 | 1 | legacy | CONFIRMED |
| P17c | ESP, legacy window 32, displacement = window - 1 | 2 of 2 | 2 | legacy | CONFIRMED |
| P17d | ESP, ESN window 256, displacement = window | 1 of 2 | 1 | ESN | CONFIRMED |
| P17e | ESP, ESN window 256, displacement = window - 1 | 2 of 2 | 2 | ESN | CONFIRMED |

*P17a observed reorder depth 91–92; five traffic cases x 20 runs, and P17f is
scored from the same runs, so the round is 100 runs. P17b-P17e reinject two
captured packets at displacement `window` (rejected) and `window - 1` (accepted).
P17f, the mode check, is CONFIRMED and is the 'Effective mode' column.*

All six predictions are confirmed. P17a paces the sender at 1 ms per datagram and
records a depth of 91–92, inside the frozen [64, 200] band; the 256-packet window
is wider than that depth and delivers 600 of 600 datagrams, matching the reference
filter and the sequence-error count exactly. A large window is therefore not too
small by itself: what P16d measured was the depth of a 33 kpps burst, not the
window. P17b–P17e then place two captured packets at exactly displacement `window`
and `window − 1`: the packet at the window is rejected and the one inside it is
accepted, in 20/20 runs, in both the legacy 32-packet window and the ESN
256-packet window, with the strict `< window` reference filter agreeing in every
run. P17f reads the effective mode from `ip xfrm state` in every reinjection run
rather than inferring it, which is what licenses labelling the 256-packet results
ESN at all. Figure 7(b) plots the reinjection outcome: one packet at the window is
rejected, one at `window − 1` is accepted, in both modes.

What this settles, and what it does not. It settles both caveats: the boundary is
strict on this kernel, and the round-2 window-256 case was an ESN SA. It does not
turn P16d into a confirmation — that prediction stays refuted — and it is still
one kernel, one ESP implementation, one iproute2 version, a single-packet test at
one alignment rather than a sweep of window sizes, and a controlled harness
action on packets the harness itself generated, not a replay attack. The round
also refuted nothing, which is itself a limitation: cases that isolate a
mechanism are not a random sample of kernels.

**Credence scoring.** Table 7 gives the 18 scored predictions.

**Table 7. Round-2 credences and outcomes.** Credences were recorded before the
run, not assigned after the outcomes were known; the Brier term is
(credence − outcome)².

| Prediction | Credence | Outcome (1 = confirmed) | Brier term |
|---|---|---|---|
| P13h | 0.95 | 1 | 0.0025 |
| P13a | 0.90 | 1 | 0.0100 |
| P13b | 0.90 | 1 | 0.0100 |
| P13c | 0.90 | 1 | 0.0100 |
| P13d | 0.70 | 1 | 0.0900 |
| P13e | 0.70 | 1 | 0.0900 |
| P13f | 0.60 | 1 | 0.1600 |
| P13g | 0.60 | 1 | 0.1600 |
| P14a | 0.60 | 1 | 0.1600 |
| P14b | 0.60 | 1 | 0.1600 |
| P14c | 0.90 | 1 | 0.0100 |
| P14d | 0.95 | 1 | 0.0025 |
| P15_bytes | 0.80 | 1 | 0.0400 |
| P15_delivery | 0.75 | 1 | 0.0625 |
| P16a | 0.85 | 1 | 0.0225 |
| P16b | 0.90 | 1 | 0.0100 |
| P16c | 0.90 | 1 | 0.0100 |
| P16d | 0.70 | 0 | 0.4900 |

*Brier score 0.0833 over 18 scored predictions; expected refutations at these
credences 3.8, observed 1.*

**Table 7b. Round-3 credences and outcomes.** The same scoring, applied to the six
replay-window predictions.

| Prediction | Credence | Outcome (1 = confirmed) | Brier term |
|---|---|---|---|
| P17a | 0.75 | 1 | 0.0625 |
| P17b | 0.80 | 1 | 0.0400 |
| P17c | 0.80 | 1 | 0.0400 |
| P17d | 0.70 | 1 | 0.0900 |
| P17e | 0.70 | 1 | 0.0900 |
| P17f | 0.95 | 1 | 0.0025 |

*Brier score 0.0542 over 6 scored predictions; expected refutations at these
credences 1.3, observed 0.*

**Table 8. Headline counts.** One row per round; a prediction counts as confirmed
only if every fidelity that tested it confirms.

| Round | Confirmed |
|---|---|
| P1-P7 | 6 of 7 |
| P8-P12 | 5 of 5 |
| P13-P16 | 17 of 18 |
| P17 | 6 of 6 |
| total | 34 of 36 |

### 5.7 What the counts do and do not mean

Under the stated credences round 2's expected score was 0.15 with 3.8 expected
refutations; the observed score is 0.0833 with one refutation, and the credences
were too cautious on the implementation-detail cases (0.6–0.7), all of which came
in. The one failure is not an implementation detail but a parameter: how deep a
burst a 100 ms netem queue with a 33 kpps sender makes. The eight frozen
assumptions about the kernel (A1–A8) all held. Round 3 expected 1.3 refutations at
its own credences and observed none, so its 0.0542 is weaker evidence about
calibration than round 2's 0.0833: it says the boundary cases were easy, which
they were designed to be.

**Table 9. Per-round expected and observed Brier scores.** Computed from the
credence tables above.

| Round | Scored | Expected refutations | Observed refutations | Brier |
|---|---|---|---|---|
| P13–P16 | 18 | 3.8 | 1 (P16d) | 0.0833 |
| P17 | 6 | 1.3 | 0 | 0.0542 |

### 5.8 The P6 survival sweep and P7 structural inertness

**P6 (54 cases).** All six orderings of `T`, `E`, `S` were crossed with two
targets, parser depth 1–3 and AAD scope none or the target where valid: 54 cases.
The formal predictor declares 36 visible and 18 invisible targets, 40 reachable
and 14 unreachable, 32 rewrites applied, 16 authentication failures and 16
delivery failures. Model, SimPy and Linux match the predictor on visibility,
mutation, acceptance and delivery in **every case** (0 mismatches). Because the
predictor and the relay encode the same rule, this is a consistency check of the
implementation, not evidence that the rule matches deployed middleboxes.

**P7 (structural inertness).** With a `T→F` stack and three fragments, both
length-bearing rewrites (`F.length → 0x0009`, `T.udp_len → 0x0009`) give 0 %
delivery at all three fidelities, although neither field is authenticated and
both are visible; the inert source-port rewrite gives 100 %. Excluding a field
from authentication is not sufficient for safe rewriting if it carries framing
structure.

### 5.9 The measurements in one view

The tables above state the measurements as numbers. Three figures carry the same
records drawn, so that the shape of each result is visible without reconstructing it
from a table: the staircase that makes sizing non-commutative (Figure 5), the
per-decapsulator split and the conntrack collision (Figure 6), and the replay window
against the depth of the burst (Figure 7). Each figure plots the values of the tables
it names and no other value; where a table and a figure give the same number, they are
the same reduction of the same rows.

![Figure 5](../figures/paperA_fig5_quantised_sizing.pdf){width=100%}

**Figure 5.** Quantised sizing, P9 and P10. (a) WireGuard's wire size against the
inner length `L` (log scale): the nine measured points, the staircase
$60 + 16\lceil L/16\rceil$ and the stipulated fixed composite `L + 56`. The measured
value lies
on the staircase at every length, so the encryptor's overhead exceeds the stipulation
by 4 to 16 B, and the excess is a function of `L mod 16` rather than a constant.
(b) `d(L)`, the wire length of IPIP-inside-WireGuard minus the reverse, for eight
lengths: +12 B when `L mod 16 = 0` and −4 B otherwise. The sign follows the staircase,
not the constant, which is why no choice of fixed overhead can make the two orders
commute. Data: 20 runs per length, identical in every run.

![Figure 6](../figures/paperA_fig6_decapsulation.pdf){width=100%}

**Figure 6.** Decapsulation and middlebox state, P13 and P14. (a) Delivery for a CE
mark written on the outer header after the NAT, by decapsulator and inner codepoint.
IPIP drops every packet when the inner packet is Not-ECT — 50 frame errors per run, a
frame error rather than a queue drop — while WireGuard and ESP deliver every packet
and leave the inner field as it was; with an inner ECT(0) mark all three deliver and
the CE propagates inward. (b) Two ESP clients behind one NAT: whichever client sends
first is delivered and the other is not, with exactly one ESP conntrack entry between
them; swapping the order swaps the loser, and ESP-in-UDP gives the NAT a usable key,
after which both clients are delivered and no ESP entry is created. Data: 20 runs per
case, 50–60 datagrams per run.

![Figure 7](../figures/paperA_fig7_replay_window.pdf){width=100%}

**Figure 7.** The replay window, P16 and P17. (a) Delivered datagrams per run for the
four P16 cases against the 2,000 sent, with the observed reorder depth printed below
each case. Delivery is complete where the reordering is shallower than the window (the
4 ms case at window 32, and WireGuard's default window) and is largely discarded where
a ~2,000-packet burst meets a 32- or 256-packet window; in every run the kernel's
delivered count equals the count a strict anti-replay filter should have accepted.
(b) P17's reinjection result: a captured packet displaced by exactly the window is
rejected and one displaced by `window − 1` is accepted, in both the legacy 32-packet
and the ESN 256-packet mode; P17a, for contrast, delivers 600 of 600 at depth 91–92
inside a 256-packet window. Data: 20 runs per case in both rounds.

Read together, the three figures are the paper's argument in pictures. Figure 5 shows
that a size-quantising layer makes the order of composition a measured quantity rather
than a matter of taste. Figure 6 shows that the same visible, unauthenticated field can
be fatal or inert depending on the decapsulator, and that a middlebox's own lookup
state can decide delivery before any field matters. Figure 7 shows that the integrity
layer's replay window is a state parameter with a sharp boundary, so reordering is a
loss mechanism that no field-class rule can express on its own.

## 6. Discussion and Threats to Validity

### 6.1 What the rule buys, and where it is incomplete

The rule predicts every case in this paper that depends only on visibility,
reachability and integrity scope, and it fails in exactly four places, each of
which it names rather than hides: quantised sizes (P9, P10), derived values (P12),
lookup-key collisions (P14) and decapsulation coupling (P13). The four additions
are not stylistic: each is a case where two implementations of the same
specification text disagree, and each is measurable in a way that a deployment
can check.

The practical reading is a checklist, not a theorem. Before placing a layer inside
another, ask: does the outer layer's length function quantise? does any value the
receiver recomputes depend on a field a middlebox may rewrite? does the receiver
key state on a field the path can collide? does the decapsulator combine an outer
value with an inner one? A "yes" to any of the four means the ordering must be
tested on the target kernel, not assumed.

### 6.2 Threats to validity

We separate four kinds: construct validity (are we measuring the intended
quantity?), internal validity (could the harness be lying?), external validity
(does it generalise?) and statistical validity (is n enough?).

#### 6.2.1 Simulator–kernel discrepancy

The Python model is byte-exact and has no queue; SimPy adds a finite drop-tail
queue; the kernel adds its own length accounting, its own padding, its own parser
and its own state machine. The three fidelities agree on every arithmetic
prediction in this paper (P1, P2, P4, P9, P10) and disagree on exactly one
delivery prediction (P5) and on the *precision* of the replay counts (P16a: the
kernel matches the reference filter with an inclusive boundary, so the arithmetic
is exact but the boundary convention is not shared with the model).

The threat is that agreement at model level is cheap: the model and SimPy were
written by the same author from the same specification as the predictions, so
their agreement is a consistency check. The kernel is the only independent
implementation here, and it is one kernel. The mitigation is structural: the
kernel result is always the one that decides the verdict, and where the model and
kernel disagreed (P5) the verdict followed the kernel. The residual threat —
a model that is wrong in the same way as the prediction, and a kernel that is
wrong in a way this harness cannot see — is not eliminated by any number of
fidelities, only by a second kernel.

#### 6.2.2 The stipulated 56-byte composite overhead

P9's comparison uses a stipulated composite of `E = 28 B` and `T = 28 B`, i.e.
56 B with no padding. The stipulation is deliberately simple and it is *low*: the
measured WireGuard overhead is `60 + 16·ceil(L/16) − L`, which for the tested
lengths is 4 to 16 B above the stipulation. Two consequences follow, and both are
in the paper rather than in a footnote. First, every P4-style claim of exact
commutation holds under the stipulation and fails under the real encryptor: the
stipulated arithmetic is a *model of the fixed-size regime*, not a model of
WireGuard. Second, P9's verdict is really a calibration result — "the stipulated
composite is low by 4 + (16·ceil(L/16) − L) bytes" — and it is reported that way.
A reader who wants a deployment number should read Table A1, not the 56.

The threat is that a different stipulation (say, 60 B) would change the *size* of
the P4/P10 discrepancy but not its sign, because the sign is set by the staircase
`R`, not by the constant. We verified this by recomputing `d(L)` with the measured
staircase in Table A2: `d(L)` is never zero for any tested `L`, whatever the
constant. The 56 therefore does not carry the conclusion; the staircase does.

#### 6.2.3 Kernel and toolchain scope

All kernel evidence comes from one WSL2 series (`6.18.54.1` for P1–P7,
`6.18.58.1` for P8–P17), one iproute2 (6.19.0), one wireguard-tools
(1.0.20250521), one nftables (1.1.6), and one NAT implementation (nftables
masquerade). The frozen two-kernel replication clause is **unmet**, and we report
it as unmet rather than redefining the clause. Consequences:

- P13's per-decapsulator table is the result most likely to move on another kernel,
  because the outer-CE/inner-Not-ECT drop is a decapsulator decision that the RFCs
  do not settle. On a kernel with the WireGuard patch reverted, the three-answer
  table would have a different shape.
- P14's first-come-first-served conntrack behaviour depends on the generic
  conntrack tracker's handling of protocol 50, which is a kernel implementation
  detail and not a standards requirement.
- P11's use of the raw-offset `pedit` form is forced by iproute2 6.19's rejection
  of the layered `udp len` field; on another iproute2 the same rewrite would be
  expressed differently, though the delivered outcome (0 %) should not change
  because the field is structural.
- The kernel is a WSL2 build. Its networking stack is standard Linux, but the
  virtualisation layer is not part of any deployed middlebox, and no physical NIC
  offload path was exercised: checksum offload was explicitly *disabled* as a gate,
  which makes the results conservative with respect to offload-induced rewrites
  rather than representative of them.

#### 6.2.4 Author identity: the predictor wrote the harness

Predictions were written by the same person who built the harness, from
specifications they knew. Confirmation therefore validates the method; the
informative results are the cases where the specification leaves behaviour open
(P13, P14, P16). This threat cannot be removed by more seeds; it can only be
reported, and it is the reason the paper's contribution is framed as *method plus
measured facts* rather than as *surprise*.

#### 6.2.5 Statistical power

Twenty paired runs per case gives roughly 1 pp resolution on a pooled delivery
proportion near 50 % and better near the extremes (P8's 0 % and 100 % outcomes are
not statistical claims at all: they are exhaustive over the runs). The
consequences: P2's delivery equality (37.98 vs 38.17 % at Linux, a 0.19 pp
difference with a paired CI of 0.33 pp) is a *non-rejection*, not an equivalence
test with a stated margin; P15's 0.38 pp difference against a 1.5 pp limit is
likewise a margin chosen in the frozen prediction rather than derived from power
analysis. With 30 paired runs, as in the companion paper, the CI on a 50 % pooled
proportion would tighten by about 18 %; that would not change any confirmation in
this paper, and it is stated so that a reader can see the design's headroom.

#### 6.2.6 Construct validity: what "delivery" means here

"Delivery" is measured at the receiving application: a datagram counts if the
receiving process read it. It is not a transport-level measure, so a datagram
dropped by a replay window is indistinguishable, in this metric, from one dropped
by a full queue. The reference replayer (P16, P17) separates the two by
reconstructing what the anti-replay filter should have accepted; that is why the
replay results are stated as "delivered equals the reference filter" rather than as
a delivery percentage. Where the reference filter is not available (P2, P5, P7),
the metric is the plain ratio and the causal claim is carried by the cause gate,
not by the number.

#### 6.2.7 Security is out of scope

Keys, nonces and tags are not evaluated; SPI and sequence values are read from
captures only to attribute packets. A rewrite that breaks delivery is a
*reliability* finding here, not a security claim: nothing in this paper says an
attacker cannot mount the same rewrite deliberately.

### 6.3 Generality

The conclusions bound these cases, not "all middleboxes", and not IPv6 (§3.4). The
field-class rule is stated at a level that should travel — visibility,
reachability, integrity scope, structure, quantisation, derivation, lookup keys,
decapsulation coupling are properties any header-processing stack has — but every
*number* in §5 is a measurement on one kernel, one NAT and one encryptor. A
deployment should re-run P9, P10, P13 and P14 on its own kernel; each of those four
cases is a minutes-long experiment, and §4.8 gives the procedure.

One variable is ours rather than measured: the middlebox's *parse depth* is defined
operationally in §3.3 as a byte offset, and this paper does not measure the parse
depth of any deployed middlebox. Honda et al. measure what middleboxes rewrite;
they do not report a depth distribution that we could reuse. Any claim of the form
"a real NAT parses this far" would therefore be unsupported here, and we make none:
P6 sweeps depth 1–3 as a parameter and reports where the predictor and the kernel
agree, which is a consistency result, not a survey.

## 7. Conclusion

Layers with fixed-size effects commute exactly, and layers that quantise size do
not. Six orderings of tunnelling, encryption and sequencing all produce 1,104 B on
the wire, while swapping IPIP and WireGuard changes the wire length by −4 or +12 B
as a function of `L mod 16`. The cross-fidelity design is what makes the contrast
visible: the first claim is confirmed identically by a Python model, a SimPy
simulator and a Linux kernel, while the second only appears once a real encryptor's
padding is in the loop.

Integrity boundaries are fragile in ways the field alone does not predict. AH
through NAT delivers 0 %, ESP and WireGuard deliver 100 %, an outer CE mark is
fatal on IPIP and inert on the other two, and an inner UDP checksum fails after a
rewrite it never authenticated. What survives is the field-class rule of §3.2 with
four named incompletenesses — quantised, derived, lookup-key,
decapsulation-coupled — plus one state parameter, the replay window, whose
boundary was measured to the packet in P17.

The study's value is as much in its failures as in its confirmations. Two
predictions are refuted and stay refuted: P5, because the compressor saw a 28-byte
header the frozen model stipulated away, and P16d, because a 33 kpps burst is
deeper than the window the prediction assumed. Reporting them costs nothing and
buys the reader the ability to calibrate the rest: 34 of 36 confirmed, Brier 0.0833
and 0.0542, on one kernel, with the two-kernel replication clause stated as unmet.
The next step is the one this study cannot take alone: the same fourteen cases
on a second kernel, from a different implementer, with the predictions frozen again
before the run.

## 8. References

Citations are given in BibTeX order of first use; DOIs are included where one
exists, and RFC numbers are given in lieu of a DOI.

```bibtex
@inproceedings{honda2011extend,
  author    = {Honda, Michio and Nishida, Yoshifumi and Raiciu, Costin and
               Greenhalgh, Adam and Handley, Mark and Tokuda, Hideyuki},
  title     = {Is it still possible to extend {TCP}?},
  booktitle = {Proceedings of the 2011 ACM SIGCOMM Conference on Internet
               Measurement (IMC)},
  year      = {2011},
  doi       = {10.1145/2068816.2068834}
}

@inproceedings{sherry2012middleboxes,
  author    = {Sherry, Justine and Hasan, Shaddi and Scott, Colin and
               Krishnamurthy, Arvind and Ratnasamy, Sylvia and Sekar, Vyas},
  title     = {Making middleboxes someone else's problem: network processing as
               a cloud service},
  booktitle = {Proceedings of ACM SIGCOMM 2012},
  year      = {2012},
  doi       = {10.1145/2377677.2377710}
}

@misc{rfc3022,
  author = {Srisuresh, Pyda and Egevang, Kjeld},
  title  = {Traditional {IP} Network Address Translator ({NAT})},
  howpublished = {RFC 3022, IETF},
  year   = {2001}
}

@misc{rfc4787,
  author = {Audet, Fran{\c{c}}ois and Jennings, Cullen},
  title  = {Network Address Translation ({NAT}) Behavioral Requirements for
            Unicast {UDP}},
  howpublished = {RFC 4787, IETF},
  year   = {2007}
}

@misc{rfc3715,
  author = {Aboba, Bernard and Dixon, William},
  title  = {{IPsec}-Network Address Translation ({NAT}) Compatibility
            Requirements},
  howpublished = {RFC 3715, IETF},
  year   = {2004}
}

@misc{rfc4302,
  author = {Kent, Stephen},
  title  = {{IP} Authentication Header},
  howpublished = {RFC 4302, IETF},
  year   = {2005}
}

@misc{rfc4303,
  author = {Kent, Stephen},
  title  = {{IP} Encapsulating Security Payload ({ESP})},
  howpublished = {RFC 4303, IETF},
  year   = {2005}
}

@misc{rfc3948,
  author = {Huttunen, Ari and Swander, Brian and Volpe, Victor and DiBurro,
            Larry and Stenberg, Markus},
  title  = {{UDP} Encapsulation of {IPsec} {ESP} Packets},
  howpublished = {RFC 3948, IETF},
  year   = {2005}
}

@misc{rfc6040,
  author = {Briscoe, Bob},
  title  = {Tunnelling of Explicit Congestion Notification},
  howpublished = {RFC 6040, IETF},
  year   = {2010}
}

@misc{rfc3168,
  author = {Ramakrishnan, Kadangode and Floyd, Sally and Black, David},
  title  = {The Addition of Explicit Congestion Notification ({ECN}) to {IP}},
  howpublished = {RFC 3168, IETF},
  year   = {2001}
}

@misc{rfc8200,
  author = {Deering, Steve and Hinden, Robert},
  title  = {Internet Protocol, Version 6 ({IPv6}) Specification},
  howpublished = {RFC 8200, IETF},
  year   = {2017}
}

@misc{rfc8201,
  author = {McCann, Jack and Deering, Steve and Mogul, Jeffrey and Hinden, Robert},
  title  = {Path {MTU} Discovery for {IP} Version 6},
  howpublished = {RFC 8201, IETF},
  year   = {2017}
}

@misc{rfc1191,
  author = {Mogul, Jeffrey and Deering, Steve},
  title  = {Path {MTU} Discovery},
  howpublished = {RFC 1191, IETF},
  year   = {1990}
}

@misc{rfc8899,
  author = {Fairhurst, Gorry and Jones, Tom and T{\"u}xen, Michael and
            R{\"u}ngeler, Ilpo and V{\"o}lker, Timo},
  title  = {Packetization Layer Path {MTU} Discovery for Datagram Transports},
  howpublished = {RFC 8899, IETF},
  year   = {2020}
}

@misc{rfc8900,
  author = {Gont, Fernando and Liu, Zhen and Huston, Geoff and Sood, Shwetha},
  title  = {{IP} Fragmentation Considered Fragile},
  howpublished = {RFC 8900, IETF},
  year   = {2020}
}

@inproceedings{herzberg2013fragmentation,
  author    = {Herzberg, Amir and Shulman, Haya},
  title     = {Fragmentation Considered Poisonous},
  booktitle = {Proceedings of the IEEE Conference on Communications and Network
               Security (CNS)},
  year      = {2013}
}

@article{zhang2014ndn,
  author  = {Zhang, Lixia and Afanasyev, Alexander and Burke, Jeffrey and
             Jacobson, Van and claffy, kc and Crowley, Patrick and Papadopoulos,
             Christos and Wang, Lan and Zhang, Beichuan},
  title   = {Named Data Networking},
  journal = {ACM SIGCOMM Computer Communication Review},
  volume  = {44},
  number  = {3},
  pages   = {66--73},
  year    = {2014},
  doi     = {10.1145/2656877.2656887}
}

@inproceedings{hoque2013nlsr,
  author    = {Hoque, A. K. M. Mahmudul and Amin, Syed Obaid and Alyyan, Adam
               and Zhang, Beichuan and Zhang, Lixia and Wang, Lan},
  title     = {{NLSR}: Named-data Link State Routing Protocol},
  booktitle = {Proceedings of the 3rd ACM SIGCOMM Workshop on Information-Centric
               Networking (ICN)},
  year      = {2013},
  doi       = {10.1145/2491224.2491231}
}

@inproceedings{pei2000fsr,
  author    = {Pei, Guangyu and Gerla, Mario and Chen, Tsu-Wei},
  title     = {Fisheye State Routing: A Routing Scheme for Ad Hoc Wireless
               Networks},
  booktitle = {Proceedings of the IEEE International Conference on Communications
               (ICC)},
  year      = {2000},
  doi       = {10.1109/ICC.2000.853066}
}

@inproceedings{milic2009fisheye,
  author    = {Mili{\'c}, Dragan and Braun, Torsten},
  title     = {Fisheye: Topology Aware Choice of Peers for Overlay Networks},
  booktitle = {Proceedings of the 34th IEEE Conference on Local Computer Networks
               (LCN)},
  year      = {2009},
  doi       = {10.1109/LCN.2009.5355168}
}

@book{day2008patterns,
  author    = {Day, John},
  title     = {Patterns in Network Architecture: A Return to Fundamentals},
  publisher = {Prentice Hall},
  year      = {2008}
}

@article{saltzer1984endtoend,
  author  = {Saltzer, Jerome H. and Reed, David P. and Clark, David D.},
  title   = {End-to-End Arguments in System Design},
  journal = {ACM Transactions on Computer Systems},
  volume  = {2},
  number  = {4},
  pages   = {277--288},
  year    = {1984},
  doi     = {10.1145/357401.357402}
}

@inproceedings{donenfeld2017wireguard,
  author    = {Donenfeld, Jason A.},
  title     = {{WireGuard}: Next Generation Kernel Network Tunnel},
  booktitle = {Proceedings of the Network and Distributed System Security
               Symposium (NDSS)},
  year      = {2017},
  doi       = {10.14722/ndss.2017.23160}
}

@article{nosek2018preregistration,
  author  = {Nosek, Brian A. and Ebersole, Charles R. and DeHaven, Alexander C.
             and Mellor, David T.},
  title   = {The Preregistration Revolution},
  journal = {Proceedings of the National Academy of Sciences},
  volume  = {115},
  number  = {11},
  pages   = {2600--2606},
  year    = {2018},
  doi     = {10.1073/pnas.1708274114}
}
```

## Appendix A. Detail tables

The two tables below are the raw P9/P10 size records. They are in an appendix
because the conclusions they carry are stated in §5.2 and drawn in Figure 5; the
tables are here so that a reader can check the arithmetic without leaving the
paper.

**Table A1. P9: WireGuard wire size against the formula $60 + 16\lceil L/16\rceil$.** Nine inner
lengths, each run 20 times with five datagrams per run; the wire size is identical in
every run of a length, so one observed value is shown per length.

| Inner length L (B) | $R(L) = 16\lceil L/16\rceil$ | Predicted wire (B) | Observed wire (B) | Observed − (L + 56) | Match |
|---|---|---|---|---|---|
| 29 | 32 | 92 | 92 | 7 | yes |
| 44 | 48 | 108 | 108 | 8 | yes |
| 60 | 64 | 124 | 124 | 8 | yes |
| 61 | 64 | 124 | 124 | 7 | yes |
| 76 | 80 | 140 | 140 | 8 | yes |
| 100 | 112 | 172 | 172 | 16 | yes |
| 1000 | 1008 | 1068 | 1068 | 12 | yes |
| 1024 | 1024 | 1084 | 1084 | 4 | yes |
| 1400 | 1408 | 1468 | 1468 | 12 | yes |

**Table A2. P10: IPIP and WireGuard nesting order.** Eight inner lengths in both
nesting orders, 20 runs each. `d(L)` is the measured wire length of
IPIP-inside-WireGuard minus the reverse, and it is never zero.

| Inner length L (B) | L mod 16 | Wire, IPIP then WG (B) | Wire, WG then IPIP (B) | Difference d(L) | Match |
|---|---|---|---|---|---|
| 64 | 0 | 156 | 144 | +12 (predicted +12) | yes |
| 65 | 1 | 156 | 160 | -4 (predicted -4) | yes |
| 76 | 12 | 156 | 160 | -4 (predicted -4) | yes |
| 77 | 13 | 172 | 160 | +12 (predicted +12) | yes |
| 79 | 15 | 172 | 160 | +12 (predicted +12) | yes |
| 100 | 4 | 188 | 192 | -4 (predicted -4) | yes |
| 1000 | 8 | 1084 | 1088 | -4 (predicted -4) | yes |
| 1008 | 0 | 1100 | 1088 | +12 (predicted +12) | yes |


