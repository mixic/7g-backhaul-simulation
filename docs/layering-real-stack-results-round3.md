# Layering real-stack results, round 3 (P17)

**Predictions frozen at commit:** `285c8e9`
(`docs/layering-real-stack-predictions-round3.md`, committed before any round-3
harness code existed; never edited afterwards).
**Harness:** `validation/round3/` (rate-limited ESP, raw AF_PACKET capture and
reinjection, legacy/ESN mode recording).
**Protocol:** the frozen 20 runs per case; five traffic cases plus the mode
check = **100 runs**, all on `6.18.58.1-microsoft-standard-WSL2`.
**Raw output:** `validation/round3/results/observations.csv`, `verdicts.csv`,
`summary.md`, `calibration.md`, `environment.txt`, `errors.txt` (empty).
**Verdict summary:** **P17a-P17f all CONFIRMED; Brier 0.0542 over six scored
predictions; no INVALID, INCONCLUSIVE or NOT RUN.**

## What round 3 was for

Round 2 left P16d refuted at a depth of about 2000 and could not hit the
strict/inclusive replay-window boundary exactly. It also recorded, but did not
separate, the fact that `replay-window 256` silently became an ESN SA while
`replay-window 32` stayed legacy. Round 3 tests the three loose ends directly:

1. a rate-limited sender whose depth is gated in [64, 200];
2. captured-and-reinjected ESP at displacement `window - 1` and `window`;
3. the legacy/ESN mode recorded in every reinjection run.

## Environment

| Item | Value |
|---|---|
| Kernel | `6.18.58.1-microsoft-standard-WSL2` |
| Root | `wsl -u root`, uid 0 |
| Python | 3.14.4 |
| iproute2 | 6.19.0 |
| nftables | 1.1.6 |
| Predictions commit | `285c8e9` |
| Runs | 100 (5 cases x 20; P17f is scored from the same runs) |

This is the **same kernel** as round 2. Round 3 is a follow-up on one kernel, not
a second-kernel replication; M3 is separate and still NOT RUN.

## P17a: rate-limited depth inside the window

`P17a` uses ESP tunnel mode with a 256-packet window (recorded as ESN), 100 ms
netem delay, 25 % reorder, 600 datagrams at 1 ms spacing.

| Metric | Result (20 runs) |
|---|---:|
| Depth | 91-92 (mean 91.95) |
| Depth gate [64, 200] | 20/20 pass |
| Sent | 600 per run |
| Delivered | 600 per run |
| Reference filter accepted | 600 per run |
| Delivery matches reference | 20/20 |
| Sequence errors | 0 per run |

The depth is inside the pre-registered band by a wide margin, and a window of
256 is wider than the depth. This is the direct check that P16d's refutation was
about the **depth**, not about the 256-packet window as such: when the depth is
91-92, the same window delivers every packet.

## P17b-P17e: exact boundary

Each run captures at least 120 (legacy) or 320 (ESN) ESP packets with the
original packets dropped at the receiver ingress, selects the highest sequence
`max` and the packet at `max - offset`, then reinjects `[max, target]`.

| Case | Mode | Offset | Delivered (expected) | Reference (expected) | Result |
|---|---:|---:|---:|---:|---|
| P17b | legacy window 32 | 32 | 1 (1) | 1 (1) | CONFIRMED |
| P17c | legacy window 32 | 31 | 2 (2) | 2 (2) | CONFIRMED |
| P17d | ESN window 256 | 256 | 1 (1) | 1 (1) | CONFIRMED |
| P17e | ESN window 256 | 255 | 2 (2) | 2 (2) | CONFIRMED |

The result is exact in all 20 runs per case: a packet at displacement equal to
the window is rejected, and a packet at displacement one less is accepted, in
both the legacy and the ESN context. The reference filter (strict `< window`)
matches the kernel in every run. The original-delivery gate was 0 received
during capture in every run, so the reinjection saw a fresh replay state; the
capture gate passed in every run.

## P17f: mode recording

`ip xfrm state` was read in every P17b-P17e run:

| Configured window | Effective context | Runs |
|---:|---|---:|
| 32 | legacy (`replay-window 32`, no ESN context) | 20/20 P17b, 20/20 P17c |
| 256 | ESN (`anti-replay esn context`, bitmap-length 8) | 20/20 P17d, 20/20 P17e |

The mode is recorded, not inferred. On this kernel/iproute2, a 256-packet
replay window is an ESN SA; that is why round 2's P16d is an ESN result.

## Calibration

| Prediction | Credence | Outcome | Brier |
|---|---:|---:|---:|
| P17a | 0.75 | 1 | 0.0625 |
| P17b | 0.80 | 1 | 0.0400 |
| P17c | 0.80 | 1 | 0.0400 |
| P17d | 0.70 | 1 | 0.0900 |
| P17e | 0.70 | 1 | 0.0900 |
| P17f | 0.95 | 1 | 0.0025 |
| **Total** | | **6/6** | **0.0542** |

The credences were cautious on the two ESN boundary cases (0.70) and on the
rate-limited depth (0.75); all three came in. The mode mapping was the most
confident prediction (0.95) and held in all 80 reinjection runs. A zero-refutation
round is a limitation as well as a result: the cases were designed to isolate the
mechanism, so they are not a random sample of kernels.

## Dispositions and gates

- Every case is CONFIRMED. No case is REFUTED, INCONCLUSIVE, INVALID or NOT RUN.
- Gates: warm-up, offload disabled, capture, original-delivery drop, depth
  (P17a), and mode recording all passed in every run.
- The raw capture and reinjection are a controlled harness action on packets the
  harness generated; this is not a replay attack and no cryptographic security is
  claimed.

## Interpretation limits

- **One kernel.** Same kernel as round 2; not a second-kernel replication.
- **One ESP implementation.** The boundary is Linux xfrm ESP, one iproute2
  version, one veth topology.
- **Reinjection is not multipath.** The displacement is exact and harness-made;
  netem is used only in P17a.
- **No security claim.** Keys, SPIs and sequence numbers are test values.
- **The boundary is a single-packet test.** It establishes the strict/inclusive
  reading at one alignment; it does not sweep every window size.

## Reproduce

```bash
python3 -m validation.round3.run --probe
python3 -m validation.round3.run --dry-run --only P17a
python3 -m validation.round3.run --runs 20
python3 -m unittest tests.test_round3 -q
```

The frozen predictions are not edited. If a future run disagrees, add a dated
addendum here; do not change `docs/layering-real-stack-predictions-round3.md`.

## Artifacts

| Artifact | Path |
|---|---|
| Frozen predictions | [`docs/layering-real-stack-predictions-round3.md`](layering-real-stack-predictions-round3.md) |
| Harness | [`validation/round3/`](../validation/round3/) |
| Raw capture/inject | [`validation/round3/raw.py`](../validation/round3/raw.py) |
| Observations / verdicts | [`validation/round3/results/observations.csv`](../validation/round3/results/observations.csv), [`verdicts.csv`](../validation/round3/results/verdicts.csv) |
| Calibration / environment | [`calibration.md`](../validation/round3/results/calibration.md), [`environment.txt`](../validation/round3/results/environment.txt) |
| Tests | [`tests/test_round3.py`](../tests/test_round3.py) |
