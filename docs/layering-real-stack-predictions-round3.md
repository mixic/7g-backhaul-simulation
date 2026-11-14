# Layering real-stack predictions, round 3 (P17)

**Status: FROZEN.** This file is committed before the round-3 harness exists.
Constants, thresholds and credences below are the protocol; the predictions file
is not edited after the freeze commit. Results go in
[`layering-real-stack-results-round3.md`](layering-real-stack-results-round3.md)
with a dated addendum for any correction.

Round 2 left three things untested:

1. P16d's refutation was caused by a **depth** of about 2000, not by the
   replay-window mechanism. A rate-limited sender should place the depth inside
   a pre-registered band and show that a window larger than the depth delivers
   every packet.
2. The strict/inclusive boundary (`max - seq` equal to the window) was never hit
   exactly, because netem produced a random depth.
3. `replay-window 256` silently became an **ESN** SA on this kernel/iproute2,
   while a 32-packet window stayed legacy. The boundary should be recorded
   separately for each mode.

This round tests those three things. It is a follow-up, not a new field-class
claim. The prior-art log for the surrounding ECN/NAT behaviour is
[`prior-art-p13-p14.md`](prior-art-p13-p14.md); P17 is about replay semantics,
not ECN.

## 1. Common setup

- Four namespaces from `validation.round2.net.Topology` (no NAT), one ESP
  tunnel-mode SA pair, inner `10.201.0.1 -> 10.201.0.2`, UDP port 9999.
- One key per SA pair; both ends identical.
- Warm-up uses one probe packet before the impairment, so the SA is live.
- The receiver counts decapsulated UDP datagrams; the raw capture is on `vN2`
  egress in the router namespace.
- A `tc` ingress drop on the receiver interface (`vB2`) prevents the original
  packets from reaching xfrm; the drop is removed before reinjection. The
  original-delivery gate requires 0 received datagrams during capture.
- Every run is fresh: fresh namespaces, fresh SA, fresh keys, fresh counters.
- 20 runs per case, as in rounds 1 and 2.

## 2. P17a: rate-limited depth inside a window

**Claim.** With a sender paced at 1 ms per datagram (1000 pps), 100 ms netem
delay and 25 % reorder, the depth is in **[64, 200]**, the 256-packet ESN window
is wider than the depth, and every datagram is delivered.

**Protocol.**

| Item | Value |
|---|---|
| Stack | ESP tunnel mode |
| Window | 256 (the kernel records ESN; see P17f) |
| Impairment | `netem delay 100ms reorder 25%`, limit 100000 |
| Datagrams | 600 |
| Sender interval | 1.0 ms (1000 pps) |
| Depth gate | 64 <= depth <= 200 |
| Predicted delivery | 600/600 |
| Predicted reference | 600/600 |
| Predicted seq errors | 0 |

**Verdict.** CONFIRMED iff the depth gate passes, `sent >= 590`,
`delivered == sent`, `reference_accepted == sent`, and
`delivery_matches_reference = 1`. REFUTED iff the depth gate passes but
delivery or reference is below `sent`. INVALID if the depth gate fails, the
capture is short, the warm-up fails, or a setup error occurs. Credence **0.75**.

## 3. P17b: legacy boundary, displacement = window

**Claim.** With a legacy 32-packet window, a packet whose displacement is
exactly 32 (`max - seq = 32`) is rejected; a packet at displacement 31 is
accepted.

**Protocol.** Capture at least 80 ESP packets with the ingress drop in place.
Select the highest captured sequence `max` and the packet at `max - 32`.
Reinject in the order `[max, max - 32]`. The receiver must count **1** of the
2 injected datagrams. The reference filter (strict `< window`) must also count
1.

**Verdict.** CONFIRMED iff the original-delivery gate is 0, both frames exist,
the mode is legacy, `delivered == 1`, and `reference_accepted == 1`. REFUTED iff
`delivered == 2` or `reference_accepted == 2`. INVALID on a gate failure.
Credence **0.80**.

## 4. P17c: legacy boundary, displacement = window - 1

**Claim.** With a legacy 32-packet window, a packet whose displacement is
exactly 31 (`max - seq = 31`) is accepted.

**Protocol.** Same capture, but select `max` and `max - 31`; reinject
`[max, max - 31]`. The receiver must count **2** of 2.

**Verdict.** CONFIRMED iff the original-delivery gate is 0, both frames exist,
the mode is legacy, `delivered == 2`, and `reference_accepted == 2`. REFUTED iff
`delivered < 2` or `reference_accepted < 2`. INVALID on a gate failure.
Credence **0.80**.

## 5. P17d: ESN boundary, displacement = window

**Claim.** With the 256-packet ESN window, a packet whose displacement is
exactly 256 is rejected.

**Protocol.** Capture at least 300 ESP packets; select `max` and
`max - 256`; reinject `[max, max - 256]`. The receiver must count **1** of 2.
The mode must be ESN.

**Verdict.** Same structure as P17b. Credence **0.70**.

## 6. P17e: ESN boundary, displacement = window - 1

**Claim.** With the 256-packet ESN window, a packet whose displacement is
exactly 255 is accepted.

**Protocol.** Capture at least 300 ESP packets; select `max` and
`max - 255`; reinject `[max, max - 255]`. The receiver must count **2** of 2.
The mode must be ESN.

**Verdict.** Same structure as P17c. Credence **0.70**.

## 7. P17f: mode recorded explicitly

**Claim.** On this kernel/iproute2, `replay-window 32` creates a **legacy**
anti-replay context, and `replay-window 256` creates an **ESN** context
(`anti-replay esn context`, bitmap-length 8). The mode is recorded in every
P17b-P17e run, not inferred.

**Verdict.** CONFIRMED iff every P17b-P17e run records the expected mode
(legacy for 32, ESN for 256). REFUTED if any run records the other mode.
INVALID if the mode cannot be read. Credence **0.95**.

## 8. Credences and Brier terms

| Prediction | Credence |
|---|---:|
| P17a | 0.75 |
| P17b | 0.80 |
| P17c | 0.80 |
| P17d | 0.70 |
| P17e | 0.70 |
| P17f | 0.95 |

The Brier score is the mean of `(credence - outcome)^2` over the six scored
predictions; INVALID and NOT RUN are unscored. A refusal to run is not a
confirmation.

## 9. What this does not test

- Other kernels, other iproute2 versions, other NICs or other ESP
  implementations. The mode mapping is this host's.
- ECN, NAT, WireGuard or fragmentation; those are round 2.
- A real multipath path. The reordering is netem or an explicit reinjection,
  not a production multipath scheduler.
- Security. The keys and SPIs are test values; no cryptographic strength is
  claimed.
- A user-space replay attack. The reinjection is a controlled harness action on
  packets the harness itself generated.

## 10. Reporting

Every case gets one disposition: CONFIRMED, REFUTED, INCONCLUSIVE, INVALID or
NOT RUN. The raw observations, verdicts, environment and calibration are written
under `validation/round3/results/`. The results document reports every
disposition, including a refutation, and does not edit this file.
