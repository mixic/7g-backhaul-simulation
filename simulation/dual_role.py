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

"""Continuous dual-role capacity split: serve (alpha) versus load-balance.

The frozen claim and scenarios are in ``docs/dual-role.md``.  A node's total
resource is shared between serving (terminating demand from a warm cache) and
forwarding/load-balancing (transit capacity).  ``alpha`` is a continuous
control variable in ``[0, 1]``.  The separated baseline fixes interior nodes
at ``alpha = 0`` (pure load balancers) and edge nodes at ``alpha = 1`` (pure
servers), the architectural split of a proxy-based service mesh.

This is a flow-level model.  It does not emit packets, has no ACK clock and no
congestion-control stack; results are conditional on the stipulated topology,
demand and controller parameters.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

ORIGIN = "O"
CONTROL_INTERVAL = 2
DEFAULT_TICKS = 120

#: Cache working set and reference queueing delay.
CATALOG_GB = 0.5
QUEUE_REFERENCE_MS = 20.0
SERVE_LATENCY_MS = 5.0
LATENCY_REFERENCE_MS = 25.0

#: Demand reference for normalising the sweep load.
NOMINAL_DEMAND_MBPS = {"E1": 40.0, "E2": 50.0, "E3": 30.0}


def _no_attack(_tick: int) -> Mapping[str, float]:
    return {target: 0.0 for target in NOMINAL_DEMAND_MBPS}


@dataclass(frozen=True)
class Link:
    name: str
    a: str
    b: str
    capacity_mbps: float
    latency_ms: float
    mtu_bytes: int


@dataclass(frozen=True)
class Node:
    name: str
    resource_mbps: float
    cache_capacity_gb: float = 0.0
    warm_seconds: float = 8.0


@dataclass(frozen=True)
class Path:
    target: str
    nodes: tuple[str, ...]
    links: tuple[Link, ...]
    capacity_mbps: float
    latency_ms: float
    fragment_factor: float


@dataclass(frozen=True)
class ControllerParams:
    """Stipulated controller gains; never fitted to results."""

    alpha0: float = 0.5
    gain: float = 1.0
    w_pressure: float = 1.0
    w_velocity: float = 0.5
    w_acceleration: float = 0.3
    damping: float = 0.5
    velocity_ref: float = 0.05
    acceleration_ref: float = 0.01
    temperature: float = 0.45
    #: When true, negative velocity/acceleration contribute to the serve
    #: signal instead of being clipped at zero.
    signed_trends: bool = False
    #: Extra weight on negative trend terms; only used when signed_trends is
    #: true.  ``1.0`` is symmetric, ``2.0`` releases twice as fast.
    release_gain: float = 1.0


DEFAULT_CONTROLLER = ControllerParams()

#: Fractions for the separated baseline; interior nodes balance, edges serve.
SEPARATED_ALPHA = {"M1": 0.0, "M2": 0.0, "E1": 1.0, "E2": 1.0, "E3": 1.0}


@dataclass(frozen=True)
class Scenario:
    key: str
    demand: Callable[[int], Mapping[str, float]]
    attack: Callable[[int], Mapping[str, float]] = _no_attack
    load_multiplier: float = 1.0
    ticks: int = DEFAULT_TICKS


@dataclass(frozen=True)
class Classifier:
    """Stipulated name-class admission error rates.

    ``false_positive`` is the fraction of legitimate demand dropped by the
    filter; ``false_negative`` is the fraction of the flood admitted.
    """

    false_positive: float = 0.02
    false_negative: float = 0.10

    def __post_init__(self) -> None:
        for name in ("false_positive", "false_negative"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1].")


@dataclass
class RunMetrics:
    delivered_goodput_mbps: float
    delivered_percent: float
    p95_latency_ms: float
    mean_alpha_abs_delta: float
    alpha_trace: dict[str, list[float]] = field(default_factory=dict)
    goodput_trace: list[float] = field(default_factory=list)
    target_delivered_percent: dict[str, float] = field(default_factory=dict)
    target_legit_delivered_percent: dict[str, float] = field(default_factory=dict)
    legit_delivered_trace: dict[str, list[float]] = field(default_factory=dict)
    legit_offered_trace: dict[str, list[float]] = field(default_factory=dict)
    latency_weighted: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class _Allocation:
    link_load: dict[str, float]
    delivered_mbps: dict[str, float]
    served_mbps: dict[str, float]
    latency_samples: list[tuple[float, float]]
    unmet_mbps: float
    oscillation: float
    shares: dict[tuple[str, int], float]


def build_nodes() -> dict[str, Node]:
    return {
        "O": Node("O", resource_mbps=1e9),
        "M1": Node("M1", resource_mbps=160.0, cache_capacity_gb=0.10),
        "M2": Node("M2", resource_mbps=140.0, cache_capacity_gb=0.10),
        "E1": Node("E1", resource_mbps=100.0, cache_capacity_gb=0.20),
        "E2": Node("E2", resource_mbps=140.0, cache_capacity_gb=0.30),
        "E3": Node("E3", resource_mbps=90.0, cache_capacity_gb=0.20),
    }


def build_links() -> tuple[Link, ...]:
    return (
        Link("O-M1", "O", "M1", 200.0, 2.0, 9000),
        Link("O-M2", "O", "M2", 120.0, 5.0, 1500),
        Link("M1-M2", "M1", "M2", 100.0, 3.0, 9000),
        Link("M1-E1", "M1", "E1", 80.0, 2.0, 1500),
        Link("M1-E2", "M1", "E2", 70.0, 6.0, 1200),
        Link("M2-E2", "M2", "E2", 60.0, 8.0, 1500),
        Link("M2-E3", "M2", "E3", 40.0, 20.0, 1200),
        Link("E1-E2", "E1", "E2", 30.0, 3.0, 1500),
        Link("E2-E3", "E2", "E3", 25.0, 5.0, 1200),
    )


def build_paths(
    nodes: Mapping[str, Node],
    links: Sequence[Link],
    targets: Sequence[str] = ("E1", "E2", "E3"),
) -> dict[str, tuple[Path, ...]]:
    neighbours: dict[str, list[tuple[str, Link]]] = {name: [] for name in nodes}
    for link in links:
        neighbours[link.a].append((link.b, link))
        neighbours[link.b].append((link.a, link))

    result: dict[str, tuple[Path, ...]] = {}
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
        found.sort(key=lambda path: (path.latency_ms, -path.capacity_mbps, path.nodes))
        result[target] = tuple(found)
    return result


def _make_path(target: str, nodes: tuple[str, ...], links: tuple[Link, ...]) -> Path:
    capacity = min(link.capacity_mbps for link in links) if links else 1e9
    latency = sum(link.latency_ms for link in links)
    fragment_factor = max(1.0, max((1500.0 / link.mtu_bytes for link in links), default=1.0))
    return Path(target, nodes, links, capacity, latency, fragment_factor)


def _steady(tick: int) -> Mapping[str, float]:
    return dict(NOMINAL_DEMAND_MBPS)


def _flash_crowd(tick: int) -> Mapping[str, float]:
    demand = dict(NOMINAL_DEMAND_MBPS)
    if 40 <= tick < 80:
        demand["E2"] += 60.0
        demand["E3"] += 30.0
    return demand


def _ddos_attack(tick: int) -> Mapping[str, float]:
    """Focused demand flood at E2: a stipulated DDoS-shaped surge.

    The model cannot tell malicious from legitimate bytes, so this is a demand
    flood, not a security model.  It measures graceful degradation and attack
    isolation (delivery to the *unattacked* targets), not scrubbing.  The
    attack is tracked separately from demand so the attack-aware admission can
    filter it.
    """
    attack = {target: 0.0 for target in NOMINAL_DEMAND_MBPS}
    if 40 <= tick < 100:
        attack["E2"] = 250.0
    return attack


def _flood_wave_attack(tick: int) -> Mapping[str, float]:
    """Trapezoidal flood at E2: ramp up, plateau, ramp down.

    The ramp-down gives the trend estimator negative velocity; the transitions
    give negative acceleration.  This is the signal the signed controller is
    supposed to use, unlike the step-shaped ``ddos`` scenario.
    """
    attack = {target: 0.0 for target in NOMINAL_DEMAND_MBPS}
    if 40 <= tick < 55:
        attack["E2"] = 250.0 * (tick - 40) / 15.0
    elif 55 <= tick < 85:
        attack["E2"] = 250.0
    elif 85 <= tick < 100:
        attack["E2"] = 250.0 * (100 - tick) / 15.0
    return attack


SCENARIOS: dict[str, Scenario] = {
    "steady": Scenario("steady", _steady),
    "flash_crowd": Scenario("flash_crowd", _flash_crowd),
    "ddos": Scenario("ddos", _steady, attack=_ddos_attack),
    "flood_wave": Scenario("flood_wave", _steady, attack=_flood_wave_attack),
}


class DualRoleSimulation:
    """Discrete-time flow model of the continuous dual-role controller."""

    def __init__(
        self,
        scenario: str | Scenario,
        mode: str,
        seed: int,
        controller: ControllerParams = DEFAULT_CONTROLLER,
        nodes: Mapping[str, Node] | None = None,
        links: Sequence[Link] | None = None,
        load_multiplier: float = 1.0,
        admission: str = "open",
        classifier: Classifier = Classifier(),
    ) -> None:
        if mode not in {"fluid", "separated"}:
            raise ValueError(f"Unknown mode: {mode}")
        if admission not in {"open", "authenticated"}:
            raise ValueError(f"Unknown admission mode: {admission}")
        self.admission = admission
        self.classifier = classifier
        self.scenario = SCENARIOS[scenario] if isinstance(scenario, str) else scenario
        self.mode = mode
        self.controller = controller
        self.nodes = dict(nodes or build_nodes())
        self.links = tuple(links or build_links())
        self.paths = build_paths(self.nodes, self.links)
        self.rng = random.Random(seed)
        self.load_multiplier = load_multiplier
        self.alpha: dict[str, float] = self._initial_alpha()
        self.cache_fill: dict[str, float] = {name: 0.0 for name in self.nodes}
        self.prev_link_load: dict[str, float] = {link.name: 0.0 for link in self.links}
        self.share: dict[tuple[str, int], float] = {}
        self.tick = 0
        self.pressure_history: dict[str, list[float]] = {name: [] for name in self.nodes}
        self.alpha_deltas: list[float] = []
        self.alpha_trace: dict[str, list[float]] = {name: [] for name in self.nodes}
        self.goodput_trace: list[float] = []
        self.p95_trace: list[float] = []
        self._incident_capacity = self._build_incident_capacity()

    def _initial_alpha(self) -> dict[str, float]:
        if self.mode == "separated":
            return {name: SEPARATED_ALPHA.get(name, 0.0) for name in self.nodes}
        return {
            name: 0.0 if name == ORIGIN else self.controller.alpha0
            for name in self.nodes
        }

    def _build_incident_capacity(self) -> dict[str, float]:
        incident = {name: 0.0 for name in self.nodes}
        for link in self.links:
            incident[link.a] += link.capacity_mbps
            incident[link.b] += link.capacity_mbps
        return incident

    def forward_capacity(self, name: str) -> float:
        if name == ORIGIN:
            return 1e12
        return (1.0 - self.alpha[name]) * self.nodes[name].resource_mbps

    def serve_capacity(self, name: str) -> float:
        if name == ORIGIN:
            return 0.0
        hit = self.hit_ratio(name)
        return self.alpha[name] * self.nodes[name].resource_mbps * hit

    def hit_ratio(self, name: str) -> float:
        node = self.nodes[name]
        max_hit = min(1.0, node.cache_capacity_gb / CATALOG_GB)
        return min(1.0, self.cache_fill[name] / CATALOG_GB, max_hit)

    # -- controller --------------------------------------------------------

    def update_alpha(self) -> None:
        if self.mode == "separated":
            self.alpha_deltas.append(0.0)
            return
        updated: dict[str, float] = {}
        for name in self.nodes:
            if name == ORIGIN:
                updated[name] = 0.0
                continue
            pressure = self._pressure(name)
            velocity, acceleration = self._trend(name, pressure)
            hit = self.hit_ratio(name)
            if self.controller.signed_trends:
                velocity_term = (
                    self.controller.w_velocity
                    * velocity
                    / self.controller.velocity_ref
                )
                acceleration_term = (
                    self.controller.w_acceleration
                    * acceleration
                    / self.controller.acceleration_ref
                )
                if velocity_term < 0.0:
                    velocity_term *= self.controller.release_gain
                if acceleration_term < 0.0:
                    acceleration_term *= self.controller.release_gain
                trend_signal = velocity_term + acceleration_term
            else:
                trend_signal = (
                    self.controller.w_velocity
                    * max(0.0, velocity)
                    / self.controller.velocity_ref
                    + self.controller.w_acceleration
                    * max(0.0, acceleration)
                    / self.controller.acceleration_ref
                )
            serve_signal = (
                self.controller.w_pressure * pressure * hit + trend_signal
            )
            target = min(1.0, max(0.0, self.controller.alpha0 + self.controller.gain * serve_signal))
            updated[name] = (
                (1.0 - self.controller.damping) * self.alpha[name]
                + self.controller.damping * target
            )
        delta = sum(abs(updated[name] - self.alpha[name]) for name in updated) / max(1, len(updated) - 1)
        self.alpha_deltas.append(delta)
        self.alpha = updated

    def _pressure(self, name: str) -> float:
        incident_capacity = self._incident_capacity.get(name, 0.0)
        if incident_capacity <= 0.0:
            return 0.0
        return min(1.0, self._incident_load(name) / incident_capacity)

    def _incident_load(self, name: str) -> float:
        return sum(
            self.prev_link_load.get(link.name, 0.0)
            for link in self.links
            if link.a == name or link.b == name
        )

    def _trend(self, name: str, pressure: float) -> tuple[float, float]:
        history = self.pressure_history[name]
        history.append(pressure)
        if len(history) > 3:
            history.pop(0)
        if len(history) < 3:
            return 0.0, 0.0
        older, previous, current = history
        interval = float(CONTROL_INTERVAL)
        velocity = (current - previous) / interval
        acceleration = (current - 2.0 * previous + older) / (interval**2)
        return velocity, acceleration

    # -- simulation --------------------------------------------------------

    def run(self) -> RunMetrics:
        latency_weighted: list[tuple[float, float]] = []
        goodput_ticks: list[float] = []
        offered_ticks: list[float] = []
        target_delivered: dict[str, list[float]] = {}
        target_offered: dict[str, list[float]] = {}
        legit_delivered: dict[str, list[float]] = {}
        legit_offered: dict[str, list[float]] = {}
        for tick in range(self.scenario.ticks):
            self.tick = tick
            if tick % CONTROL_INTERVAL == 0:
                self.update_alpha()
            legit, attack = self._classes(tick)
            admitted_legit, admitted_attack = self._admit(legit, attack)
            effective = {
                target: admitted_legit[target] + admitted_attack[target]
                for target in legit
            }
            allocation = self._allocate(effective)
            self._commit(allocation)
            delivered = sum(allocation.delivered_mbps.values())
            offered = sum(effective.values())
            goodput_ticks.append(delivered)
            offered_ticks.append(offered)
            latency_weighted.extend(allocation.latency_samples)
            for target, amount in allocation.delivered_mbps.items():
                target_delivered.setdefault(target, []).append(amount)
                target_offered.setdefault(target, []).append(effective[target])
                share = (
                    admitted_legit[target] / effective[target]
                    if effective[target] > 1e-12
                    else 1.0
                )
                legit_delivered.setdefault(target, []).append(amount * share)
                legit_offered.setdefault(target, []).append(legit[target])
            for name in self.nodes:
                self.alpha_trace[name].append(self.alpha[name])
            self.goodput_trace.append(delivered)

        mean_goodput = sum(goodput_ticks) / len(goodput_ticks) if goodput_ticks else 0.0
        total_offered = sum(offered_ticks)
        return RunMetrics(
            delivered_goodput_mbps=mean_goodput,
            delivered_percent=(
                100.0 * sum(goodput_ticks) / total_offered if total_offered else 100.0
            ),
            p95_latency_ms=_weighted_p95(latency_weighted),
            mean_alpha_abs_delta=(
                sum(self.alpha_deltas) / len(self.alpha_deltas) if self.alpha_deltas else 0.0
            ),
            alpha_trace={name: list(trace) for name, trace in self.alpha_trace.items()},
            goodput_trace=list(goodput_ticks),
            target_delivered_percent={
                target: 100.0
                * sum(target_delivered[target])
                / max(1e-9, sum(target_offered[target]))
                for target in target_delivered
            },
            target_legit_delivered_percent={
                target: 100.0
                * sum(legit_delivered[target])
                / max(1e-9, sum(legit_offered[target]))
                for target in legit_delivered
            },
            legit_delivered_trace={
                target: list(values) for target, values in legit_delivered.items()
            },
            legit_offered_trace={
                target: list(values) for target, values in legit_offered.items()
            },
            latency_weighted=list(latency_weighted),
        )

    def _classes(self, tick: int) -> tuple[dict[str, float], dict[str, float]]:
        """Split noisy total demand into legitimate and attack volume."""
        total = self._demand(tick)
        attack = self.scenario.attack(tick)
        legit: dict[str, float] = {}
        attack_adjusted: dict[str, float] = {}
        for target, amount in total.items():
            attack_amount = max(0.0, min(amount, float(attack.get(target, 0.0))))
            attack_adjusted[target] = attack_amount
            legit[target] = max(0.0, amount - attack_amount)
        return legit, attack_adjusted

    def _admit(
        self,
        legit: Mapping[str, float],
        attack: Mapping[str, float],
    ) -> tuple[dict[str, float], dict[str, float]]:
        if self.admission == "authenticated":
            admitted_legit = {
                target: value * (1.0 - self.classifier.false_positive)
                for target, value in legit.items()
            }
            admitted_attack = {
                target: value * self.classifier.false_negative
                for target, value in attack.items()
            }
        else:
            admitted_legit = dict(legit)
            admitted_attack = dict(attack)
        return admitted_legit, admitted_attack

    def _demand(self, tick: int) -> dict[str, float]:
        base = self.scenario.demand(tick)
        attack = self.scenario.attack(tick)
        combined = {
            target: float(base.get(target, 0.0)) + float(attack.get(target, 0.0))
            for target in base
        }
        return {
            target: max(
                0.0,
                value
                * self.load_multiplier
                * (1.0 + 0.04 * self.rng.gauss(0.0, 1.0)),
            )
            for target, value in combined.items()
        }

    # -- allocation --------------------------------------------------------

    def _allocate(self, demand: Mapping[str, float]) -> _Allocation:
        link_load = {link.name: 0.0 for link in self.links}
        node_forward_used = {name: 0.0 for name in self.nodes}
        node_served = {name: 0.0 for name in self.nodes}
        delivered = {target: 0.0 for target in demand}
        shares: dict[tuple[str, int], float] = {}
        latency_entries: list[tuple[Path | None, int, int, float, float]] = []
        unmet = 0.0
        oscillation = 0.0

        for target in sorted(demand):
            paths = self.paths[target]
            potentials = [self._path_potential(path) for path in paths]
            raw = [
                math.exp(-potential / self.controller.temperature)
                for potential in potentials
            ]
            total = sum(raw)
            weights = [value / total for value in raw]
            previous = [
                self.share.get((target, index), weights[index])
                for index in range(len(paths))
            ]
            damped = [
                (1.0 - self.controller.damping) * previous[index]
                + self.controller.damping * weights[index]
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

            # 1. Serving at the target node terminates demand without
            #    traversing any link; only the remainder transits.
            local = 0.0
            if self.alpha[target] > 1e-6:
                room = max(0.0, self.serve_capacity(target) - node_served[target])
                local = min(target_demand, room)
                node_served[target] += local
                delivered[target] += local
                latency_entries.append((None, 0, 0, local, SERVE_LATENCY_MS))
            remaining = target_demand - local

            # 2. Water-fill the remainder across paths within link and node
            #    forwarding budgets.
            order = sorted(range(len(paths)), key=lambda index: potentials[index])
            allocation = {index: 0.0 for index in range(len(paths))}
            for _ in range(3):
                if remaining <= 1e-9:
                    break
                for index in order:
                    if damped[index] <= 0.0 or remaining <= 1e-9:
                        continue
                    path = paths[index]
                    link_room = min(
                        link.capacity_mbps - link_load[link.name] for link in path.links
                    )
                    node_room = min(
                        self.forward_capacity(node) - node_forward_used[node]
                        for node in path.nodes[1:-1]
                    )
                    room = max(0.0, min(link_room, node_room))
                    take = min(remaining * damped[index], room)
                    allocation[index] += take
                    for link in path.links:
                        link_load[link.name] += take
                    for node in path.nodes[1:-1]:
                        node_forward_used[node] += take
                    remaining -= take

            unmet += max(0.0, remaining)

            # 3. Intermediate serving: a cached copy at an interior node
            #    relieves the upstream links but still traverses downstream.
            for index, amount in allocation.items():
                if amount <= 0.0:
                    continue
                path = paths[index]
                serve_index = self._serve_point(path, node_served)
                served_part = 0.0
                if serve_index is not None:
                    node_name = path.nodes[serve_index]
                    room = max(
                        0.0, self.serve_capacity(node_name) - node_served[node_name]
                    )
                    served_part = min(amount, room)
                    node_served[node_name] += served_part
                    for link in path.links[:serve_index]:
                        link_load[link.name] = max(0.0, link_load[link.name] - served_part)
                    for node in path.nodes[1:serve_index]:
                        node_forward_used[node] = max(
                            0.0, node_forward_used[node] - served_part
                        )
                transit = amount - served_part
                if served_part > 0.0:
                    delivered[target] += served_part
                    latency_entries.append(
                        (path, serve_index, len(path.links), served_part, SERVE_LATENCY_MS)
                    )
                if transit > 0.0:
                    delivered[target] += transit
                    latency_entries.append((path, 0, len(path.links), transit, 0.0))

        latency_samples = [
            (
                SERVE_LATENCY_MS
                if path is None
                else self._path_latency(path, start, end, extra, link_load),
                amount,
            )
            for path, start, end, amount, extra in latency_entries
        ]
        return _Allocation(
            link_load=link_load,
            delivered_mbps=delivered,
            served_mbps=node_served,
            latency_samples=latency_samples,
            unmet_mbps=unmet,
            oscillation=oscillation,
            shares=shares,
        )

    def _serve_point(
        self, path: Path, node_served: Mapping[str, float]
    ) -> int | None:
        for index in range(len(path.nodes) - 2, 0, -1):
            name = path.nodes[index]
            if name == ORIGIN:
                continue
            if (
                self.alpha[name] > 1e-6
                and self.serve_capacity(name) - node_served.get(name, 0.0) > 1e-9
            ):
                return index
        return None

    def _path_potential(self, path: Path) -> float:
        utilization = max(
            min(
                1.0,
                self.prev_link_load[link.name] / max(1e-9, link.capacity_mbps),
            )
            for link in path.links
        )
        return (
            utilization
            + 0.6 * (path.latency_ms / LATENCY_REFERENCE_MS)
            + 0.4 * (path.fragment_factor - 1.0)
        )

    def _path_latency(
        self,
        path: Path,
        start: int,
        end: int,
        extra: float,
        link_load: Mapping[str, float],
    ) -> float:
        total = extra
        for link in path.links[start:end]:
            utilization = min(
                1.0, link_load[link.name] / max(1e-9, link.capacity_mbps)
            )
            total += link.latency_ms + QUEUE_REFERENCE_MS * utilization**3
        return total

    def _commit(self, allocation: _Allocation) -> None:
        self.prev_link_load = allocation.link_load
        self.share = allocation.shares
        # A node that is committed to serving (alpha > 0) invests in warming its
        # cache, at a rate proportional to its serving commitment.  Without this
        # a cold cache can never warm, because serving requires a non-zero hit
        # ratio in the first place.
        for name, node in self.nodes.items():
            if name == ORIGIN or self.alpha[name] <= 0.0:
                continue
            max_hit = min(1.0, node.cache_capacity_gb / CATALOG_GB)
            rate = self.alpha[name] / node.warm_seconds
            self.cache_fill[name] = min(
                max_hit,
                self.cache_fill[name] + (max_hit - self.cache_fill[name]) * rate,
            )

    def __repr__(self) -> str:
        return f"DualRoleSimulation({self.scenario.key}, {self.mode})"


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
    mode: str,
    seed: int,
    controller: ControllerParams = DEFAULT_CONTROLLER,
    load_multiplier: float = 1.0,
    admission: str = "open",
    classifier: Classifier = Classifier(),
) -> RunMetrics:
    """Run one replicate of one mode on one scenario."""
    return DualRoleSimulation(
        scenario,
        mode,
        seed,
        controller,
        load_multiplier=load_multiplier,
        admission=admission,
        classifier=classifier,
    ).run()
