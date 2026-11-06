# Layering testbed results

**Predictions frozen at commit:** `96d59f3` (docs/layering-predictions.md,
committed before any experiment code).
**Results generated:** 3 November 2026.
**Verdict:** six of seven predictions confirmed; **P5 is refuted at the Linux
fidelity**, and the refutation is explained rather than removed.

**Scope.** This testbed measures wire size, maximum payload, delivery,
ordering, duplicates and authentication acceptance. It does **not** evaluate
cryptographic security; the AEAD is a toy with a published key. Loss is i.i.d.
and stipulated, and every overhead, MTU and seed count is stipulated, not
measured. The middlebox is a stipulated user-space rewriter, not a measured
device. Header visibility is reported separately and is not part of O.

## Verdicts

| Prediction | Model | SimPy | Linux | Overall |
|---|---|---|---|---|
| P1 — compress/encrypt size | CONFIRMED | CONFIRMED | CONFIRMED | **CONFIRMED** |
| P2 — encrypt/fragment overhead | CONFIRMED | CONFIRMED | CONFIRMED | **CONFIRMED** |
| P3 — integrity scope | CONFIRMED | CONFIRMED | CONFIRMED | **CONFIRMED** |
| P4 — fixed-overhead commutativity | CONFIRMED | CONFIRMED | CONFIRMED | **CONFIRMED** |
| P5 — compress/fragment delivery | CONFIRMED | CONFIRMED | **REFUTED** | **REFUTED** |
| P6 — survival sweep (54 cases) | CONFIRMED | CONFIRMED | CONFIRMED | **CONFIRMED** |
| P7 — structural inertness | CONFIRMED | CONFIRMED | CONFIRMED | **CONFIRMED** |

The executable-model and SimPy observations are in
`validation/layering/results/model_observations.csv` and
`simpy_observations.csv`; the Linux observations are in
`linux_observations.csv`; the mechanical checks are in `verdicts.csv`.

## What each fidelity executed

- **Executable model.** All P1–P7 cases. Stochastic cases use 2000 paired
  seeds and the deterministic loss draw
  `loss_unit(seed, datagram, fragment)`.
- **SimPy.** The same cases through per-fragment SimPy processes sharing one
  finite drop-tail queue (`simulation.link_queue.DropTailQueue`), with the
  same loss draws as the model.
- **Linux.** The same cases through two network namespaces, a veth pair, a TUN
  device in each namespace and seeded `tc netem` loss. Stochastic cases use 40
  netem seeds × 100 datagrams. TUN and veth MTUs are 40000 B so only the
  modelled `F` layer fragments; the modelled path MTU stays 1500 B.

The Linux application payload is normalised to `model_payload − 28` bytes, so
the IP/UDP datagram handed to the codec is `model_payload` bytes. Its first 28
bytes are real IP/UDP headers rather than corpus bytes. This normalisation is
recorded in the predictions file and is the direct cause of the P5 refutation
below.

**In-order delivery and duplicates.** Every executed case reports 100 %
in-order delivery and 0 % duplicates for the datagrams it delivers. This is by
construction: the data plane is single-path, there is no retransmission and
fragments are reassembled before the application sees them. Those two
observables are recorded in the CSVs but do not discriminate between
orderings; the predictions do not claim otherwise.

## P1 — compression and encryption do not commute on size

| Quantity | Model | SimPy | Linux |
|---|---:|---:|---:|
| `C -> E` text wire bytes | 17253 | 17253 | 17469 (mean) |
| `E -> C` text wire bytes | 32815 | 32815 | 32814 (mean) |
| ratio `E -> C` / `C -> E` | 1.902 | 1.902 | 1.878 |
| random-case absolute difference | 1 B | 1 B | 3 B |
| max payload, `C -> E` / `E -> C` | 2670 / 1461 | 2670 / 1461 | not exercised |

All frozen thresholds pass: the text ratio is ≥ 1.75 in the model and SimPy
and ≥ 1.50 in Linux; the random-case difference is ≤ 64 B. The max-payload
corollary is deterministic codec arithmetic and was exercised in the model and
SimPy only; the Linux checks cover wire bytes, delivery and authentication.

This is a regression prediction. Confirming it shows that the implementations
reproduce a well-known size effect, not that any ordering is a better design.

## P2 — encrypt/fragment differ in overhead, not delivery

| Quantity | Model | SimPy | Linux |
|---|---:|---:|---:|
| `E -> F` wire bytes | 12100 | 12100 | 12100 |
| `F -> E` wire bytes | 12324 | 12324 | 12324 |
| difference | 224 | 224 | 224 |
| delivery `E -> F` | 0.3935 | 0.3935 | 0.3798 |
| delivery `F -> E` | 0.3935 | 0.3935 | 0.3817 |
| paired difference (95 % CI) | 0.00 pp (0.00) | 0.00 pp (0.00) | −0.20 pp (0.33) |

The byte difference is exactly `28 × (9 − 1) = 224 B` in every fidelity. With
common loss draws the model and SimPy deliver or lose both orderings together,
so their paired difference is exactly zero. The Linux means are 0.8 pp below
the stipulated `0.9^9 = 0.38742`; the paired interval includes zero. P2 is
confirmed.

## P3 — integrity scope

| Case | Stack | AAD covers target | Visibility | Mutation | Auth acceptance | Delivery |
|---|---|---|---|---:|---:|---:|
| a | `E -> T` | `T.src_port` | visible | yes | 0 % | 0 % |
| b | `E -> T` | none | visible | yes | 100 % | 100 % |
| c | `T -> E` | none | invisible | no | 100 % | 100 % |

All three fidelities return exactly these extremes, with no intermediate
acceptance value. Case (a) is the operational shape of the known NAT/IPsec
failure: a middlebox rewrites a field the receiver authenticates, and the
receiver rejects the datagram. The testbed does not reproduce real ESP or a
real NAT; RFC 3715 and the middlebox measurements of Honda et al. (IMC 2011,
"Is it still possible to extend TCP?") are the external context, not a
validated comparison.

P3 is a research prediction. It is confirmed here for the stipulated toy AEAD
and rewriter, which is narrower than the real-world claim.

## P4 — fixed-overhead layers commute on size

All six orderings of `T`, `E`, `S` produce **1104 B** on the wire
(1024 + 28 + 28 + 24) in all three fidelities. The model and SimPy also produce
the same maximum payload, **1420 B**; the Linux harness checks wire bytes and
delivery/auth (100 % in every ordering) but does not binary-search the maximum
payload.

Visibility, recorded separately and **not** a failure criterion:

| Ordering | `T.src_port` visible | `S.seq` visible |
|---|---|---|
| `T -> E -> S` | no (inside E) | yes |
| `T -> S -> E` | no (inside E) | no (inside E) |
| `E -> T -> S` | yes | yes |
| `E -> S -> T` | yes | yes |
| `S -> T -> E` | no (inside E) | no (inside E) |
| `S -> E -> T` | yes | no (inside E) |

P4 is a regression prediction and is confirmed.

## P5 — compress-then-fragment versus fragment-then-compress (refuted at Linux)

Frozen prediction: `n1 = 3` for `C -> F` and `n2 = 6` for `F -> C`, so
delivery should be `0.9^3 = 0.729` versus `0.9^6 = 0.531441`, a **19.7559 pp**
difference; control (1000 text bytes) has `n1 = n2 = 1` and no difference.

| Fidelity | `n1` | `n2` | `C -> F` | `F -> C` | difference | CI95 |
|---|---:|---:|---:|---:|---:|---:|
| Model | 3 | 6 | 0.7375 | 0.5350 | +20.25 pp | ±1.76 |
| SimPy | 3 | 6 | 0.7375 | 0.5350 | +20.25 pp | ±1.76 |
| Linux | **4** | 6 | 0.6428 | 0.5192 | **+12.35 pp** | ±1.13 |
| Frozen expectation | 3 | 6 | 0.7290 | 0.5314 | +19.76 pp | — |

The model and SimPy confirm the prediction. The Linux run does **not**: its
difference is 12.35 pp, outside the frozen 4.0 pp margin, and its `C -> F`
delivery is 8.6 pp below 0.729. Under the frozen rules this is a
**refutation**, and it is reported as one. Nothing in the model, scenario or
tolerance was changed to remove it.

### Why Linux differs

The Linux `C -> F` datagram has four fragments, not three. The Linux codec
compresses the 8192-byte IP datagram, whose first 28 bytes are the real
IPv4/UDP header and whose remaining 8164 bytes are `corpus[28:]`. With stock
zlib 1.3.1 that packet compresses to about 4507 B, above the three-fragment
boundary of `3 × 1492 = 4476 B`. The model compresses the pure corpus, which is
4395 B under the Windows zlib-ng build and 4458 B under stock zlib; both fit in
three fragments. The representation difference, not the `(1−p)^n` arithmetic,
changes `n1`.

Recomputing the Linux expectation with its observed fragment count gives
`0.9^4 − 0.9^6 = 12.47 pp`; Linux measures 12.35 pp, and each delivery estimate
is within 1.4 pp of the corresponding `n = 4` / `n = 6` formula. The control
case measured 0.8880 and 0.8885 for the two orderings (difference −0.05 pp),
within its frozen tolerance.

### What the refutation does and does not show

It shows that a pre-registered cross-fidelity scenario can fail to be the same
scenario: feeding real IP/UDP headers into a compressor moved a payload across
a fragment boundary. It does not show that compress-then-fragment loses its
delivery advantage; with the Linux fragment count the advantage is 12.47 pp,
which the Linux run reproduces. The predictions file is not edited; a dated
addendum records the discrepancy and the zlib-variant caveat.

## P6 — the survival condition over 54 cases

All six orderings of `T`, `E`, `S` were crossed with two targets
(`T.src_port`, `S.seq`), middlebox parser depth 1–3, and AAD scope either none
or the target where that is a valid configuration: **54 cases**, zero
tolerance.

Across the 54 cases the formal predictor declares 36 visible and 18 invisible
targets, 40 reachable and 14 unreachable, 32 rewrites applied, 16
authentication failures and 16 delivery failures. The model, SimPy and Linux
runs match the predictor on visibility, mutation, acceptance and delivery in
**every case** (0 mismatches). Examples from the Linux run:

- `T -> E -> S`, target `T.src_port`, depth 2, no AAD: invisible at the wire,
  no mutation, 100 % acceptance.
- `E -> T -> S`, target `S.seq`, depth 1: reachable and visible, rewritten,
  100 % acceptance (unauthenticated).
- `S -> E -> T`, target `T.src_port`, depth 3, AAD protect: visible,
  authenticated, 0 % acceptance.
- `E -> T -> S`, target `T.src_port`, depth 1: the field is visible but deeper
  than the parser, so it is not rewritten and acceptance is 100 %.

P6 is the research core: it tests the combined condition (visibility,
reachability, integrity scope) rather than one arithmetic consequence. It is
confirmed for the stipulated rewriter and AEAD. Because all three fidelities
share the codec, and because the predictor and the relay encode the *same*
visible/reachable/authenticated rule, the zero-mismatch result is a
**consistency check**: it shows that the implementation computes the rule it was
written to compute. It is **not** evidence that the rule matches real
middleboxes or real AEAD. The middlebox is a user-space rewriter with a
scripted parser depth and the AEAD is a toy with a published key, so P6 bounds
the internal logic, not deployed behaviour. Ground truth against WireGuard or
ESP and Linux NAT is an open next step, not a result.

## P7 — structural inertness

Stack `T -> F`, 4096 random bytes, three fragments, no loss. All three targets
are visible and unauthenticated, so the integrity-scope rule alone predicts
survival.

| Rewrite target | Auth acceptance | Delivery (all fidelities) |
|---|---:|---:|
| `F.length` → `0x0009` | 100 % | **0 %** |
| `T.udp_len` → `0x0009` | 100 % | **0 %** |
| `T.src_port` → `0x9C40` (inert) | 100 % | **100 %** |

The two length-bearing fields break reassembly or the tunnel length check even
though no integrity scope covers them. P7 is confirmed at all three fidelities,
with zero tolerance. It is the non-obvious part of the condition: excluding a
field from authentication is not sufficient for safe rewriting if the field
carries framing structure.

## What this result does and does not show

- P1, P2, P4 and P5 are arithmetic regression tests. Confirming them shows that
  the three implementations reproduce the specified arithmetic; it is not
  evidence about deployed networks.
- P3, P6 and P7 are the research contribution. They support the formal
  survival condition for a stipulated middlebox with a fixed parser depth, a
  toy AEAD and three implementations of the same codec. They do not establish
  the condition for real middleboxes, real ESP, or arbitrary protocols.
- P3's case (a) has external ground truth in the NAT/IPsec literature, but the
  testbed does not reproduce ESP or a real NAT; the external literature is
  context, not a validation of this implementation.
- The Linux fidelity uses the same codec as the Python fidelities. Agreement
  demonstrates that the codec behaves the same under kernel loss and real TUN
  I/O; it does not provide an independent implementation of layer semantics.
- No security property is evaluated. The compress-then-encrypt information
  leak, key secrecy, nonce reuse and tag forgery are out of scope.
- Loss is i.i.d. per fragment and stipulated. There is no wireless PHY/MAC
  model, no congestion control and no cross traffic.
- The Linux `C -> F` fragment-count shift shows a reproducibility hazard:
  compression is implementation-dependent (zlib-ng versus stock zlib) and
  payload normalisation can change a discrete fragment count. Any future
  cross-fidelity prediction with compressible data near a fragment boundary
  must state the encoded input, not just the application payload.

## Limitations

- Security properties are not evaluated.
- Loss is i.i.d. and stipulated; results do not transfer to wireless or
  congested networks.
- Overheads, MTU, loss and seed counts are stipulated. The only measured
  calibration values are the corpus compression ratios recorded in the
  predictions file.
- The middlebox is a user-space rewriter with a fixed parser depth; it is not
  a measured middlebox.
- P1 and P4 max-payload corollaries were exercised only in the model and
  SimPy; the Linux runs check wire bytes and delivery instead.
- P5 is refuted at Linux, as reported above.
- The ns-3 stretch goal (M6) was not attempted; no ns-3 tree was available in
  the execution environment.

## Reproduction

From the repository root:

```powershell
py -3 -m validation.layering.run_model  --output validation\layering\results\model_observations.csv
py -3 -m validation.layering.run_simpy  --output validation\layering\results\simpy_observations.csv
py -3 -m validation.layering.run_linux  --output validation\layering\results\linux_observations.csv
py -3 -m validation.layering.report --model validation\layering\results\model_observations.csv --simpy validation\layering\results\simpy_observations.csv --linux validation\layering\results\linux_observations.csv --verdicts validation\layering\results\verdicts.csv --doc docs\layering-results.md
```

The full guide is in [REPLICATION.md](../REPLICATION.md); the Linux privileges
and topology are in
[validation/linux_layering/README.md](../validation/linux_layering/README.md).
The report command writes its mechanical check tables to
`docs/layering-results.generated.md` when this hand-maintained narrative
already exists, so a later run cannot silently overwrite the refutation
explanation.

Environment used for the committed results: Windows 11, Python 3.14.7 with
zlib-ng 1.3.1 for the model and SimPy; WSL2 Ubuntu, kernel
6.18.54.1-microsoft-standard-WSL2, Python 3.14.4 with stock zlib 1.3.1 for the
Linux data plane; 40 netem seeds (1–40) × 100 datagrams for the stochastic
Linux cases.

## Addendum

See the 2026-11-03 addendum in
[docs/layering-predictions.md](layering-predictions.md). It records the P5
fragment-count and zlib-variant discrepancy without changing the frozen
prediction or tolerances.
