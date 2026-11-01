# 7G Multi-Medium Backhaul and Self-Scaling CDN Simulator

This project explores how a mobile user's application session could remain continuous while packets travel over a changing mixture of microwave, HF, satellite, mobile, Wi-Fi, and drone-relay links. It combines variable-MTU packetization and reassembly with adaptive transport selection and demand-driven edge-cache placement.

The CDN direction is inspired by Milan Nikolic's University of Bern master's thesis, [*Gezora: A Self-Scalable Content Distribution Network* (2010)](Ni10.pdf). The repository includes the thesis PDF for reference. This simulator is an independent educational implementation, not a reproduction of the thesis or an operational 7G network.

## What is modeled

- **Stable application session:** one session ID and byte stream are preserved as fragments use different links.
- **Mixed transport:** fragments can be striped across Microwave, HF, Satellite, Mobile, Wi-Fi, and drone-relay links without treating the change of medium as a new application session.
- **Variable MTU:** each link advertises a current MTU and encapsulation overhead; fragments are sized to fit, and the receiver reassembles by byte offset, even when fragments arrive out of order.
- **Adaptive transport:** an online reward learner explores MTU sizes per link; a failed fragment is retried using another medium.
- **Self-scaling CDN:** regional request demand and content popularity drive cache placement, warming, and eviction.
- **Acceleration-aware scaling:** the request-rate predictor uses velocity and acceleration to forecast demand and can provision a regional cache before the raw request-count threshold is reached.
- **Telemetry and crisis simulation:** environment load, pressure, losses, storms, and solar flares are surfaced in the simulation dashboard.

## Important limitation

“No handover or break” is the design goal at the application-session abstraction, not a guarantee of zero packet delay or loss in real mobile networks. This prototype does not implement real radio handover, carrier bonding, IP mobility, congestion control, authentication, or deployment-grade RL. It models fragment retry and reassembly across simulated links; practical seamlessness requires compatible endpoints, network support, and field testing.

## Repository structure

```text
7g-backhaul-simulation/
├── .github/
│   ├── ISSUE_TEMPLATE/bug_report.md
│   └── workflows/ci.yml
├── backhaul_sim/                 # Graph scenarios and Tomahawk CDN example
├── docs/                         # Architecture and research notes
├── figures/                      # Generated PNG dashboard frames
├── simulation/
│   ├── cdn.py                    # Demand learning and regional caches
│   ├── channels.py               # Heterogeneous link definitions
│   ├── continuity.py             # MTU adaptation and fragment reassembly
│   ├── environment.py            # Link conditions and stochastic disasters
│   ├── router.py                 # Soft path allocation
│   ├── telemetry.py              # INT-style telemetry
│   └── trends.py                 # Velocity/acceleration forecasting
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

The output includes a byte-stream transfer across media, CDN cache decisions, demand rate and acceleration, and a live transport telemetry table. Dashboard PNGs are written to `figures/`.

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

## License

This project uses the MIT license included in the repository.
