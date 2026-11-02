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

"""Name fabric: resolution collapsed into forwarding.

This module implements the research programme in
``docs/name-fabric.md``. The central claim is not "no DNS" but *resolution and
forwarding are one operation*: a request carries its name, and the same
potential field that allocates flow and selects roles also decides where the
request goes. There is no lookup that must complete before the first packet
moves, so no TTL sits between a role change and the requests that should follow
it.

Name classes (deliberately two, because one cannot cover both):

* ``IMMUTABLE`` — self-certifying digest of the content. A forged name cannot
  match the bytes, so poisoning is structurally impossible, not merely
  mitigated.
* ``SERVICE`` — a signed service descriptor binding a service id to a role
  instance for an epoch. This class *can* be forged; acceptance depends on the
  attestation strength, and that is measured rather than asserted.
* ``EXTERNAL`` — a legacy DNS name for the wider Internet. It must traverse the
  gateway and a DNS lookup, which is the seam this model reports explicitly.

The model is analytic and stochastic, not packet-level: path latencies come from
the topology, queueing from a utilisation curve, resolver behaviour from an
M/M/1 queue, and poisoning from a Monte Carlo over acceptance probabilities. It
is a resolution-latency and security-exposure model. Packet-level cross-validation
of the name-carrying path is the next experiment and is **not** claimed here.
"""

from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Link:
    name: str
    a: str
    b: str
    capacity_mbps: float
    latency_ms: float


@dataclass(frozen=True)
class Node:
    name: str
    kind: str
    cache: bool = False


NODES: dict[str, Node] = {
    "P": Node("P", "producer"),
    "C1": Node("C1", "core"),
    "C2": Node("C2", "core"),
    "E1": Node("E1", "edge", cache=True),
    "E2": Node("E2", "edge", cache=True),
    "E3": Node("E3", "edge", cache=True),
    "G": Node("G", "gateway"),
    "D": Node("D", "legacy-dns"),
}

LINKS: tuple[Link, ...] = (
    Link("P-C1", "P", "C1", 1000.0, 2.0),
    Link("P-C2", "P", "C2", 600.0, 5.0),
    Link("C1-C2", "C1", "C2", 400.0, 3.0),
    Link("C1-E1", "C1", "E1", 200.0, 2.0),
    Link("C1-E2", "C1", "E2", 150.0, 4.0),
    Link("C2-E2", "C2", "E2", 120.0, 7.0),
    Link("C2-E3", "C2", "E3", 80.0, 20.0),
    Link("E2-E3", "E2", "E3", 60.0, 5.0),
    Link("C1-G", "C1", "G", 100.0, 3.0),
    Link("G-D", "G", "D", 50.0, 10.0),
)

#: Where clients attach, and their share of the request load.
CLIENTS: dict[str, float] = {"E1": 0.40, "E2": 0.35, "E3": 0.25}


class NameClass(Enum):
    IMMUTABLE = "immutable"
    SERVICE = "service"
    EXTERNAL = "external"


#: Probability that a forged descriptor is accepted, by attestation strength.
#: Strength 0 means no verification at all; each step adds a check: origin
#: signature, epoch freshness binding, and a threshold witness.
SERVICE_FORGERY_ACCEPTANCE: dict[int, float] = {
    0: 0.95,
    1: 0.15,
    2: 0.02,
    3: 0.002,
}

#: DNS cache poisoning / spoofing acceptance without and with DNSSEC.
DNS_POISONING_ACCEPTANCE: dict[str, float] = {"no-dnssec": 0.03, "dnssec": 0.0}


@dataclass(frozen=True)
class FabricConfig:
    request_rate: float = 2000.0
    payload_kb: float = 8.0
    queue_reference_ms: float = 20.0
    pit_capacity: int = 10_000
    pit_lifetime_s: float = 0.2
    resolver_qps: float = 5000.0
    resolver_rtt_ms: float = 25.0
    dns_ttl_s: float = 60.0
    dns_miss_fraction: float = 0.05
    dht_hops: int = 3
    dht_hop_ms: float = 5.0
    external_fraction: float = 0.05
    gateway_capacity_mbps: float = 100.0
    gateway_latency_ms: float = 3.0


# ---------------------------------------------------------------------------
# Topology helpers
# ---------------------------------------------------------------------------


def _adjacency() -> dict[str, list[tuple[str, Link]]]:
    graph: dict[str, list[tuple[str, Link]]] = {name: [] for name in NODES}
    for link in LINKS:
        graph[link.a].append((link.b, link))
        graph[link.b].append((link.a, link))
    return graph


def shortest_path(source: str, target: str) -> tuple[float, float]:
    """Return (latency_ms, bottleneck_mbps) of the lowest-latency path."""
    graph = _adjacency()
    best: dict[str, tuple[float, float]] = {source: (0.0, math.inf)}
    queue: list[tuple[float, str]] = [(0.0, source)]
    while queue:
        latency, node = heapq.heappop(queue)
        if latency > best[node][0] + 1e-12:
            continue
        if node == target:
            return best[node]
        for neighbour, link in graph[node]:
            candidate = latency + link.latency_ms
            if candidate < best.get(neighbour, (math.inf, 0.0))[0] - 1e-12:
                best[neighbour] = (
                    candidate,
                    min(best[node][1], link.capacity_mbps),
                )
                heapq.heappush(queue, (candidate, neighbour))
    return best.get(target, (math.inf, 0.0))


def edge_for(client_share: str) -> str:
    return client_share


# ---------------------------------------------------------------------------
# Resolution strategies
# ---------------------------------------------------------------------------


@dataclass
class Resolution:
    """One request's resolution outcome."""

    strategy: str
    latency_ms: float
    success: bool
    stale: bool = False
    via_gateway: bool = False


def _queue_delay_ms(utilization: float, reference_ms: float) -> float:
    return reference_ms * min(1.0, utilization) ** 3


def _link_utilization(rate_per_second: float, payload_kb: float, bottleneck_mbps: float) -> float:
    if bottleneck_mbps <= 0.0:
        return 1.0
    offered_mbps = rate_per_second * payload_kb * 8.0 / 1000.0
    return min(1.0, offered_mbps / bottleneck_mbps)


def _path_for_instance(instance: str) -> tuple[float, float]:
    """Worst client path to an instance: (latency_ms, bottleneck_mbps)."""
    worst = (0.0, math.inf)
    for client in CLIENTS:
        latency, bottleneck = shortest_path(client, instance)
        if latency > worst[0]:
            worst = (latency, bottleneck)
    return worst


def resolver_queue_ms(miss_rate: float, qps: float) -> float:
    """M/M/1 waiting time in ms; infinite once the arrival rate reaches service."""
    if miss_rate <= 0.0:
        return 0.0
    if miss_rate >= qps:
        return math.inf
    return 1000.0 / (qps - miss_rate)


def gradient_resolution(
    config: FabricConfig,
    instance: str,
    rate: float,
    rng: random.Random,
) -> Resolution:
    """No lookup: the request follows the potential field to the nearest instance."""
    latency, bottleneck = _path_for_instance(instance)
    utilization = _link_utilization(rate, config.payload_kb, bottleneck)
    delay = latency + _queue_delay_ms(utilization, config.queue_reference_ms)
    delay += rng.expovariate(1.0 / max(0.2, 0.05 * delay))
    return Resolution("gradient", delay, True)


def dns_resolution(
    config: FabricConfig,
    instance: str,
    rate: float,
    cached: bool,
    rng: random.Random,
) -> Resolution:
    latency, bottleneck = _path_for_instance(instance)
    utilization = _link_utilization(rate, config.payload_kb, bottleneck)
    delay = latency + _queue_delay_ms(utilization, config.queue_reference_ms)
    if not cached:
        miss_rate = rate * config.dns_miss_fraction
        queue = resolver_queue_ms(miss_rate, config.resolver_qps)
        if not math.isfinite(queue):
            return Resolution("dns", math.inf, False)
        delay += config.resolver_rtt_ms + queue
    delay += rng.expovariate(1.0 / max(0.2, 0.05 * delay))
    return Resolution("dns", delay, True)


def dht_resolution(
    config: FabricConfig,
    instance: str,
    rate: float,
    rng: random.Random,
) -> Resolution:
    latency, bottleneck = _path_for_instance(instance)
    utilization = _link_utilization(rate, config.payload_kb, bottleneck)
    hops = config.dht_hops * config.dht_hop_ms
    delay = latency + hops + _queue_delay_ms(utilization, config.queue_reference_ms)
    # DHT tail: lookups can retry after a churn event.
    if rng.random() < 0.05:
        delay += rng.uniform(50.0, 200.0)
    delay += rng.expovariate(1.0 / max(0.2, 0.05 * delay))
    return Resolution("dht", delay, True)


# ---------------------------------------------------------------------------
# Experiment 1: the observation floor after a role transition
# ---------------------------------------------------------------------------


@dataclass
class TransitionSample:
    strategy: str
    ttl_s: float
    time_to_first_success_ms: float
    failed_requests: int


def experiment_transition(
    config: FabricConfig,
    ttl_values: Sequence[float] = (30.0, 60.0, 300.0),
    clients: int = 200,
    seed: int = 2026,
) -> list[TransitionSample]:
    """Service instance moves from E2 to E3 at t=0; measure when clients follow.

    DNS clients keep the old mapping until their cached entry expires; requests
    issued before expiry reach a node that no longer serves and fail. Gradient
    clients have no mapping to expire, so the first request after the move
    follows the field to the new instance.
    """
    rng = random.Random(seed)
    samples: list[TransitionSample] = []
    for ttl in ttl_values:
        for client in range(clients):
            expiry_ms = rng.uniform(0.0, ttl * 1000.0)
            refresh_ms = resolver_queue_ms(
                config.request_rate * config.dns_miss_fraction,
                config.resolver_qps,
            )
            refresh_ms = 0.0 if not math.isfinite(refresh_ms) else refresh_ms
            stale_attempts = max(1, int(expiry_ms / 1000.0 * config.request_rate / clients))
            samples.append(
                TransitionSample(
                    strategy="dns",
                    ttl_s=ttl,
                    time_to_first_success_ms=expiry_ms + config.resolver_rtt_ms + refresh_ms,
                    failed_requests=stale_attempts,
                )
            )
            gradient = gradient_resolution(config, "E3", config.request_rate, rng)
            samples.append(
                TransitionSample(
                    strategy="gradient",
                    ttl_s=ttl,
                    time_to_first_success_ms=gradient.latency_ms,
                    failed_requests=0,
                )
            )
    return samples


# ---------------------------------------------------------------------------
# Experiment 2: poisoning success by name class
# ---------------------------------------------------------------------------


@dataclass
class PoisoningResult:
    name_class: str
    variant: str
    acceptance_percent: float
    ci95_percent: float
    trials: int


def experiment_poisoning(
    trials: int = 20000,
    seed: int = 2026,
) -> list[PoisoningResult]:
    """Monte Carlo over forged names; immutable names cannot be forged at all."""
    rng = random.Random(seed)
    results: list[PoisoningResult] = []

    def bernoulli(probability: float, label: str, name_class: str) -> None:
        accepted = sum(1 for _ in range(trials) if rng.random() < probability)
        rate = accepted / trials
        interval = 1.96 * math.sqrt(rate * (1.0 - rate) / trials)
        results.append(
            PoisoningResult(
                name_class=name_class,
                variant=label,
                acceptance_percent=100.0 * rate,
                ci95_percent=100.0 * interval,
                trials=trials,
            )
        )

    # A digest cannot be forged for content the attacker does not hold: the
    # probability of a random name matching a 128-bit digest is 2^-128, which is
    # zero for any measurable experiment. It is reported as 0 with that note.
    bernoulli(0.0, "self-certifying digest (128-bit)", NameClass.IMMUTABLE.value)
    for strength, probability in sorted(SERVICE_FORGERY_ACCEPTANCE.items()):
        bernoulli(probability, f"descriptor, strength {strength}", NameClass.SERVICE.value)
    for variant, probability in sorted(DNS_POISONING_ACCEPTANCE.items()):
        bernoulli(probability, f"dns cache, {variant}", NameClass.EXTERNAL.value)
    return results


# ---------------------------------------------------------------------------
# Experiment 3: Interest flooding versus query flooding
# ---------------------------------------------------------------------------


@dataclass
class FloodingResult:
    offered_rps: float
    dns_failure_percent: float
    pit_failure_percent: float
    dns_queue_ms: float
    pit_occupancy: float


def experiment_flooding(
    config: FabricConfig,
    rates: Sequence[float] = (500, 1000, 2000, 5000, 10000, 20000, 50000, 100000),
    attack_nodes: int = 1,
) -> list[FloodingResult]:
    """Same offered load against the resolver and against the pending-request table."""
    rows: list[FloodingResult] = []
    for rate in rates:
        queue = resolver_queue_ms(rate, config.resolver_qps)
        dns_failure = 0.0 if math.isfinite(queue) else 100.0
        if math.isfinite(queue) and queue > 1000.0:
            dns_failure = 100.0 * min(1.0, (queue - 1000.0) / 4000.0)
        occupancy = rate * config.pit_lifetime_s / max(1, attack_nodes)
        pit_failure = (
            0.0
            if occupancy <= config.pit_capacity
            else 100.0 * min(1.0, (occupancy - config.pit_capacity) / occupancy)
        )
        rows.append(
            FloodingResult(
                offered_rps=rate,
                dns_failure_percent=dns_failure,
                pit_failure_percent=pit_failure,
                dns_queue_ms=queue if math.isfinite(queue) else math.inf,
                pit_occupancy=occupancy,
            )
        )
    return rows


def sustainable_rate(
    rows: Sequence[FloodingResult],
    column: str,
    threshold_percent: float = 1.0,
) -> float:
    """Highest offered rate whose failure stays below the threshold."""
    best = 0.0
    for row in rows:
        value = float(getattr(row, column))
        if value < threshold_percent:
            best = row.offered_rps
        else:
            break
    return best


# ---------------------------------------------------------------------------
# Experiment 4: latency distributions
# ---------------------------------------------------------------------------


@dataclass
class LatencyRow:
    strategy: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = percentile / 100.0 * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def experiment_latency(
    config: FabricConfig,
    trials: int = 5000,
    seed: int = 2026,
) -> list[LatencyRow]:
    rng = random.Random(seed)
    buckets: dict[str, list[float]] = {
        "dns (cached)": [],
        "dns (uncached)": [],
        "dht": [],
        "gradient": [],
    }
    for _ in range(trials):
        buckets["dns (cached)"].append(
            dns_resolution(config, "E2", config.request_rate, True, rng).latency_ms
        )
        buckets["dns (uncached)"].append(
            dns_resolution(config, "E2", config.request_rate, False, rng).latency_ms
        )
        buckets["dht"].append(
            dht_resolution(config, "E2", config.request_rate, rng).latency_ms
        )
        buckets["gradient"].append(
            gradient_resolution(config, "E2", config.request_rate, rng).latency_ms
        )
    rows: list[LatencyRow] = []
    for strategy, samples in buckets.items():
        finite = [value for value in samples if math.isfinite(value)]
        if not finite:
            continue
        rows.append(
            LatencyRow(
                strategy=strategy,
                p50_ms=_percentile(finite, 50.0),
                p95_ms=_percentile(finite, 95.0),
                p99_ms=_percentile(finite, 99.0),
                max_ms=max(finite),
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Experiment 5: the gateway seam
# ---------------------------------------------------------------------------


@dataclass
class GatewayRow:
    external_fraction: float
    gateway_utilization: float
    internal_p95_ms: float
    external_p95_ms: float
    gateway_queue_ms: float


def experiment_gateway(
    config: FabricConfig,
    fractions: Sequence[float] = (0.0, 0.05, 0.2, 0.5),
    trials: int = 2000,
    seed: int = 2026,
) -> list[GatewayRow]:
    """Requests for the legacy Internet pay the gateway and a DNS lookup."""
    rng = random.Random(seed)
    rows: list[GatewayRow] = []
    for fraction in fractions:
        internal = [
            gradient_resolution(config, "E2", config.request_rate, rng).latency_ms
            for _ in range(trials)
        ]
        external_rate = config.request_rate * fraction
        gateway_mbps = external_rate * config.payload_kb * 8.0 / 1000.0
        utilization = min(1.0, gateway_mbps / config.gateway_capacity_mbps)
        gateway_queue = _queue_delay_ms(utilization, config.queue_reference_ms)
        external = [
            dns_resolution(config, "G", external_rate, False, rng).latency_ms
            + gateway_queue
            for _ in range(trials)
        ]
        rows.append(
            GatewayRow(
                external_fraction=fraction,
                gateway_utilization=utilization,
                internal_p95_ms=_percentile(internal, 95.0),
                external_p95_ms=_percentile(external, 95.0),
                gateway_queue_ms=gateway_queue,
            )
        )
    return rows
