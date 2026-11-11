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

"""Flapping-DDoS experiment for CRMR (H15).

The scenario is the M11 DDoS, but the attack is *flapping*: five 3 s bursts
separated by 3 s of calm between t = 30 s and t = 57 s.  The edges are what a
discrete controller chatters on, and they are what the continuous rotation is
supposed to smooth.

Three arms share the network, instances, request stream and capacity model:

* **static T-NDN** — the same local anomaly detector, dimension pinned to 1,
  prefix routing to the primary instance;
* **DDMR** — the M11 discrete 1 -> 4 jump, hysteresis, all-or-nothing reroute;
* **CRMR** — the phase controller of ``simulation/crmr.py``; the metric rotates
  continuously and the legitimate share sent to a healthy replica is
  ``sin^2(theta)``, so migration is spread over the rotation.

The control tick is 0.1 s so that the continuous migration is resolved; the
manifold is recomputed every 2 s (and immediately when a discrete dimension
changes).  The anomaly detector is the M11 block monitor with a 2 s window, so
the 3 s bursts are visible.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from simulation import crmr
from simulation import ddmr
from simulation import ddmr_scenario as base
from simulation import ndn_scenario
from simulation.ndn_network import PhysicalNetwork

SIM_S = 60.0
TICK_S = 0.1
LEGIT_RPS = 200.0
ATTACK_RPS = 500.0
CAPACITY_RPS = 200.0
BLOCK0_SHARE = 0.40
BOTS = 20
JITTER_LEGIT_MS = 2.0
JITTER_ATTACK_MS = 30.0
QUEUE_REFERENCE_MS = 20.0
MANIFOLD_PERIOD_S = 2.0

#: Attack windows: five flapping bursts (stress) and one sustained burst.
SCENARIO_WINDOWS = {
    "flapping": tuple(
        (30.0 + 6.0 * index, 33.0 + 6.0 * index) for index in range(5)
    ),
    "sustained": ((30.0, 45.0),),
}

CPU_WATTS = 15.0
ENERGY_PER_LOST_REQUEST_J = 0.02

SEEDS = 30
BASE_SEED = 2026
STRATEGIES = ("static", "ddmr", "crmr")


@dataclass
class ArmRun:
    strategy: str
    cdr_cycles: list[float]
    cdr_mean: float
    cdr_std: float
    cdr_overall: float
    cdr_block0: float
    p95_ms: float
    peak_churn: float
    tv_churn: float
    switches: int
    cpu_total_ms: float
    cpu_4d_ms: float
    calls_4d: int
    calls_1d: int
    delivered_window: int
    legit_window: int
    timeline: list[dict[str, object]] = field(default_factory=list)


@dataclass
class SeedResult:
    seed: int
    runs: dict[str, ArmRun]
    prevented_drops: int
    energy_saved_j: float
    energy_cpu_j: float
    energy_ratio: float
    h15: dict[str, bool]


def flapping_attack(seed: int, windows) -> list[base.Request]:
    rng = random.Random(seed * 65_537 + 101)
    requests: list[base.Request] = []
    for start, end in windows:
        time_s = start
        while True:
            time_s += rng.expovariate(ATTACK_RPS)
            if time_s >= end:
                break
            requests.append(
                base.Request(
                    time_s=time_s,
                    consumer=rng.choice(base.bots()),
                    block=0,
                    attack=True,
                    jitter_ms=10.0 + rng.expovariate(1.0 / JITTER_ATTACK_MS),
                )
            )
    return requests


def generate_requests(seed: int, windows) -> list[base.Request]:
    """Legitimate Poisson stream plus the botnet bursts, time-ordered."""
    rng = random.Random(seed * 104_729 + 17)
    weights = base.block_weights()
    consumers = base.legit_consumers()
    requests: list[base.Request] = []

    time_s = 0.0
    while True:
        time_s += rng.expovariate(LEGIT_RPS)
        if time_s >= SIM_S:
            break
        block = rng.choices(range(base.BLOCKS), weights=weights, k=1)[0]
        requests.append(
            base.Request(
                time_s=time_s,
                consumer=rng.choice(consumers),
                block=block,
                attack=False,
                jitter_ms=rng.expovariate(1.0 / JITTER_LEGIT_MS),
            )
        )
    requests.extend(flapping_attack(seed, windows))
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


def _in_cycle(time_s: float, cycles) -> int | None:
    for index, (start, end) in enumerate(cycles):
        if start <= time_s < end:
            return index
    return None


def simulate(
    strategy: str,
    seed: int,
    network: PhysicalNetwork,
    requests: list[base.Request],
    instances: list[list[int]],
    cycles,
) -> ArmRun:
    rng = random.Random(seed * 811 + STRATEGIES.index(strategy))
    monitor = ddmr.AnomalyMonitor()
    block_monitor = ddmr.BlockMonitor(warmup_s=10.0, window_s=1.0)
    dimension_controller = (
        ddmr.DimensionController() if strategy == "ddmr" else None
    )
    phase_controller = crmr.PhaseController() if strategy == "crmr" else None
    ddmr_router = ddmr.DdmrRouter() if strategy == "ddmr" else None
    crmr_router = crmr.CrmrRouter() if strategy == "crmr" else None

    manifold: ddmr.Manifold | None = None
    phase_manifold: crmr.PhaseManifold | None = None
    attacked_sticky = False
    last_manifold_s = -1.0
    last_calm = True
    queue_estimate = {node: 0.0 for row in instances for node in row}

    cpu_total_ms = 0.0
    cpu_4d_ms = 0.0
    calls_4d = 0
    calls_1d = 0
    delivered_window = 0
    legit_window = 0
    delivered_block0 = 0
    legit_block0 = 0
    delivered_overall = 0
    legit_overall = 0
    window_latencies: list[float] = []
    cycle_legit = [0] * len(cycles)
    cycle_delivered = [0] * len(cycles)
    peak_churn = 0.0
    tv_churn = 0.0
    previous_share = 0.0
    timeline: list[dict[str, object]] = []

    index = 0
    total = len(requests)
    time_s = 0.0
    while time_s < SIM_S:
        tick_end = time_s + TICK_S
        batch: list[base.Request] = []
        while index < total and requests[index].time_s < tick_end:
            batch.append(requests[index])
            index += 1

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
        if dimension_controller is not None:
            dimension, switched = dimension_controller.update(anomaly, time_s)
        if phase_controller is not None:
            phase_controller.update(anomaly, TICK_S)

        # -- manifold epoch ---------------------------------------------------
        epoch = time_s - last_manifold_s >= MANIFOLD_PERIOD_S
        if strategy == "crmr" and phase_controller is not None:
            calm = phase_controller.theta <= crmr.CALM_EPS
            if epoch or calm != last_calm:
                points = monitor.active_points(time_s)
                if len(points) >= 8:
                    if calm:
                        manifold = ddmr.compute_manifold(points, ddmr.DIMENSION_CALM)
                        cpu_total_ms += manifold.time_ms
                        calls_1d += 1
                    else:
                        phase_manifold = crmr.compute_phase_manifold(
                            points, phase_controller.theta, phase_controller.radius
                        )
                        cpu_total_ms += phase_manifold.time_ms
                        cpu_4d_ms += phase_manifold.time_ms
                        calls_4d += 1
                    last_manifold_s = time_s
                last_calm = calm
        elif strategy == "ddmr":
            if epoch or switched:
                points = monitor.active_points(time_s)
                if len(points) >= 8:
                    manifold = ddmr.compute_manifold(points, dimension)
                    cpu_total_ms += manifold.time_ms
                    if dimension == ddmr.DIMENSION_SHOCK:
                        cpu_4d_ms += manifold.time_ms
                        calls_4d += 1
                    else:
                        calls_1d += 1
                    last_manifold_s = time_s
        else:
            if epoch:
                points = monitor.active_points(time_s)
                if len(points) >= 8:
                    manifold = ddmr.compute_manifold(points, ddmr.DIMENSION_CALM)
                    cpu_total_ms += manifold.time_ms
                    calls_1d += 1
                    last_manifold_s = time_s

        # -- routing share (theoretical, for churn accounting) ----------------
        if strategy == "crmr":
            if block_monitor.anomaly(0, time_s) > 0.3:
                attacked_sticky = True
            if phase_controller is not None and phase_controller.theta <= crmr.CALM_EPS:
                attacked_sticky = False
            attacked = attacked_sticky
        else:
            attacked = manifold is not None and 0 in manifold.attacked_blocks
        if strategy == "crmr" and phase_controller is not None:
            share = (
                phase_controller.fraction()
                if attacked and phase_controller.theta > crmr.CALM_EPS
                else 0.0
            )
        elif strategy == "ddmr" and dimension_controller is not None:
            share = 1.0 if (dimension == ddmr.DIMENSION_SHOCK and attacked) else 0.0
        else:
            share = 0.0
        change = abs(share - previous_share)
        peak_churn = max(peak_churn, change)
        tv_churn += change
        previous_share = share

        # -- route ------------------------------------------------------------
        counts = {node: 0 for row in instances for node in row}
        choices: dict[int, int] = {}
        for position, request in enumerate(batch):
            row = instances[request.block]
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
            if ddmr_router is not None:
                node = ddmr_router.choose(
                    flow,
                    manifold,
                    dimension,
                    row,
                    latency_by_node,
                )
            elif crmr_router is not None:
                node = crmr_router.choose(
                    request.consumer,
                    request.block,
                    flow.point(),
                    phase_manifold,
                    phase_controller,  # type: ignore[arg-type]
                    row,
                    latency_by_node,
                    {0} if attacked else set(),
                )
            else:
                node = primary
            choices[position] = node
            counts[node] += 1

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
            if request.attack:
                continue
            legit_overall += 1
            if delivered:
                delivered_overall += 1
            cycle = _in_cycle(request.time_s, cycles)
            if cycle is not None:
                legit_window += 1
                cycle_legit[cycle] += 1
                if request.block == 0:
                    legit_block0 += 1
                if delivered:
                    delivered_window += 1
                    cycle_delivered[cycle] += 1
                    window_latencies.append(latency)
                    if request.block == 0:
                        delivered_block0 += 1

        if strategy == "crmr" and phase_controller is not None:
            state = round(phase_controller.theta, 4)
            fraction = round(phase_controller.fraction(), 4)
            b0 = phase_manifold.b0 if phase_manifold else (manifold.b0 if manifold else 0)
            b1 = phase_manifold.b1 if phase_manifold else (manifold.b1 if manifold else 0)
        elif strategy == "ddmr":
            state = dimension
            fraction = share
            b0 = manifold.b0 if manifold else 0
            b1 = manifold.b1 if manifold else 0
        else:
            state = ddmr.DIMENSION_CALM
            fraction = 0.0
            b0 = manifold.b0 if manifold else 0
            b1 = manifold.b1 if manifold else 0

        timeline.append(
            {
                "time_s": round(time_s, 2),
                "anomaly": round(anomaly, 4),
                "state": state,
                "fraction": fraction,
                "b0": b0,
                "b1": b1,
            }
        )
        time_s = tick_end

    cdr_cycles = [
        100.0 * cycle_delivered[index] / cycle_legit[index]
        if cycle_legit[index]
        else 0.0
        for index in range(len(cycles))
    ]
    cdr_mean = sum(cdr_cycles) / len(cdr_cycles)
    variance = sum((value - cdr_mean) ** 2 for value in cdr_cycles) / len(
        cdr_cycles
    )
    switches = 0
    if dimension_controller is not None:
        switches = dimension_controller.expansions + dimension_controller.collapses
    if phase_controller is not None:
        switches = phase_controller.crossings

    return ArmRun(
        strategy=strategy,
        cdr_cycles=cdr_cycles,
        cdr_mean=cdr_mean,
        cdr_std=math.sqrt(variance),
        cdr_overall=100.0 * delivered_overall / legit_overall if legit_overall else 0.0,
        cdr_block0=100.0 * delivered_block0 / legit_block0 if legit_block0 else 0.0,
        p95_ms=_percentile(window_latencies, 0.95),
        peak_churn=peak_churn,
        tv_churn=tv_churn,
        switches=switches,
        cpu_total_ms=cpu_total_ms,
        cpu_4d_ms=cpu_4d_ms,
        calls_4d=calls_4d,
        calls_1d=calls_1d,
        delivered_window=delivered_window,
        legit_window=legit_window,
        timeline=timeline,
    )


def _windows(scenario) -> tuple[tuple[float, float], ...]:
    if isinstance(scenario, str):
        return SCENARIO_WINDOWS[scenario]
    return tuple(scenario)


def run_seed(seed: int = BASE_SEED, scenario="flapping") -> SeedResult:
    windows = _windows(scenario)
    network = PhysicalNetwork(seed=seed)
    placement = ndn_scenario.producer_placement(network)
    instances = base.instance_nodes(network, placement)
    requests = generate_requests(seed, windows)

    runs = {
        strategy: simulate(strategy, seed, network, requests, instances, windows)
        for strategy in STRATEGIES
    }

    prevented = runs["crmr"].delivered_window - runs["static"].delivered_window
    energy_saved = max(0, prevented) * ENERGY_PER_LOST_REQUEST_J
    energy_cpu = runs["crmr"].cpu_4d_ms / 1000.0 * CPU_WATTS
    cdr_gap = runs["ddmr"].cdr_mean - runs["crmr"].cdr_mean
    cdr_gain_static = runs["crmr"].cdr_mean - runs["static"].cdr_mean

    h15 = {
        "churn": runs["crmr"].peak_churn <= 0.5 * runs["ddmr"].peak_churn,
        "cdr": cdr_gap <= 5.0 and cdr_gain_static >= 15.0,
        "variance": (
            runs["crmr"].cdr_std < runs["ddmr"].cdr_std
            if len(windows) > 1
            else True
        ),
        "energy": energy_cpu < energy_saved,
    }
    return SeedResult(
        seed=seed,
        runs=runs,
        prevented_drops=prevented,
        energy_saved_j=energy_saved,
        energy_cpu_j=energy_cpu,
        energy_ratio=energy_cpu / energy_saved if energy_saved > 0 else math.inf,
        h15=h15,
    )
