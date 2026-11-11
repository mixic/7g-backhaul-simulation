# 7g-backhaul-simulation
# Copyright (C) 2026 MILAN NIKOLIC
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""DDoS shockwave scenario for DDMR (M11).

Legitimate traffic runs for 60 s at 200 requests/s over the 20 prefix blocks
(block 0 carries 40 % of it).  From t = 30 s to t = 45 s a botnet of 20
consumers sends 500 requests/s to *the same block 0*, so the attack and the
legitimate traffic share their base prefix — the case the DDMR brief is about.

Every block has three service instances (the primary and two replicas).  All
four strategies see the same instances, the same requests and the same failure
model:

* NLSR and FSR-NDN use the primary (prefix routing, no anomaly input);
* static T-NDN runs the *same* anomaly detector and the *same* manifold code,
  but its dimension is pinned to 1, so it always uses the primary;
* DDMR expands to four dimensions when the local anomaly crosses the threshold
  and routes the legitimate component to a healthy replica.

Instance delivery is a drop-tail model: offered rate above ``CAPACITY_RPS``
drops ``1 - capacity/offered`` of the requests, and the queue delay is
``20 ms * utilisation^3``.  A dropped legitimate request is the outcome the CDR
measures.  Attack requests are never counted in the CDR, but they do load the
primary instance.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from simulation import ddmr
from simulation import ndn_scenario
from simulation.ndn_network import PhysicalNetwork

#: Frozen scenario constants.
NODE_COUNT = 100
BLOCKS = 20
INSTANCES_PER_BLOCK = 3
CAPACITY_RPS = 200.0
LEGIT_RPS = 200.0
ATTACK_RPS = 500.0
ATTACK_START_S = 30.0
ATTACK_END_S = 45.0
SIM_S = 60.0
TICK_S = 0.25
BLOCK0_SHARE = 0.40
BOTS = 20
JITTER_LEGIT_MS = 2.0
JITTER_ATTACK_MS = 30.0
QUEUE_REFERENCE_MS = 20.0

#: Energy accounting (stipulated, see docs/ddmr.md).
CPU_WATTS = 15.0
ENERGY_PER_LOST_REQUEST_J = 0.02

SEEDS = 30
BASE_SEED = 2026
STRATEGIES = ("nlsr", "fsr", "static", "ddmr")


@dataclass(frozen=True)
class Request:
    time_s: float
    consumer: int
    block: int
    attack: bool
    jitter_ms: float


@dataclass
class StrategyRun:
    strategy: str
    cdr_window: float
    cdr_overall: float
    cdr_block0_window: float
    p95_window_ms: float
    legit_window: int
    delivered_window: int
    tda_total_ms: float
    tda_4d_ms: float
    tda_4d_calls: int
    manifold_calls: int
    expansions: int
    collapses: int
    first_expansion_s: float | None
    last_shock_s: float | None
    early_collapse: bool
    timeline: list[dict[str, object]] = field(default_factory=list)


@dataclass
class SeedResult:
    seed: int
    runs: dict[str, StrategyRun]
    attack_window_s: tuple[float, float]
    prevented_drops: int
    energy_saved_j: float
    energy_cpu_j: float
    energy_ratio: float
    cdr_gain_points: float
    h14_supported: bool


def bots() -> list[int]:
    """Twenty consumers spread over the node ordering."""
    ordered = sorted(range(NODE_COUNT), key=lambda node: node)
    return ordered[:: max(1, NODE_COUNT // BOTS)][:BOTS]


def legit_consumers() -> list[int]:
    bot_set = set(bots())
    return [node for node in range(NODE_COUNT) if node not in bot_set]


def block_weights() -> list[float]:
    remainder = (1.0 - BLOCK0_SHARE) / (BLOCKS - 1)
    return [BLOCK0_SHARE] + [remainder] * (BLOCKS - 1)


def instance_nodes(network: PhysicalNetwork, placement) -> list[list[int]]:
    """Three instances per block: the primary and its two nearest free nodes."""
    primaries = set(placement.block_to_node)
    used: set[int] = set()
    rows: list[list[int]] = []
    for block, primary in enumerate(placement.block_to_node):
        candidates = sorted(
            (
                node
                for node in range(network.node_count)
                if node != primary and node not in primaries and node not in used
            ),
            key=lambda node: (network.distance_ms[primary][node], node),
        )
        replicas = candidates[: INSTANCES_PER_BLOCK - 1]
        used.update(replicas)
        rows.append([primary] + replicas)
    return rows


def generate_requests(seed: int) -> list[Request]:
    rng = random.Random(seed * 104_729 + 17)
    weights = block_weights()
    consumers = legit_consumers()
    requests: list[Request] = []

    time_s = 0.0
    while True:
        time_s += rng.expovariate(LEGIT_RPS)
        if time_s >= SIM_S:
            break
        block = rng.choices(range(BLOCKS), weights=weights, k=1)[0]
        requests.append(
            Request(
                time_s=time_s,
                consumer=rng.choice(consumers),
                block=block,
                attack=False,
                jitter_ms=rng.expovariate(1.0 / JITTER_LEGIT_MS),
            )
        )

    time_s = ATTACK_START_S
    while True:
        time_s += rng.expovariate(ATTACK_RPS)
        if time_s >= ATTACK_END_S:
            break
        requests.append(
            Request(
                time_s=time_s,
                consumer=rng.choice(bots()),
                block=0,
                attack=True,
                jitter_ms=10.0 + rng.expovariate(1.0 / JITTER_ATTACK_MS),
            )
        )

    requests.sort(key=lambda request: request.time_s)
    return requests


def _queue_ms(offered_rps: float) -> float:
    utilisation = min(1.0, offered_rps / CAPACITY_RPS)
    return QUEUE_REFERENCE_MS * utilisation**3


def _drop_fraction(offered_rps: float) -> float:
    if offered_rps <= CAPACITY_RPS:
        return 0.0
    return 1.0 - CAPACITY_RPS / offered_rps


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = fraction * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def simulate(
    strategy: str,
    seed: int,
    network: PhysicalNetwork,
    requests: list[Request],
    instances: list[list[int]],
) -> StrategyRun:
    """Run one strategy over the shared request stream."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")
    rng = random.Random(seed * 911 + STRATEGIES.index(strategy))

    monitor = ddmr.AnomalyMonitor()
    block_monitor = ddmr.BlockMonitor()
    controller = (
        ddmr.DimensionController()
        if strategy in ("static", "ddmr")
        else None
    )
    router: object | None = None
    if strategy == "ddmr":
        router = ddmr.DdmrRouter()
    elif strategy == "static":
        router = ddmr.StaticTndnRouter()

    manifold: ddmr.Manifold | None = None
    last_manifold_s = -1.0
    queue_estimate = {node: 0.0 for row in instances for node in row}
    timeline: list[dict[str, object]] = []
    tda_total_ms = 0.0
    tda_4d_ms = 0.0
    tda_4d_calls = 0
    manifold_calls = 0

    legit_window = 0
    delivered_window = 0
    legit_block0_window = 0
    delivered_block0_window = 0
    legit_overall = 0
    delivered_overall = 0
    window_latencies: list[float] = []
    delivered_any_window = 0

    index = 0
    total = len(requests)
    time_s = 0.0
    while time_s < SIM_S:
        tick_end = time_s + TICK_S
        batch: list[Request] = []
        while index < total and requests[index].time_s < tick_end:
            batch.append(requests[index])
            index += 1

        # -- arrivals update the kinematic state -----------------------------
        for request in batch:
            primary = instances[request.block][0]
            flow = monitor.flow(
                request.consumer,
                request.block,
                network.distance_ms[request.consumer][primary],
            )
            flow.observe(request.time_s, request.jitter_ms)
            block_monitor.observe(request.block, request.time_s)

        anomaly = block_monitor.global_anomaly(time_s)
        dimension = ddmr.DIMENSION_CALM
        switched = False
        if controller is not None:
            dimension, switched = controller.update(anomaly, time_s)

        # -- manifold epoch --------------------------------------------------
        active_classes = strategy in ("ddmr", "static")
        if active_classes and (switched or time_s - last_manifold_s >= ddmr.MANIFOLD_PERIOD_S):
            points = monitor.active_points(time_s)
            if len(points) >= 8:
                used_dimension = (
                    dimension if strategy == "ddmr" else ddmr.DIMENSION_CALM
                )
                manifold = ddmr.compute_manifold(points, used_dimension)
                tda_total_ms += manifold.time_ms
                if used_dimension == ddmr.DIMENSION_SHOCK:
                    tda_4d_ms += manifold.time_ms
                    tda_4d_calls += 1
                manifold_calls += 1
                last_manifold_s = time_s

        # -- route -----------------------------------------------------------
        counts = {node: 0 for row in instances for node in row}
        choices: dict[int, int] = {}
        for position, request in enumerate(batch):
            row = instances[request.block]
            if router is not None:
                primary = row[0]
                flow = monitor.flow(
                    request.consumer,
                    request.block,
                    network.distance_ms[request.consumer][primary],
                )
                latency_by_node = {
                    node: network.distance_ms[request.consumer][node]
                    + queue_estimate.get(node, 0.0)
                    for node in row
                }
                node = router.choose(  # type: ignore[union-attr]
                    flow,
                    manifold,
                    dimension if strategy == "ddmr" else ddmr.DIMENSION_CALM,
                    row,
                    latency_by_node,
                )
            else:
                node = row[0]
            choices[position] = node
            counts[node] += 1

        # -- instance state and delivery -------------------------------------
        offered = {node: count / TICK_S for node, count in counts.items()}
        drop = {node: _drop_fraction(rate) for node, rate in offered.items()}
        queue = {node: _queue_ms(rate) for node, rate in offered.items()}
        queue_estimate.update(queue)

        for position, request in enumerate(batch):
            node = choices[position]
            latency = network.distance_ms[request.consumer][node] + queue[node]
            primary = instances[request.block][0]
            flow = monitor.flow(
                request.consumer,
                request.block,
                network.distance_ms[request.consumer][primary],
            )
            flow.add_latency(request.time_s, latency)
            delivered = rng.random() >= drop[node]
            in_window = ATTACK_START_S <= request.time_s < ATTACK_END_S
            if request.attack:
                continue
            legit_overall += 1
            if delivered:
                delivered_overall += 1
            if in_window:
                legit_window += 1
                if delivered:
                    delivered_window += 1
                    window_latencies.append(latency)
                if request.block == 0:
                    legit_block0_window += 1
                    if delivered:
                        delivered_block0_window += 1

        if active_classes:
            timeline.append(
                {
                    "time_s": time_s,
                    "dimension": dimension if strategy == "ddmr" else ddmr.DIMENSION_CALM,
                    "anomaly": round(anomaly, 4),
                    "b0": manifold.b0 if manifold else 0,
                    "b1": manifold.b1 if manifold else 0,
                    "cpu_ms": round(manifold.time_ms, 3) if manifold else 0.0,
                }
            )
        else:
            timeline.append(
                {
                    "time_s": time_s,
                    "dimension": 0,
                    "anomaly": round(anomaly, 4),
                    "b0": 0,
                    "b1": 0,
                    "cpu_ms": 0.0,
                }
            )
        time_s = tick_end

    shock_times = [
        float(entry["time_s"])
        for entry in timeline
        if entry["dimension"] == ddmr.DIMENSION_SHOCK
    ]
    first_expansion = min(shock_times) if shock_times else None
    last_shock = max(shock_times) if shock_times else None
    early = first_expansion is not None and any(
        float(entry["time_s"]) < ATTACK_END_S
        for entry in timeline
        if entry["dimension"] == ddmr.DIMENSION_CALM
        and float(entry["time_s"]) > (first_expansion or 0.0)
    )

    return StrategyRun(
        strategy=strategy,
        cdr_window=100.0 * delivered_window / legit_window if legit_window else 0.0,
        cdr_overall=100.0 * delivered_overall / legit_overall if legit_overall else 0.0,
        cdr_block0_window=(
            100.0 * delivered_block0_window / legit_block0_window
            if legit_block0_window
            else 0.0
        ),
        p95_window_ms=_percentile(window_latencies, 0.95),
        legit_window=legit_window,
        delivered_window=delivered_window,
        tda_total_ms=tda_total_ms,
        tda_4d_ms=tda_4d_ms,
        tda_4d_calls=tda_4d_calls,
        manifold_calls=manifold_calls,
        expansions=controller.expansions if controller else 0,
        collapses=controller.collapses if controller else 0,
        first_expansion_s=first_expansion,
        last_shock_s=last_shock,
        early_collapse=early,
        timeline=timeline,
    )


def run_seed(seed: int = BASE_SEED) -> SeedResult:
    network = PhysicalNetwork(seed=seed)
    placement = ndn_scenario.producer_placement(network)
    instances = instance_nodes(network, placement)
    requests = generate_requests(seed)

    runs = {
        strategy: simulate(strategy, seed, network, requests, instances)
        for strategy in STRATEGIES
    }

    ddmr_run = runs["ddmr"]
    static_run = runs["static"]
    prevented = ddmr_run.delivered_window - static_run.delivered_window
    energy_saved = max(0, prevented) * ENERGY_PER_LOST_REQUEST_J
    energy_cpu = ddmr_run.tda_4d_ms / 1000.0 * CPU_WATTS
    gain = ddmr_run.cdr_window - static_run.cdr_window
    return SeedResult(
        seed=seed,
        runs=runs,
        attack_window_s=(ATTACK_START_S, ATTACK_END_S),
        prevented_drops=prevented,
        energy_saved_j=energy_saved,
        energy_cpu_j=energy_cpu,
        energy_ratio=energy_cpu / energy_saved if energy_saved > 0 else math.inf,
        cdr_gain_points=gain,
        h14_supported=gain >= 15.0 and energy_cpu < energy_saved,
    )
