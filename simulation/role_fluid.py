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

"""Role-fluid multipath paradigm: potential-field flow with local role selection.

This module implements the paradigm described in ``docs/role-fluid-paradigm.md``,
not the earlier predictive-scheduling hypothesis. Two physical metaphors
motivate the controller and are kept separate on purpose:

* **Water overflowing a river** — flow distributes over the available paths in
  proportion to a potential gradient, and excess above a path's capacity spills
  onto the alternatives. This is the *scheduler* rule: local water-filling with
  no forecast.
* **Seismic waves crossing the crust** — at every medium boundary energy
  partitions into transmitted and reflected components. The transmission
  coefficient is the fraction of the packet that fits the next medium's MTU;
  the reflected part is requeued. This is the *boundary* rule, where
  heterogeneous fragmentation becomes a first-class effect.

A node is not fixed to a role. At each control interval it may be a ``forward``
router, a ``balance`` load balancer, or a ``serve`` cache/server, chosen from a
local potential that trades incident congestion, operating cost, and the
amortised cost of switching. Because paths terminate at nodes that may become
servers, path selection and role selection are the same optimisation: choosing
a path chooses what the node at its end should become.

What this model is and is not:

* It is a *model-level* simulator. It is not a protocol implementation: no
  packets on a wire, no ACK clock, no retransmission, no MPTCP scheduler.
  Results are conditional on the stipulated topology, costs and demand.
* It is **not** cross-validated against ns-3. The transport cross-validation in
  ``docs/external-validation.md`` covers a different (two-path, fixed-role)
  scenario; extending it to role transitions is the next experiment.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

ORIGIN = "O"
ROLES: tuple[str, ...] = ("forward", "balance", "serve")
DEFAULT_TICKS = 120
CONTROL_INTERVAL = 5

#: Reference values that make the potential terms dimensionless.
LATENCY_REFERENCE_MS = 25.0
COST_REFERENCE_PER_GB = 2.0

#: Cache-hit latency and per-transit serve overhead, milliseconds.
LOCAL_SERVE_LATENCY_MS = 2.0
SERVE_LATENCY_MS = 5.0

#: Queueing delay: queue_ms = QUEUE_REFERENCE_MS * utilization**3.
QUEUE_REFERENCE_MS = 20.0

#: Monetary parameters in US dollars. One tick is one simulated second.
UNMET_PENALTY_PER_GB = 10.0
CONGESTION_VALUE_USD_PER_TICK = 0.10
GB_PER_MBPS_TICK = 1.0 / 8000.0

POLICIES: tuple[str, ...] = (
    "static_design",
    "centralized_greedy",
    "local_fluid",
    "local_congestion",
    "local_reactive",
)


@dataclass(frozen=True)
class Link:
    """One backhaul link with a medium-specific profile."""

    name: str
    a: str
    b: str
    capacity_mbps: float
    latency_ms: float
    mtu_bytes: int
    loss: float
    cost_per_gb: float


@dataclass(frozen=True)
class Node:
    """A polymorphic node. ``service_capacity_mbps`` bounds the serve role."""

    name: str
    service_capacity_mbps: float = 0.0
    serve_cost_per_gb: float = 6.0
    fill_cost_per_gb: float = 3.0
    switch_cost_usd: float = 0.05
    balance_cost_usd_per_tick: float = 0.01


@dataclass(frozen=True)
class Path:
    """One simple origin-to-demand-node path."""

    target: str
    nodes: tuple[str, ...]
    links: tuple[Link, ...]
    capacity_mbps: float
    latency_ms: float
    loss: float
    cost_per_gb: float
    fragment_factor: float


@dataclass(frozen=True)
class Scenario:
    """Demand and link-availability schedule for one experiment."""

    key: str
    title: str
    demand: Callable[[int], Mapping[str, float]]
    link_scale: Callable[[int, str], float] = lambda _tick, _link: 1.0
    ticks: int = DEFAULT_TICKS


@dataclass(frozen=True)
class FlowWeights:
    """Controller parameters. ``damping=1.0`` means no memory (unstable)."""

    temperature: float = 0.45
    w_congestion: float = 1.0
    w_latency: float = 0.6
    w_fragment: float = 0.4
    w_cost: float = 0.3
    damping: float = 0.5
    hysteresis_usd: float = 0.004
    switch_horizon_ticks: int = 20
    serve_attraction: float = 0.9
    balance_impedance: float = 0.75
    w_balance_bonus: float = 0.15


DEFAULT_WEIGHTS = FlowWeights()


@dataclass
class RunMetrics:
    """Per-replicate outcome of one controller on one scenario."""

    delivered_percent: float
    p95_latency_ms: float
    total_cost_usd: float
    role_switches: int
    oscillation_index: float
    local_serve_percent: float
    cache_fill_gb: float


@dataclass
class _LatencyEntry:
    """A delivered volume whose delay is resolved after all loads are final."""

    start: int
    end: int
    amount_mbps: float
    extra_ms: float


@dataclass
class _Allocation:
    link_load: dict[str, float]
    served_gb: dict[str, float]
    share: dict[tuple[str, int], float]
    delivered_mbps: dict[str, float]
    latency_samples: list[tuple[float, float]]
    link_cost: float
    serve_cost: float
    fill_cost: float
    unmet_gb: float
    unmet_fraction: dict[str, float]
    oscillation: float


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


def build_nodes() -> dict[str, Node]:
    """Six polymorphic nodes: one origin, two cores, three edge caches."""
    return {
        "O": Node("O"),
        "C1": Node("C1", service_capacity_mbps=30.0),
        "C2": Node("C2", service_capacity_mbps=30.0),
        "E1": Node("E1", service_capacity_mbps=40.0),
        "E2": Node("E2", service_capacity_mbps=60.0),
        "E3": Node("E3", service_capacity_mbps=40.0),
    }


def build_links() -> tuple[Link, ...]:
    """Heterogeneous backhauls: fibre, microwave, Wi-Fi, satellite."""
    return (
        Link("O-C1", "O", "C1", 200.0, 2.0, 9000, 0.0005, 0.5),
        Link("O-C2", "O", "C2", 80.0, 6.0, 1500, 0.0020, 1.2),
        Link("C1-C2", "C1", "C2", 100.0, 3.0, 9000, 0.0005, 0.6),
        Link("C1-E1", "C1", "E1", 60.0, 2.0, 1500, 0.0010, 0.8),
        Link("C1-E2", "C1", "E2", 50.0, 4.0, 1200, 0.0050, 1.5),
        Link("C2-E2", "C2", "E2", 40.0, 7.0, 1500, 0.0040, 1.2),
        Link("C2-E3", "C2", "E3", 25.0, 25.0, 1200, 0.0100, 4.0),
        Link("E1-E2", "E1", "E2", 30.0, 3.0, 1500, 0.0020, 0.9),
        Link("E2-E3", "E2", "E3", 20.0, 5.0, 1200, 0.0030, 1.1),
    )


def build_paths(
    nodes: Mapping[str, Node],
    links: Sequence[Link],
    targets: Sequence[str] = ("E1", "E2", "E3"),
) -> dict[str, tuple[Path, ...]]:
    """Enumerate every simple origin-to-target path with a medium-aware profile."""
    neighbours: dict[str, list[tuple[str, Link]]] = {name: [] for name in nodes}
    for link in links:
        neighbours[link.a].append((link.b, link))
        neighbours[link.b].append((link.a, link))

    paths: dict[str, tuple[Path, ...]] = {}
    for target in targets:
        found: list[Path] = []

        def walk(current: str, visited: tuple[str, ...], chain: tuple[Link, ...]) -> None:
            if current == target:
                found.append(_make_path(target, visited, chain))
                return
            for neighbour, link in neighbours[current]:
                if neighbour in visited:
                    continue
                walk(neighbour, visited + (neighbour,), chain + (link,))

        walk(ORIGIN, (ORIGIN,), ())
        found.sort(key=lambda path: (path.latency_ms, path.cost_per_gb, path.nodes))
        paths[target] = tuple(found)
    return paths


def _make_path(target: str, node_names: tuple[str, ...], links: tuple[Link, ...]) -> Path:
    capacity = min(link.capacity_mbps for link in links)
    latency = sum(link.latency_ms for link in links)
    loss = 1.0 - math.prod(1.0 - link.loss for link in links)
    cost = sum(link.cost_per_gb for link in links)
    # The transmission coefficient at a medium boundary is bounded by the MTU
    # ratio: a 1200-byte link costs 25 % more per byte than a 1500-byte link.
    fragment_factor = max(1.0, max(1500.0 / link.mtu_bytes for link in links))
    return Path(
        target=target,
        nodes=node_names,
        links=links,
        capacity_mbps=capacity / fragment_factor,
        latency_ms=latency,
        loss=loss,
        cost_per_gb=cost,
        fragment_factor=fragment_factor,
    )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def _steady(_tick: int) -> Mapping[str, float]:
    return {"E1": 40.0, "E2": 50.0, "E3": 30.0}


def _flash_crowd(tick: int) -> Mapping[str, float]:
    total = 120.0 + (140.0 if 40 <= tick < 80 else 0.0)
    return {"E1": 0.33 * total, "E2": 0.42 * total, "E3": 0.25 * total}


def _backhaul_outage(tick: int, link: str) -> float:
    if 50 <= tick < 90 and link in {"O-C1", "C1-E2"}:
        return 0.1
    return 1.0


SCENARIOS: dict[str, Scenario] = {
    "steady": Scenario(
        "steady",
        "Steady demand across fibre, microwave and satellite",
        _steady,
    ),
    "flash_crowd": Scenario(
        "flash_crowd",
        "Edge flash crowd: demand more than doubles at t=40 s",
        _flash_crowd,
    ),
    "backhaul_outage": Scenario(
        "backhaul_outage",
        "Primary fibre and one microwave link degrade to 10 % at t=50 s",
        _steady,
        _backhaul_outage,
    ),
}


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


class RoleFluidSimulation:
    """Discrete-time simulation of role-fluid multipath flow."""

    def __init__(
        self,
        scenario: Scenario,
        policy: str,
        seed: int,
        weights: FlowWeights = DEFAULT_WEIGHTS,
        nodes: Mapping[str, Node] | None = None,
        links: Sequence[Link] | None = None,
    ) -> None:
        if policy not in POLICIES:
            raise ValueError(f"Unknown policy: {policy}")
        self.scenario = scenario
        self.policy = policy
        self.weights = weights
        self.nodes = dict(nodes or build_nodes())
        self.links = tuple(links or build_links())
        self.paths = build_paths(self.nodes, self.links)
        self.rng = random.Random(seed)
        self.roles: dict[str, str] = (
            self._static_roles()
            if policy == "static_design"
            else dict.fromkeys(self.nodes, "forward")
        )
        self.prev_link_load: dict[str, float] = {link.name: 0.0 for link in self.links}
        self.share: dict[tuple[str, int], float] = {}
        self.previous_served_gb: dict[str, float] = {name: 0.0 for name in self.nodes}
        self.unmet_fraction: dict[str, float] = {name: 0.0 for name in self.nodes}
        self.switches = 0
        self.cache_fill_gb = 0.0
        self.oscillation_total = 0.0
        self.oscillation_ticks = 0
        self._incident_capacity = self._build_incident_capacity()

    # -- public -----------------------------------------------------------

    def run(self) -> RunMetrics:
        delivered_samples: list[float] = []
        latency_samples: list[tuple[float, float]] = []
        total_cost = 0.0
        served_gb_total = 0.0
        transit_gb_total = 0.0

        for tick in range(self.scenario.ticks):
            demand = self._demand(tick)
            capacities = {
                link.name: link.capacity_mbps * self.scenario.link_scale(tick, link.name)
                for link in self.links
            }
            if tick % CONTROL_INTERVAL == 0:
                decided = self._decide_roles(demand, capacities)
                changed = [name for name in decided if decided[name] != self.roles[name]]
                self.switches += len(changed)
                total_cost += sum(self.nodes[name].switch_cost_usd for name in changed)
                self.roles = decided

            allocation = self._allocate(self.roles, demand, capacities)
            self._commit(allocation)

            delivered = sum(allocation.delivered_mbps.values())
            requested = sum(demand.values())
            delivered_samples.append(100.0 * delivered / max(1e-9, requested))
            latency_samples.extend(allocation.latency_samples)
            served_gb_total += sum(allocation.served_gb.values())
            transit_gb_total += sum(allocation.link_load.values()) * GB_PER_MBPS_TICK
            total_cost += (
                allocation.link_cost
                + allocation.serve_cost
                + allocation.fill_cost
                + allocation.unmet_gb * UNMET_PENALTY_PER_GB
                + self._balance_cost(self.roles)
            )

        mean_delivered = sum(delivered_samples) / len(delivered_samples) if delivered_samples else 0.0
        total_gb = served_gb_total + transit_gb_total
        return RunMetrics(
            delivered_percent=mean_delivered,
            p95_latency_ms=_weighted_p95(latency_samples),
            total_cost_usd=total_cost,
            role_switches=self.switches,
            oscillation_index=(
                self.oscillation_total / self.oscillation_ticks
                if self.oscillation_ticks
                else 0.0
            ),
            local_serve_percent=100.0 * served_gb_total / max(1e-9, total_gb),
            cache_fill_gb=self.cache_fill_gb,
        )

    # -- controllers ------------------------------------------------------

    def _decide_roles(
        self,
        demand: Mapping[str, float],
        capacities: Mapping[str, float],
    ) -> dict[str, str]:
        if self.policy == "static_design":
            return self._static_roles()
        if self.policy == "local_fluid":
            return self._local_roles(self.weights.hysteresis_usd, use_unmet=True)
        if self.policy == "local_congestion":
            return self._local_roles(self.weights.hysteresis_usd, use_unmet=False)
        if self.policy == "local_reactive":
            return self._local_roles(0.0, use_unmet=True)
        return self._centralized_roles(demand, capacities)

    def _static_roles(self) -> dict[str, str]:
        roles = {name: "forward" for name in self.nodes}
        roles["C1"] = "balance"
        roles["E2"] = "serve"
        roles["E3"] = "serve"
        return roles

    def _local_roles(self, hysteresis: float, use_unmet: bool) -> dict[str, str]:
        chosen: dict[str, str] = {}
        for name, node in self.nodes.items():
            if name == ORIGIN:
                chosen[name] = "forward"
                continue
            capacity = max(1e-9, self._incident_capacity.get(name, 0.0))
            utilization = min(1.0, self._incident_load(name) / capacity)
            best_role = self.roles[name]
            best_cost = self._local_role_cost(
                best_role, utilization, node, capacity, name, use_unmet
            )
            for role in ROLES:
                if role == "serve" and node.service_capacity_mbps <= 0.0:
                    continue
                cost = self._local_role_cost(
                    role, utilization, node, capacity, name, use_unmet
                )
                if cost < best_cost - hysteresis:
                    best_cost = cost
                    best_role = role
            chosen[name] = best_role
        return chosen

    def _local_role_cost(
        self,
        role: str,
        utilization: float,
        node: Node,
        incident_capacity: float,
        name: str,
        use_unmet: bool,
    ) -> float:
        switch = (
            0.0
            if role == self.roles[name]
            else node.switch_cost_usd / max(1, self.weights.switch_horizon_ticks)
        )
        if role == "serve":
            relief = self.weights.serve_attraction * min(
                1.0,
                node.service_capacity_mbps / incident_capacity,
            )
            operating = node.serve_cost_per_gb * node.service_capacity_mbps * GB_PER_MBPS_TICK
            avoided = 0.0
            if use_unmet:
                avoided = (
                    self.unmet_fraction.get(name, 0.0)
                    * UNMET_PENALTY_PER_GB
                    * node.service_capacity_mbps
                    * GB_PER_MBPS_TICK
                )
            return (
                utilization * (1.0 - relief) * CONGESTION_VALUE_USD_PER_TICK
                + operating
                + switch
                - avoided
            )
        if role == "balance":
            hot, spare = self._incident_utilization_range(name)
            relief = max(0.0, hot - spare) * self.weights.balance_impedance
            return (
                max(0.0, utilization - relief) * CONGESTION_VALUE_USD_PER_TICK
                + node.balance_cost_usd_per_tick
                + switch
            )
        return utilization * CONGESTION_VALUE_USD_PER_TICK + switch

    def _centralized_roles(
        self,
        demand: Mapping[str, float],
        capacities: Mapping[str, float],
    ) -> dict[str, str]:
        current = dict(self.roles)
        best_cost = self._objective(current, demand, capacities)
        for _ in range(2):
            improved = False
            for name, node in self.nodes.items():
                if name == ORIGIN:
                    continue
                for role in ROLES:
                    if role == current[name]:
                        continue
                    if role == "serve" and node.service_capacity_mbps <= 0.0:
                        continue
                    candidate = dict(current)
                    candidate[name] = role
                    cost = self._objective(candidate, demand, capacities)
                    if cost < best_cost - 1e-9:
                        best_cost = cost
                        current = candidate
                        improved = True
            if not improved:
                break
        return current

    def _objective(
        self,
        roles: Mapping[str, str],
        demand: Mapping[str, float],
        capacities: Mapping[str, float],
    ) -> float:
        allocation = self._allocate(roles, demand, capacities)
        switch_cost = sum(
            self.nodes[name].switch_cost_usd / max(1, self.weights.switch_horizon_ticks)
            for name, role in roles.items()
            if role != self.roles[name]
        )
        return (
            allocation.link_cost
            + allocation.serve_cost
            + allocation.fill_cost
            + allocation.unmet_gb * UNMET_PENALTY_PER_GB
            + self._balance_cost(roles)
            + switch_cost
        )

    def _balance_cost(self, roles: Mapping[str, str]) -> float:
        return sum(
            self.nodes[name].balance_cost_usd_per_tick
            for name, role in roles.items()
            if role == "balance"
        )

    # -- allocation -------------------------------------------------------

    def _allocate(
        self,
        roles: Mapping[str, str],
        demand: Mapping[str, float],
        capacities: Mapping[str, float],
    ) -> _Allocation:
        link_load = {link.name: 0.0 for link in self.links}
        served = {name: 0.0 for name in self.nodes}
        served_gb = {name: 0.0 for name in self.nodes}
        delivered = {target: 0.0 for target in demand}
        shares: dict[tuple[str, int], float] = {}
        latency_entries: list[tuple[Path, _LatencyEntry]] = []
        unmet_gb = 0.0
        unmet_fraction: dict[str, float] = {name: 0.0 for name in self.nodes}
        oscillation = 0.0

        for target in sorted(demand):
            paths = self.paths[target]
            potentials = [
                self._path_potential(path, capacities, roles) for path in paths
            ]
            raw = [math.exp(-potential / self.weights.temperature) for potential in potentials]
            raw_total = sum(raw)
            target_weights = [value / raw_total for value in raw]
            previous = [
                self.share.get((target, index), target_weights[index])
                for index in range(len(paths))
            ]
            damped = [
                (1.0 - self.weights.damping) * previous[index]
                + self.weights.damping * target_weights[index]
                for index in range(len(paths))
            ]
            damped_total = sum(damped)
            damped = [value / damped_total for value in damped]
            for index, value in enumerate(damped):
                shares[(target, index)] = value
            oscillation += 0.5 * sum(
                abs(damped[index] - previous[index]) for index in range(len(paths))
            )

            target_demand = demand[target]
            local = 0.0
            if roles.get(target) == "serve":
                room = max(0.0, self.nodes[target].service_capacity_mbps - served[target])
                local = min(target_demand, room)
                served[target] += local
                served_gb[target] += local * GB_PER_MBPS_TICK
                delivered[target] += local
            remaining = target_demand - local

            order = sorted(range(len(paths)), key=lambda index: potentials[index])
            allocation = {index: 0.0 for index in range(len(paths))}
            leftover = remaining
            for _ in range(3):
                active = [
                    index
                    for index in order
                    if damped[index] > 0.0
                    and leftover > 1e-9
                    and self._residual(paths[index], link_load, capacities) > 1e-9
                ]
                if not active:
                    break
                weight_total = sum(damped[index] for index in active)
                proposed = {index: leftover * damped[index] / weight_total for index in active}
                overflow = 0.0
                for index in active:
                    room = self._residual(paths[index], link_load, capacities)
                    take = min(proposed[index], room)
                    allocation[index] += take
                    for link in paths[index].links:
                        link_load[link.name] += take
                    overflow += proposed[index] - take
                leftover = overflow

            allocated = sum(allocation.values())
            missing = max(0.0, remaining - allocated)
            unmet_gb += missing * GB_PER_MBPS_TICK
            unmet_fraction[target] = missing / max(1e-9, target_demand)

            for index, amount in allocation.items():
                if amount <= 0.0:
                    continue
                path = paths[index]
                serve_index = self._serve_point(path, roles, served)
                served_part = 0.0
                if serve_index is not None:
                    node_name = path.nodes[serve_index]
                    room = max(
                        0.0,
                        self.nodes[node_name].service_capacity_mbps - served[node_name],
                    )
                    served_part = min(amount, room)
                    served[node_name] += served_part
                    served_gb[node_name] += served_part * GB_PER_MBPS_TICK
                    for link in path.links[serve_index:]:
                        link_load[link.name] = max(0.0, link_load[link.name] - served_part)
                transit = amount - served_part

                if served_part > 0.0:
                    cut = serve_index or 0
                    delivered[target] += served_part * _delivery(path, 0, cut)
                    latency_entries.append(
                        (path, _LatencyEntry(0, cut, served_part, SERVE_LATENCY_MS))
                    )
                if transit > 0.0:
                    delivered[target] += transit * _delivery(path, 0, len(path.links))
                    latency_entries.append(
                        (path, _LatencyEntry(0, len(path.links), transit, 0.0))
                    )

        latency_samples = [
            (
                self._path_latency(path, entry, link_load, capacities, roles),
                entry.amount_mbps,
            )
            for path, entry in latency_entries
        ]
        link_cost = sum(
            link_load[link.name] * GB_PER_MBPS_TICK * link.cost_per_gb for link in self.links
        )
        serve_cost = sum(
            served_gb[name] * self.nodes[name].serve_cost_per_gb for name in served_gb
        )
        fill_cost = sum(
            max(0.0, served_gb[name] - self.previous_served_gb.get(name, 0.0))
            * self.nodes[name].fill_cost_per_gb
            for name in served_gb
        )
        return _Allocation(
            link_load=link_load,
            served_gb=served_gb,
            share=shares,
            delivered_mbps=delivered,
            latency_samples=latency_samples,
            link_cost=link_cost,
            serve_cost=serve_cost,
            fill_cost=fill_cost,
            unmet_gb=unmet_gb,
            unmet_fraction=unmet_fraction,
            oscillation=oscillation,
        )

    def _serve_point(
        self,
        path: Path,
        roles: Mapping[str, str],
        served: Mapping[str, float],
    ) -> int | None:
        for index in range(len(path.nodes) - 2, 0, -1):
            name = path.nodes[index]
            if (
                roles.get(name) == "serve"
                and served.get(name, 0.0) < self.nodes[name].service_capacity_mbps - 1e-9
            ):
                return index
        return None

    def _path_latency(
        self,
        path: Path,
        entry: _LatencyEntry,
        link_load: Mapping[str, float],
        capacities: Mapping[str, float],
        roles: Mapping[str, str],
    ) -> float:
        total = entry.extra_ms
        for link in path.links[entry.start : entry.end]:
            utilization = min(1.0, link_load[link.name] / max(1e-9, capacities[link.name]))
            queue = QUEUE_REFERENCE_MS * utilization**3
            if roles.get(link.a) == "balance" or roles.get(link.b) == "balance":
                queue *= self.weights.balance_impedance
            total += link.latency_ms + queue
        return total

    def _path_potential(
        self,
        path: Path,
        capacities: Mapping[str, float],
        roles: Mapping[str, str],
    ) -> float:
        utilization = max(
            min(1.0, self.prev_link_load[link.name] / max(1e-9, capacities[link.name]))
            for link in path.links
        )
        balancers = sum(1 for name in path.nodes[1:-1] if roles.get(name) == "balance")
        return (
            self.weights.w_congestion * utilization
            + self.weights.w_latency * (path.latency_ms / LATENCY_REFERENCE_MS)
            + self.weights.w_fragment * (path.fragment_factor - 1.0)
            + self.weights.w_cost * (path.cost_per_gb / COST_REFERENCE_PER_GB)
            - self.weights.w_balance_bonus * balancers
        )

    @staticmethod
    def _residual(
        path: Path,
        link_load: Mapping[str, float],
        capacities: Mapping[str, float],
    ) -> float:
        return max(
            0.0,
            min(capacities[link.name] - link_load[link.name] for link in path.links),
        )

    # -- state ------------------------------------------------------------

    def _commit(self, allocation: _Allocation) -> None:
        self.prev_link_load = allocation.link_load
        self.share = allocation.share
        self.previous_served_gb = dict(allocation.served_gb)
        self.unmet_fraction = dict(allocation.unmet_fraction)
        self.cache_fill_gb += sum(allocation.served_gb.values())
        self.oscillation_total += allocation.oscillation
        self.oscillation_ticks += 1

    def _build_incident_capacity(self) -> dict[str, float]:
        incident = {name: 0.0 for name in self.nodes}
        for link in self.links:
            incident[link.a] += link.capacity_mbps
            incident[link.b] += link.capacity_mbps
        return incident

    def _incident_utilization_range(self, name: str) -> tuple[float, float]:
        values: list[float] = []
        for link in self.links:
            if link.a == name or link.b == name:
                values.append(
                    min(1.0, self.prev_link_load.get(link.name, 0.0) / max(1e-9, link.capacity_mbps))
                )
        if not values:
            return (0.0, 0.0)
        return (max(values), min(values))

    def _incident_load(self, name: str) -> float:
        return sum(
            self.prev_link_load.get(link.name, 0.0)
            for link in self.links
            if link.a == name or link.b == name
        )

    def _demand(self, tick: int) -> dict[str, float]:
        base = self.scenario.demand(tick)
        return {
            target: max(0.0, value * (1.0 + 0.04 * self.rng.gauss(0.0, 1.0)))
            for target, value in base.items()
        }


def _delivery(path: Path, start: int, end: int) -> float:
    return math.prod(1.0 - link.loss for link in path.links[start:end])


def _weighted_p95(samples: Sequence[tuple[float, float]]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    total = sum(weight for _, weight in ordered)
    if total <= 0.0:
        return 0.0
    cutoff = 0.95 * total
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= cutoff:
            return value
    return ordered[-1][0]


def simulate_run(
    scenario: str | Scenario,
    policy: str,
    seed: int,
    weights: FlowWeights = DEFAULT_WEIGHTS,
) -> RunMetrics:
    """Run one replicate of one controller on one scenario."""
    resolved = SCENARIOS[scenario] if isinstance(scenario, str) else scenario
    return RoleFluidSimulation(resolved, policy, seed, weights).run()
