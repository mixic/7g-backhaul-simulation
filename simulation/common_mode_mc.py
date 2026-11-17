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

"""Continuous-time Monte Carlo simulation of the common-mode testbed.

This module is the stochastic engine of the Monte Carlo study.  The protocol it
implements is frozen in ``docs/common-mode-mc-predictions.md``; the structural
scenario (topology, arms, path selection, event targets, cost index) is imported
from :mod:`simulation.common_mode`, which remains the single source of truth for
the structural model.

What is simulated
-----------------
* every dependency is an alternating renewal process (exponential time to
  failure, lognormal duration): shared identity, DNS and AI endpoint, the tenant
  gateway, the cooperative controller, the provider control planes, the provider
  nodes, the edge links, the aggregation conduits and the provider-cloud links;
* an incident of a named class can be injected at a sampled time with a sampled
  duration, superimposed on the background process;
* offered demand is a diurnal process with Ornstein-Uhlenbeck noise;
* effective link capacity is a protocol efficiency times an adaptive-modulation
  process, so a healthy path can still be congested;
* a fallback activates with a probability, a sampled delay and a sampled
  capacity, per tenant and per dependency-outage episode;
* the service state is piecewise constant in continuous time, and availability
  is the time-weighted served-over-offered ratio.

Common random numbers
---------------------
Every random input of a replication is drawn once and shared by all nine arms,
so per-replication paired differences are meaningful and a seed cannot confound
the comparison.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from simulation import common_mode as cm

#: Incident experiment horizon (24 h) and campaign horizon (30 d).
H_INCIDENT_S = 24 * 3600.0
H_CAMPAIGN_S = 30 * 24 * 3600.0

#: Seed base of the frozen protocol.
BASE_SEED = 2026

#: Maximum number of dependency-outage episodes a replication can index.  The
#: fallback draws are stored per (episode, tenant); episodes beyond this bound
#: wrap around, which is a documented approximation.
MAX_EPISODES = 256

#: The default replication counts of the frozen protocol.
INCIDENT_REPLICATIONS = 2000
CAMPAIGN_REPLICATIONS = 500

#: Campaign length used for the SLO-breach metric.
CAMPAIGN_DAYS = 30

#: Duration cap for every sampled outage and for the injected incident.
DURATION_CAP_S = 6 * 3600.0


@dataclass(frozen=True)
class ProcessSpec:
    """Lognormal-duration / exponential-arrival failure process."""

    mtbf_s: float
    median_s: float
    sigma_ln: float

    @property
    def p95_duration_s(self) -> float:
        return self.median_s * math.exp(1.645 * self.sigma_ln)


@dataclass(frozen=True)
class MCParams:
    """The stochastic constants of the simulation.

    The defaults are the frozen values of
    ``docs/common-mode-mc-predictions.md``.  A sensitivity run passes a modified
    instance; the module constants are never mutated.
    """

    #: Local-policy efficiency of the one-way boundary (stipulated).
    one_way_efficiency: float = 0.90
    #: Protocol/encapsulation efficiency applied to every link.
    protocol_efficiency: float = 0.95
    #: Adaptive-modulation factor: mean, stationary sd and correlation time.
    modulation_mean: float = 0.98
    modulation_sd: float = 0.03
    modulation_tau_s: float = 120.0
    #: Diurnal demand amplitude and Ornstein-Uhlenbeck demand noise.
    demand_diurnal_amplitude: float = 0.10
    demand_ou_sd: float = 0.05
    demand_ou_tau_s: float = 1800.0
    base_demand_gbps: float = 1.00
    #: Fallback profiles.  The delays and capacities are the *medians* of the
    #: lognormal draws; the probabilities are activation probabilities.
    fallback_tested_probability: float = 0.98
    fallback_untested_probability: float = 0.60
    fallback_tested_delay_s: float = 2.0
    fallback_untested_delay_s: float = 8.0
    fallback_tested_capacity_gbps: float = 0.50
    fallback_untested_capacity_gbps: float = 0.30
    #: Shared-control mean time between failures (varied in E4).
    shared_mtbf_days: float = 21.0
    #: Dispersion of the fallback delay and capacity draws.
    fallback_delay_sigma_ln: float = 0.50
    fallback_untested_delay_sigma_ln: float = 0.60
    fallback_capacity_sigma_ln: float = 0.15
    fallback_untested_capacity_sigma_ln: float = 0.20
    #: Edge/link capacity of the frozen scenario (Gbps), used by the sensitivity
    #: engine so the topology stays the single source of truth.
    edge_capacity_gbps: float = 1.05


DEFAULT_PARAMS = MCParams()

#: Incident injection: start window and duration medians (seconds).
INCIDENT_START_MIN_S = 6 * 3600.0
INCIDENT_START_SPAN_S = 12 * 3600.0
INCIDENT_SIGMA_LN = 0.80
INCIDENT_MEDIAN_S: dict[str, float] = {
    "none": 0.0,
    "link": 25 * 60.0,
    "srlg": 25 * 60.0,
    "backhaul_cut": 40 * 60.0,
    "provider_cp": 45 * 60.0,
    "idp": 45 * 60.0,
    "ai": 45 * 60.0,
    "tenant_gw": 30 * 60.0,
    "controller_link": 25 * 60.0,
    "ai_link": 30 * 60.0,
}


def process_specs(params: MCParams = DEFAULT_PARAMS) -> dict[str, ProcessSpec]:
    """The frozen failure-process table, keyed by dependency class."""
    day = 24 * 3600.0
    return {
        "shared": ProcessSpec(params.shared_mtbf_days * day, 45 * 60.0, 1.00),
        "gateway": ProcessSpec(30 * day, 30 * 60.0, 0.80),
        "controller": ProcessSpec(30 * day, 30 * 60.0, 0.80),
        "provider_cp": ProcessSpec(14 * day, 20 * 60.0, 1.00),
        "provider": ProcessSpec(120 * day, 10 * 60.0, 0.80),
        "edge_link": ProcessSpec(60 * day, 3 * 60.0, 0.60),
        "conduit": ProcessSpec(45 * day, 8 * 60.0, 0.80),
        "pcloud": ProcessSpec(90 * day, 6 * 60.0, 0.70),
    }


@dataclass(frozen=True)
class Unit:
    """One failure process and the network elements it takes down."""

    name: str
    kind: str  # "node", "link" or "srlg"
    targets: tuple[str, ...]
    spec: ProcessSpec


def build_units(
    scenario: cm.Scenario, params: MCParams = DEFAULT_PARAMS
) -> tuple[Unit, ...]:
    """Build the failure-process units for the frozen scenario."""
    specs = process_specs(params)
    units: list[Unit] = []
    for name in ("idp", "dns", "ai"):
        units.append(Unit(f"shared-{name}", "node", (name,), specs["shared"]))
    units.append(Unit("gateway", "node", (scenario.tenant_gateway,), specs["gateway"]))
    units.append(Unit("controller", "node", (scenario.controller,), specs["controller"]))
    for provider, control_plane in sorted(scenario.provider_cps.items()):
        units.append(Unit(f"cp-{provider}", "node", (control_plane,), specs["provider_cp"]))
        units.append(Unit(f"node-{provider}", "node", (provider,), specs["provider"]))
    for link in scenario.links:
        if link.source.startswith("e"):
            units.append(
                Unit(f"link-{link.name}", "link", (link.name,), specs["edge_link"])
            )
    conduits: dict[str, list[str]] = {}
    for link in scenario.links:
        if link.source.startswith("a") and link.target.startswith("p"):
            conduits.setdefault(link.srlg, []).append(link.name)
    for srlg, targets in sorted(conduits.items()):
        units.append(Unit(f"srlg-{srlg}", "srlg", tuple(sorted(targets)), specs["conduit"]))
    for link in scenario.links:
        if link.source.startswith("p") and link.target.startswith("c"):
            units.append(Unit(f"link-{link.name}", "link", (link.name,), specs["pcloud"]))
    return tuple(units)


@dataclass(frozen=True)
class Interval:
    """A piece of time over which the dependency state does not change."""

    start: float
    end: float
    down_nodes: frozenset[str]
    down_links: frozenset[str]
    episode: int

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def midpoint(self) -> float:
        return 0.5 * (self.start + self.end)

    @property
    def any_down(self) -> bool:
        return bool(self.down_nodes or self.down_links)


# --- Sampling --------------------------------------------------------------------------


def _sample_process(
    rng: np.random.Generator, spec: ProcessSpec, horizon: float
) -> list[tuple[float, float]]:
    """Sample the busy intervals of one alternating renewal process."""
    spans: list[tuple[float, float]] = []
    time = 0.0
    while time < horizon:
        time += float(rng.exponential(spec.mtbf_s))
        if time >= horizon:
            break
        duration = float(
            spec.median_s * math.exp(spec.sigma_ln * float(rng.standard_normal()))
        )
        duration = min(max(duration, 1.0), DURATION_CAP_S, horizon - time)
        spans.append((time, time + duration))
        time += duration
    return spans


def _sample_injected(
    rng: np.random.Generator, kind: str, horizon: float
) -> tuple[float, float] | None:
    """Sample the injected incident window, or ``None`` for the ``none`` class."""
    if kind == "none":
        return None
    start = INCIDENT_START_MIN_S + float(rng.random()) * INCIDENT_START_SPAN_S
    duration = INCIDENT_MEDIAN_S[kind] * math.exp(
        INCIDENT_SIGMA_LN * float(rng.standard_normal())
    )
    duration = min(max(duration, 60.0), DURATION_CAP_S, horizon - start)
    return (start, start + duration)


def build_timeline(
    units: Sequence[Unit],
    sampled: dict[str, list[tuple[float, float]]],
    injected: tuple[float, float] | None,
    injected_targets: tuple[frozenset[str], frozenset[str]],
    horizon: float,
) -> list[Interval]:
    """Sweep the sampled spans into piecewise-constant dependency states.

    An *episode* is a maximal run of time with at least one dependency down.  All
    arms share the episode numbering, so the fallback draws are paired.
    """
    by_name = {unit.name: unit for unit in units}
    events: list[tuple[float, int, str]] = []
    for unit in units:
        for start, end in sampled.get(unit.name, ()):
            events.append((start, 1, unit.name))
            events.append((end, -1, unit.name))
    if injected is not None:
        events.append((injected[0], 1, "__injected__"))
        events.append((injected[1], -1, "__injected__"))
    events.sort(key=lambda item: (item[0], item[1]))
    bounds = sorted({0.0, horizon, *(item[0] for item in events)})

    active: dict[str, int] = {}
    down_nodes: set[str] = set()
    down_links: set[str] = set()
    episode = 0
    previous_down = False
    intervals: list[Interval] = []
    cursor = 0
    for index in range(len(bounds) - 1):
        start, end = bounds[index], bounds[index + 1]
        while cursor < len(events) and events[cursor][0] <= start + 1e-9:
            _, delta, name = events[cursor]
            cursor += 1
            count = active.get(name, 0) + delta
            if count <= 0:
                active.pop(name, None)
            else:
                active[name] = count
        down_nodes, down_links = _active_targets(
            active, by_name, injected_targets
        )
        has_down = bool(down_nodes or down_links)
        if has_down and not previous_down:
            episode += 1
        previous_down = has_down
        intervals.append(
            Interval(
                start,
                end,
                down_nodes,
                down_links,
                min(episode, MAX_EPISODES - 1) if has_down else 0,
            )
        )
    return intervals


def _active_targets(
    active: dict[str, int],
    by_name: dict[str, Unit],
    injected_targets: tuple[frozenset[str], frozenset[str]],
) -> tuple[frozenset[str], frozenset[str]]:
    """Recompute the down sets for the current active-unit set."""
    nodes: set[str] = set()
    links: set[str] = set()
    for name in active:
        if name == "__injected__":
            injected_nodes, injected_links = injected_targets
            nodes.update(injected_nodes)
            links.update(injected_links)
            continue
        unit = by_name[name]
        if unit.kind == "node":
            nodes.update(unit.targets)
        else:
            links.update(unit.targets)
    return frozenset(nodes), frozenset(links)


def _ou_series(
    rng: np.random.Generator,
    midpoints: Sequence[float],
    mean: float,
    sd: float,
    tau_s: float,
    clip: tuple[float, float] | None = None,
) -> list[float]:
    """Exact Ornstein-Uhlenbeck sampling at increasing times."""
    values: list[float] = []
    previous = mean + sd * float(rng.standard_normal())
    previous_time = 0.0
    for time in midpoints:
        dt = max(time - previous_time, 0.0)
        phi = math.exp(-dt / tau_s)
        noise = math.sqrt(max(1.0 - phi * phi, 0.0)) * sd * float(rng.standard_normal())
        previous = mean + phi * (previous - mean) + noise
        value = previous
        if clip is not None:
            value = min(max(value, clip[0]), clip[1])
        values.append(value)
        previous_time = time
    return values


@dataclass(frozen=True)
class Processes:
    """The stochastic processes of one replication on the interval grid."""

    demand: dict[str, list[float]]
    modulation: dict[str, list[float]]
    activation: np.ndarray
    delay: dict[str, np.ndarray]
    capacity: dict[str, np.ndarray]


def sample_processes(
    scenario: cm.Scenario,
    intervals: Sequence[Interval],
    replication: int,
    params: MCParams = DEFAULT_PARAMS,
    base_seed: int = BASE_SEED,
) -> Processes:
    """Sample demand, link modulation and the fallback draws on the grid."""
    midpoints = [interval.midpoint for interval in intervals]
    day = 24 * 3600.0

    demand_rng = np.random.default_rng([base_seed, replication, 2])
    demand: dict[str, list[float]] = {}
    for tenant in scenario.tenants:
        smooth = _ou_series(
            demand_rng, midpoints, 0.0, params.demand_ou_sd, params.demand_ou_tau_s
        )
        demand[tenant.name] = [
            params.base_demand_gbps
            * (
                1.0
                + params.demand_diurnal_amplitude
                * math.sin(2 * math.pi * (time - 2 * 3600.0) / day)
            )
            * math.exp(value)
            for time, value in zip(midpoints, smooth)
        ]

    modulation_rng = np.random.default_rng([base_seed, replication, 3])
    modulation: dict[str, list[float]] = {}
    #: Adaptive modulation is a property of the radio edge link (microwave or
    #: mmWave).  The aggregation and provider-cloud links are fibre and are
    #: modelled as stable; applying an independent modulation process to every
    #: link of a path would bias the path minimum below the per-link mean, which
    #: is an artefact of the minimum, not a property of the link.
    flat = [1.0] * len(midpoints)
    for link in scenario.links:
        if link.source.startswith("e"):
            modulation[link.name] = _ou_series(
                modulation_rng,
                midpoints,
                params.modulation_mean,
                params.modulation_sd,
                params.modulation_tau_s,
                clip=(0.60, 1.00),
            )
        else:
            modulation[link.name] = flat

    fallback_rng = np.random.default_rng([base_seed, replication, 4])
    tenants = len(scenario.tenants)
    activation = fallback_rng.random((MAX_EPISODES, tenants))
    delay = {
        "tested": np.exp(
            fallback_rng.standard_normal((MAX_EPISODES, tenants))
            * params.fallback_delay_sigma_ln
        ),
        "untested": np.exp(
            fallback_rng.standard_normal((MAX_EPISODES, tenants))
            * params.fallback_untested_delay_sigma_ln
        ),
    }
    capacity = {
        "tested": np.exp(
            fallback_rng.standard_normal((MAX_EPISODES, tenants))
            * params.fallback_capacity_sigma_ln
        ),
        "untested": np.exp(
            fallback_rng.standard_normal((MAX_EPISODES, tenants))
            * params.fallback_untested_capacity_sigma_ln
        ),
    }
    return Processes(demand, modulation, activation, delay, capacity)


def sample_replication(
    scenario: cm.Scenario,
    replication: int,
    event_kind: str = "none",
    horizon: float = H_INCIDENT_S,
    params: MCParams = DEFAULT_PARAMS,
    base_seed: int = BASE_SEED,
) -> tuple[list[Interval], tuple[float, float] | None, dict[str, list[tuple[float, float]]]]:
    """Sample one replication's dependency timeline and injected incident."""
    rng = np.random.default_rng([base_seed, replication, 1])
    units = build_units(scenario, params)
    sampled = {unit.name: _sample_process(rng, unit.spec, horizon) for unit in units}
    injected = _sample_injected(rng, event_kind, horizon)
    injected_targets = (
        cm._event_targets(scenario, event_kind)
        if event_kind != "none"
        else (frozenset(), frozenset())
    )
    timeline = build_timeline(
        units, sampled, injected, injected_targets, horizon
    )
    return timeline, injected, sampled


# --- Per-arm path plans ---------------------------------------------------------------


@dataclass(frozen=True)
class PathPlan:
    links: tuple[tuple[str, float], ...]
    nodes: frozenset[str]
    provider_cp: str | None


@dataclass(frozen=True)
class TenantPlan:
    name: str
    index: int
    paths: tuple[PathPlan, ...]


def _path_plan(scenario: cm.Scenario, path: cm.Path) -> PathPlan:
    return PathPlan(
        links=tuple((link.name, link.capacity_gbps) for link in path.links),
        nodes=frozenset(path.nodes),
        provider_cp=scenario.provider_cps.get(path.provider),
    )


def arm_plans(scenario: cm.Scenario, arm: cm.Arm) -> tuple[TenantPlan, ...]:
    """Precompute the tenant/path plans of one arm."""
    selected = cm.select_paths(scenario, arm)
    return tuple(
        TenantPlan(
            name=tenant.name,
            index=index,
            paths=tuple(_path_plan(scenario, path) for path in selected[tenant.name]),
        )
        for index, tenant in enumerate(scenario.tenants)
    )


# --- Service evaluation ----------------------------------------------------------------


@dataclass(frozen=True)
class FallbackProfile:
    probability: float
    delay_s: float
    capacity_gbps: float
    tag: str


def fallback_profile(
    arm: cm.Arm, params: MCParams = DEFAULT_PARAMS
) -> FallbackProfile | None:
    """The fallback profile of an arm, or ``None`` when it has no fallback."""
    if arm.fallback == "tested":
        return FallbackProfile(
            params.fallback_tested_probability,
            params.fallback_tested_delay_s,
            params.fallback_tested_capacity_gbps,
            "tested",
        )
    if arm.fallback == "untested":
        return FallbackProfile(
            params.fallback_untested_probability,
            params.fallback_untested_delay_s,
            params.fallback_untested_capacity_gbps,
            "untested",
        )
    return None


def _path_capacity(
    plan: PathPlan,
    down_nodes: frozenset[str],
    down_links: frozenset[str],
    modulation: dict[str, list[float]],
    index: int,
    efficiency: float,
) -> float:
    if plan.provider_cp is not None and plan.provider_cp in down_nodes:
        return 0.0
    if plan.nodes & down_nodes:
        return 0.0
    capacity = math.inf
    for name, nominal in plan.links:
        if name in down_links:
            return 0.0
        value = nominal * modulation[name][index]
        if value < capacity:
            capacity = value
    return 0.0 if capacity is math.inf else capacity * efficiency


@dataclass(frozen=True)
class TenantMetrics:
    name: str
    segments: tuple[tuple[float, float, float, bool], ...]
    capacities: tuple[float, ...]
    event_availability: float
    overall_availability: float
    recovery_s: float
    fallback_activated: bool
    day_availability: tuple[float, ...]


def _states(
    scenario: cm.Scenario,
    arm: cm.Arm,
    tenant: TenantPlan,
    intervals: Sequence[Interval],
    modulation: dict[str, list[float]],
    params: MCParams,
    ignore_nodes: frozenset[str],
) -> list[tuple[float, bool]]:
    """Per-interval (available path capacity, need-fallback) of one tenant."""
    states: list[tuple[float, bool]] = []
    for index, interval in enumerate(intervals):
        down_nodes = interval.down_nodes - ignore_nodes
        control = cm._control_ok(scenario, arm, down_nodes)
        capacity = 0.0
        if control:
            # A global cooperative controller that is down reduces the usable
            # path set to the primary path (the reference model's rule).
            paths = tenant.paths
            if arm.controller == "global" and scenario.controller in down_nodes:
                paths = tenant.paths[:1]
            for plan in paths:
                capacity += _path_capacity(
                    plan,
                    down_nodes,
                    interval.down_links,
                    modulation,
                    index,
                    params.protocol_efficiency,
                )
        need = (not control) or capacity <= 0.0
        states.append((capacity if control else 0.0, need))
    return states


def _activation_windows(
    intervals: Sequence[Interval],
    states: Sequence[tuple[float, bool]],
    draws: Processes,
    fallback: FallbackProfile | None,
    tenant_index: int,
) -> list[float | None]:
    """The instant at which the fallback starts serving in each interval."""
    length = len(intervals)
    active_from: list[float | None] = [None] * length
    if fallback is None:
        return active_from
    activation = draws.activation[:, tenant_index]
    delay_draw = draws.delay[fallback.tag][:, tenant_index]
    index = 0
    while index < length:
        if not states[index][1]:
            index += 1
            continue
        run_start = index
        episode = intervals[index].episode
        while (
            index + 1 < length
            and states[index + 1][1]
            and intervals[index + 1].episode == episode
        ):
            index += 1
        run_end = index
        index += 1
        if activation[episode] >= fallback.probability:
            continue
        delay = fallback.delay_s * float(delay_draw[episode])
        delay = min(max(delay, 0.5), 300.0)
        start = intervals[run_start].start + delay
        if start >= intervals[run_end].end:
            continue
        for position in range(run_start, run_end + 1):
            if intervals[position].end > start:
                active_from[position] = max(start, intervals[position].start)
                for later in range(position + 1, run_end + 1):
                    active_from[later] = intervals[later].start
                break
    return active_from


def tenant_metrics(
    scenario: cm.Scenario,
    arm: cm.Arm,
    tenant: TenantPlan,
    intervals: Sequence[Interval],
    demand: Sequence[float],
    modulation: dict[str, list[float]],
    draws: Processes,
    params: MCParams,
    fallback: FallbackProfile | None,
    window: tuple[float, float] | None,
    horizon: float,
    days: int = 0,
    ignore_nodes: frozenset[str] = frozenset(),
) -> TenantMetrics:
    """Build the service segments of one arm and tenant and aggregate them."""
    states = _states(
        scenario, arm, tenant, intervals, modulation, params, ignore_nodes
    )
    active_from = _activation_windows(intervals, states, draws, fallback, tenant.index)
    fallback_capacity = (
        draws.capacity[fallback.tag][:, tenant.index] * fallback.capacity_gbps
        if fallback is not None
        else None
    )

    segments: list[tuple[float, float, float, bool]] = []
    for index, interval in enumerate(intervals):
        offered = demand[index]
        capacity, _ = states[index]
        base = min(offered, capacity)
        if arm.one_way:
            base *= params.one_way_efficiency
        any_down = interval.any_down
        ratio = base / offered if offered > 0 else 0.0
        start = active_from[index]
        if start is None or fallback_capacity is None:
            segments.append((interval.start, interval.end, ratio, any_down))
            continue
        served = min(
            offered, base + min(max(offered - base, 0.0), float(fallback_capacity[interval.episode]))
        )
        ratio_fallback = served / offered if offered > 0 else 0.0
        if start <= interval.start:
            segments.append((interval.start, interval.end, ratio_fallback, any_down))
        elif start >= interval.end:
            segments.append((interval.start, interval.end, ratio, any_down))
        else:
            segments.append((interval.start, start, ratio, any_down))
            segments.append((start, interval.end, ratio_fallback, any_down))

    overall_weighted = 0.0
    overall_duration = 0.0
    event_weighted = 0.0
    event_duration = 0.0
    fallback_activated = False
    window_start, window_end = window if window is not None else (0.0, horizon)
    for start, end, ratio, _ in segments:
        duration = end - start
        overall_weighted += duration * ratio
        overall_duration += duration
        low = max(start, window_start)
        high = min(end, window_end)
        if high > low:
            event_weighted += (high - low) * ratio
            event_duration += high - low
    overall = overall_weighted / overall_duration if overall_duration else 0.0
    event = (
        event_weighted / event_duration
        if event_duration
        else (overall if window is None else 0.0)
    )
    if window is None:
        event = overall

    if window is not None and fallback is not None:
        for index, interval in enumerate(intervals):
            if active_from[index] is None:
                continue
            if interval.end > max(interval.start, window_start) and interval.start < window_end:
                fallback_activated = True
                break

    recovery = 0.0
    if window is not None:
        incident_start = window_start
        recovery = window_end - window_start
        run_start: float | None = None
        for start, end, ratio, _ in segments:
            if end <= incident_start:
                continue
            low = max(start, incident_start)
            if low >= window_end:
                break
            if ratio >= 0.90 - 1e-12:
                if run_start is None:
                    run_start = low
                if end - run_start >= 3.0:
                    recovery = max(0.0, run_start - incident_start)
                    break
            else:
                run_start = None

    day_availability: list[float] = []
    if days:
        day_length = horizon / days
        weighted = [0.0] * days
        totals = [0.0] * days
        for start, end, ratio, _ in segments:
            first = int(start // day_length)
            last = int(min(days - 1, max(0.0, end - 1e-9) // day_length))
            for day in range(first, last + 1):
                low = max(start, day * day_length)
                high = min(end, (day + 1) * day_length)
                if high > low:
                    weighted[day] += (high - low) * ratio
                    totals[day] += high - low
        day_availability = [
            weighted[day] / totals[day] if totals[day] else 0.0 for day in range(days)
        ]

    return TenantMetrics(
        name=tenant.name,
        segments=tuple(segments),
        capacities=tuple(state[0] for state in states),
        event_availability=event,
        overall_availability=overall,
        recovery_s=recovery,
        fallback_activated=fallback_activated,
        day_availability=tuple(day_availability),
    )


# --- Results ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunResult:
    arm: str
    event: str
    replication: int
    availability_event: float
    availability_overall: float
    recovery_s: float
    blast_radius: float
    path_independence: float
    fallback_rate: float
    cost_index: float
    tenants: tuple[tuple[str, float, bool], ...] = ()


@dataclass(frozen=True)
class CampaignResult:
    arm: str
    replication: int
    availability_ss: float
    policy_loss: float
    congestion_loss: float
    dependency_loss: float
    shared_attrib: float
    slo_breach_days: float
    shared_incidents: int
    tenants: tuple[tuple[str, float], ...] = ()


def _cost_index(scenario: cm.Scenario, arm: cm.Arm) -> float:
    selected = cm.select_paths(scenario, arm)
    path_count = sum(len(selected[tenant.name]) for tenant in scenario.tenants) / len(
        scenario.tenants
    )
    return (
        0.5 * path_count
        + 0.1 * (1.0 if arm.tenant_isolation else 0.0)
        + 0.1 * (1.0 if arm.independent_control else 0.0)
        + 0.1 * (1.0 if arm.one_way else 0.0)
        + 0.05 * (1.0 if arm.controller == "global" else 0.0)
    )


def _path_independence(scenario: cm.Scenario, arm: cm.Arm) -> float:
    selected = cm.select_paths(scenario, arm)
    return sum(
        cm.path_independence(selected[tenant.name]) for tenant in scenario.tenants
    ) / len(scenario.tenants)


def _run_incident_arm(
    scenario: cm.Scenario,
    arm: cm.Arm,
    event_kind: str,
    replication: int,
    intervals: Sequence[Interval],
    injected: tuple[float, float] | None,
    demand: dict[str, list[float]],
    modulation: dict[str, list[float]],
    draws: Processes,
    params: MCParams,
    plans: Sequence[TenantPlan],
    fallback: FallbackProfile | None,
) -> RunResult:
    window = injected
    totals = {"event": 0.0, "overall": 0.0, "recovery": 0.0, "fallback": 0.0, "blast": 0.0}
    tenant_rows: list[tuple[str, float, bool]] = []
    for tenant in plans:
        metrics = tenant_metrics(
            scenario,
            arm,
            tenant,
            intervals,
            demand[tenant.name],
            modulation,
            draws,
            params,
            fallback,
            window,
            H_INCIDENT_S,
        )
        tenant_rows.append(
            (tenant.name, metrics.event_availability, metrics.fallback_activated)
        )
        totals["event"] += metrics.event_availability
        totals["overall"] += metrics.overall_availability
        totals["recovery"] += metrics.recovery_s
        totals["fallback"] += 1.0 if metrics.fallback_activated else 0.0
        totals["blast"] += 1.0 if metrics.event_availability < 0.50 else 0.0
    count = len(plans)
    return RunResult(
        arm=arm.name,
        event=event_kind,
        replication=replication,
        availability_event=totals["event"] / count,
        availability_overall=totals["overall"] / count,
        recovery_s=totals["recovery"] / count,
        blast_radius=totals["blast"] / count,
        path_independence=_path_independence(scenario, arm),
        fallback_rate=totals["fallback"] / count,
        cost_index=_cost_index(scenario, arm),
        tenants=tuple(tenant_rows),
    )


def incident_runs(
    event_kinds: Sequence[str],
    arms: Sequence[cm.Arm],
    replications: Sequence[int],
    scenario: cm.Scenario | None = None,
    params: MCParams | None = None,
    base_seed: int = BASE_SEED,
) -> list[RunResult]:
    """Run the incident experiment, sampling each replication once for all arms."""
    scenario = scenario or cm.build_backhaul_scenario()
    params = params or DEFAULT_PARAMS
    plans = {arm.name: arm_plans(scenario, arm) for arm in arms}
    fallbacks = {arm.name: fallback_profile(arm, params) for arm in arms}
    results: list[RunResult] = []
    for event_kind in event_kinds:
        for replication in replications:
            intervals, injected, _ = sample_replication(
                scenario, replication, event_kind, H_INCIDENT_S, params, base_seed
            )
            processes = sample_processes(scenario, intervals, replication, params, base_seed)
            for arm in arms:
                results.append(
                    _run_incident_arm(
                        scenario,
                        arm,
                        event_kind,
                        replication,
                        intervals,
                        injected,
                        processes.demand,
                        processes.modulation,
                        processes,
                        params,
                        plans[arm.name],
                        fallbacks[arm.name],
                    )
                )
    return results


def _campaign_arm(
    scenario: cm.Scenario,
    arm: cm.Arm,
    replication: int,
    intervals: Sequence[Interval],
    processes: Processes,
    params: MCParams,
    plans: Sequence[TenantPlan],
    fallback: FallbackProfile | None,
) -> CampaignResult:
    """Availability and its decomposition for one arm and one campaign.

    The unavailability decomposes exactly into a policy term (the one-way
    efficiency), a congestion term (demand above the available capacity while
    every dependency is up) and a dependency term (loss while something is down).
    """
    total = 0.0
    policy = 0.0
    congestion = 0.0
    dependency = 0.0
    breaches = 0
    tenant_rows: list[tuple[str, float]] = []
    efficiency = params.one_way_efficiency if arm.one_way else 1.0
    for tenant in plans:
        metrics = tenant_metrics(
            scenario,
            arm,
            tenant,
            intervals,
            processes.demand[tenant.name],
            processes.modulation,
            processes,
            params,
            fallback,
            None,
            H_CAMPAIGN_S,
            days=CAMPAIGN_DAYS,
        )
        tenant_rows.append((tenant.name, metrics.overall_availability))
        total += metrics.overall_availability
        breaches += sum(1 for value in metrics.day_availability if value < 0.99)
        demand = processes.demand[tenant.name]
        segment = 0
        for index, interval in enumerate(intervals):
            offered = demand[index]
            if offered <= 0.0:
                continue
            if interval.any_down:
                midpoint = interval.midpoint
                while (
                    segment < len(metrics.segments)
                    and metrics.segments[segment][1] <= midpoint
                ):
                    segment += 1
                ratio = (
                    metrics.segments[segment][2]
                    if segment < len(metrics.segments)
                    else 0.0
                )
                dependency += interval.duration * (1.0 - ratio)
            else:
                capacity = metrics.capacities[index]
                policy += interval.duration * (1.0 - efficiency)
                congestion += interval.duration * efficiency * max(
                    0.0, 1.0 - capacity / offered
                )
    count = len(plans)
    availability = total / count
    duration = H_CAMPAIGN_S
    policy_share = policy / (count * duration)
    congestion_share = congestion / (count * duration)
    dependency_share = dependency / (count * duration)

    ablated = 0.0
    for tenant in plans:
        metrics = tenant_metrics(
            scenario,
            arm,
            tenant,
            intervals,
            processes.demand[tenant.name],
            processes.modulation,
            processes,
            params,
            fallback,
            None,
            H_CAMPAIGN_S,
            ignore_nodes=frozenset({"idp", "dns", "ai"}),
        )
        ablated += metrics.overall_availability
    ablated /= count
    attribution = 0.0
    if dependency_share > 0.0:
        attribution = min(1.0, max(0.0, (ablated - availability) / dependency_share))
    return CampaignResult(
        arm=arm.name,
        replication=replication,
        availability_ss=availability,
        policy_loss=policy_share,
        congestion_loss=congestion_share,
        dependency_loss=dependency_share,
        shared_attrib=attribution,
        slo_breach_days=breaches / count,
        shared_incidents=0,
        tenants=tuple(tenant_rows),
    )


def campaign_runs(
    arms: Sequence[cm.Arm],
    replications: Sequence[int],
    scenario: cm.Scenario | None = None,
    params: MCParams | None = None,
    base_seed: int = BASE_SEED,
) -> list[CampaignResult]:
    """Run the 30-day campaign, sampling each replication once for all arms."""
    scenario = scenario or cm.build_backhaul_scenario()
    params = params or DEFAULT_PARAMS
    plans = {arm.name: arm_plans(scenario, arm) for arm in arms}
    fallbacks = {arm.name: fallback_profile(arm, params) for arm in arms}
    results: list[CampaignResult] = []
    for replication in replications:
        intervals, _, sampled = sample_replication(
            scenario, replication, "none", H_CAMPAIGN_S, params, base_seed
        )
        processes = sample_processes(scenario, intervals, replication, params, base_seed)
        shared_incidents = sum(
            len(sampled.get(unit.name, ()))
            for unit in build_units(scenario, params)
            if unit.name.startswith("shared-")
        )
        for arm in arms:
            result = _campaign_arm(
                scenario,
                arm,
                replication,
                intervals,
                processes,
                params,
                plans[arm.name],
                fallbacks[arm.name],
            )
            results.append(
                CampaignResult(
                    **{
                        **result.__dict__,
                        "shared_incidents": shared_incidents,
                    }
                )
            )
    return results


def simulate_incident(
    arm: cm.Arm,
    event_kind: str,
    replication: int,
    scenario: cm.Scenario | None = None,
    params: MCParams | None = None,
    base_seed: int = BASE_SEED,
) -> RunResult:
    """Run one arm on one replication of one incident class."""
    return incident_runs(
        [event_kind], [arm], [replication], scenario, params, base_seed
    )[0]


def simulate_campaign(
    arm: cm.Arm,
    replication: int,
    scenario: cm.Scenario | None = None,
    params: MCParams | None = None,
    base_seed: int = BASE_SEED,
) -> CampaignResult:
    """Run one arm over one 30-day campaign replication."""
    return campaign_runs([arm], [replication], scenario, params, base_seed)[0]
