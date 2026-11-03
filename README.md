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
and costs more than a sensible static role design (flash crowd: 95.90 % vs
99.65 % delivery, $15.44 vs $12.48), because it keeps switching while the static
design pre-warms two edge caches. A centralised controller with the true
objective is much cheaper ($8.90) and delivers 99.34 % in that scenario, but in
the steady and outage scenarios it delivers less than the static design
(99.38 %/99.41 % vs 99.85 %) because it is myopic and will not invest in a cache
it cannot foresee using.

Serving is now a finite resource rather than a free local termination: each
node has a 0.10–0.35 GB cache against a 0.5 GB working set, a hit ratio that
warms over 8 s and caps what serving can deliver (3.9–20.1 % mean hit across arms), and a
cached copy at a core node still traverses the downstream path. What the
experiment establishes is conditional: damping is mandatory (undamped share
oscillation 0.29–0.46 falls to 0.022–0.034 at λ = 0.5), a role **dwell timer**
is required because a one-tick signal cannot evaluate a role with a warm-up
cost, and churn trades against delivery (15.8 switches / 95.20 % / $15.83 at zero
hysteresis, 6.8 switches / 97.90 % / $13.20 at 0.02 $, 1.0 switch / 91.66 % /
$10.18 at 0.05 $). The earlier claim that instability peaks at *moderate* path
heterogeneity was an artifact of the cache-free model and is withdrawn. The
paradigm is therefore not demonstrated — the conditions it needs are identified.

### Protocol specification and ns-3 cross-validation

The paradigm's protocol now exists and has been cross-checked externally.
[`docs/rfmp-protocol.md`](docs/rfmp-protocol.md) specifies **RFMP v0.1**: data
and ACK formats, the sender's weighted scheduling and path state, the receiver's
reordering buffer with deadline, the ACK clock, the failure detector, the
role-transition procedure and the MTU boundary rule.
[`simulation/rfmp.py`](simulation/rfmp.py) and
[`validation/ns3/rfmp-role-transition.cc`](validation/ns3/rfmp-role-transition.cc)
implement that specification independently, and
[`docs/rfmp-validation.md`](docs/rfmp-validation.md) reports the paired
comparison on scenario RT1 (scripted `forward` → `serve` → `forward` epochs with
a 100 ms overlap at each boundary).

All five acceptance criteria fixed before the run pass, with the largest
residual at 1.6 µs:

| Metric | ns-3.49 | Python | Δ |
| --- | ---: | ---: | ---: |
| In-order delivery (%) | 100.0000 | 100.0000 | 0.0000 |
| Duplicate rate (%) | 0.9901 | 0.9901 | 0.0000 |
| Transition gap at 6 s / 12 s (ms) | 0.79 / 0.88 | 0.79 / 0.88 | ≤ 0.0003 |
| p95 reorder stall (ms) | 16.3128 | 16.3122 | +0.0006 |
| Mean delivery delay (ms) | 15.5617 | 15.5601 | +0.0016 |

A transition does not interrupt the stream: the in-order release gap is one
packet interval, and the cost appears as a 16.3 ms reorder stall — inside the
predicted 20 ms drain bound of the slower path, with duplicates from the overlap
fully suppressed.

```bash
NS3_DIR=~/ns-3-dev SEEDS=5 ./validation/ns3/run-rfmp.sh
py -3 -m validation.run_rfmp_experiment \
    --ns3-csv output/validation/rfmp_ns3.csv --seeds 1 2 3 4 5 \
    --output-dir output/validation
```

A second scenario, **RT2**, removes the warm-cache assumption: the serving
node starts cold, its hit ratio ramps linearly from 0 to 1 over 8 s, and hits
and misses are sourced exclusively by `X` and `O`. Both implementations agree to
four decimals on the served fraction (37.5167 %, the exact mean of the ramp),
with zero duplicates and transition gaps of 5.7 ms / 10.7 ms: a cold cache turns
the transition from a switch into a ramp instead of losing the stream.

What this validates: the transition mechanics, reordering, duplicate
suppression, the scheduling/boundary rules and the cache-aware split. What it
does not: the role-*selection* policy (the epochs are scripted), the ACK clock
and failure detector (not exercised), wireless physics, and congestion control.
The cache is a stipulated linear warm-up with no eviction or popularity curve.
Closing the loop between the protocol and the controller is the next experiment.

## Dual-role nodes: continuous α (new concept)

The role-fluid work above treats a role as a discrete state. The dual-role
experiment makes the split continuous: `α ∈ [0, 1]` is the fraction of a node's
resource committed to **serving** from a warm cache, and `1 − α` is the
fraction committed to **forwarding / load balancing**. Every node reallocates
`α` from local pressure, its velocity and its acceleration; the separated
baseline fixes interior nodes at `α = 0` (pure balancers) and edge nodes at
`α = 1` (pure servers), the proxy-based architectural split.

The claim and acceptance tests are frozen in
[docs/dual-role.md](docs/dual-role.md) before the comparison; results are in
[docs/dual-role-results.md](docs/dual-role-results.md).

The main claim is **refuted**. At the separated arm's first sub-95 % load
(`L* = 1.4 ×` nominal), the fluid arm's goodput is 3.7 % higher (threshold 5 %)
and its p95 latency is 2.23 × the separated baseline (threshold ≤ 1.5 ×). The
controller does improve the delivered fraction through the middle of the sweep
(98.2 % vs 95.8 % at 1.3 ×), but it pays a latency cost and degrades faster
above 1.7 ×. An exploratory DDoS flood at `E2` is also negative: the
pressure-maximising rule serves the attack and starves forwarding to an
unattacked target (`E3`: 92.1 % vs 98.8 %). The model cannot distinguish
attack from legitimate demand and implements no scrubbing or rate limiting;
this is **not** a DDoS defence. The result is reported as a refutation, not
tuned away.

```powershell
py -3 tools\benchmark_dual_role.py --output-dir figures --replicates 12 --seed 2026
py -3 tools\plot_dual_role.py --input-dir figures --output-dir figures
```

Figures: `dual_role_alpha.png` (α and 1−α over the flash crowd),
`dual_role_throughput.png` (goodput and delivery vs load),
`dual_role_latency_cdf.png`, `dual_role_stability.png` and
`dual_role_ddos.png` (delivery by target under the flood).

The follow-up claim in [docs/attack-aware.md](docs/attack-aware.md) tests
whether authenticated name-class admission — the service-layer analogue of the
layering testbed's integrity-scope finding — fixes that failure. It is also
**refuted as stated**: at 50 % flood leakage all-target legitimate delivery
falls below 95 % and the `E3` gain is only 1.73 pp; even with perfect flood
rejection the `E3` gain is 4.91 pp, missing the pre-registered 5 pp bar by
0.09 pp. The sweep does yield the useful condition: the filter must reject
about 80 % of the flood to keep every target at ≥ 95 % in this topology. See
[docs/attack-aware-results.md](docs/attack-aware-results.md). The RFMP loop is
still not closed; this remains a flow-level controller.

A further pre-registered test asks whether **negative** velocity and
acceleration — the receding side of a flood — can drive capacity release back
to forwarding. On a trapezoidal flood, signing the trend terms is also
**refuted**: `E3` legitimate delivery in the decay window falls from 93.07 % to
82.99 % (−10.08 pp against a required +2 pp), steady-state delivery loses
1.10 pp (limit 1 pp), and the shorter `α` recovery is degenerate because the
controller never commits much in the first place. The finite-difference trend
flips sign at every control step, reintroducing role churn. See
[docs/signed-trends.md](docs/signed-trends.md) and
[docs/signed-trends-results.md](docs/signed-trends-results.md).

## SDN mapping: Software-Defined CDN and Backhaul

[docs/sdn-mapping.md](docs/sdn-mapping.md) maps the concepts onto the SDN
stack. The continuous `α` split is a control-plane decision executed by the
data plane over a southbound `set_alpha` instruction; authenticated name-class
admission is a control-plane application enforced at the data plane; signed
trends are control-plane analytics; RFMP role epochs are southbound role
transitions; the layered authentication scope constrains which fields the
controller may act on. The document lists the additional components for an
**SD-CDN** (name/content controller, replica placement, cache controller,
admission, role/α, telemetry, origin policy) and for an **SD-BH** (link-state
collector, path/TE, epoch orchestrator, tunnel manager, admission, SLO
controller, telemetry), with the interfaces between them.

`simulation/sdn_plane.py` implements the minimal control-plane/data-plane
split: `FloodAwareController` turns a northbound flood policy into
`SouthboundMessage` instructions and `SDNDualRoleSimulation` applies them. The
pre-registered claim is **confirmed**: steady delivery is unchanged (99.24 %),
and under the DDoS flood the SDN override delivers 99.07 % to the unattacked
`E3` versus 92.08 % for local control (+6.99 pp). It does not reduce total
attack congestion (64.86 % vs 64.91 %); protection comes from keeping `E3`'s
serving capacity pinned, not from dropping attack volume. The alert is
stipulated perfect, only `set_alpha` is implemented, and RFMP epochs remain
scripted. See [docs/sdn-results.md](docs/sdn-results.md).

## Layered-protocol testbed (phase 0)

The repository also contains a three-fidelity testbed for encapsulated stacks.
[docs/layering-predictions.md](docs/layering-predictions.md) froze seven
predictions over wire size, delivery, ordering and authentication scope;
[docs/layering-results.md](docs/layering-results.md) classifies them in the
executable model, SimPy and a Linux network-namespace/TUN data plane under
`tc netem`. Six predictions are confirmed; P5 is refuted at the Linux fidelity
and the cause (a payload normalisation that changes the fragment count) is
explained rather than removed. The testbed measures size, delivery and
authentication acceptance only, and makes no cryptographic security claim.
Reproduction commands are in [REPLICATION.md](REPLICATION.md).

## The name fabric: DNS-independence as one operation

The strongest version of the paradigm is not "no DNS". It is that **resolution
and forwarding are one operation**: a request carries its name, and the same
potential field that allocates flow and selects roles decides where it goes.
Nothing completes before the first packet moves, so no TTL sits between a role
change and the requests that follow it.

`simulation/name_fabric.py` implements that fabric with two name classes:
self-certifying digests for immutable content (poisoning structurally
impossible) and signed service descriptors for role-fluid services (forgery
risk that attestation reduces). Run it with:

```powershell
py tools\benchmark_name_fabric.py --output-dir figures
```

Five pre-registered experiments, and what they measured:

- **The floor removed:** a service moving between edge nodes is observed by
  clients in 28.7 s at a 30 s DNS TTL, versus 35.7 ms with gradient
  resolution — link-limited, as predicted. The absolute 10 ms threshold
  pre-registered for the gradient **failed** (the new instance sits behind a
  saturated 80 Mbit/s link); it is reported as a failure rather than moved.
- **Poisoning by name class:** immutable 0.000 %, service descriptors 95.4 %,
  14.9 %, 2.0 %, 0.18 % as attestation strengthens, DNSSEC 0 % versus 3.25 %
  without. The service curve is the honest residual — and its probabilities are
  stipulated, not a measurement of a real signature scheme.
- **Interest flooding versus query flooding:** the pending table sustains
  ~25× the load of a 5 000 QPS resolver per node under these defaults, which
  contradicts the "root tier is the weak point" narrative and is driven by
  stipulated capacities, not by a structural advantage.
- **Tail latency:** gradient p99 is 22.7 ms, a cached DNS answer 22.5 ms, and a
  DHT 217 ms — the DHT lowers the mean and raises the floor.
- **The gateway seam:** external requests cost ~2× an internal one even at an
  idle gateway, and its p95 reaches 71 ms at a 50 % external share.

What this does **not** establish: no packet-level cross-validation yet (the
RFMP harness is the vehicle), no bootstrap model, no name-table memory bound,
and no sensitivity analysis. See [docs/name-fabric.md](docs/name-fabric.md).

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
│   ├── name-fabric.md            # DNS-independence: resolution as forwarding
│   ├── peer-mesh.md              # Mesh routing and cache-defense model
│   ├── positioning-7g.md         # What the "7G" codename does and does not claim
│   ├── quantum-cooperative-backhaul.md # Quantum-resource abstraction
│   ├── real-packet-and-npu.md    # UDP demo and optional inference guide
│   ├── rfmp-protocol.md          # RFMP v0.1 protocol specification
│   ├── rfmp-validation.md        # Role-transition cross-validation report
│   ├── role-fluid-paradigm.md    # Role-fluid paradigm, model and first results
│   ├── dual-role.md              # Continuous serve/balance claim and scenarios
│   ├── dual-role-results.md      # Dual-role comparison, refutation and DDoS
│   ├── attack-aware.md           # Pre-registered authenticated-admission claim
│   ├── attack-aware-results.md   # Classifier sweep and its refutation
│   ├── signed-trends.md          # Pre-registered signed velocity/acceleration claim
│   ├── signed-trends-results.md  # Signed-trend refutation and role-churn finding
│   ├── sdn-mapping.md            # SDN stack mapping, SD-CDN and SD-BH components
│   ├── sdn-results.md            # SDN role-override comparison
│   ├── layering-predictions.md   # Frozen P1-P7 encapsulation predictions
│   └── layering-results.md       # Three-fidelity layering classification
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
│   ├── name_fabric_flooding.csv  # Flooding thresholds
│   ├── name_fabric_gateway.csv   # Gateway seam cost
│   ├── name_fabric_latency.csv   # Strategy latency distributions
│   ├── name_fabric_poisoning.csv # Poisoning acceptance by name class
│   ├── name_fabric_transition.csv # Transition observation floor
│   ├── ns3_s1_replicates.csv     # ns-3 runs for cross-validation scenario S1
│   ├── public_safety_benchmark_summary.csv
│   ├── public_safety_multimedia_qos.png
│   ├── public_safety_overflow_timeseries.png
│   ├── role_fluid_cost_calibration.csv # Potential cost-weight calibration sweep
│   ├── role_fluid_hysteresis.csv # Churn versus responsiveness sweep
│   ├── role_fluid_paired.csv     # Paired controller differences
│   ├── role_fluid_per_seed.csv   # Per-seed role-fluid runs
│   ├── rfmp_comparison.csv       # ns-3 versus Python RFMP comparison
│   ├── rfmp_ns3_replicates.csv   # ns-3 RFMP role-transition runs
│   ├── rfmp_python_replicates.csv # Python RFMP role-transition runs
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
│   ├── dual_role_summary.csv     # Dual-role arm means and intervals
│   ├── dual_role_per_seed.csv    # Paired-seed dual-role runs
│   ├── dual_role_sweep.csv       # Delivered load sweep
│   ├── dual_role_verdict.csv     # Frozen acceptance tests at L*
│   ├── dual_role_alpha_trace.csv # Alpha per node and tick
│   ├── dual_role_stability.csv   # Mean |delta alpha| per tick
│   ├── dual_role_latency_cdf.csv # Volume-weighted latency quantiles
│   ├── dual_role_ddos.csv        # Delivery by target under the flood
│   ├── dual_role_alpha.png
│   ├── dual_role_throughput.png
│   ├── dual_role_latency_cdf.png
│   ├── dual_role_stability.png
│   ├── dual_role_ddos.png
│   ├── attack_aware_summary.csv  # Admission arms and legitimate delivery
│   ├── attack_aware_sweep.csv    # Delivery vs classifier leakage
│   ├── attack_aware_verdict.csv  # Pre-registered admission tests
│   ├── attack_aware_ddos.png     # Legitimate delivery vs false-negative rate
│   ├── signed_trends_summary.csv # Signed vs positive trend arm means
│   ├── signed_trends_verdict.csv # Pre-registered signed-trend tests
│   ├── signed_trends_alpha.csv   # Mean E2 alpha trace
│   ├── signed_trends_alpha.png
│   ├── sdn_summary.csv           # SDN/local/separated arm means
│   ├── sdn_verdict.csv           # Pre-registered SDN tests
│   ├── sdn_control.png
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
│   ├── name_fabric.py            # Name-based forwarding, name classes and attacks
│   ├── packet_io.py              # Real UDP loopback framing and payload verification
│   ├── packet_demo.py            # Local packet transfer and optional inference CLI
│   ├── pretraining.py            # Synthetic congestion forecaster training and ONNX export
│   ├── quantum.py                # Quantum resource and qubit-frame capacity model
│   ├── link_queue.py             # Bounded FIFO drop-tail queue (validated model)
│   ├── rfmp.py                   # RFMP v0.1 Python discrete-event reference
│   ├── router.py                 # Soft path allocation
│   ├── role_fluid.py             # Role-fluid potential-field model and controllers
│   ├── dual_role.py              # Continuous alpha serve/balance model and DDoS scenario
│   ├── sdn_plane.py              # Southbound messages and SDN role-override policy
│   ├── layering/                 # Typed C/E/T/F/S codec, stacks and survival model
│   ├── security.py               # HMAC session credential model
│   ├── telemetry.py              # INT-style telemetry
│   └── trends.py                 # Velocity/acceleration forecasting
├── tools/
│   ├── benchmark_brain_inspired.py # Event-driven multipath and multicloud study
│   ├── benchmark_congestion_control.py # Reno vs MPTCP LIA vs OLIA comparison
│   ├── benchmark_fair.py         # Independent-policy (ablation) benchmark
│   ├── benchmark_role_fluid.py   # Role-fluid paradigm comparison and sweeps
│   ├── benchmark_sensitivity.py  # Paired one-factor-at-a-time sensitivity sweeps
│   ├── benchmark_name_fabric.py  # Five name-fabric experiments
│   ├── benchmark_dual_role.py    # Continuous alpha comparison, sweep and DDoS
│   ├── plot_dual_role.py         # Alpha, throughput, latency, stability, DDoS plots
│   ├── benchmark_attack_aware.py # Authenticated admission vs classifier leakage
│   ├── plot_attack_aware.py      # Legitimate delivery vs false-negative rate
│   ├── benchmark_signed_trends.py # Signed vs positive trend on a shaped flood
│   ├── plot_signed_trends.py     # Alpha and decay-delivery plots
│   ├── benchmark_sdn.py          # SDN role-override comparison
│   ├── plot_sdn.py               # Delivery-by-target and steady-state plots
│   ├── benchmark_vision.py       # CDN, handover, and backhaul policy studies
│   └── validation_io.py          # Normalize and compare simulator/testbed results
├── validation/
│   ├── ns3/
│   │   ├── README.md             # ns-3 build and run instructions
│   │   ├── rfmp-role-transition.cc # RFMP role-transition reference
│   │   ├── run-rfmp.sh           # Build and run the RFMP reference
│   │   ├── run-s1.sh             # Build and run the S1 reference
│   │   ├── s1-multipath-handover.cc # ns-3 reference implementation
│   │   └── s1_mapping.json       # Metric mapping for validation_io
│   ├── rfmp/rt1_mapping.json     # RT1 metric mapping for validation_io
│   ├── run_rfmp_experiment.py    # RFMP comparison report
│   ├── run_s1_experiment.py      # Python side + paired comparison report
│   ├── layering/                 # Layering runners, classifier and committed CSVs
│   ├── linux_layering/           # Two-netns TUN relay and tc-netem harness
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
│   ├── test_name_fabric.py
│   ├── test_packet_io.py
│   ├── test_protocol_models.py
│   ├── test_quantum_backhaul.py
│   ├── test_rfmp.py
│   ├── test_role_fluid.py
│   ├── test_dual_role.py
│   ├── test_sdn_plane.py
│   ├── test_layering_codec.py
│   ├── test_layering_linux.py
│   ├── test_layering_properties.py
│   ├── test_layering_report.py
│   ├── test_layering_scenarios.py
│   ├── test_layering_simpy.py
│   ├── test_validation_workflow.py
│   └── test_vision_benchmark.py
├── CITATION.cff                  # Citation metadata (CFF 1.2.0)
├── GOAL.md                       # Current testbed goal and milestone status
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
