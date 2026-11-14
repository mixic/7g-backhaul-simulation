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

"""Flow-level common-mode resilience testbed (H16-H20).

The testbed models a six-tenant 7G cooperative AI backhaul: three aggregation
sites, three providers, two cloud regions, shared identity/DNS/AI control, a
shared tenant gateway, a global cooperative controller and local fallbacks.

The model is deliberately structural rather than packet-level:

* a tenant is served only when its data path, control plane, tenant boundary and
  fallback (when needed) are available together;
* multipath is a set of paths whose value is their SRLG/provider independence,
  not their count;
* isolation is a cut that removes a dependency but can also remove capability;
* a fallback has an activation probability, a delay and a capacity fraction;
* a common-mode event is sampled once per event and shared by every arm.

The scenario and the hypotheses are frozen in ``docs/common-mode-predictions.md``.
The freeze commit is recorded in ``docs/common-mode-results.md``.  No constant
in this module may be tuned after the run without a new prediction document.
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass
from typing import Iterable, Sequence

#: Simulation clock.
TICK_S = 1.0
SIM_S = 60.0

#: Event timing (frozen).
EVENT_START_MIN_S = 15.0
EVENT_START_SPAN_S = 10.0
EVENT_DURATION_MIN_S = 20.0
EVENT_DURATION_SPAN_S = 10.0

#: Demand and capacity (frozen).
DEMAND_GBPS = 1.0
DEMAND_JITTER = 0.05
PATH_CAPACITY_GBPS = 1.05
AGG_PROVIDER_CAPACITY_GBPS = 1.20
PROVIDER_CLOUD_CAPACITY_GBPS = 1.50

#: Local-policy efficiency of a one-way boundary (frozen).
ONE_WAY_EFFICIENCY = 0.90

#: Fallback profiles (frozen).
FALLBACK_TESTED_PROBABILITY = 0.98
FALLBACK_UNTESTED_PROBABILITY = 0.60
FALLBACK_TESTED_DELAY_S = 2.0
FALLBACK_UNTESTED_DELAY_S = 8.0
FALLBACK_TESTED_CAPACITY_GBPS = 0.50
FALLBACK_UNTESTED_CAPACITY_GBPS = 0.30

#: Measurement constants.
RECOVERY_TARGET = 0.90
RECOVERY_HOLD_TICKS = 3
BLAST_RADIUS_TARGET = 0.50

#: Event kinds (frozen).
EVENT_KINDS: tuple[str, ...] = (
    "none",
    "link",
    "srlg",
    "backhaul_cut",
    "provider_cp",
    "idp",
    "ai",
    "tenant_gw",
    "controller_link",
    "ai_link",
)

#: The seed base used by the benchmark.
BASE_SEED = 2026
SEEDS = 30


@dataclass(frozen=True)
class Node:
    name: str
    kind: str


@dataclass(frozen=True)
class Link:
    name: str
    source: str
    target: str
    capacity_gbps: float
    latency_ms: float
    srlg: str
    provider: str | None = None


@dataclass(frozen=True)
class Path:
    nodes: tuple[str, ...]
    links: tuple[Link, ...]
    capacity_gbps: float
    latency_ms: float
    provider: str
    srlgs: frozenset[str]


@dataclass(frozen=True)
class Tenant:
    name: str
    edge: str
    fallback: str


@dataclass(frozen=True)
class Scenario:
    name: str
    nodes: dict[str, Node]
    links: tuple[Link, ...]
    tenants: tuple[Tenant, ...]
    provider_cps: dict[str, str]
    shared_controls: tuple[str, str, str]
    tenant_gateway: str
    controller: str


@dataclass(frozen=True)
class FallbackProfile:
    probability: float
    delay_s: float
    capacity_gbps: float


@dataclass(frozen=True)
class Arm:
    name: str
    label: str
    path_policy: str
    tenant_isolation: bool
    independent_control: bool
    one_way: bool
    fallback: str | None
    controller: str

    @property
    def ai_required(self) -> bool:
        return not self.one_way


@dataclass(frozen=True)
class Event:
    kind: str
    start_s: float
    end_s: float
    failed_nodes: frozenset[str] = frozenset()
    failed_links: frozenset[str] = frozenset()

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass(frozen=True)
class SeedInputs:
    seed: int
    event: Event
    demand_factors: dict[str, float]
    fallback_draws: dict[str, float]


@dataclass(frozen=True)
class TenantRun:
    name: str
    availability_event: float
    availability_overall: float
    recovery_s: float
    fallback_activated: bool


@dataclass(frozen=True)
class RunResult:
    arm: str
    event: str
    seed: int
    availability_event: float
    availability_overall: float
    recovery_s: float
    blast_radius: float
    path_independence: float
    fallback_rate: float
    cost_index: float
    tenants: tuple[TenantRun, ...] = ()


#: The nine arms.  They differ only in mechanism, never in inputs.
ARMS: dict[str, Arm] = {
    "A1": Arm(
        "A1", "Concentration", "single", False, False, False, None, "none"
    ),
    "A2": Arm(
        "A2", "Multipath, shared fate", "shortest3", False, False, False, None, "local"
    ),
    "A3": Arm(
        "A3", "Multipath, SRLG-disjoint", "disjoint3", False, False, False, None, "local"
    ),
    "A4": Arm(
        "A4", "A3 + tenant isolation", "disjoint3", True, False, False, None, "local"
    ),
    "A5": Arm(
        "A5", "A4 + independent control", "disjoint3", True, True, False, None, "local"
    ),
    "A6": Arm(
        "A6",
        "A5 + one-way boundary + tested fallback",
        "disjoint3",
        True,
        True,
        True,
        "tested",
        "local",
    ),
    "A7": Arm(
        "A7",
        "A6 with untested fallback",
        "disjoint3",
        True,
        True,
        True,
        "untested",
        "local",
    ),
    "A8": Arm(
        "A8", "A5 + global cooperative controller", "disjoint3", True, True, False, None, "global"
    ),
    "A9": Arm(
        "A9",
        "A1 + isolation + tested fallback",
        "single",
        True,
        True,
        True,
        "tested",
        "none",
    ),
}


def build_backhaul_scenario() -> Scenario:
    """Build the frozen cooperative AI backhaul scenario."""
    nodes: dict[str, Node] = {}
    for index in range(1, 7):
        nodes[f"e{index}"] = Node(f"e{index}", "edge")
        nodes[f"fb{index}"] = Node(f"fb{index}", "fallback")
    for index in range(1, 4):
        nodes[f"a{index}"] = Node(f"a{index}", "aggregation")
        nodes[f"p{index}"] = Node(f"p{index}", "provider")
        nodes[f"p{index}-cp"] = Node(f"p{index}-cp", "provider-control")
    nodes["c1"] = Node("c1", "cloud")
    nodes["c2"] = Node("c2", "cloud")
    for name in ("idp", "dns", "ai"):
        nodes[name] = Node(name, "shared-control")
    nodes["mt-gw"] = Node("mt-gw", "tenant-gateway")
    nodes["coop"] = Node("coop", "controller")

    links: list[Link] = []
    for tenant_index in range(1, 7):
        for agg_index in range(1, 4):
            links.append(
                Link(
                    f"e{tenant_index}-a{agg_index}",
                    f"e{tenant_index}",
                    f"a{agg_index}",
                    PATH_CAPACITY_GBPS,
                    1.0 + 0.25 * (agg_index - 1),
                    f"edge-{tenant_index}-{agg_index}",
                )
            )
    for agg_index in range(1, 4):
        for provider_index in range(1, 4):
            links.append(
                Link(
                    f"a{agg_index}-p{provider_index}",
                    f"a{agg_index}",
                    f"p{provider_index}",
                    AGG_PROVIDER_CAPACITY_GBPS,
                    4.0 + 2.0 * (agg_index - 1) + 0.5 * (provider_index - 1),
                    f"agg-{agg_index}",
                    f"p{provider_index}",
                )
            )
    links.extend(
        [
            Link("p1-c1", "p1", "c1", PROVIDER_CLOUD_CAPACITY_GBPS, 8.0, "prov-1-cloud-1", "p1"),
            Link("p2-c1", "p2", "c1", PROVIDER_CLOUD_CAPACITY_GBPS, 8.5, "prov-2-cloud-1", "p2"),
            Link("p3-c2", "p3", "c2", PROVIDER_CLOUD_CAPACITY_GBPS, 9.0, "prov-3-cloud-2", "p3"),
        ]
    )

    tenants = tuple(
        Tenant(f"t{index}", f"e{index}", f"fb{index}") for index in range(1, 7)
    )
    return Scenario(
        name="cooperative-ai-backhaul",
        nodes=nodes,
        links=tuple(links),
        tenants=tenants,
        provider_cps={"p1": "p1-cp", "p2": "p2-cp", "p3": "p3-cp"},
        shared_controls=("idp", "dns", "ai"),
        tenant_gateway="mt-gw",
        controller="coop",
    )


def _make_path(nodes: tuple[str, ...], links: tuple[Link, ...]) -> Path:
    providers = {link.provider for link in links if link.provider is not None}
    provider = next(iter(providers)) if len(providers) == 1 else "mixed"
    return Path(
        nodes=nodes,
        links=links,
        capacity_gbps=min(link.capacity_gbps for link in links),
        latency_ms=sum(link.latency_ms for link in links),
        provider=provider,
        srlgs=frozenset(link.srlg for link in links),
    )


def enumerate_paths(scenario: Scenario, tenant: Tenant) -> tuple[Path, ...]:
    """Enumerate simple edge-to-cloud paths, sorted by latency then nodes."""
    adjacency: dict[str, list[tuple[Link, str]]] = {
        name: [] for name in scenario.nodes
    }
    for link in scenario.links:
        adjacency[link.source].append((link, link.target))

    targets = {"c1", "c2"}
    found: list[Path] = []

    def walk(
        node: str,
        path_nodes: tuple[str, ...],
        path_links: tuple[Link, ...],
        visited: frozenset[str],
    ) -> None:
        if node in targets:
            found.append(_make_path(path_nodes, path_links))
            return
        if len(path_nodes) >= 4:
            return
        for link, next_node in adjacency.get(node, []):
            if next_node in visited:
                continue
            walk(
                next_node,
                path_nodes + (next_node,),
                path_links + (link,),
                visited | {next_node},
            )

    walk(tenant.edge, (tenant.edge,), (), frozenset({tenant.edge}))
    return tuple(sorted(found, key=lambda path: (round(path.latency_ms, 6), path.nodes)))


def _greedy_disjoint(paths: Sequence[Path], limit: int) -> tuple[Path, ...]:
    selected: list[Path] = []
    used: set[str] = set()
    for path in paths:
        if used.isdisjoint(path.srlgs):
            selected.append(path)
            used.update(path.srlgs)
            if len(selected) == limit:
                break
    return tuple(selected) if selected else tuple(paths[:1])


def select_paths(scenario: Scenario, arm: Arm) -> dict[str, tuple[Path, ...]]:
    """Select each tenant's path set under the arm's frozen policy."""
    selected: dict[str, tuple[Path, ...]] = {}
    for tenant in scenario.tenants:
        paths = enumerate_paths(scenario, tenant)
        if not paths:
            selected[tenant.name] = ()
        elif arm.path_policy == "single":
            selected[tenant.name] = tuple(paths[:1])
        elif arm.path_policy == "shortest3":
            selected[tenant.name] = tuple(paths[:3])
        elif arm.path_policy == "disjoint3":
            selected[tenant.name] = _greedy_disjoint(paths, 3)
        else:
            raise ValueError(f"unknown path policy: {arm.path_policy}")
    return selected


def path_independence(paths: Sequence[Path]) -> float:
    """Largest pairwise-SRLG-disjoint, provider-distinct subset / path count."""
    if not paths:
        return 0.0
    best = 0
    for size in range(1, len(paths) + 1):
        for subset in itertools.combinations(paths, size):
            if len({path.provider for path in subset}) < size:
                continue
            if all(
                left.srlgs.isdisjoint(right.srlgs)
                for left, right in itertools.combinations(subset, 2)
            ):
                best = max(best, size)
    return best / len(paths)


def _event_targets(scenario: Scenario, kind: str) -> tuple[frozenset[str], frozenset[str]]:
    if kind == "none":
        return frozenset(), frozenset()
    if kind == "link":
        return frozenset(), frozenset({"a1-p1"})
    if kind == "srlg":
        links = frozenset(
            link.name for link in scenario.links if link.srlg == "agg-1"
        )
        return frozenset(), links
    if kind == "backhaul_cut":
        links = frozenset(
            link.name
            for link in scenario.links
            if link.source.startswith("a") and link.target.startswith("p")
        )
        return frozenset(), links
    if kind == "provider_cp":
        return frozenset({"p1-cp"}), frozenset()
    if kind == "idp":
        return frozenset({"idp"}), frozenset()
    if kind == "ai":
        return frozenset({"ai"}), frozenset()
    if kind == "tenant_gw":
        return frozenset({"mt-gw"}), frozenset()
    if kind == "controller_link":
        return frozenset({"coop"}), frozenset({"a1-p1"})
    if kind == "ai_link":
        return frozenset({"ai"}), frozenset({"a1-p1"})
    raise ValueError(f"unknown event: {kind}")


def build_seed_inputs(scenario: Scenario, seed: int, event_kind: str) -> SeedInputs:
    """Draw one event, one demand vector and one fallback vector per seed.

    The draws are shared by every arm, which is what makes the comparison
    paired.  The draw order is frozen: start, duration, demand, fallback.
    """
    if event_kind not in EVENT_KINDS:
        raise ValueError(f"unknown event: {event_kind}")
    rng = random.Random(seed * 1_000_003 + 17)
    start = EVENT_START_MIN_S + rng.random() * EVENT_START_SPAN_S
    duration = EVENT_DURATION_MIN_S + rng.random() * EVENT_DURATION_SPAN_S
    demand_factors = {
        tenant.name: 1.0 + rng.uniform(-DEMAND_JITTER, DEMAND_JITTER)
        for tenant in scenario.tenants
    }
    fallback_draws = {
        tenant.name: rng.random() for tenant in scenario.tenants
    }
    failed_nodes, failed_links = _event_targets(scenario, event_kind)
    event = Event(
        kind=event_kind,
        start_s=start,
        end_s=start + duration,
        failed_nodes=failed_nodes,
        failed_links=failed_links,
    )
    return SeedInputs(
        seed=seed,
        event=event,
        demand_factors=demand_factors,
        fallback_draws=fallback_draws,
    )


def _fallback_profile(arm: Arm) -> FallbackProfile | None:
    if arm.fallback == "tested":
        return FallbackProfile(
            FALLBACK_TESTED_PROBABILITY,
            FALLBACK_TESTED_DELAY_S,
            FALLBACK_TESTED_CAPACITY_GBPS,
        )
    if arm.fallback == "untested":
        return FallbackProfile(
            FALLBACK_UNTESTED_PROBABILITY,
            FALLBACK_UNTESTED_DELAY_S,
            FALLBACK_UNTESTED_CAPACITY_GBPS,
        )
    return None


def _control_ok(scenario: Scenario, arm: Arm, failed_nodes: frozenset[str]) -> bool:
    if not arm.tenant_isolation and scenario.tenant_gateway in failed_nodes:
        return False
    if not arm.independent_control:
        if "idp" in failed_nodes or "dns" in failed_nodes:
            return False
    if arm.ai_required and "ai" in failed_nodes:
        return False
    return True


def _path_ok(
    scenario: Scenario,
    path: Path,
    failed_nodes: frozenset[str],
    failed_links: frozenset[str],
) -> bool:
    if any(link.name in failed_links for link in path.links):
        return False
    if any(node in failed_nodes for node in path.nodes):
        return False
    control_plane = scenario.provider_cps.get(path.provider)
    if control_plane is not None and control_plane in failed_nodes:
        return False
    return True


def _service(
    scenario: Scenario,
    arm: Arm,
    paths: Sequence[Path],
    demand_gbps: float,
    failed_nodes: frozenset[str],
    failed_links: frozenset[str],
    tick: int,
    event: Event,
    fallback_draw: float,
    fallback: FallbackProfile | None,
) -> tuple[float, bool]:
    control_ok = _control_ok(scenario, arm, failed_nodes)
    available = [
        path
        for path in paths
        if _path_ok(scenario, path, failed_nodes, failed_links)
    ]
    if arm.controller == "global" and scenario.controller in failed_nodes:
        primary = paths[0] if paths else None
        available = (
            [primary]
            if primary is not None
            and _path_ok(scenario, primary, failed_nodes, failed_links)
            else []
        )

    path_capacity = sum(path.capacity_gbps for path in available) if control_ok else 0.0
    path_served = min(demand_gbps, path_capacity)
    if arm.one_way:
        path_served *= ONE_WAY_EFFICIENCY

    need_fallback = (not control_ok) or (not available)
    fallback_active = False
    if (
        need_fallback
        and fallback is not None
        and fallback_draw < fallback.probability
        and tick >= event.start_s + fallback.delay_s
    ):
        fallback_active = True

    fallback_served = 0.0
    if fallback_active and fallback is not None:
        fallback_served = min(
            max(0.0, demand_gbps - path_served), fallback.capacity_gbps
        )
    return min(demand_gbps, path_served + fallback_served), fallback_active


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def simulate(
    arm: Arm,
    scenario: Scenario | None = None,
    seed: int = BASE_SEED,
    event_kind: str = "none",
) -> RunResult:
    """Run one arm on one seed and one event."""
    scenario = scenario or build_backhaul_scenario()
    inputs = build_seed_inputs(scenario, seed, event_kind)
    event = inputs.event
    paths_by_tenant = select_paths(scenario, arm)
    fallback = _fallback_profile(arm)
    tenant_runs: list[TenantRun] = []

    for tenant in scenario.tenants:
        demand = DEMAND_GBPS * inputs.demand_factors[tenant.name]
        paths = paths_by_tenant[tenant.name]
        fallback_draw = inputs.fallback_draws[tenant.name]
        served: list[float] = []
        fallback_activated = False

        for tick in range(int(SIM_S)):
            active = (
                event.kind != "none" and event.start_s <= tick < event.end_s
            )
            failed_nodes = event.failed_nodes if active else frozenset()
            failed_links = event.failed_links if active else frozenset()
            amount, used_fallback = _service(
                scenario,
                arm,
                paths,
                demand,
                failed_nodes,
                failed_links,
                tick,
                event,
                fallback_draw,
                fallback,
            )
            served.append(amount / demand if demand > 0 else 0.0)
            if active and used_fallback:
                fallback_activated = True

        availability_overall = _mean(served)
        event_ticks = [
            tick
            for tick in range(int(SIM_S))
            if event.kind != "none" and event.start_s <= tick < event.end_s
        ]
        availability_event = (
            _mean(served[tick] for tick in event_ticks)
            if event_ticks
            else availability_overall
        )

        recovery_s = 0.0
        if event.kind != "none":
            recovery_s = event.duration_s
            first_tick = int(math.ceil(event.start_s))
            for tick in range(
                max(0, first_tick), int(SIM_S) - RECOVERY_HOLD_TICKS + 1
            ):
                if all(
                    served[offset] >= RECOVERY_TARGET - 1e-12
                    for offset in range(tick, tick + RECOVERY_HOLD_TICKS)
                ):
                    recovery_s = max(0.0, tick - event.start_s)
                    break

        tenant_runs.append(
            TenantRun(
                name=tenant.name,
                availability_event=availability_event,
                availability_overall=availability_overall,
                recovery_s=recovery_s,
                fallback_activated=fallback_activated,
            )
        )

    path_count = _mean(len(paths_by_tenant[tenant.name]) for tenant in scenario.tenants)
    independence = _mean(
        path_independence(paths_by_tenant[tenant.name])
        for tenant in scenario.tenants
    )
    cost = (
        0.5 * path_count
        + 0.1 * (1.0 if arm.tenant_isolation else 0.0)
        + 0.1 * (1.0 if arm.independent_control else 0.0)
        + 0.1 * (1.0 if arm.one_way else 0.0)
        + 0.05 * (1.0 if arm.controller == "global" else 0.0)
    )
    return RunResult(
        arm=arm.name,
        event=event_kind,
        seed=seed,
        availability_event=_mean(run.availability_event for run in tenant_runs),
        availability_overall=_mean(run.availability_overall for run in tenant_runs),
        recovery_s=_mean(run.recovery_s for run in tenant_runs),
        blast_radius=sum(
            1 for run in tenant_runs if run.availability_event < BLAST_RADIUS_TARGET
        )
        / len(tenant_runs),
        path_independence=independence,
        fallback_rate=sum(1 for run in tenant_runs if run.fallback_activated)
        / len(tenant_runs),
        cost_index=cost,
        tenants=tuple(tenant_runs),
    )
