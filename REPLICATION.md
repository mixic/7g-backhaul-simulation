# Replication and Validation Guide

This guide gives the exact commands needed to install the simulator, run its
test suite, regenerate its benchmarks, and compare its outputs with an external
simulator or testbed. It is written so that a third party can attempt a
replication without private context.

**Status as of version 0.1.0 (2 November 2026):** this project has received no
external issue, pull request, fork contribution, or citation, and no independent
replication has been published. The software and the vision paper have not been
peer reviewed. Nothing in this guide should be read as evidence that anyone
outside the project has used, validated, or endorsed it.

The guide is also the place where completed external validations would be
listed. That table is currently empty by design; see
[Published external validations](#published-external-validations).

## Contents

- [Before you start](#before-you-start)
- [Install and run the test suite](#install-and-run-the-test-suite)
- [Run the vision benchmark](#run-the-vision-benchmark)
- [Run the sensitivity benchmark](#run-the-sensitivity-benchmark)
- [Run the cooperative benchmark replicates](#run-the-cooperative-benchmark-replicates)
- [Run the layered-protocol testbed](#run-the-layered-protocol-testbed)
- [Run the dual-role comparison](#run-the-dual-role-comparison)
- [The validation I/O tool](#the-validation-io-tool)
- [Produce a comparison CSV from an external simulator](#produce-a-comparison-csv-from-an-external-simulator)
- [Published external validations](#published-external-validations)
- [Known model limitations to test first](#known-model-limitations-to-test-first)
- [Reporting your result](#reporting-your-result)

## Before you start

- Python 3.10 or newer. The CI workflow uses Python 3.11.
- Git, and enough disk space for Matplotlib output.
- A shell. Commands below are shown for Windows PowerShell with `py -3`, which
  is how the author runs the project. On macOS or Linux, replace `py -3` with
  `python3`, replace backslashes in paths with forward slashes, and activate
  the virtual environment with `source .venv/bin/activate`.
- Record the exact commit before running anything:

```powershell
git rev-parse HEAD
```

- Do not edit benchmark definitions or metric units to make a comparison match.
  Record deviations instead.

## Install and run the test suite

From the repository root:

```powershell
git clone https://github.com/mixic/7g-backhaul-simulation.git
cd 7g-backhaul-simulation
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 -m pip install --upgrade pip
py -3 -m pip install -r requirements.txt
```

Run the full suite with pytest:

```powershell
py -3 -m pip install pytest
py -3 -m pytest
```

The suite is also unittest-compatible, which is what CI runs:

```powershell
py -3 -m unittest discover -s tests -v
```

The vision paper records **93 tests passing** (plus 7 parameterised subtests)
for the version it describes (2 November 2026). Re-run the suite yourself; do
not take that number on trust. If a test fails, report the failure rather than
working around it.

## Run the vision benchmark

This regenerates the synthetic policy comparison and the public-safety handover
study. It writes summary CSVs and plots under `figures/`:

```powershell
py -3 tools\benchmark_vision.py --output-dir figures --replicates 30 --seed 2026
```

Flags:

- `--output-dir` — output directory. Default: `figures`.
- `--replicates` — number of replicate runs. Default: `30`.
- `--seed` — base random seed. Default: `2026`.

Expected artifacts include `figures/vision_benchmark_summary.csv`,
`figures/public_safety_benchmark_summary.csv`, and the corresponding PNG plots.
Results are synthetic and conditional on the configured scenarios. They are not
measurements of deployed networks. The reactive and predictive multipath arms
in this legacy benchmark share a path allocator and use different cache gains,
so similar goodput is expected by design; that comparison has been superseded
by `tools/benchmark_fair.py` (next section) and its results are described in
the paper's §10.1.

## Run the controlled policy benchmark

This is the replacement for the vision benchmark's reactive-versus-predictive
comparison. Each arm owns an allocator instance, cache gains are held constant
within each comparison, and pressure prediction is ablated against cache
prediction over paired seeds:

```powershell
py -3 tools\benchmark_fair.py --output-dir output\fair_benchmark --replicates 30 --seed 2026
```

It writes `output/fair_benchmark/vision_fair_summary.csv`,
`vision_fair_paired.csv` (paired differences, 95 % intervals, exact sign test)
and `vision_fair_per_seed.csv`. The published conclusion is negative for
pressure prediction: the predictive arm does not gain goodput, and the measured
gains come from predictive cache scaling. Attempts to overturn that result are
a useful contribution, but the comparison design (independent allocator
instances, constant cache gains) must be preserved, and any change must be
reported as a deviation.

## Run the layered-protocol testbed

The layering testbed evaluates the **frozen** predictions in
[docs/layering-predictions.md](docs/layering-predictions.md) at three fidelity
levels: the executable Python model, SimPy, and a Linux network-namespace data
plane. The predictions file was committed before the experiment code and its
tolerances do not change. Do not edit tolerances or scenarios to make a run
pass; record a failure instead.

The executable model and SimPy need only the repository requirements:

```powershell
py -3 -m validation.layering.run_model --output validation\layering\results\model_observations.csv
py -3 -m validation.layering.run_simpy --output validation\layering\results\simpy_observations.csv
```

The Linux data plane uses two network namespaces joined by a veth pair, a TUN
device in each namespace, and `tc netem` loss on the veth. It requires root and
`iproute2` (`ip`, `tc`), `/dev/net/tun`, and user/network namespace support.
On Windows the command delegates to WSL2 (distro `Ubuntu`) as root; on Linux it
must already run as root. No other privilege is used. The harness creates and
deletes the namespaces `layA`/`layB` and never changes the host network
configuration.

```powershell
py -3 -m validation.layering.run_linux --output validation\layering\results\linux_observations.csv
```

It runs 40 Linux replicates (netem seeds 1–40, 100 datagrams each) for the
stochastic predictions and one replicate for the deterministic cases; the full
run takes several minutes. The harness normalises the application payload to
`model_payload - 28` bytes so the IP/UDP datagram handed to the codec is the
model's payload size. See [validation/linux_layering/README.md](validation/linux_layering/README.md)
for the exact setup and privilege list.

Then classify every prediction against the frozen tolerances:

```powershell
py -3 -m validation.layering.report --model validation\layering\results\model_observations.csv --simpy validation\layering\results\simpy_observations.csv --linux validation\layering\results\linux_observations.csv --verdicts validation\layering\results\verdicts.csv --doc docs\layering-results.md
```

The observation CSVs use the normalized validation schema
(`source, scenario, policy, seed, metric, value, unit`) and the metric names
and units registered in `tools/validation_io.py`. The report uses paired seeds
and 95 % intervals where the quantity is stochastic. It writes its mechanical
tables to `docs/layering-results.generated.md` when the hand-maintained
`docs/layering-results.md` already exists, so a rerun cannot silently overwrite
the refutation explanation. All three fidelities share the codec, so agreement
checks the codec under different execution environments, not independent
protocol semantics.

## Run the dual-role comparison

This compares the continuous serve/load-balance controller (`α ∈ [0,1]`) with
the separated fixed-role baseline. The claim and acceptance tests are frozen in
[docs/dual-role.md](docs/dual-role.md); the classified results, including the
refutation and the exploratory DDoS run, are in
[docs/dual-role-results.md](docs/dual-role-results.md).

From the repository root:

```powershell
py -3 tools\benchmark_dual_role.py --output-dir figures --replicates 12 --seed 2026
py -3 tools\plot_dual_role.py --input-dir figures --output-dir figures
py -3 -m pytest tests\test_dual_role.py -q
```

The benchmark writes `figures/dual_role_summary.csv`,
`dual_role_per_seed.csv`, `dual_role_sweep.csv`, `dual_role_verdict.csv`,
`dual_role_alpha_trace.csv`, `dual_role_stability.csv`,
`dual_role_latency_cdf.csv` and `dual_role_ddos.csv`. The plot tool writes the
five `figures/dual_role_*.png` files. The verdict file applies the frozen
tests mechanically; it is not edited to make the claim pass.

The comparison is a flow-level model with stipulated topology, demand and
controller gains. It does not emit packets and is not a DDoS defence: the
`ddos` scenario is a demand flood, not attack classification or scrubbing.

The attack-aware follow-up filters unauthenticated flood volume before it
reaches the role controller. Its claim is frozen in
[docs/attack-aware.md](docs/attack-aware.md) and its classifier sweep is in
[docs/attack-aware-results.md](docs/attack-aware-results.md):

```powershell
py -3 tools\benchmark_attack_aware.py --output-dir figures
py -3 tools\plot_attack_aware.py --input-dir figures --output-dir figures
```

It writes `figures/attack_aware_summary.csv`, `attack_aware_sweep.csv`,
`attack_aware_verdict.csv` and `figures/attack_aware_ddos.png`. The classifier
false-positive and false-negative rates are stipulated inputs, not measured
performance of a real name-verification scheme.

## Run the ns-3 cross-validation experiment (scenario S1)

The external cross-check described in
[docs/external-validation.md](docs/external-validation.md) has two halves. The
reference half needs Linux or WSL, a C++17 toolchain, cmake and an ns-3.49
source tree:

```bash
NS3_DIR=~/ns-3-dev SEEDS=8 ./validation/ns3/run-s1.sh
```

It writes `output/validation/ns3_s1.csv`. The Python half reproduces the two
model variants, normalizes both sides and writes the paired comparison:

```powershell
py -3 -m validation.run_s1_experiment --ns3-csv output\validation\ns3_s1.csv --seeds 1 2 3 4 5 6 7 8 --output-dir output\validation
```

This writes `output/validation/s1_comparison.csv`. If you change the scenario,
change it in both `validation/scenario_s1.py` and
`validation/ns3/s1-multipath-handover.cc`; the shared constants are duplicated
on purpose so that a silent divergence is impossible.

The reference configuration matters: ns-3.49 installs a default FqCoDel queue
disc with a 10 240-packet limit, and the published comparison removes it so
that the configured 100-packet FIFO buffer is the only queue. Re-running with
ns-3 defaults reproduces a much deeper buffer and multi-second latency tails
(see §6 of the validation report). Report the buffer configuration you used.

## Run the coupled congestion-control comparison

```powershell
py -3 tools\benchmark_congestion_control.py --output-dir figures
```

This compares uncoupled Reno, LIA (RFC 6356) and OLIA (published Khalili et al.
rule) on a two-path flow (20 Mbit/s / 5 ms and 8 Mbit/s / 25 ms, 1460-byte
segments, 60 s, 8 paired seeds). It writes
`figures/congestion_benchmark_summary.csv`,
`figures/congestion_benchmark_replicates.csv` and
`figures/congestion_benchmark_paired_differences.csv`. The published result is
that Reno and LIA saturate both paths and are indistinguishable in total
goodput, while OLIA is 1.345 Mbit/s (4.8 %) below LIA in this model. This is a
window-level model, not an MPTCP stack: do not present it as conformance
evidence, and state the RTT source, step size and queue size with any
comparison.

## Run the sensitivity benchmark

This runs paired one-factor-at-a-time sweeps around a scenario's default
parameters:

```powershell
py -3 tools\benchmark_sensitivity.py --scenario nominal --parameter path_capacity_scale --replicates 20 --seed 2026 --output figures\sensitivity.csv
```

Flags:

- `--output` — output CSV path. Default: `figures/sensitivity.csv`.
- `--replicates` — repeats per case. Default: `5`.
- `--seed` — base seed. Default: `2026`.
- `--scenario` — one or more of `nominal`, `peak_demand`, `correlated_outage`.
  Default: `nominal`.
- `--policy` — one or more of `Reactive baseline`, `Full cooperative`,
  `Reactive with selective duplication`, `Predictive paths only`,
  `Prepared cloud only`, `Predictive paths and prepared cloud`.
- `--parameter` — one or more of `demand_scale`, `path_capacity_scale`,
  `path_delay_scale`, `path_loss_scale`, `setup_delay_scale`,
  `cloud_startup_scale`, `forecast_horizon_seconds`. The default is all
  parameters except the two setup/startup scales.

The CSV reports per-case means, normal-approximation 95% intervals, and paired
deltas against each parameter's default. These intervals describe replicate
variation at the chosen parameter values; they are not a global sensitivity
analysis and do not quantify uncertainty in the model form.

## Run the cooperative benchmark replicates

The validation I/O export expects the run-level replicate CSV produced by the
cooperative benchmark. Regenerate it with the same command used in the README:

```powershell
py -3 tools\benchmark_brain_inspired.py --output-dir figures --replicates 20 --seed 2026
```

This writes `figures/brain_inspired_cooperative_replicates.csv`, with one row
per scenario, policy, and paired seed. A measured trace can be replayed instead
of the synthetic demand schedule:

```powershell
py -3 tools\benchmark_brain_inspired.py --measured-trace data\measured_network.csv --output-dir figures\trace_run --replicates 20 --seed 2026
```

Trace replay still applies the configured outage schedule and the synthetic
queue, jitter, and cloud models. It is not packet-for-packet replay.

## The validation I/O tool

`tools/validation_io.py` normalizes run-level metrics to a common schema and
computes paired differences. It does not run ns-3, OMNeT++/INET, Sionna, MPTCP,
or a testbed; you supply the external results. It is invoked as a module from
the repository root:

```powershell
py -3 -m tools.validation_io --help
py -3 -m tools.validation_io export-simulation --help
py -3 -m tools.validation_io normalize-external --help
py -3 -m tools.validation_io compare --help
```

### `export-simulation`

Converts the simulator's replicate CSV into normalized long-form records.

```powershell
py -3 -m tools.validation_io export-simulation --input figures\brain_inspired_cooperative_replicates.csv --output figures\python_normalized.csv
```

Flags:

- `--input` (required) — simulator replicate CSV.
- `--output` (required) — normalized CSV to write.
- `--source` (optional) — source label. Default: `python_simpy`.

The input must contain `scenario`, `policy`, `seed`, and at least one
recognized metric column. By default the export includes every recognized
metric column that is present in the file. The command fails if no recognized
metric is present or a value is non-finite. `METRIC_UNITS` in
`tools/validation_io.py` is the authoritative list.

### `normalize-external`

Converts an external CSV using a JSON mapping.

```powershell
py -3 -m tools.validation_io normalize-external --input results\external_runs.csv --mapping results\mapping.json --source ns3 --output figures\ns3_normalized.csv
```

Flags:

- `--input` (required) — external run-level CSV.
- `--mapping` (required) — JSON mapping file.
- `--source` (required) — source label, for example `ns3`,
  `omnetpp-inet`, or `testbed`.
- `--output` (required) — normalized CSV to write.

### `compare`

Pairs normalized records and reports differences with an uncertainty interval.

```powershell
py -3 -m tools.validation_io compare --left figures\python_normalized.csv --right figures\ns3_normalized.csv --output figures\crosscheck.csv
```

Flags:

- `--left` (required) — first normalized CSV.
- `--right` (required) — second normalized CSV.
- `--output` (required) — comparison CSV to write.
- `--left-policy` (optional) — filter the left side to one policy label.
- `--right-policy` (optional) — filter the right side to one policy label.

`--left-policy` and `--right-policy` must be supplied together or not at all.
The command requires at least **two matched seed pairs** per
scenario/policy/metric group; with fewer it raises an error rather than
reporting a degenerate interval. It rejects unit mismatches, rejects empty
files, and reports unmatched rows instead of silently dropping them.

The output columns are: `left_source`, `right_source`, `scenario`,
`left_policy`, `right_policy`, `metric`, `unit`, `paired_seeds`,
`left_unmatched`, `right_unmatched`, `left_mean`, `right_mean`,
`left_minus_right_mean`, and `paired_ci95`.

The comparison CSV reports paired differences; it does not decide whether the
two systems "agree". State the acceptance criterion before looking at the
result.

### Canonical metrics and units

The normalized schema is:

```text
source, scenario, policy, seed, metric, value, unit
```

External mappings must use these canonical metric names and units exactly:

| Metric | Unit |
|---|---|
| `demand_delivery_percent` | `percent` |
| `critical_service_availability_percent` | `percent` |
| `video_frames_on_time_percent` | `percent` |
| `audio_packets_on_time_percent` | `percent` |
| `p95_video_frame_delay_ms` | `ms` |
| `p95_audio_interarrival_variation_ms` | `ms` |
| `video_stall_seconds` | `s` |
| `longest_video_freeze_seconds` | `s` |
| `media_copy_loss_percent` | `percent` |
| `path_recovery_seconds` | `s` |
| `path_recovery_censored` | `boolean` |
| `cloud_recovery_seconds` | `s` |
| `cloud_recovery_censored` | `boolean` |
| `mean_active_paths` | `paths` |
| `duplicate_packet_percent` | `percent` |
| `duplicate_payload_percent` | `percent` |
| `secondary_region_capacity_mbps_seconds` | `Mbps*s` |
| `media_queue_drop_percent` | `percent` |
| `packet_delivery_percent` | `percent` |
| `one_way_delay_p95_ms` | `ms` |
| `goodput_mbps` | `Mbps` |
| `active_paths_mean` | `paths` |
| `primary_share_percent` | `percent` |

A mapping may include a subset of these metrics; it may not rename them or use
a different unit. If `tools/validation_io.py` gains metrics after this guide is
written, that file wins.

## Produce a comparison CSV from an external simulator

The goal is a normalized CSV for your external run that can be paired with the
simulator's normalized CSV by scenario, policy, seed, and metric.

1. **Choose one bounded scenario and matching policies.** A link-impairment and
   handover case is the recommended first target. Use the same scenario and
   policy names on both sides, or use `policy_values` in the mapping to
   translate external labels. Only map labels when they denote the same policy.
2. **Run your external implementation.** Record the simulator or testbed
   version, module versions, topology, workload, seeds, and units. Produce one
   summarized row per repeat (seed), not raw packet traces.
3. **Write the mapping JSON.** Example for an external run implementing the
   reactive policy:

```json
{
  "scenario": "scenario_name",
  "policy": "policy_name",
  "seed": "run_id",
  "metrics": {
    "video_frames_on_time_percent": {
      "column": "video_ontime_percent",
      "unit": "percent"
    },
    "p95_video_frame_delay_ms": {
      "column": "p95_frame_delay_ms",
      "unit": "ms"
    }
  },
  "policy_values": {
    "Reactive": "Reactive baseline"
  }
}
```

   `scenario`, `policy`, and `seed` name columns in the external CSV.
   `metrics` maps canonical names to `{ "column": "...", "unit": "..." }`.
   `policy_values` is optional and maps external policy labels to simulator
   labels.
4. **Normalize the external CSV.**

```powershell
py -3 -m tools.validation_io normalize-external --input results\external_runs.csv --mapping results\mapping.json --source ns3 --output figures\ns3_normalized.csv
```

5. **Normalize the simulator replicates.** Regenerate the replicate CSV first
   with `tools/benchmark_brain_inspired.py` if needed, then:

```powershell
py -3 -m tools.validation_io export-simulation --input figures\brain_inspired_cooperative_replicates.csv --output figures\python_normalized.csv
```

6. **Compare.**

```powershell
py -3 -m tools.validation_io compare --left figures\python_normalized.csv --right figures\ns3_normalized.csv --output figures\crosscheck.csv
```

7. **Interpret and report.** Include the comparison CSV, the mapping JSON, and
   the external CSV or a stable link in your replication report. State which
   scenario and behavior the comparison covers and which it does not.

To compare two external algorithms directly (for example MPTCP LIA versus
OLIA), normalize each policy result separately and compare them with policy
filters:

```powershell
py -3 -m tools.validation_io compare --left results\lia_normalized.csv --right results\olia_normalized.csv --left-policy LIA --right-policy OLIA --output results\lia_vs_olia.csv
```

Do not relabel LIA or OLIA as the Python reactive policy. The simulator does not
implement TCP congestion windows, acknowledgements, or MPTCP schedulers, so
those comparisons must come from a real MPTCP stack or a compatible simulator
module.

## Published external validations

**Third-party entries: none.** As of version 0.1.0, no independent replication
or third-party validation has been completed, submitted, or published. There is
nothing to cite and no one outside the project has used the software in a way
this project can verify.

One cross-simulator validation exists and was **performed by the author**: the
two-path handover scenario S1 compared against ns-3.49 (see
[docs/external-validation.md](docs/external-validation.md)). It is
author-performed and therefore not independent; it is listed below so the two
categories are not confused. A third-party replication of it is the most useful
contribution the project could receive right now.

| Reference | Reporter / affiliation (optional) | Submodel(s) | External reference | Scenario(s) / seeds | Project commit | Result | Link |
|---|---|---|---|---|---|---|---|
| Author-performed, not independent | Milan Nikolic | transport, queueing, scheduling, handover | ns-3.49 | S1: `s0_nominal` and `s1_handover`, seeds 1-8 | recorded in the report | queue-free model matched within 0.02 % at low load and over-reported delivery by 6.5 points under handover overload; FIFO model matched within 0.01 points | [external-validation.md](docs/external-validation.md) |
| *No third-party runs as of version 0.1.0* | — | — | — | — | — | — | — |

To get a run listed:

1. Open a
   [replication report](https://github.com/mixic/7g-backhaul-simulation/issues/new?template=replication_report.yml)
   with your environment, exact commit, commands, whether results matched,
   deviations, and artifacts.
2. Grant permission to list the replication. A "no" means the report can still
   be discussed, but it will not be added to the table.
3. The maintainer will attempt to check the reported commands against the
   reported commit. If the result cannot be checked, the row will say so.
4. Failed and partial replications will be listed with their outcome. Listing
   is not endorsement, and a listed result validates only the matched scenario
   and assumptions.

Until that happens, the correct description is: **no published external
validations**.

## Known model limitations to test first

These are the limitations stated in the README and the vision paper. They are
the most useful targets for a first challenge or replication because a result
there changes what the project can claim.

| Limitation | Why it matters | Suggested first test |
|---|---|---|
| No cross-simulator validation of wireless behavior | One handover scenario has been cross-checked against ns-3 with point-to-point links, but no wireless PHY/MAC model has been compared. | Repeat scenario S1 with an ns-3 Wi-Fi or mmWave link in place of the secondary point-to-point path; compare delay and loss distributions. |
| Link, traffic, queue, and failure parameters are stipulated | The models are not calibrated to operational traces, so absolute KPI values are not measurements. | Replay a documented measured trace and compare distributions; document trace provenance and preprocessing. |
| The controlled benchmark still uses synthetic dynamics | The negative predictive result is a property of the model, not of real networks. | Repeat the ablation with trace-driven demand, cost and outage schedules. |
| No MPTCP implementation | The simulator has no TCP ACK packets, slow start, retransmissions or schedulers; the new LIA/OLIA comparison is a window-level model. | Compare LIA and OLIA in a real MPTCP stack or a simulator module that implements MPTCP semantics; do not relabel them as the Python policy. |
| Forecasting is finite-difference extrapolation | Constant-acceleration extrapolation is a baseline, not a validated traffic model. | Compare against persistence, moving average, and learned baselines on temporally separated traces; report MAE/RMSE, lead time, and missing-telemetry behavior. |
| The ONNX MLP is trained on synthetic telemetry | Its weights do not demonstrate operational forecasting skill. | Pretrain on synthetic data only as a smoke test; validate separately on measured data before making any predictive claim. |
| Media packets are event-driven but bulk traffic is fluid | Packet-level queueing effects for bulk cross-traffic are not represented. | Compare per-packet delay and loss under matched bulk load against a packet-level simulator. |
| Mobility and IP anchoring are protocol-inspired models | They do not interoperate with live radio or carrier infrastructure. | Compare handover interruption and address stability against a measured handover trace or testbed. |
| CDN and Kubernetes/multicloud behavior is simulated | No production cache, cluster, or cloud provider is controlled. | Use a trace-driven request workload; measure hit ratio, origin load, churn, and replica startup against an emulated cache or cluster. |
| The quantum link is a key-resource abstraction | It carries no classical bytes and does not implement QKD. | Test the key-buffer abstraction only; do not treat it as a quantum-channel validation. |
| UDP transfer is loopback only | Loopback success says nothing about wireless, satellite, or wide-area behavior. | Repeat over a controlled multi-host network with documented impairments before drawing any transport conclusion. |
| The Q-learning agent is tabular and toy-scale | It is a real RL algorithm in a small environment, not deployment-grade learning. | Test convergence, stability, and behavior under non-stationary link conditions. |
| Sensitivity is one-factor-at-a-time | Correlated failures and interactions are not covered. | Run a factorial or global sensitivity analysis over correlated failure, forecast error, and cloud assumptions. |
| Single author, no peer review, no independent validation | The evidence base is limited by the absence of independent scrutiny; the one cross-simulator check was performed by the author. | Attempt a replication (starting with scenario S1) and report it, including negative results. |

## Reporting your result

Use the
[replication report](https://github.com/mixic/7g-backhaul-simulation/issues/new?template=replication_report.yml)
for a full run, or the
[validation challenge](https://github.com/mixic/7g-backhaul-simulation/issues/new?template=validation_challenge.yml)
for a specific model-fidelity discrepancy. Include:

- the commit hash, environment, and exact commands;
- raw or summarized outputs, with units;
- the acceptance criterion you used, chosen before seeing the comparison;
- deviations and failures, not only the parts that matched;
- permission (or refusal) to list the run.

Contributions of independent validation evidence are the highest-priority
contribution type for this project. See
[docs/community-engagement.md](docs/community-engagement.md) for the current
engagement status and the collaboration offer, and
[CONTRIBUTING.md](CONTRIBUTING.md) for the general workflow.
