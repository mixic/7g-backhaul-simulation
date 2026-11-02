# 7G Multi-Medium Backhaul and Self-Scaling CDN Simulator

This project explores how a mobile user's application session could remain continuous while packets travel over a changing mixture of microwave, HF, satellite, mobile, Wi-Fi, and drone-relay links. It combines variable-MTU packetization and reassembly with adaptive transport selection and demand-driven edge-cache placement.

The CDN direction is inspired by Milan Nikolic's University of Bern master's thesis, [*Gezora: A Self-Scalable Content Distribution Network* (2010)](Ni10.pdf). The repository includes the thesis PDF for reference. This simulator is an independent educational implementation, not a reproduction of the thesis or an operational 7G network.

## What is modeled

- **Stable application session:** one session ID and byte stream are preserved as fragments use different links.
- **Mixed transport:** fragments can be striped across Microwave, HF, Satellite, Mobile, Wi-Fi, and drone-relay links without treating the change of medium as a new application session.
- **Variable MTU:** each link advertises a current MTU and encapsulation overhead; fragments are sized to fit, and the receiver reassembles by byte offset, even when fragments arrive out of order.
- **Radio handover and IP mobility models:** signal hysteresis/time-to-trigger controls make-before-break cell changes while a simulated IP anchor preserves the session address.
- **Carrier bonding and congestion control:** fragments are scheduled over available media; per-link AIMD pacing reacts to delivery feedback.
- **Authenticated sessions:** optional expiring HMAC-signed credentials can gate transport sessions.
- **Adaptive transport:** an online reward learner explores MTU sizes per link; a failed fragment is retried using another medium.
- **Q-learning routing:** a tabular agent adjusts routing weights from outcomes while masking unavailable media.
- **Self-scaling CDN:** regional request demand and content popularity drive cache placement, warming, and eviction.
- **Acceleration-aware scaling:** the request-rate predictor uses velocity and acceleration to forecast demand and can provision a regional cache before the raw request-count threshold is reached.
- **Kubernetes-inspired edge scaling:** a forecast-aware model computes bounded cache-pod replica targets and reports when modeled demand exceeds configured cluster capacity.
- **Multicloud AI placement:** an explainable scheduler ranks configured AI datacenters by latency, egress estimate, accelerator load/capacity, availability, and optional latency SLO.
- **Active-active peer mesh:** traffic is proportionally distributed over multiple available paths using capacity, cost, congestion forecasts, and congestion velocity/acceleration.
- **Cache defenses:** trusted content manifests reject digest mismatches; an NPU-inspired anomaly score blocks low-reuse, high-novelty cache admissions.
- **Quantum-assisted resources:** a separate qubit-frame/key-buffer abstraction can supply modeled key material without treating quantum links as byte-carrying media.
- **Cooperative multibackhaul policy:** coordinates classical mesh routing, per-route payload MTU, demand-driven cache placement, and optional quantum-resource reservations.
- **Real local packet demo:** an opt-in UDP loopback command sends and verifies actual socket datagrams; it is separate from the network-medium simulation.
- **Optional ONNX inference:** a caller-supplied model can run through an explicitly selected ONNX Runtime execution provider; inference fails if profiling detects CPU or other-provider fallback.
- **Telemetry and crisis simulation:** environment load, pressure, losses, storms, and solar flares are surfaced in the simulation dashboard.

## Important limitation

“No handover or break” is the goal at the application-session abstraction, not a guarantee of zero packet delay or loss in real mobile networks. Radio handover, carrier bonding, IP mobility, congestion control, and authentication are represented by protocol-inspired simulator models; they do not interoperate with live radio/carrier infrastructure or provide production-grade security. The quantum link is only a simulated key-resource abstraction: it does not carry classical bytes or implement QKD. The Q-learning implementation is a real tabular RL algorithm in this toy environment, not deployment-grade RL. Practical seamlessness requires standards-based integrations, compatible endpoints, and field testing.

## Scientific status

This repository is an early-stage, single-author research prototype for
hypothesis generation. It is not a peer-reviewed contribution and not evidence
that the proposed architecture outperforms deployed 6G systems. “7G” is a
project codename, not a standardized generation, and the work does **not**
cover the directions that dominate post-6G research (THz communication,
light-wave backhaul, AI-native air interface, integrated sensing). That
divergence, item by item, is documented in
[docs/positioning-7g.md](docs/positioning-7g.md).

### External cross-validation (first results)

The transport model has now been compared, seed by seed, with an independent
packet-level implementation in **ns-3.49** for a two-path handover scenario.
The full method, configuration and reproduction commands are in
[docs/external-validation.md](docs/external-validation.md).

| Scenario | Metric | ns-3.49 | model v0.1 (queue-free) | model v0.2 (FIFO, shipped) |
| --- | --- | --- | --- | --- |
| Nominal dual-path | delivery / p95 delay | 99.862 % / 26.230 ms | 99.850 % / 26.228 ms | 99.850 % / 26.228 ms |
| Handover + overload | delivery / p95 delay | 93.231 % / 150.150 ms | 99.756 % / 26.228 ms | 93.221 % / 147.496 ms |

The queue-free abstraction was accurate while links were lightly loaded and
badly wrong when a handover pushed 12 Mbit/s onto an 8 Mbit/s path: it
over-reported delivery by 6.5 percentage points and under-reported p95 delay by
a factor of 5.7. The corrected model — a bounded FIFO drop-tail queue per link,
now in [simulation/link_queue.py](simulation/link_queue.py) — reproduces the
reference to within 0.01 points of delivery and 1.8 % of p95 delay.

What remains unvalidated is stated plainly in the same document: wireless
media have no PHY/MAC/fading model, the transport is a UDP constant-bit-rate
stream rather than TCP/MPTCP, and the CDN, cloud, multicloud, quantum and
routing-agent modules have no external counterpart at all. The Python/SimPy
benchmarks still use stipulated link, traffic, queue and failure models and
have not been calibrated against operational traces. The deterministic policy
benchmarks use finite-difference velocity and acceleration extrapolation; a
separate ONNX MLP is trained on synthetic telemetry and is not the predictor
used for the paired cooperative benchmark.

### Policy comparison after correcting the benchmark design

The earlier vision benchmark shared one allocation function across reactive and
predictive policies and gave the "proposed" arm different cache gains, so its
goodput differences could not be attributed to prediction. The corrected
benchmark ([tools/benchmark_fair.py](tools/benchmark_fair.py)) gives every arm
its own allocator instance, holds cache gains constant inside each comparison,
and ablates pressure prediction and cache prediction separately over 30 paired
seeds per scenario.

The result is negative for the core predictive mechanism: pressure forecasting
slightly **reduces** delivered goodput in all four scenarios (−1.31 Mbit/s in
the urban flash crowd, −0.11, −0.06 and −0.004 Mbit/s elsewhere; 95 % intervals
exclude zero), while predictive cache scaling accounts for the small gains and
cost reductions. The repository therefore does not claim a predictive-scheduling
advantage; the earlier claim is retracted in the paper.

The separate cooperative path/cloud benchmark tests deterministic activation,
pre-warming and selective-duplication policies; it does not implement trained
distributed AI or live Kubernetes/multicloud control.

### Coupled congestion control: Reno, LIA and OLIA

The simulator now includes a window-level coupled congestion-control model
(`simulation/congestion.py`): uncoupled Reno, plus LIA (RFC 6356) and OLIA (the
published Khalili et al. rule). It is not a TCP implementation — no ACK packets,
slow start, retransmission or MPTCP schedulers — so the comparison is
model-level:

```powershell
py tools\benchmark_congestion_control.py --output-dir figures
```

On a two-path flow (20 Mbit/s / 5 ms and 8 Mbit/s / 25 ms, 8 paired seeds),
Reno and LIA both saturate both paths and are indistinguishable in total
goodput (LIA − Reno = −0.0008 Mbit/s, 95 % CI [−0.0013, −0.0003]); OLIA reaches
1.345 Mbit/s (4.8 % of capacity) less than LIA, because the long-RTT path
remains the "max window" path so its coupling term is zero and drop-tail
halving keeps it below the bandwidth-delay product. The paper reports this as a
model-level, testable finding; it is not MPTCP conformance evidence.

## Role-fluid multipath paradigm (current direction)

The repository's original framing — predictive scheduling and forecast-assisted
cache warming — measured a *consequence* of the underlying idea rather than the
idea itself. The paradigm now implemented is different: **a node has no fixed
role**. At any moment it may be a router, a server/cache, or a load balancer,
and the role is a control variable chosen continuously. Because a path
terminates at a node that may become a server, path selection and role selection
are one optimisation — something MPTCP cannot express, because its endpoints
are fixed by the connection.

The multipath protocol that carries this is governed by two rules, each with a
physical analogue:

- **gradient flow** (water overflowing a river): flow splits over candidate
  paths in proportion to a potential gradient and spills onto alternatives when
  a path is full — a local rule with memory, no forecast;
- **boundary coefficients** (seismic waves crossing the crust): at each medium
  boundary the transmitted fraction is bounded by the MTU ratio and the
  reflected part is requeued, making heterogeneous fragmentation a first-class
  term in the potential.

The model and its first results are in
[docs/role-fluid-paradigm.md](docs/role-fluid-paradigm.md); run it with:

```powershell
py tools\benchmark_role_fluid.py --output-dir figures --replicates 6 --seed 2026
```

The first results are reported as a **negative result for the naive
controller**: on a six-node heterogeneous topology the local rule delivers less
and costs more than a sensible static role design (flash crowd: 91.7 % vs
95.1 % delivery, $16.99 vs $14.79), because its potential mis-prices serving and
transit. A centralised controller with the true objective is much cheaper
($10.43) but delivers less under stress (88.7 %). What the experiment does
establish is conditional: the local rule needs its own unmet-demand signal
(+1.41 pp delivery), damping is mandatory (share oscillation falls from 0.190 to
0.031), role churn is the paradigm's hidden cost (hysteresis: 33.8 switches and
$17.30 at zero, 2.0 switches and $11.95 at 0.05 $), and instability peaks at
*moderate* path heterogeneity rather than maximal. The paradigm is therefore not
demonstrated — the conditions it needs are identified.

### Community status

As of this release there are no external issues, pull requests, forks or
citations; the project has not been peer reviewed or independently replicated.
The artifacts needed for others to test it — replication guide, issue forms,
citation metadata — are in place: [REPLICATION.md](REPLICATION.md),
[CITATION.cff](CITATION.cff) and
[docs/community-engagement.md](docs/community-engagement.md). Research
directions now include wireless and trace-based validation, MPTCP LIA/OLIA
comparisons, independent review and replication. See the
[vision paper](docs/7g-backhaul-vision-paper.md) for the staged evaluation
plan.

## Repository structure

```text
7g-backhaul-simulation/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   ├── replication_report.yml      # Replication attempt form
│   │   └── validation_challenge.yml    # Model-fidelity challenge form
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/ci.yml
├── backhaul_sim/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── engine.py
│   └── models.py
├── docs/
│   ├── 7g-backhaul-author.tex    # Paper author and formatting metadata
│   ├── 7g-backhaul-vision-paper.md  # Research vision, methods, results, and limitations
│   ├── 7g-backhaul-vision-paper.tex # Generated LaTeX source
│   ├── 7g-backhaul-vision-paper.pdf # Generated paper
│   ├── architecture.md           # System model and assumptions
│   ├── community-engagement.md   # Engagement status, collaboration offer
│   ├── discoverability.md        # KPI definitions and repository topics
│   ├── external-validation.md    # ns-3 cross-validation report (scenario S1)
│   ├── multicloud-kubernetes.md  # Cloud and Kubernetes model boundaries
│   ├── peer-mesh.md              # Mesh routing and cache-defense model
│   ├── positioning-7g.md         # What the "7G" codename does and does not claim
│   ├── quantum-cooperative-backhaul.md # Quantum-resource abstraction
│   ├── real-packet-and-npu.md    # UDP demo and optional inference guide
│   └── role-fluid-paradigm.md    # Role-fluid paradigm, model and first results
├── figures/
│   ├── 7g_fabric_tick_0.png
│   ├── 7g_fabric_tick_1.0.png
│   ├── 7g_fabric_tick_2.0.png
│   ├── 7g_fabric_tick_3.0.png
│   ├── 7g_fabric_tick_4.0.png
│   ├── 7g_fabric_tick_5.0.png
│   ├── 7g_fabric_tick_6.0.png
│   ├── 7g_fabric_tick_7.0.png
│   ├── 7g_fabric_tick_8.0.png
│   ├── 7g_fabric_tick_9.0.png
│   ├── brain_inspired_cooperative_benchmark.csv
│   ├── brain_inspired_cooperative_benchmark.png
│   ├── brain_inspired_cooperative_effects.png
│   ├── brain_inspired_cooperative_replicates.csv
│   ├── brain_inspired_cooperative_resources.png
│   ├── brain_inspired_cooperative_timeseries.png
│   ├── congestion_benchmark_paired_differences.csv # Reno/LIA/OLIA paired contrasts
│   ├── congestion_benchmark_replicates.csv # Per-seed congestion-control runs
│   ├── congestion_benchmark_summary.csv  # Reno/LIA/OLIA arm means
│   ├── ns3_s1_replicates.csv     # ns-3 runs for cross-validation scenario S1
│   ├── public_safety_benchmark_summary.csv
│   ├── public_safety_multimedia_qos.png
│   ├── public_safety_overflow_timeseries.png
│   ├── role_fluid_cost_calibration.csv # Potential cost-weight calibration sweep
│   ├── role_fluid_hysteresis.csv # Churn versus responsiveness sweep
│   ├── role_fluid_paired.csv     # Paired controller differences
│   ├── role_fluid_per_seed.csv   # Per-seed role-fluid runs
│   ├── role_fluid_stability.csv  # Damping versus latency-spread sweep
│   ├── role_fluid_summary.csv    # Role-fluid controller means
│   ├── s1_ns3_comparison.csv     # Paired ns-3 versus model differences
│   ├── s1_python_replicates.csv  # Python model runs for scenario S1
│   ├── telemetry_dashboard.png
│   ├── vision_benchmark_cache.png
│   ├── vision_benchmark_continuity.png
│   ├── vision_benchmark_cost.png
│   ├── vision_benchmark_goodput.png
│   ├── vision_benchmark_latency.png
│   ├── vision_benchmark_summary.csv
│   ├── vision_benchmark_urban_timeseries.png
│   ├── vision_fair_paired.csv    # Controlled-benchmark paired differences
│   └── vision_fair_summary.csv   # Controlled-benchmark arm means
├── models/
│   ├── congestion_forecast.npz   # Synthetic model weights
│   └── congestion_forecast.onnx  # Exported congestion forecaster
├── simulation/
│   ├── analytics.py              # Historical KPI CSV logger
│   ├── carrier_bonding.py        # Byte allocation over available media
│   ├── cdn.py                    # Demand learning and regional caches
│   ├── channels.py               # Heterogeneous link definitions
│   ├── congestion.py             # Per-link AIMD congestion control
│   ├── continuity.py             # MTU adaptation and fragment reassembly
│   ├── cooperative.py            # Coordinated mesh, demand, and quantum policy
│   ├── environment.py            # Link conditions and stochastic disasters
│   ├── learning.py               # Masked tabular Q-learning
│   ├── mesh.py                   # Peer mesh and cache defenses
│   ├── mobility.py               # Handover and stable simulated IP binding
│   ├── npu_inference.py          # Optional ONNX provider inference checks
│   ├── orchestration.py          # Simulated edge scaling and AI site placement
│   ├── packet_io.py              # Real UDP loopback framing and payload verification
│   ├── packet_demo.py            # Local packet transfer and optional inference CLI
│   ├── pretraining.py            # Synthetic congestion forecaster training and ONNX export
│   ├── quantum.py                # Quantum resource and qubit-frame capacity model
│   ├── link_queue.py             # Bounded FIFO drop-tail queue (validated model)
│   ├── router.py                 # Soft path allocation
│   ├── role_fluid.py             # Role-fluid potential-field model and controllers
│   ├── security.py               # HMAC session credential model
│   ├── telemetry.py              # INT-style telemetry
│   └── trends.py                 # Velocity/acceleration forecasting
├── tools/
│   ├── benchmark_brain_inspired.py # Event-driven multipath and multicloud study
│   ├── benchmark_congestion_control.py # Reno vs MPTCP LIA vs OLIA comparison
│   ├── benchmark_fair.py         # Independent-policy (ablation) benchmark
│   ├── benchmark_role_fluid.py   # Role-fluid paradigm comparison and sweeps
│   ├── benchmark_sensitivity.py  # Paired one-factor-at-a-time sensitivity sweeps
│   ├── benchmark_vision.py       # CDN, handover, and backhaul policy studies
│   └── validation_io.py          # Normalize and compare simulator/testbed results
├── validation/
│   ├── ns3/
│   │   ├── README.md             # ns-3 build and run instructions
│   │   ├── run-s1.sh             # Build and run the ns-3 reference
│   │   ├── s1-multipath-handover.cc # ns-3 reference implementation
│   │   └── s1_mapping.json       # Metric mapping for validation_io
│   ├── run_s1_experiment.py      # Python side + paired comparison report
│   └── scenario_s1.py            # Shared scenario spec and Python models
├── tests/
│   ├── test_backhaul_sim.py
│   ├── test_brain_inspired_benchmark.py
│   ├── test_cloud_orchestration.py
│   ├── test_congestion_control.py
│   ├── test_continuity.py
│   ├── test_fair_benchmark.py
│   ├── test_link_queue.py
│   ├── test_mesh.py
│   ├── test_packet_io.py
│   ├── test_protocol_models.py
│   ├── test_quantum_backhaul.py
│   ├── test_role_fluid.py
│   ├── test_validation_workflow.py
│   └── test_vision_benchmark.py
├── CITATION.cff                  # Citation metadata (CFF 1.2.0)
├── REPLICATION.md                # How to replicate and report results
├── Ni10.pdf
├── LICENSE
├── CONTRIBUTING.md
├── Dockerfile
├── docker-compose.yml
├── main.py
├── pyproject.toml
├── requirements.txt
├── .gitattributes
└── .gitignore
```

## Installation

```bash
git clone https://github.com/mixic/7g-backhaul-simulation.git
cd 7g-backhaul-simulation
pip install -r requirements.txt
```

## Execution

Install dependencies and run the combined continuity, cache-scaling, and environment simulation:

```bash
pip install -r requirements.txt
python main.py
```

The output includes a byte-stream transfer across media, CDN cache decisions, demand rate and acceleration, simulated edge scaling and AI datacenter placement, an active-active peer-mesh routing/cache example, and a live transport telemetry table. Dashboard PNGs are written to `figures/`.
Historical network and transfer metrics are appended to `output/network_history.csv`.

The Kubernetes and multicloud features are simulation models, not deployment
adapters. See [docs/multicloud-kubernetes.md](docs/multicloud-kubernetes.md)
for the modeled policies, cost assumptions, and integration boundaries.
The mesh routing and cache security abstractions are described in
[docs/peer-mesh.md](docs/peer-mesh.md).
The quantum-assisted architecture and classical/quantum MTU distinction are
described in [docs/quantum-cooperative-backhaul.md](docs/quantum-cooperative-backhaul.md).
The loopback packet test and optional ONNX inference prerequisites and limits are
documented in [docs/real-packet-and-npu.md](docs/real-packet-and-npu.md).
The long-horizon planetary backhaul and orbital AI edge vision is presented in
[docs/7g-backhaul-vision-paper.md](docs/7g-backhaul-vision-paper.md).
The paper proposes a typed temporal topology model to coordinate across
standardized OSI/protocol layers, while retaining existing packet
encapsulation and defining testable hypotheses for predictability, security,
and interoperability.
Download the typeset [paper PDF](docs/7g-backhaul-vision-paper.pdf) or use the
[LaTeX source](docs/7g-backhaul-vision-paper.tex).
The paper now includes a chapter on AI- and NPU-assisted TCP transport
optimization, distinguishing router packet-processing hardware from neural
inference hardware and documenting congestion-control and deployment limits.
Its related-work section cites closely matching heterogeneous-MPTCP, video
scheduling, reinforcement-learning, and real-time multipath-media studies;
it treats them as component precedents, not proof that the full proposed
network/content/cloud combination is novel.

The paper's synthetic policy comparison can be regenerated with:

```powershell
py tools\benchmark_vision.py --output-dir figures --replicates 30 --seed 2026
```

This writes the summary CSV and comparison plots into `figures/`. The plot
labels distinguish a single-path reference, a reactive multipath baseline
(6G-oriented), and the proposed predictive-cooperative policy. These are
experiment-specific simulated policies, not 5G/6G/7G standards
implementations or measurements of deployed networks.

> **Superseded comparison.** This benchmark shares one allocation function
> between the reactive and predictive multipath policies and gives the
> "proposed" arm different cache gains, so its goodput differences cannot be
> attributed to prediction. It is kept for continuity of the paper's earlier
> figures only. The controlled replacement is `tools/benchmark_fair.py`,
> which gives every arm its own allocator instance, holds cache gains constant
> inside each comparison, and ablates pressure prediction against cache
> prediction over 30 paired seeds.

The controlled benchmark is run with:

```powershell
py tools\benchmark_fair.py --output-dir figures --replicates 30 --seed 2026
```

Its conclusion is that pressure prediction does not improve delivered goodput
(it slightly reduces it); the measured gains come from predictive cache
scaling. The published results are committed as
`figures/vision_fair_summary.csv` and `figures/vision_fair_paired.csv`, and the
per-seed data is regenerated by the command above. Methodology, the side-by-side
architecture comparison, results, figures, and limitations are documented in
the paper.
The same command also generates a public-safety handover study comparing
single-path switching, reactive multipath, predictive overflow multipath, and
predictive multipath with selective media assist. Its real-time multimedia
KPIs include on-time video-frame and audio-packet delivery, frame delay, audio
delay variation, total video stall, longest freeze, explicit handover
interruption, duplicate-packet ratio, and mean duplicated-media payload rate.
The media-assist overhead is reported both as duplicate packets relative to
original packets and as Mbps of duplicated payload; the packet ratio is not a
capacity percentage. Results are in
`figures/public_safety_benchmark_summary.csv` and
`figures/public_safety_multimedia_qos.png`.

The separate cooperative path/cloud failure study can be run with:

```powershell
py tools\benchmark_brain_inspired.py --output-dir figures --replicates 20 --seed 2026
```

This SimPy event-driven abstraction queues individual real-time media packets
on finite-buffer path servers, serializes them at modeled link rates, applies
path propagation delay/jitter/loss, and reconstructs each video frame from
four required segments against a 150 ms deadline. Audio packets have a 50 ms
deadline. Aggregate bulk demand remains a per-second fluid load used to
estimate cross-traffic pressure and service capacity; bulk packets are not
simulated individually. The cloud model includes region health and replica
startup delays, but does not run Kubernetes or a cloud provider.

The six matched policy arms separate reactive routing, predictive path
activation, cloud pre-warming, and selective media duplication. Three paired
scenario profiles cover nominal load, peak demand, and correlated terrestrial
outage with slower setup/startup. Output CSV rows contain means, marginal
intervals, and paired differences from the reactive baseline; generated plots
are `figures/brain_inspired_cooperative_benchmark.png` and
`figures/brain_inspired_cooperative_resources.png`, plus
`figures/brain_inspired_cooperative_effects.png` with paired effect intervals,
`figures/brain_inspired_cooperative_timeseries.png` with paired-seed
load/capacity and frame-QoS timelines around injected faults. These are still synthetic
simulation results, not trained distributed AI, a measured 6G baseline, or
evidence of deployed-network superiority. The zero-recovery points are
explicitly marked; they mean the modeled QoS target was already met at the
failure instant. Capacity-time and duplicate payload are resource costs, not
benefits by themselves.

The simulator can replay a measured, one-second demand and path-telemetry
trace from a CSV with exactly 240 samples for each configured path. Required
columns are `second,critical_mbps,bulk_mbps,path,capacity_mbps,delay_ms,loss_probability`.
Each second must have one row for `fiber`, `cellular`, `microwave`, and
`satellite`; traffic values must agree across the four rows. Rates and
capacities are Mbps, delay is milliseconds, and loss is a probability from
0 to 1. This replays sampled demand, capacity, delay, and loss, but still
applies the benchmark's configured outage schedule, synthetic queue/jitter
model, cloud behavior, and media workload. It is not packet-for-packet trace
replay or a measured testbed emulation.

```powershell
py tools\benchmark_brain_inspired.py --measured-trace data\measured_network.csv --output-dir figures\trace_run --replicates 20 --seed 2026
```

Every benchmark run also writes `brain_inspired_cooperative_replicates.csv`
with paired-seed, run-level metrics. Explore one-factor-at-a-time sensitivity
to demand, link capacity/delay/loss, setup/startup delay, and forecast horizon:

```powershell
py tools\benchmark_sensitivity.py --scenario nominal --parameter path_capacity_scale --replicates 20 --seed 2026 --output figures\sensitivity.csv
```

The sensitivity CSV reports per-case means and normal-approximation 95%
intervals plus paired deltas against each parameter's default setting. It
does not quantify uncertainty in the model form and is not a substitute for
global sensitivity analysis. Expand `--scenario` and `--parameter` to cover
additional conditions; runtime grows with the number of cases and replicates.

### ns-3 cross-validation experiment (scenario S1)

The first external cross-check is implemented end to end: the same
two-path handover scenario is modelled in this repository and in ns-3.49, and
the metrics are compared seed by seed. Results and interpretation are in
[docs/external-validation.md](docs/external-validation.md). To reproduce:

```bash
# Reference implementation (Linux or WSL with a C++17 toolchain and ns-3.49)
NS3_DIR=~/ns-3-dev SEEDS=8 ./validation/ns3/run-s1.sh

# Python models, normalization and the paired comparison report
py -3 -m validation.run_s1_experiment \
    --ns3-csv output/validation/ns3_s1.csv \
    --seeds 1 2 3 4 5 6 7 8 \
    --output-dir output/validation
```

The experiment is small on purpose: a fixed-rate UDP stream over two paths
(20 Mbit/s / 5 ms and 8 Mbit/s / 25 ms), a 100-packet FIFO buffer per path, and
a four-second outage of the primary path. Both implementations use the same
smooth weighted round-robin rule, so packet-to-path assignment must match
exactly — a check that would fail on any divergence in scheduling or handover
logic. Replicate-level results are committed as
`figures/ns3_s1_replicates.csv`, `figures/s1_python_replicates.csv` and
`figures/s1_ns3_comparison.csv`.

For comparison with ns-3, OMNeT++/INET, Linux MPTCP, or an authorized
testbed, normalize run-level metrics to the same units and align scenario,
policy, and seed. Export simulator replicates, then normalize external
measurements with a JSON mapping:

```powershell
py -m tools.validation_io export-simulation --input figures\brain_inspired_cooperative_replicates.csv --output figures\python_normalized.csv
py -m tools.validation_io normalize-external --input results\external_runs.csv --mapping results\mapping.json --source ns3 --output figures\ns3_normalized.csv
py -m tools.validation_io compare --left figures\python_normalized.csv --right figures\ns3_normalized.csv --output figures\crosscheck.csv
```

The mapping JSON names the external CSV columns for `scenario`, `policy`,
and `seed`; `metrics` maps canonical metric names to `{ "column": "...",
"unit": "..." }`. Optional `policy_values` maps external policy labels to
the corresponding simulator label. The comparison only includes matched
scenario/policy/seed/metric tuples, requires at least two matched seed pairs,
reports unmatched rows, and rejects unit mismatches. MPTCP
congestion controls such as LIA and OLIA must be exercised by an actual
MPTCP-capable implementation or simulator module; the current media-queue
abstraction does not implement TCP congestion windows, ACK behavior, or
MPTCP schedulers.

Example `mapping.json` for an external run that implements the same reactive
policy:

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
  }
}
```

Only map policy labels when they represent the same policy. To compare LIA
with OLIA, compare the separate externally normalized policy records directly:

```powershell
py -m tools.validation_io compare --left results\lia_normalized.csv --right results\olia_normalized.csv --left-policy LIA --right-policy OLIA --output results\lia_vs_olia.csv
```

Do not relabel either algorithm as the Python reactive policy.

For testbed runs, record the same scenario and policy identifiers, random
seed or run identifier, KPI definitions, and units. Preserve raw timestamped
measurements separately; summarize repeat-level values into the mapped
external CSV before normalization. The adapters enable analysis, but do not
configure routers, launch external simulators, or provide a live testbed.

The default 20-seed results attribute most nominal video-QoS improvement to
prepared cloud capacity: prepared-cloud-only gains 8.24 percentage points in
video on-time delivery over the reactive baseline, while predictive paths
alone gain 0.13 points. In the modeled correlated outage, prepared cloud
improves video on-time delivery from 87.70% to 98.00%; selective duplication
in the full cooperative arm reduces p95 delay among reconstructed frames
from about 129 ms to 33 ms at 5.52% duplicate-payload overhead. These effects
are conditional on the synthetic model and do not establish that the overall
design outperforms real 6G or any deployed network.

To rebuild the paper from the Markdown source with Pandoc and MiKTeX, run these
commands from the repository root in PowerShell:

```powershell
pandoc --from=markdown+tex_math_single_backslash --standalone --table-of-contents --toc-depth=3 --shift-heading-level-by=-1 --metadata lang=en-US --variable documentclass=article --variable fontsize=11pt --variable geometry:margin=1in --variable linestretch=1.15 --variable colorlinks=true --variable linkcolor=blue --variable urlcolor=blue --include-in-header=docs\7g-backhaul-author.tex --output docs\7g-backhaul-vision-paper.tex docs\7g-backhaul-vision-paper.md
pdflatex --enable-installer --interaction=nonstopmode --halt-on-error --output-directory=docs docs\7g-backhaul-vision-paper.tex
pdflatex --enable-installer --interaction=nonstopmode --halt-on-error --output-directory=docs docs\7g-backhaul-vision-paper.tex
```

Run the local UDP packet demonstration independently of the simulation:

```bash
python -m simulation.packet_demo --payload-size 64000 --max-datagram-bytes 1200
```

An optional hardware-provider inference run requires a compatible ONNX model,
the vendor runtime, and an available NPU. A small congestion forecasting model
can be pretrained from synthetic telemetry with the optional ONNX exporter; it
must be calibrated using measured data before operational use. See the linked
guide for instructions and limitations.

## Key performance indicators

- **Session continuity:** successful byte-stream reconstructions / completed transfer attempts
- **Goodput:** application payload bits delivered per simulated elapsed time
- **Retry rate:** fallback or retransmission attempts per delivered fragment
- **Cache hit ratio:** cache hits / requests observed
- **Per-link state:** routing allocation, load, pressure, MTU, estimated loss, and latency

CSV fields, units, and suggested GitHub discovery topics are described in [docs/discoverability.md](docs/discoverability.md).

## Demand acceleration model

For a sampled metric `x`, the estimator computes:

```text
velocity      v = (x[t] - x[t-1]) / Δt
acceleration  a = (x[t] - 2*x[t-1] + x[t-2]) / Δt²
forecast      x[t+H] = x[t] + v*H + 0.5*a*H²
```

The generic estimator can be used for request rate, throughput, or latency. Cache scale-up currently uses the forecasted recent request rate. Positive throughput growth could inform capacity pre-provisioning; increasing latency velocity/acceleration could become an early route-shift signal. The current demo does not yet feed those two metrics into routing decisions.

## Thesis connection

The design builds on the thesis's self-scalable CDN direction: observe regional request demand, identify popular content, route requests to regional surrogates, and grow cache capacity as demand changes. See the [architecture note](docs/architecture.md) for the model, assumptions, and limitations.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Contribution guide

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [Bug report template](.github/ISSUE_TEMPLATE/bug_report.md)
- [CI workflow](.github/workflows/ci.yml)
- [Suggested GitHub topics and KPI definitions](docs/discoverability.md)

## License

This project is licensed under the GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
