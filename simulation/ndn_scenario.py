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

"""Paired-seed M10 experiment: T-NDN against NLSR, FSR-NDN and Fisheye-Overlay.

One seed produces one physical network, one producer placement, one request
stream, one failed link, and the same four strategies evaluated on them.  The
seed is the pairing key, so every reported difference is a paired difference.

The simulator is a *routing and control-plane model*, not a packet simulator.
Requests are Poisson arrivals; a request is delivered if its route exists at the
time it is sent (or before its Interest lifetime expires), and latency is the
shortest-path latency plus a fixed per-hop queue term.  What is modelled exactly
is the thing under test: how many FIB entries each plan needs, and how long each
plan takes to have a usable route after a topology change.

Scenario constants are frozen before the run and repeated in
``docs/tndn-predictions.md``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from simulation import fisheye_overlay_baseline as fisheye
from simulation import fsr_baseline as fsr
from simulation import nlsr_baseline as nlsr
from simulation import tndn_router as tndn
from simulation.ndn_network import (
    FAILURE_S,
    NODE_COUNT,
    PhysicalNetwork,
)
from simulation.topology import NAME_COUNT, PRODUCER_COUNT, Analysis

#: Frozen scenario constants.
SEED_COUNT = 30
BASE_SEED = 2026
REQUEST_RATE = 200.0  # requests per second
SIM_SECONDS = 60.0
INTEREST_LIFETIME_S = 1.0
QUEUE_MS_PER_HOP = 2.0
NAMES_PER_PRODUCER = NAME_COUNT // PRODUCER_COUNT
PRODUCER_GRID = (5, 4)  # 5 columns x 4 rows = 20 producers

STRATEGIES = ("nlsr", "fsr", "fisheye", "tndn")


@dataclass(frozen=True)
class ProducerPlacement:
    block_to_node: tuple[int, ...]
    node_to_block: tuple[int, ...]


@dataclass(frozen=True)
class PairInfo:
    """Route facts for one (consumer, producer block) pair."""

    affected: bool
    before_latency_ms: float
    after_latency_ms: float
    hops_before: int
    switch_node: int


@dataclass(frozen=True)
class SeedResult:
    seed: int
    failure_s: float
    failure_link: int
    fib_mean: dict[str, float]
    convergence_p99_s: dict[str, float]
    cdr_percent: dict[str, float]
    p95_latency_ms: dict[str, float]
    tda_ms: float
    tda_core_ms: float
    requests: int
    affected_fraction: float


def producer_placement(network: PhysicalNetwork) -> ProducerPlacement:
    """Evenly spread 5x4 producer sites, nearest node to each cell centre."""
    columns, rows = PRODUCER_GRID
    used: set[int] = set()
    block_to_node: list[int] = []
    for row in range(rows):
        for column in range(columns):
            centre_x = (column + 0.5) / columns
            centre_y = (row + 0.5) / rows
            ranked = sorted(
                range(network.node_count),
                key=lambda node: (
                    math.hypot(
                        network.positions[node][0] - centre_x,
                        network.positions[node][1] - centre_y,
                    ),
                    node,
                ),
            )
            chosen = next(node for node in ranked if node not in used)
            used.add(chosen)
            block_to_node.append(chosen)

    node_to_block = [-1] * network.node_count
    for block, node in enumerate(block_to_node):
        node_to_block[node] = block
    return ProducerPlacement(tuple(block_to_node), tuple(node_to_block))


def path_nodes(network: PhysicalNetwork, source: int, target: int) -> list[int]:
    if source == target:
        return [source]
    nodes = [source]
    node = source
    while node != target:
        step = network.next_hop[node][target]
        if step < 0:
            return []
        nodes.append(step)
        node = step
    return nodes


def pair_table(
    network: PhysicalNetwork,
    network_after: PhysicalNetwork,
    failure_link: int,
    placement: ProducerPlacement,
) -> list[list[PairInfo]]:
    """Affected/latency/switch facts for every consumer x producer block."""
    before = network.distance_ms
    after = network_after.distance_ms
    table: list[list[PairInfo]] = []
    for consumer in range(network.node_count):
        row = []
        for block, origin in enumerate(placement.block_to_node):
            nodes = path_nodes(network, consumer, origin)
            affected = False
            switch = consumer
            for index in range(len(nodes) - 1):
                link = network.link_between(nodes[index], nodes[index + 1])
                if link == failure_link:
                    affected = True
                    switch = nodes[index]
                    break
            latency_before = before[consumer][origin]
            latency_after = after[consumer][origin]
            if not math.isfinite(latency_after):
                latency_after = latency_before
            row.append(
                PairInfo(
                    affected=affected,
                    before_latency_ms=latency_before + QUEUE_MS_PER_HOP * network.hops[consumer][origin],
                    after_latency_ms=latency_after + QUEUE_MS_PER_HOP * network_after.hops[consumer][origin],
                    hops_before=network.hops[consumer][origin],
                    switch_node=switch,
                )
            )
        table.append(row)
    return table


def leg_table(
    network: PhysicalNetwork,
    network_after: PhysicalNetwork,
    failure_link: int,
) -> tuple[list[list[bool]], list[list[float]], list[list[float]]]:
    """Affected flag plus before/after latency for every ordered node pair."""
    count = network.node_count
    affected = [[False] * count for _ in range(count)]
    latency_before = [[0.0] * count for _ in range(count)]
    latency_after = [[0.0] * count for _ in range(count)]
    for a in range(count):
        for b in range(count):
            if a == b:
                continue
            latency_before[a][b] = (
                network.distance_ms[a][b] + QUEUE_MS_PER_HOP * network.hops[a][b]
            )
            latency_after[a][b] = (
                network_after.distance_ms[a][b]
                + QUEUE_MS_PER_HOP * network_after.hops[a][b]
            )
            affected[a][b] = failure_link in network.path_links(a, b)
    return affected, latency_before, latency_after


def generate_requests(seed: int) -> list[tuple[float, int, int]]:
    """Poisson request stream: (time, consumer, name index)."""
    rng = random.Random(seed * 7919 + 13)
    requests: list[tuple[float, int, int]] = []
    time_s = 0.0
    while True:
        time_s += rng.expovariate(REQUEST_RATE)
        if time_s >= SIM_SECONDS:
            break
        requests.append((time_s, rng.randrange(NODE_COUNT), rng.randrange(NAME_COUNT)))
    return requests


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    rank = fraction * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _evaluate(
    strategy: str,
    requests: list[tuple[float, int, int]],
    network: PhysicalNetwork,
    table: list[list[PairInfo]],
    placement: ProducerPlacement,
    plans: dict[str, object],
    leg_affected: list[list[bool]],
    leg_latency_before: list[list[float]],
    leg_latency_after: list[list[float]],
    rng: random.Random,
) -> tuple[float, float, float]:
    """Return (CDR %, p95 latency ms, 99th-percentile reconvergence s)."""
    delivered_latencies: list[float] = []
    pending_success: list[float] = []
    delivered = 0

    if strategy == "nlsr":
        plan: nlsr.NlsrPlan = plans["nlsr"]  # type: ignore[assignment]
    elif strategy == "fsr":
        plan = plans["fsr"]  # type: ignore[assignment]
    elif strategy == "tndn":
        plan = plans["tndn"]  # type: ignore[assignment]
    else:
        plan = plans["fisheye"]  # type: ignore[assignment]

    for time_s, consumer, name in requests:
        block = name // NAMES_PER_PRODUCER
        producer_node = placement.block_to_node[block]
        if strategy == "fisheye":
            overlay: fisheye.FisheyePlan = plan  # type: ignore[assignment]
            peer = overlay.peer_for_bucket(consumer, name)
            base_ms = (
                leg_latency_before[consumer][peer]
                + leg_latency_before[peer][producer_node]
            )
            affected = (
                leg_affected[consumer][peer] or leg_affected[peer][producer_node]
            )
        else:
            info = table[consumer][block]
            base_ms = info.before_latency_ms
            affected = info.affected

        if not affected:
            delivered += 1
            delivered_latencies.append(base_ms)
            continue

        if strategy == "fisheye":
            recovery_s = overlay.recovery_s(rng)
            after_ms = (
                leg_latency_after[consumer][peer]
                + leg_latency_after[peer][producer_node]
            )
        elif strategy == "nlsr":
            recovery_s = plan.recovery_s(0, block)
            after_ms = table[consumer][block].after_latency_ms
        elif strategy == "fsr":
            recovery_s = plan.recovery_s(network, consumer, block, rng)
            after_ms = table[consumer][block].after_latency_ms
        else:
            switch = table[consumer][block].switch_node
            recovery_s = plan.recovery_s(switch, block)  # type: ignore[union-attr]
            after_ms = table[consumer][block].after_latency_ms

        recover_at = FAILURE_S + recovery_s
        if FAILURE_S <= time_s < FAILURE_S + INTEREST_LIFETIME_S:
            # A pending request is one that needs the failed route: issued while
            # the outage is unresolved.  Reconvergence is the time from the
            # failure until a usable route exists again, independent of when
            # that particular request arrived; delivery is scored separately
            # against the Interest lifetime.
            pending_success.append(recover_at)
        if time_s < FAILURE_S and time_s + base_ms / 1000.0 <= FAILURE_S:
            delivered += 1
            delivered_latencies.append(base_ms)
            continue

        if time_s >= recover_at:
            delivered += 1
            delivered_latencies.append(after_ms)
            continue

        if time_s + INTEREST_LIFETIME_S >= recover_at:
            delivered += 1
            delivered_latencies.append((recover_at - time_s) * 1000.0 + after_ms)
        # else: dropped

    cdr = 100.0 * delivered / len(requests)
    p95 = percentile(delivered_latencies, 0.95)
    convergence = 0.0
    if pending_success:
        convergence = max(0.0, percentile(pending_success, 0.99) - FAILURE_S)
    return cdr, p95, convergence


def run_seed(seed: int, analysis: Analysis) -> SeedResult:
    network = PhysicalNetwork(seed=seed)
    placement = producer_placement(network)
    failure_link = network.choose_failure_link()
    network_after = network.without_link(failure_link)
    table = pair_table(network, network_after, failure_link, placement)
    leg_affected, leg_latency_before, leg_latency_after = leg_table(
        network, network_after, failure_link
    )
    requests = generate_requests(seed)

    plans: dict[str, object] = {
        "nlsr": nlsr.build(
            network, list(placement.block_to_node), after_network=network_after
        ),
        "fsr": fsr.build(network, list(placement.block_to_node)),
        "fisheye": fisheye.build(network, seed=seed),
        "tndn": tndn.build(network, analysis, list(placement.block_to_node)),
    }

    fib_mean = {
        "nlsr": nlsr.fib_mean(plans["nlsr"]),  # type: ignore[arg-type]
        "fsr": fsr.fib_mean(plans["fsr"]),  # type: ignore[arg-type]
        "fisheye": fisheye.fib_mean(plans["fisheye"]),  # type: ignore[arg-type]
        "tndn": plans["tndn"].fib_mean(),  # type: ignore[union-attr]
    }

    convergence: dict[str, float] = {}
    cdr: dict[str, float] = {}
    p95: dict[str, float] = {}
    for strategy, strategy_seed in zip(
        STRATEGIES, (seed * 31 + 1, seed * 31 + 2, seed * 31 + 3, seed * 31 + 4)
    ):
        rng = random.Random(strategy_seed)
        cdr_value, p95_value, convergence_value = _evaluate(
            strategy,
            requests,
            network,
            table,
            placement,
            plans,
            leg_affected,
            leg_latency_before,
            leg_latency_after,
            rng,
        )
        cdr[strategy] = cdr_value
        p95[strategy] = p95_value
        convergence[strategy] = convergence_value

    total_pairs = NODE_COUNT * PRODUCER_COUNT
    affected_pairs = sum(
        1 for row in table for info in row if info.affected
    )

    return SeedResult(
        seed=seed,
        failure_s=FAILURE_S,
        failure_link=failure_link,
        fib_mean=fib_mean,
        convergence_p99_s=convergence,
        cdr_percent=cdr,
        p95_latency_ms=p95,
        tda_ms=analysis.time_ms,
        tda_core_ms=analysis.persistence_ms,
        requests=len(requests),
        affected_fraction=affected_pairs / total_pairs,
    )
