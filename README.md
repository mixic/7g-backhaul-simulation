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

## Repository structure

```text
7g-backhaul-simulation/
├── .github/
│   ├── ISSUE_TEMPLATE/bug_report.md
│   └── workflows/ci.yml
├── backhaul_sim/                 # Graph scenarios and Tomahawk CDN example
├── docs/                         # Architecture, cloud/edge design, and research notes
├── figures/                      # Generated PNG dashboard frames
├── models/                       # Synthetic congestion forecast ONNX and weights
├── simulation/
│   ├── cdn.py                    # Demand learning and regional caches
│   ├── orchestration.py         # Simulated edge scaling and AI site placement
│   ├── mesh.py                   # Peer mesh, congestion forecasts, and cache defenses
│   ├── packet_io.py              # Real UDP loopback framing and payload verification
│   ├── packet_demo.py            # Local packet transfer and optional inference CLI
│   ├── npu_inference.py          # Optional ONNX provider inference/profile checks
│   ├── pretraining.py            # Synthetic congestion forecaster training and ONNX export
│   ├── quantum.py                # Quantum resource and qubit-frame capacity model
│   ├── cooperative.py            # Coordinated mesh, demand, and quantum-resource policy
│   ├── channels.py               # Heterogeneous link definitions
│   ├── continuity.py             # MTU adaptation and fragment reassembly
│   ├── mobility.py               # Handover and stable simulated IP binding
│   ├── carrier_bonding.py        # Byte allocation over available media
│   ├── congestion.py             # Per-link AIMD congestion control
│   ├── security.py               # HMAC session credential model
│   ├── learning.py               # Masked tabular Q-learning
│   ├── analytics.py              # Historical KPI CSV logger
│   ├── environment.py            # Link conditions and stochastic disasters
│   ├── router.py                 # Soft path allocation
│   ├── telemetry.py              # INT-style telemetry
│   └── trends.py                 # Velocity/acceleration forecasting
├── tools/
│   └── benchmark_vision.py       # Reproducible synthetic policy comparison
├── tests/
├── Ni10.pdf
├── LICENSE
├── CONTRIBUTING.md
├── Dockerfile
├── docker-compose.yml
├── main.py
├── pyproject.toml
└── requirements.txt
```

## Installation

```bash
git clone https://github.com/your-user/7g-backhaul-simulation.git
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
implementations or measurements of deployed networks. The main benchmark
shares a path allocator between its reactive and predictive multipath
policies, so similar goodput is expected; it does not yet test the full
AI-assisted failure reorganization or Kubernetes/multicloud proposal.
Methodology, the side-by-side architecture comparison, results, figures, and
limitations are documented in the paper.
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
