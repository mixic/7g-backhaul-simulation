# External cross-validation of the transport model (ns-3 scenario S1)

This document reports the first external validation of the simulator: the same
handover-and-multipath scenario is implemented twice — once with this
repository's transport model and once as an independent packet-level
implementation in [ns-3.49](https://www.nsnam.org/) — and the resulting metrics
are compared seed by seed.

The short version:

- In the non-overloaded regime the repository's transport abstraction agrees
  with ns-3 to within 0.02 % on delivery, goodput, one-way delay and path
  share. That part of the model is externally validated for this scenario.
- In the handover regime, where all traffic falls back to a slower path, the
  queue-free abstraction **over-reported delivery by 6.5 percentage points and
  under-reported the 95th-percentile one-way delay by a factor of 5.7**.
- The corrected model (a bounded FIFO drop-tail queue per link, now shipped in
  [`simulation/link_queue.py`](../simulation/link_queue.py)) matches ns-3 to
  within 0.01 percentage points of delivery and 1.8 % of the p95 delay.

Everything needed to reproduce these numbers is in this repository.

## 1. Why this scenario

The critique that motivated this work was that the simulator had never been
compared with a high-fidelity simulator, so the fidelity of its link, queue and
scheduling models was an open question. The suggested first step was a simple
handover or multipath-scheduling case. Scenario S1 is deliberately minimal so
that every difference between the two implementations can be attributed to a
modelling decision rather than to scenario complexity.

## 2. Shared scenario definition

The scenario is specified once in [`validation/scenario_s1.py`](../validation/scenario_s1.py)
and mirrored verbatim in [`validation/ns3/s1-multipath-handover.cc`](../validation/ns3/s1-multipath-handover.cc).

| Item | Value |
| --- | --- |
| Duration | 20 s |
| Application payload | 1200 B per packet, 28 B IPv4/UDP header (1228 B on the wire) |
| Offered load | 12 Mbit/s constant bit rate, one packet every 0.8 ms |
| Path 0 (`fiber_primary`) | 20 Mbit/s, 5 ms one-way delay, 0.1 % packet loss |
| Path 1 (`cellular_secondary`) | 8 Mbit/s, 25 ms one-way delay, 0.5 % packet loss |
| Buffer | one FIFO drop-tail queue of 100 packets per path |
| Scheduler | smooth weighted round robin, per packet, weight = capacity / (delay + 1 ms), zero weight while a path is down |
| Handover (`s1_handover`) | path 0 unavailable on [8 s, 12 s) |
| Seeds | 8 independent seeds (1..8) |

`S0` is the same topology without the handover window; it isolates scheduling,
serialization and loss from queueing.

## 3. Implementations

**Python (this repository).** `validation/scenario_s1.py` drives the
repository's own link and queue models. Two variants are compared:

- `capacity_weighted_swrr_v0.1-noqueue` — delay is path latency plus
  serialization at link rate, with independent per-packet loss. This is the
  abstraction the repository's benchmarks previously used.
- `capacity_weighted_swrr_v0.2-fifo` — the same model plus
  `simulation.link_queue.DropTailQueue` (100 packets, single server, drop-tail),
  which is now part of the simulator package.

**ns-3 (reference).** A point-to-point, UDP, packet-level implementation with
`RateErrorModel` losses, `RngSeedManager::SetSeed/SetRun` per replicate, and no
simulator-specific tuning beyond matching the scenario table.

One configuration detail turned out to matter more than any other: ns-3.49's
`InternetStackHelper` silently installs a **FqCoDel queue disc with a
10 240-packet default limit** on every device, in addition to the device's own
100-packet drop-tail `TxQueue`. Out of the box, the reference therefore models
a much deeper, CoDel-managed buffer than the scenario specifies. The published
comparison deletes that disc, installs a 100-packet FIFO disc on the client
devices, and reduces each device `TxQueue` to a single slot, so exactly one
100-packet FIFO buffer per path survives. Section 6 shows what the unmodified
ns-3 defaults produce.

## 4. Results

Mean over 8 paired seeds; deltas are ns-3 minus model.

### S0 — no handover (calibration case)

| Metric | ns-3.49 | model v0.1 | Δ | model v0.2 | Δ |
| --- | --- | --- | --- | --- | --- |
| Packet delivery (%) | 99.862 | 99.850 | −0.012 | 99.850 | −0.012 |
| p95 one-way delay (ms) | 26.230 | 26.228 | −0.002 | 26.228 | −0.002 |
| Goodput (Mbit/s) | 11.983 | 11.982 | −0.001 | 11.982 | −0.001 |
| Share of packets on path 0 (%) | 91.548 | 91.548 | 0.000 | 91.548 | 0.000 |
| Mean active paths | 2.000 | 2.000 | 0.000 | 2.000 | 0.000 |

### S1 — handover with overload on the secondary path

| Metric | ns-3.49 | model v0.1 (queue-free) | Δ | model v0.2 (FIFO) | Δ |
| --- | --- | --- | --- | --- | --- |
| Packet delivery (%) | 93.231 | 99.756 | **+6.526 pp** | 93.221 | −0.010 pp |
| p95 one-way delay (ms) | 150.150 | 26.228 | **−123.9 ms (−82.5 %)** | 147.496 | −2.654 ms (−1.8 %) |
| Goodput (Mbit/s) | 11.188 | 11.971 | +0.783 (+7.0 %) | 11.187 | −0.001 (−0.01 %) |
| Share of packets on path 0 (%) | 73.240 | 73.240 | 0.000 | 73.240 | 0.000 |
| Mean active paths | 1.800 | 1.800 | 0.000 | 1.800 | 0.000 |

The residual 2.65 ms (1.8 %) p95 difference in S1 corresponds to roughly two
packets of buffering at 1228 B / 8 Mbit/s (≈1.23 ms per packet) and is
attributed to the reference keeping one packet in service in addition to the
100 queued, whereas the model's occupancy counts the in-service packet inside
the limit. It is stated as a known, bounded residual rather than explained away.

**Published artifacts.** The replicate-level data behind these tables is
committed so the numbers can be checked without building ns-3:
[`figures/ns3_s1_replicates.csv`](../figures/ns3_s1_replicates.csv) (ns-3
runs), [`figures/s1_python_replicates.csv`](../figures/s1_python_replicates.csv)
(both Python variants) and
[`figures/s1_ns3_comparison.csv`](../figures/s1_ns3_comparison.csv) (paired
differences). The script regenerates all three.

The path-share and active-path columns are identical by construction and act as
a sanity check that both implementations schedule and hand over identically;
they would diverge on any mistake in the weighted round-robin rule or the
handover window.

## 5. What this does and does not establish

Established:

- The transport serialization, per-path loss, smooth weighted round-robin
  scheduling and handover handling of this repository agree with an independent
  packet-level implementation in a low-load multipath scenario.
- The queue-free abstraction materially overstates delivery and understates
  delay when a handover concentrates traffic onto a slower path — a defect that
  was invisible in the repository's own benchmarks and is now fixed.

Not established:

- Fidelity for wireless media. ns-3 point-to-point links are wired abstractions;
  the simulated microwave/HF/satellite/THz media have no PHY, MAC, fading or
  interference model in either implementation.
- Transport with TCP/MPTCP feedback. S1 uses a constant-bit-rate UDP stream.
- Any CDN, cloud, multicloud, quantum or routing-agent behaviour. Those modules
  remain unvalidated.
- Generalisation beyond S1. Two scenarios and two path configurations are not a
  validation suite; the point is that the method now exists and the first
  defect is fixed.

## 6. Sensitivity to the reference configuration

The same S1 workload was run against three ns-3 buffer configurations:

| ns-3 buffer configuration | Delivery (%) | p95 delay (ms) |
| --- | --- | --- |
| ns-3.49 defaults (FqCoDel disc, 10 240 p) | 97.10 | 1127.2 |
| FIFO disc 100 p **plus** device queue 100 p | 93.63 | 271.9 |
| Matched single FIFO, 100 p | 93.23 | 150.2 |

The spread — up to 7.5× in p95 delay and 3.8 percentage points in delivery —
is caused only by which buffer the reference uses, not by any difference in
scheduling or link rates. Two lessons are recorded for the paper and for future
replication: buffer configuration must be part of any cross-validation
specification, and default simulator settings are a modelling choice that must
be reported.

## 7. Reproduction

Requirements: Python 3.10+, and (for the reference) Linux or WSL with a C++17
toolchain and cmake, plus an ns-3.49 source tree.

```bash
# 1. Build and run the ns-3 reference (8 seeds, both scenarios)
NS3_DIR=~/ns-3-dev SEEDS=8 ./validation/ns3/run-s1.sh
#    -> output/validation/ns3_s1.csv

# 2. Run both Python model variants, normalize, compare
py -3 -m validation.run_s1_experiment \
    --ns3-csv output/validation/ns3_s1.csv \
    --seeds 1 2 3 4 5 6 7 8 \
    --output-dir output/validation
#    -> output/validation/s1_comparison.csv
```

The ns-3 build used for the published numbers:

```bash
./ns3 configure \
  --enable-modules=core,network,internet,point-to-point,csma,applications,traffic-control \
  --disable-examples --disable-tests --disable-python \
  -- -DNS3_WARNINGS_AS_ERRORS=OFF
./ns3 build
```

## 8. Next steps

1. Repeat S1 with ns-3 `WifiNetDevice` or an mmWave module in place of the
   secondary point-to-point link, so a wireless medium is exercised rather than
   emulated by a rate/latency/loss tuple.
2. Add a TCP/MPTCP variant of the case, including LIA and OLIA coupling, which
   also serves the congestion-control comparison the paper lists as open work.
3. Calibrate the remaining loss and delay parameters against measured traces.
4. Extend the comparison to the CDN and multicloud modules, which currently have
   no external counterpart at all.

Each of these is tracked as a validation-challenge issue template
(`.github/ISSUE_TEMPLATE/validation_challenge.yml`) so that results are added to
this document rather than scattered across the repository.
