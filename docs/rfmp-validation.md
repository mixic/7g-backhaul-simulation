# RFMP v0.1 cross-validation: role transitions in ns-3

This document reports the external cross-check of the role-fluid paradigm's
first concrete artifact: the RFMP v0.1 protocol specification
([rfmp-protocol.md](rfmp-protocol.md)) implemented twice — as a Python
discrete-event reference and as an ns-3.49 packet-level reference — and compared
seed by seed on the role-transition scenario RT1.

**Result:** all five acceptance criteria fixed before the run pass, with margins
three orders of magnitude below their thresholds. The largest discrepancy across
nine metrics is 1.6 µs (mean delivery delay). The protocol specification is
therefore implementable without ambiguity, and no implementation detail
(queueing, event ordering, timer granularity) silently changes the behaviour it
specifies.

## 1. What is being validated, and what is not

Validated:

- the sender's smooth weighted round-robin scheduling over heterogeneous paths
  with utilisation feedback;
- per-link queueing and serialization, including the MTU-derived overhead on a
  1200-byte medium;
- the receiver's reordering buffer, duplicate suppression and deadline/late-drop
  rule;
- the role-transition procedure: a 100 ms overlap around each epoch boundary,
  duplicate suppression by sequence number, and no stop-and-wait handshake;
- the aggregate consequences of a transition: in-order release gap, reordering
  stall, and duplicate burst.

Not validated (stated so that the claim is not over-read):

- **the role decision policy.** Roles in RT1 are scripted (`forward` on
  [0,6) s, `serve` on [6,12) s, `forward` afterwards). This experiment validates
  the *mechanics* of a transition, not whether the local role-selection rule
  decides correctly. That controller is evaluated separately in
  [role-fluid-paradigm.md](role-fluid-paradigm.md).
- the ACK clock and the failure detector: no path fails and no ACK is required
  for scheduling in RT1. Both are implemented and unit-tested in the Python
  reference only.
- congestion control: the offered rate is constant and no window is closed.
- packet splitting at a medium boundary: the boundary rule is applied as a
  per-packet serialization overhead, as in the role-fluid model.
- wireless physics: both implementations use point-to-point links.

## 2. Implementations and shared specification

| | Python reference | ns-3 reference |
| --- | --- | --- |
| File | [`simulation/rfmp.py`](../simulation/rfmp.py) | [`validation/ns3/rfmp-role-transition.cc`](../validation/ns3/rfmp-role-transition.cc) |
| Model | discrete-event loop over emission, queueing, forwarding and release | packet-level UDP over point-to-point links |
| Scheduling | smooth weighted round robin, weights every 100 ms over a 500 ms utilisation window | same rule, same window, same constants |
| Jitter | hash of `(seed, packet index)` | same hash, same constants |
| Queue | `DropTailQueue(100)` per link | device drop-tail `TxQueue` 100 p, ns-3's default FqCoDel disc removed |
| Forwarding | in-process application relaying | application-level relay on the role-fluid node |

The seed-keyed jitter is deliberate: both implementations compute the same
emission schedule for a given seed, so the comparison is genuinely paired rather
than two independent random draws with the same label.

The only modelling substitution is on the 1200-byte-MTU path: the Python model
applies a 1.25× serialization factor, while ns-3 is configured at 6.4 Mbit/s so
that `1228 B / 6.4 Mbit/s` equals the Python service time. This is documented in
the program header and in §1 above.

## 3. Scenario RT1

Topology: origin `O`, role-fluid node `X`, demand node `D`. Paths from `O` to
`X`: fibre (20 Mbit/s, 4 ms, MTU 9000) and satellite (8 Mbit/s, 20 ms, MTU
1200). Edge link `X–D`: 30 Mbit/s, 2 ms. Demand is a constant 12 Mbit/s
(1200-byte packets every 0.8 ms) for 20 s.

Role epochs: `forward` on [0, 6) s, `serve` on [6, 12) s, `forward` on
[12, 20) s. Each boundary has a 100 ms overlap (50 ms head start for the
incoming source, 50 ms tail for the outgoing one).

## 4. Results (5 paired seeds, means)

### 4.1 RT1 — warm-cache transition

| Metric | ns-3.49 | Python | Δ (ns-3 − Python) | Criterion | Verdict |
| --- | ---: | ---: | ---: | --- | --- |
| In-order delivery (%) | 100.0000 | 100.0000 | 0.0000 | ≤ 0.5 pp | **PASS** |
| Duplicate rate (%) | 0.9901 | 0.9901 | 0.0000 | ≤ 0.1 pp | **PASS** |
| Handoff duplicate rate (%) | 0.9022 | 0.9022 | 0.0000 | — | informational |
| Transition gap at 6 s (ms) | 0.7945 | 0.7942 | +0.0003 | ≤ 5 ms | **PASS** |
| Transition gap at 12 s (ms) | 0.8843 | 0.8845 | −0.0002 | ≤ 5 ms | **PASS** |
| Reorder stall, p95 (ms) | 16.3128 | 16.3122 | +0.0006 | ≤ 15 % rel. | **PASS** |
| Reorder stall, max (ms) | 16.8780 | 16.8776 | +0.0004 | — | informational |
| Mean delivery delay (ms) | 15.5617 | 15.5601 | +0.0016 | — | informational |
| Late drops (%) | 0.0000 | 0.0000 | 0.0000 | — | informational |

### 4.2 RT2 — cold-cache transition

RT2 starts `X` with a cold cache: during the serve epoch its hit ratio ramps
linearly from 0 to 1 over 8 s, hits are sourced by `X` and misses by `O`, and the
assignment is exclusive (no overlap, no duplicates).

| Metric | ns-3.49 | Python | Δ (ns-3 − Python) | Criterion | Verdict |
| --- | ---: | ---: | ---: | --- | --- |
| In-order delivery (%) | 100.0000 | 100.0000 | 0.0000 | ≤ 0.5 pp | **PASS** |
| Duplicate rate (%) | 0.0000 | 0.0000 | 0.0000 | ≤ 0.1 pp | **PASS** |
| Served fraction (%) | 37.5167 | 37.5167 | 0.0000 | ≤ 0.5 pp | **PASS** |
| Transition gap at 6 s (ms) | 5.7377 | 5.7374 | +0.0002 | ≤ 5 ms | **PASS** |
| Transition gap at 12 s (ms) | 10.6507 | 10.6502 | +0.0004 | ≤ 5 ms | **PASS** |
| Reorder stall, p95 (ms) | 16.3809 | 16.3776 | +0.0033 | ≤ 15 % rel. | **PASS** |
| Reorder stall, max (ms) | 21.0778 | 21.0706 | +0.0072 | — | informational |
| Mean delivery delay (ms) | 20.2753 | 20.2721 | +0.0033 | — | informational |
| Late drops (%) | 0.0000 | 0.0000 | 0.0000 | — | informational |

A cold cache changes what a transition *is*. The served fraction is 37.52 %, the
exact mean of the linear warm-up over the 6 s epoch (3/8), and identical to four
decimals in both implementations. The transition stops being a switch and
becomes a ramp: 62.5 % of the epoch still transits the satellite path, which is
why mean delivery delay rises to 20.3 ms (RT1: 15.6 ms) and the in-order gap
grows to 5.7 ms at the start and 10.7 ms at the end of the epoch. The maximum
reorder stall rises to 21.1 ms, bounded by the slowest path rather than by the
handoff window. Duplicates are zero because exclusive sourcing needs no overlap
window: the overlap in RT1 is a cost that a cache-aware transition does not pay.

## 5. What the numbers show

1. **A warm-cache transition does not interrupt the stream.** The in-order release gap at
   both boundaries is ≈ 0.8 ms, which is exactly one packet interval: the stream
   never pauses. The spec predicted a zero gap; the measured value is the
   inter-packet spacing, not an interruption.
2. **The cost of the transition is a stall, not a gap.** Reordering stall rises
   to a p95 of 16.3 ms — the latency difference between the two paths
   (20 − 4 ms) — and a maximum of 16.9 ms, below the old path's 20 ms drain
   time. The spec predicted exactly this bound, and the measurement lands inside
   it.
3. **Overlap duplicates are exactly accounted for.** Two 100 ms overlaps at
   12 Mbit/s produce 250 duplicate arrivals out of 25 250 (0.99 %); the
   receiver suppresses all of them, so delivery stays at 100 %. The handoff
   window accounts for 0.90 % of arrivals. Both implementations agree to the
   fourth decimal.
4. **Implementation detail does not leak into behaviour.** The two
   implementations differ in event scheduling, socket buffering, queue
   implementation and language; the residuals are microseconds. That is the
   useful content of a specification cross-check: it bounds the ambiguity of the
   written protocol, not the realism of the underlying model.

## 6. Threats to validity

- **Agreement is partly by construction.** Both implementations share one
  specification, one set of constants and one jitter hash. The check therefore
  proves the specification is unambiguous and implementable, not that its
  assumptions match a real network. Realism questions (wireless PHY, congestion
  control, cache hit ratios) are untouched.
- **The role decision is out of the loop.** Scripted epochs validate transition
  mechanics. They say nothing about whether a node *should* switch. That is a
  different experiment, and it currently lives in the role-fluid model, where
  the local rule does not yet beat a static design.
- **The cache is a linear warm-up.** No eviction, no popularity curve, no
  request-level accounting: RT2's hit ratio is a stipulated ramp, so the
  measured 37.5 % served fraction validates the *implementation* of that rule,
  not the realism of the curve.
- **No failure, no loss, no congestion.** Failure detection, path removal and
  re-addition are specified but not exercised here.
- **One topology, one rate.** No sensitivity analysis over path asymmetry,
  overlap length or packet size.
- **Substitution on one path.** The 1.25× MTU overhead is a serialization factor
  rather than actual fragmentation and reassembly.

## 7. Reproduction

Requirements: Python 3.10+, and Linux or WSL with a C++17 toolchain, cmake and
an ns-3.49 tree (see [validation/ns3/README.md](../validation/ns3/README.md)).

```bash
# 1. ns-3 reference, 5 seeds, both scenarios (RT1 and RT2)
NS3_DIR=~/ns-3-dev SEEDS=5 ./validation/ns3/run-rfmp.sh
#    -> output/validation/rfmp_ns3.csv (10 rows)

# 2. Python reference, normalization and paired comparison
py -3 -m validation.run_rfmp_experiment \
    --ns3-csv output/validation/rfmp_ns3.csv \
    --seeds 1 2 3 4 5 --output-dir output/validation
#    -> output/validation/rfmp_comparison.csv
```

Published artifacts: [`figures/rfmp_ns3_replicates.csv`](../figures/rfmp_ns3_replicates.csv),
[`figures/rfmp_python_replicates.csv`](../figures/rfmp_python_replicates.csv) and
[`figures/rfmp_comparison.csv`](../figures/rfmp_comparison.csv).

## 8. Next steps (v0.2)

1. **Inject path failure** and validate the failure detector and path manager —
   the parts of the spec this round did not exercise.
2. **Close the loop:** let the role-selection controller drive the epochs
   instead of scripting them, and compare the resulting transition pattern
   between implementations.
3. **Real boundary splitting:** fragment and reassemble at an MTU change and
   validate the reflection queue, replacing the serialization substitution.
4. **Wireless medium:** replace one point-to-point path with an ns-3 Wi-Fi or
   mmWave link, so the transport meets a PHY model.
5. **MPTCP baseline:** run the same workload against a kernel or ns-3 MPTCP
   stack to measure the multipath claim rather than model it.

Each is tracked by the validation-challenge issue template, so results are added
to this document rather than scattered across the repository.
