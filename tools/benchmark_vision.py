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

"""Run reproducible, synthetic policy comparisons for the 7G vision paper."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

TICK_SECONDS = 30.0
SIMULATION_TICKS = 180
PREDICTION_HORIZON_TICKS = 3
BASE_CACHE_HIT = 0.08
SAFETY_DURATION_SECONDS = 180
SAFETY_FORECAST_HORIZON_SECONDS = 6.0
VIDEO_FRAMES_PER_SECOND = 30
VIDEO_FRAME_SEGMENTS = 14
VIDEO_FRAME_DEADLINE_MS = 150.0
AUDIO_PACKETS_PER_SECOND = 50
AUDIO_PACKET_DEADLINE_MS = 50.0
VIDEO_MEDIA_BITRATE_MBPS = 4.0
AUDIO_MEDIA_BITRATE_MBPS = 0.128
SAFETY_POLICIES = (
    "Single-path handover",
    "Reactive multipath",
    "Predictive overflow multipath",
    "Predictive multipath + media assist",
)


def _always(_tick: int) -> bool:
    return True


@dataclass(frozen=True)
class Link:
    name: str
    capacity_mbps: float
    latency_ms: float
    cost_per_gb: float
    base_loss: float
    availability: Callable[[int], bool] = _always


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    description: str
    base_demand_mbps: float
    links: tuple[Link, ...]
    demand: Callable[[int, np.random.Generator], float]
    initial_cache_hit: float = BASE_CACHE_HIT


POLICIES = (
    "5G-oriented single-path baseline (synthetic)",
    "Reactive multipath baseline (6G-oriented, synthetic)",
    "Proposed predictive-cooperative policy (synthetic)",
)


def _urban_demand(tick: int, rng: np.random.Generator) -> float:
    daily = 220.0 + 25.0 * np.sin(2.0 * np.pi * tick / 90.0)
    flash = 240.0 if 45 <= tick < 105 else 0.0
    return max(1.0, daily + flash + rng.normal(0.0, 12.0))


def _rural_demand(tick: int, rng: np.random.Generator) -> float:
    growth = 0.12 * tick
    evening_burst = 28.0 if 110 <= tick < 150 else 0.0
    return max(1.0, 58.0 + growth + evening_burst + rng.normal(0.0, 5.0))


def _mobility_demand(tick: int, rng: np.random.Generator) -> float:
    return max(
        1.0,
        150.0 + 24.0 * np.sin(2.0 * np.pi * tick / 45.0) + rng.normal(0.0, 10.0),
    )


def _orbital_demand(tick: int, rng: np.random.Generator) -> float:
    observation_burst = 45.0 if 60 <= tick < 120 else 0.0
    return max(1.0, 90.0 + observation_burst + rng.normal(0.0, 7.0))


def _cell_available(tick: int) -> bool:
    return not 42 <= tick < 72


def _fiber_available(tick: int) -> bool:
    return not 78 <= tick < 94


def _wifi_available(tick: int) -> bool:
    return tick % 30 < 25


def _leo_contact(tick: int) -> bool:
    return 12 <= tick % 60 < 42


def build_scenarios() -> tuple[Scenario, ...]:
    return (
        Scenario(
            key="urban_burst",
            title="Urban flash crowd",
            description="Sudden demand surge across fiber, microwave, cellular, and LEO paths.",
            base_demand_mbps=220.0,
            demand=_urban_demand,
            links=(
                Link("fiber", 190.0, 8.0, 0.018, 0.002),
                Link("microwave", 125.0, 14.0, 0.026, 0.008),
                Link("cellular", 95.0, 27.0, 0.052, 0.012),
                Link("leo", 115.0, 58.0, 0.115, 0.018),
            ),
        ),
        Scenario(
            key="rural_growth",
            title="Rural coverage and growth",
            description="No fiber; constrained microwave and cellular plus higher-latency LEO service.",
            base_demand_mbps=58.0,
            demand=_rural_demand,
            initial_cache_hit=0.12,
            links=(
                Link("microwave", 38.0, 24.0, 0.032, 0.012),
                Link("cellular", 24.0, 48.0, 0.060, 0.020),
                Link("leo", 92.0, 76.0, 0.125, 0.025),
            ),
        ),
        Scenario(
            key="mobility_outages",
            title="Mobility and link outages",
            description="Mobile path outage, later fiber outage, and recurring Wi-Fi availability gaps.",
            base_demand_mbps=150.0,
            demand=_mobility_demand,
            links=(
                Link("fiber", 165.0, 9.0, 0.020, 0.003, _fiber_available),
                Link("cellular", 105.0, 26.0, 0.055, 0.015, _cell_available),
                Link("wifi", 78.0, 13.0, 0.014, 0.018, _wifi_available),
                Link("leo", 100.0, 64.0, 0.120, 0.022),
            ),
        ),
        Scenario(
            key="orbital_contacts",
            title="Intermittent orbital contacts",
            description="Remote workload with scheduled LEO contact windows and a costly GEO fallback.",
            base_demand_mbps=90.0,
            demand=_orbital_demand,
            initial_cache_hit=0.10,
            links=(
                Link("remote_microwave", 32.0, 145.0, 0.045, 0.015),
                Link("leo_contact", 145.0, 72.0, 0.105, 0.025, _leo_contact),
                Link("geo_fallback", 82.0, 255.0, 0.160, 0.018),
            ),
        ),
    )


@dataclass(frozen=True)
class RunMetrics:
    delivered_goodput_mbps: float
    p95_latency_ms: float
    continuity_percent: float
    cache_hit_percent: float
    cost_usd_per_delivered_gb: float


@dataclass(frozen=True)
class RunTrace:
    demand_mbps: np.ndarray
    delivered_mbps: np.ndarray
    cache_hit_percent: np.ndarray


@dataclass(frozen=True)
class SafetyPath:
    name: str
    capacity_mbps: float
    latency_ms: float
    loss: float


@dataclass(frozen=True)
class SafetyMetrics:
    critical_delivery_percent: float
    critical_service_availability_percent: float
    longest_critical_outage_seconds: float
    delivered_goodput_mbps: float
    secondary_activation_seconds: float
    concurrent_media_percent: float
    video_frames_on_time_percent: float
    audio_packets_on_time_percent: float
    video_stall_seconds: float
    longest_video_freeze_seconds: float
    video_freeze_events: float
    p95_video_frame_delay_ms: float
    p95_audio_jitter_ms: float
    handover_interruption_seconds: float
    handover_missed_video_frames: float
    media_assist_overhead_percent: float
    media_assist_duplicate_mbps: float


@dataclass(frozen=True)
class SafetyTrace:
    demand_mbps: np.ndarray
    critical_delivery_percent: np.ndarray
    active_capacity_mbps: np.ndarray
    secondary_active: np.ndarray
    primary_degraded: np.ndarray
    video_frames_on_time_percent: np.ndarray
    audio_packets_on_time_percent: np.ndarray
    video_stall_seconds: np.ndarray
    transport_assist_active: np.ndarray


def _forecast(history: list[float], horizon: float) -> float:
    if len(history) < 3:
        return history[-1] if history else 0.0
    older, previous, current = history[-3:]
    velocity = current - previous
    acceleration = current - 2.0 * previous + older
    return float(np.clip(current + velocity * horizon + 0.5 * acceleration * horizon**2, 0.0, 1.0))


def _forecast_demand(history: list[float], horizon: float) -> float:
    if len(history) < 3:
        return max(0.0, history[-1] if history else 0.0)
    older, previous, current = history[-3:]
    velocity = current - previous
    acceleration = current - 2.0 * previous + older
    return max(0.0, current + velocity * horizon + 0.5 * acceleration * horizon**2)


def _allocate(
    demand: float,
    links: list[Link],
    scores: np.ndarray,
) -> np.ndarray:
    """Allocate demand proportionally and redistribute capacity overflow."""
    allocation = np.zeros(len(links), dtype=float)
    remaining = max(0.0, demand)
    eligible = set(range(len(links)))
    while eligible and remaining > 1e-9:
        indices = sorted(eligible)
        weights = np.asarray([max(0.0, scores[index]) for index in indices])
        if weights.sum() <= 0:
            weights = np.ones(len(indices), dtype=float)
        proposals = remaining * weights / weights.sum()
        saturated: list[int] = []
        delivered_this_round = 0.0
        for index, proposed in zip(indices, proposals):
            room = links[index].capacity_mbps - allocation[index]
            accepted = min(max(0.0, room), proposed)
            allocation[index] += accepted
            delivered_this_round += accepted
            if room <= proposed + 1e-9:
                saturated.append(index)
        remaining -= delivered_this_round
        eligible.difference_update(saturated)
        if not saturated:
            break
        if delivered_this_round <= 1e-12:
            break
    return allocation


def _weighted_percentile(values: list[float], weights: list[float], percentile: float) -> float:
    if not values or sum(weights) <= 0:
        return 0.0
    order = np.argsort(values)
    sorted_values = np.asarray(values)[order]
    sorted_weights = np.asarray(weights)[order]
    cumulative = np.cumsum(sorted_weights)
    cutoff = percentile / 100.0 * cumulative[-1]
    return float(sorted_values[min(int(np.searchsorted(cumulative, cutoff)), len(sorted_values) - 1)])


def simulate(
    scenario: Scenario,
    policy: str,
    seed: int,
    retain_trace: bool = False,
) -> tuple[RunMetrics, RunTrace | None]:
    if policy not in POLICIES:
        raise ValueError(f"Unknown policy: {policy}")
    rng = np.random.default_rng(seed)
    pressure_histories: list[list[float]] = [[] for _ in scenario.links]
    demand_history: list[float] = []
    current_cache_hit = scenario.initial_cache_hit
    delivered_samples: list[float] = []
    latency_samples: list[float] = []
    latency_weights: list[float] = []
    demand_samples: list[float] = []
    cache_samples: list[float] = []
    continuity_samples: list[bool] = []
    total_link_cost = 0.0
    total_replication_cost = 0.0
    total_delivered_gb = 0.0

    for tick in range(SIMULATION_TICKS):
        demand = scenario.demand(tick, rng)
        available_indices = [
            index
            for index, link in enumerate(scenario.links)
            if link.availability(tick)
        ]
        available_links = [scenario.links[index] for index in available_indices]
        current_pressures = [
            pressure_histories[index][-1] if pressure_histories[index] else 0.0
            for index in available_indices
        ]

        if policy == POLICIES[0]:
            current_latencies = [
                link.latency_ms + 55.0 * pressure
                for link, pressure in zip(available_links, current_pressures)
            ]
            selected = (
                int(np.argmin(current_latencies))
                if current_latencies
                else None
            )
            local_links = [available_links[selected]] if selected is not None else []
            local_global_indices = (
                [available_indices[selected]]
                if selected is not None
                else []
            )
            scores = np.ones(len(local_links), dtype=float)
        else:
            local_links = available_links
            local_global_indices = available_indices
            if policy == POLICIES[1]:
                forecast_pressures = current_pressures
            else:
                forecast_pressures = [
                    _forecast(pressure_histories[index], PREDICTION_HORIZON_TICKS)
                    for index in available_indices
                ]
            scores = np.asarray(
                [
                    link.capacity_mbps
                    / (link.latency_ms + 12.0 + 55.0 * pressure)
                    / (1.0 + 0.5 * link.cost_per_gb / 0.16)
                    for link, pressure in zip(local_links, forecast_pressures)
                ],
                dtype=float,
            )

        demand_history.append(demand / max(scenario.base_demand_mbps, 1.0))
        demand_history = demand_history[-5:]
        if policy == POLICIES[0]:
            target_cache_hit = scenario.initial_cache_hit
        elif policy == POLICIES[1]:
            reactive_demand = float(np.mean(demand_history))
            target_cache_hit = float(
                np.clip(
                    scenario.initial_cache_hit
                    + 0.13 * max(0.0, reactive_demand - 1.0),
                    scenario.initial_cache_hit,
                    0.34,
                )
            )
        else:
            predicted_demand = _forecast_demand(
                demand_history,
                PREDICTION_HORIZON_TICKS,
            )
            target_cache_hit = float(
                np.clip(
                    scenario.initial_cache_hit
                    + 0.19 * max(0.0, predicted_demand - 1.0),
                    scenario.initial_cache_hit,
                    0.48,
                )
            )

        cache_delta = target_cache_hit - current_cache_hit
        if policy == POLICIES[2]:
            cache_step = float(np.clip(cache_delta, -0.035, 0.11))
        else:
            cache_step = float(np.clip(cache_delta, -0.035, 0.065))
        current_cache_hit = float(
            np.clip(
                current_cache_hit + cache_step,
                scenario.initial_cache_hit,
                0.50,
            )
        )
        cache_bytes_gb = max(0.0, cache_step) * demand * TICK_SECONDS / 8000.0
        total_replication_cost += cache_bytes_gb * 0.07

        local_demand = demand * current_cache_hit
        backhaul_demand = demand - local_demand
        local_allocations = _allocate(backhaul_demand, local_links, scores)
        successful_remote = 0.0
        remote_latency_values: list[float] = []
        remote_latency_weights: list[float] = []
        allocated_by_link = np.zeros(len(scenario.links), dtype=float)

        for global_index, link, amount in zip(
            local_global_indices,
            local_links,
            local_allocations,
        ):
            utilization = min(1.0, amount / link.capacity_mbps)
            congestion_loss = max(0.0, utilization - 0.82) * 0.13
            packet_loss = min(0.35, link.base_loss + congestion_loss)
            delivered = amount * (1.0 - packet_loss)
            successful_remote += delivered
            allocated_by_link[global_index] = amount
            queue_delay = max(0.0, utilization - 0.65) * link.latency_ms * 2.5
            latency = link.latency_ms + queue_delay
            remote_latency_values.append(latency)
            remote_latency_weights.append(delivered)
            transferred_gb = amount * TICK_SECONDS / 8000.0
            total_link_cost += transferred_gb * link.cost_per_gb

        for global_index in available_indices:
            link = scenario.links[global_index]
            utilization = min(1.0, allocated_by_link[global_index] / link.capacity_mbps)
            packet_loss = min(
                0.35,
                link.base_loss + max(0.0, utilization - 0.82) * 0.13,
            )
            observed_pressure = float(
                np.clip(
                    0.70 * utilization
                    + 0.20 * max(0.0, utilization - 0.65) / 0.35
                    + 0.10 * packet_loss,
                    0.0,
                    1.0,
                )
            )
            pressure_histories[global_index].append(observed_pressure)
            pressure_histories[global_index] = pressure_histories[global_index][-3:]

        total_delivered = local_demand + successful_remote
        delivered_gb = total_delivered * TICK_SECONDS / 8000.0
        total_delivered_gb += delivered_gb
        continuity_samples.append(total_delivered >= 0.95 * demand)
        delivered_samples.append(total_delivered)
        demand_samples.append(demand)
        cache_samples.append(current_cache_hit)
        if local_demand > 0:
            latency_samples.append(2.0)
            latency_weights.append(local_demand)
        latency_samples.extend(remote_latency_values)
        latency_weights.extend(remote_latency_weights)

    mean_goodput = float(np.mean(delivered_samples))
    cost_per_gb = (
        (total_link_cost + total_replication_cost) / total_delivered_gb
        if total_delivered_gb > 0
        else 0.0
    )
    metrics = RunMetrics(
        delivered_goodput_mbps=mean_goodput,
        p95_latency_ms=_weighted_percentile(latency_samples, latency_weights, 95.0),
        continuity_percent=float(np.mean(continuity_samples) * 100.0),
        cache_hit_percent=float(np.mean(cache_samples) * 100.0),
        cost_usd_per_delivered_gb=float(cost_per_gb),
    )
    trace = (
        RunTrace(
            demand_mbps=np.asarray(demand_samples),
            delivered_mbps=np.asarray(delivered_samples),
            cache_hit_percent=np.asarray(cache_samples) * 100.0,
        )
        if retain_trace
        else None
    )
    return metrics, trace


def _mean_ci(values: list[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    margin = 1.96 * float(np.std(array, ddof=1)) / np.sqrt(len(array)) if len(array) > 1 else 0.0
    return float(np.mean(array)), margin


def run_benchmark(
    output_dir: Path,
    replicates: int = 30,
    seed: int = 2026,
) -> list[dict[str, object]]:
    if replicates < 2:
        raise ValueError("At least two independent replicates are required.")
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = build_scenarios()
    rng = np.random.default_rng(seed)
    seeds = [int(value) for value in rng.integers(0, 2**31 - 1, size=replicates)]
    metric_names = tuple(RunMetrics.__dataclass_fields__)
    rows: list[dict[str, object]] = []

    for scenario in scenarios:
        for policy in POLICIES:
            observations = {name: [] for name in metric_names}
            for replicate_seed in seeds:
                metrics, _ = simulate(scenario, policy, replicate_seed)
                for name in metric_names:
                    observations[name].append(float(getattr(metrics, name)))
            row: dict[str, object] = {
                "scenario": scenario.key,
                "scenario_title": scenario.title,
                "policy": policy,
                "replicates": replicates,
            }
            for metric_name, samples in observations.items():
                mean, ci95 = _mean_ci(samples)
                row[metric_name] = mean
                row[f"{metric_name}_ci95"] = ci95
            rows.append(row)

    summary_path = output_dir / "vision_benchmark_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    _plot_summary(rows, scenarios, output_dir)
    _plot_example_trace(scenarios[0], seeds[0], output_dir)
    print(f"Replicates per policy/scenario: {replicates}")
    print(f"Random seed: {seed}")
    print(f"Summary CSV: {summary_path}")
    for row in rows:
        print(
            f"{row['scenario_title']} | {row['policy']} | "
            f"goodput={row['delivered_goodput_mbps']:.1f} Mbps | "
            f"p95={row['p95_latency_ms']:.1f} ms | "
            f"continuity={row['continuity_percent']:.1f}% | "
            f"cache={row['cache_hit_percent']:.1f}% | "
            f"cost=${row['cost_usd_per_delivered_gb']:.4f}/GB"
        )
    return rows


def _plot_summary(
    rows: list[dict[str, object]],
    scenarios: tuple[Scenario, ...],
    output_dir: Path,
) -> None:
    colors = ("#4C78A8", "#F2A541", "#3A9D78", "#8055A5")
    labels = [scenario.title for scenario in scenarios]
    x = np.arange(len(scenarios))
    width = 0.24
    metric_specs = (
        (
            "delivered_goodput_mbps",
            "Delivered goodput (Mbps)",
            "Higher is better",
            "vision_benchmark_goodput.png",
        ),
        (
            "p95_latency_ms",
            "Weighted p95 latency (ms)",
            "Lower is better",
            "vision_benchmark_latency.png",
        ),
        (
            "continuity_percent",
            "Time steps meeting 95% delivery (%)",
            "Higher is better",
            "vision_benchmark_continuity.png",
        ),
        (
            "cache_hit_percent",
            "Mean cache-hit fraction (%)",
            "Descriptive",
            "vision_benchmark_cache.png",
        ),
        (
            "cost_usd_per_delivered_gb",
            "Modeled cost per delivered GB (USD)",
            "Lower is better",
            "vision_benchmark_cost.png",
        ),
    )
    lookup = {(str(row["scenario"]), str(row["policy"])): row for row in rows}

    for metric, ylabel, note, filename in metric_specs:
        figure, axis = plt.subplots(figsize=(11, 5.6), layout="constrained")
        for policy_index, policy in enumerate(POLICIES):
            means = []
            errors = []
            for scenario in scenarios:
                row = lookup[(scenario.key, policy)]
                means.append(float(row[metric]))
                errors.append(float(row[f"{metric}_ci95"]))
            offset = (policy_index - 1) * width
            axis.bar(
                x + offset,
                means,
                width,
                yerr=errors,
                capsize=3,
                label=policy,
                color=colors[policy_index],
                edgecolor="white",
                linewidth=0.6,
            )
        axis.set_ylabel(ylabel)
        axis.set_title(f"{ylabel}\n{note}; mean and 95% normal-approximation CI (n={rows[0]['replicates']})")
        axis.set_xticks(x, labels, rotation=12, ha="right")
        axis.grid(axis="y", alpha=0.25)
        axis.legend(frameon=False, loc="best")
        figure.savefig(output_dir / filename, dpi=180)
        plt.close(figure)


def _plot_example_trace(scenario: Scenario, seed: int, output_dir: Path) -> None:
    figure, (demand_axis, cache_axis) = plt.subplots(
        2,
        1,
        figsize=(11, 7),
        sharex=True,
        layout="constrained",
    )
    colors = ("#4C78A8", "#F2A541", "#3A9D78", "#8055A5")
    tick_seconds = np.arange(SIMULATION_TICKS) * TICK_SECONDS
    for policy, color in zip(POLICIES, colors):
        _, trace = simulate(scenario, policy, seed, retain_trace=True)
        if trace is None:
            raise RuntimeError("Expected a time-series trace for the example plot.")
        demand_axis.plot(
            tick_seconds,
            trace.delivered_mbps,
            color=color,
            linewidth=1.6,
            label=f"{policy}: delivered",
        )
        cache_axis.plot(
            tick_seconds,
            trace.cache_hit_percent,
            color=color,
            linewidth=1.6,
            label=policy,
        )
    _, exemplar = simulate(scenario, POLICIES[0], seed, retain_trace=True)
    if exemplar is None:
        raise RuntimeError("Expected a demand trace for the example plot.")
    demand_axis.plot(
        tick_seconds,
        exemplar.demand_mbps,
        color="#444444",
        linestyle="--",
        alpha=0.7,
        label="Requested demand",
    )
    demand_axis.set_ylabel("Traffic rate (Mbps)")
    demand_axis.set_title(
        f"Urban flash-crowd example (one reproducible run; seed={seed})"
    )
    demand_axis.grid(alpha=0.25)
    demand_axis.legend(frameon=False, ncol=2)
    cache_axis.set_ylabel("Cache-hit fraction (%)")
    cache_axis.set_xlabel("Synthetic scenario time (s)")
    cache_axis.set_ylim(0, 55)
    cache_axis.grid(alpha=0.25)
    cache_axis.legend(frameon=False, loc="upper left")
    figure.savefig(output_dir / "vision_benchmark_urban_timeseries.png", dpi=180)
    plt.close(figure)


def _safety_paths() -> tuple[SafetyPath, ...]:
    return (
        SafetyPath("Wi-Fi", 80.0, 10.0, 0.001),
        SafetyPath("Mobile", 150.0, 32.0, 0.001),
        SafetyPath("HF", 60.0, 115.0, 0.002),
        SafetyPath("Satellite", 280.0, 130.0, 0.001),
    )


def _safety_demand(tick: int, rng: np.random.Generator) -> tuple[float, float]:
    elapsed = float(tick)
    ramp = 16.0 + 0.016 * min(elapsed, 125.0) ** 2
    wave = 65.0 * np.exp(-((elapsed - 88.0) / 12.0) ** 2)
    wave += 38.0 * np.exp(-((elapsed - 145.0) / 9.0) ** 2)
    bulk = max(0.0, ramp + wave + rng.normal(0.0, 1.5))
    critical = 12.0
    return critical, bulk


def _forecast_safety_load(history: list[float], horizon: float) -> float:
    if len(history) < 3:
        return history[-1] if history else 0.0
    recent = np.asarray(history[-5:], dtype=float)
    velocities = np.diff(recent)
    velocity = float(np.median(velocities))
    accelerations = np.diff(velocities)
    acceleration = (
        float(np.clip(np.median(accelerations), -0.1, 0.1))
        if len(accelerations)
        else 0.0
    )
    return max(
        recent[-1],
        float(recent[-1] + velocity * horizon + 0.5 * acceleration * horizon**2),
    )


def _sample_media_packet(
    path: SafetyPath,
    utilization: float,
    rng: np.random.Generator,
) -> tuple[float, bool]:
    queue_delay = max(0.0, utilization - 0.65) * path.latency_ms * 2.5
    jitter_sigma = 0.5 + 0.025 * path.latency_ms
    delay = max(
        0.0,
        path.latency_ms
        + queue_delay
        + float(rng.normal(0.0, jitter_sigma)),
    )
    loss_probability = min(
        0.03,
        path.loss + max(0.0, utilization - 0.9) * 0.03,
    )
    return delay, bool(rng.random() >= loss_probability)


def _finite_percentile(values: list[float], percentile: float) -> float:
    finite_values = np.asarray(values, dtype=float)
    finite_values = finite_values[np.isfinite(finite_values)]
    return (
        float(np.percentile(finite_values, percentile))
        if finite_values.size
        else 0.0
    )


def _longest_failed_run(successes: list[bool]) -> int:
    longest = 0
    current = 0
    for success in successes:
        current = 0 if success else current + 1
        longest = max(longest, current)
    return longest


def _count_freeze_events(
    successes: list[bool],
    minimum_frames: int,
) -> int:
    count = 0
    current = 0
    for success in successes:
        if success:
            count += int(current >= minimum_frames)
            current = 0
        else:
            current += 1
    return count + int(current >= minimum_frames)


def simulate_public_safety(
    policy: str,
    seed: int,
    retain_trace: bool = False,
) -> tuple[SafetyMetrics, SafetyTrace | None]:
    if policy not in SAFETY_POLICIES:
        raise ValueError(f"Unknown public-safety policy: {policy}")

    paths = _safety_paths()
    demand_rng = np.random.default_rng(seed)
    media_rng = np.random.default_rng(seed ^ 0x5EED)
    active_paths = {0}
    current_path = 0
    pending_path: int | None = None
    handover_ticks_remaining = 0
    demand_history: list[float] = []
    requested_critical = 0.0
    delivered_critical = 0.0
    delivered_total = 0.0
    available_samples: list[bool] = []
    outage_run = 0
    longest_outage = 0
    secondary_activation = SAFETY_DURATION_SECONDS
    concurrent_samples: list[bool] = []
    demand_samples: list[float] = []
    critical_delivery_samples: list[float] = []
    active_capacity_samples: list[float] = []
    secondary_samples: list[bool] = []
    degraded_samples: list[bool] = []
    video_frame_successes: list[bool] = []
    video_frame_delays: list[float] = []
    audio_packet_successes: list[bool] = []
    audio_jitter_samples: list[float] = []
    previous_audio_delay: float | None = None
    video_frame_success_samples: list[float] = []
    audio_packet_success_samples: list[float] = []
    video_stall_samples: list[float] = []
    handover_interruption_seconds = 0.0
    handover_missed_video_frames = 0
    media_packets_sent = 0
    media_packets_original = 0
    media_packets_duplicated = 0
    duplicate_payload_mbps_seconds = 0.0
    media_assist_samples: list[bool] = []

    for tick in range(SAFETY_DURATION_SECONDS):
        duplicate_load_mbps = np.zeros(len(paths), dtype=float)
        critical_demand, bulk_demand = _safety_demand(tick, demand_rng)
        total_demand = critical_demand + bulk_demand
        demand_history.append(total_demand)
        demand_history = demand_history[-5:]

        degraded = 50 <= tick < 65
        capacities = [
            0.0 if index == 0 and degraded else path.capacity_mbps
            for index, path in enumerate(paths)
        ]
        service_indices: list[int] = []
        handover_gap = False

        if policy == SAFETY_POLICIES[0]:
            if handover_ticks_remaining:
                handover_ticks_remaining -= 1
                if handover_ticks_remaining == 0 and pending_path is not None:
                    current_path = pending_path
                    pending_path = None
                handover_gap = True
            else:
                current_capacity = capacities[current_path]
                should_switch = (
                    current_capacity <= 0.0
                    or total_demand >= 0.85 * current_capacity
                )
                if should_switch:
                    candidates = [
                        index
                        for index, capacity in enumerate(capacities)
                        if index != current_path
                        and capacity > 0.0
                        and (
                            current_capacity <= 0.0
                            or capacity > current_capacity
                        )
                    ]
                    if candidates:
                        pending_path = min(
                            candidates,
                            key=lambda index: (
                                paths[index].latency_ms,
                                -capacities[index],
                            ),
                        )
                        handover_ticks_remaining = 1
                        handover_gap = True
                    elif current_capacity > 0.0:
                        service_indices = [current_path]
                elif current_capacity > 0.0:
                    service_indices = [current_path]
        else:
            active_capacity = sum(capacities[index] for index in active_paths)
            if policy == SAFETY_POLICIES[1]:
                scale_demand = total_demand
                scale_threshold = 0.90
            else:
                scale_demand = _forecast_safety_load(
                    demand_history,
                    SAFETY_FORECAST_HORIZON_SECONDS,
                )
                scale_threshold = 0.80
            needs_overflow = scale_demand >= scale_threshold * active_capacity

            if active_capacity <= 0.0:
                available_standby = [
                    index
                    for index, capacity in enumerate(capacities)
                    if capacity > 0.0 and index not in active_paths
                ]
                if available_standby:
                    selected = max(
                        available_standby,
                        key=lambda index: capacities[index]
                        / (paths[index].latency_ms + 1.0),
                    )
                    active_paths.add(selected)
                    handover_gap = True
            elif needs_overflow:
                while True:
                    active_capacity = sum(
                        capacities[index] for index in active_paths
                    )
                    if scale_demand < scale_threshold * active_capacity:
                        break
                    standbys = [
                        index
                        for index, capacity in enumerate(capacities)
                        if capacity > 0.0 and index not in active_paths
                    ]
                    if not standbys:
                        break
                    selected = max(
                        standbys,
                        key=lambda index: capacities[index]
                        / (paths[index].latency_ms + 1.0),
                    )
                    active_paths.add(selected)

            if len(active_paths) > 1 and secondary_activation == SAFETY_DURATION_SECONDS:
                secondary_activation = tick
            service_indices = [
                index
                for index in sorted(active_paths)
                if capacities[index] > 0.0
            ]

        if handover_gap:
            service_indices = []
            handover_interruption_seconds += 1.0
            handover_missed_video_frames += VIDEO_FRAMES_PER_SECOND

        allocations = np.zeros(len(paths), dtype=float)
        critical_allocations = np.zeros(len(paths), dtype=float)
        if service_indices:
            active_links = [
                Link(
                    paths[index].name,
                    capacities[index],
                    paths[index].latency_ms,
                    0.0,
                    paths[index].loss,
                )
                for index in service_indices
            ]
            scores = np.asarray(
                [
                    paths[index].capacity_mbps
                    / (paths[index].latency_ms + 10.0)
                    for index in service_indices
                ],
                dtype=float,
            )
            critical_shares = _allocate(
                critical_demand,
                active_links,
                scores,
            )
            residual_links = [
                Link(
                    link.name,
                    max(0.0, link.capacity_mbps - critical_shares[offset]),
                    link.latency_ms,
                    link.cost_per_gb,
                    link.base_loss,
                    link.availability,
                )
                for offset, link in enumerate(active_links)
            ]
            bulk_shares = _allocate(bulk_demand, residual_links, scores)
            for offset, index in enumerate(service_indices):
                critical_allocations[index] = critical_shares[offset]
                allocations[index] = (
                    critical_shares[offset] + bulk_shares[offset]
                )

        tick_critical_delivered = 0.0
        tick_total_delivered = 0.0
        for index in service_indices:
            utilization = min(
                1.0,
                allocations[index] / max(capacities[index], 1e-9),
            )
            packet_loss = min(
                0.01,
                paths[index].loss + max(0.0, utilization - 0.9) * 0.03,
            )
            tick_critical_delivered += (
                critical_allocations[index] * (1.0 - packet_loss)
            )
            tick_total_delivered += allocations[index] * (1.0 - packet_loss)

        media_path_weights = np.asarray(
            [allocations[index] for index in service_indices],
            dtype=float,
        )
        if len(service_indices) and media_path_weights.sum() <= 0.0:
            media_path_weights = np.asarray(
                [capacities[index] for index in service_indices],
                dtype=float,
            )
        if media_path_weights.sum() > 0.0:
            media_path_weights /= media_path_weights.sum()

        tick_video_successes = 0
        for _ in range(VIDEO_FRAMES_PER_SECOND):
            segment_delays: list[float] = []
            frame_received = bool(service_indices)
            for primary_index in media_rng.choice(
                service_indices,
                size=VIDEO_FRAME_SEGMENTS,
                p=media_path_weights if len(service_indices) else None,
            ) if service_indices else ():
                primary_index = int(primary_index)
                primary_utilization = min(
                    1.0,
                    (
                        allocations[primary_index]
                        + duplicate_load_mbps[primary_index]
                    )
                    / max(capacities[primary_index], 1e-9),
                )
                primary_delay, primary_received = _sample_media_packet(
                    paths[primary_index],
                    primary_utilization,
                    media_rng,
                )
                segment_received = (
                    primary_received
                    and primary_delay <= VIDEO_FRAME_DEADLINE_MS
                )
                on_time_delays = (
                    [primary_delay] if segment_received else []
                )
                media_packets_sent += 1
                media_packets_original += 1
                expected_delay = (
                    paths[primary_index].latency_ms
                    + max(0.0, primary_utilization - 0.65)
                    * paths[primary_index].latency_ms
                    * 2.5
                )
                should_duplicate = (
                    policy == SAFETY_POLICIES[3]
                    and len(service_indices) > 1
                    and (
                        expected_delay >= 0.65 * VIDEO_FRAME_DEADLINE_MS
                        or paths[primary_index].loss >= 0.0015
                        or primary_utilization >= 0.85
                    )
                )
                if should_duplicate:
                    backup_candidates = [
                        index
                        for index in service_indices
                        if index != primary_index
                        and paths[index].latency_ms < VIDEO_FRAME_DEADLINE_MS
                    ]
                    if backup_candidates:
                        backup_index = min(
                            backup_candidates,
                            key=lambda index: (
                                paths[index].latency_ms,
                                -capacities[index],
                            ),
                        )
                        duplicate_packet_load = (
                            VIDEO_MEDIA_BITRATE_MBPS
                            / (
                                VIDEO_FRAMES_PER_SECOND
                                * VIDEO_FRAME_SEGMENTS
                            )
                        )
                        backup_utilization = min(
                            1.0,
                            (
                                allocations[backup_index]
                                + duplicate_load_mbps[backup_index]
                                + duplicate_packet_load
                            )
                            / max(capacities[backup_index], 1e-9),
                        )
                        backup_delay, backup_received = _sample_media_packet(
                            paths[backup_index],
                            backup_utilization,
                            media_rng,
                        )
                        media_packets_sent += 1
                        media_packets_duplicated += 1
                        duplicate_load_mbps[backup_index] += (
                            duplicate_packet_load
                        )
                        if (
                            backup_received
                            and backup_delay <= VIDEO_FRAME_DEADLINE_MS
                        ):
                            on_time_delays.append(backup_delay)
                            segment_received = True
                if on_time_delays:
                    segment_delays.append(min(on_time_delays))
                frame_received = frame_received and segment_received
            frame_delay = max(segment_delays, default=float("inf"))
            video_frame_delays.append(frame_delay)
            on_time = frame_received and frame_delay <= VIDEO_FRAME_DEADLINE_MS
            video_frame_successes.append(on_time)
            tick_video_successes += int(on_time)

        tick_audio_successes = 0
        fast_audio_paths = sorted(
            service_indices,
            key=lambda index: (
                paths[index].latency_ms,
                -capacities[index],
            ),
        )[: 2 if policy == SAFETY_POLICIES[3] else 1]
        for _ in range(AUDIO_PACKETS_PER_SECOND):
            arrivals: list[float] = []
            media_packets_original += 1
            for index in fast_audio_paths:
                utilization = min(
                    1.0,
                    (
                        allocations[index]
                        + duplicate_load_mbps[index]
                    )
                    / max(capacities[index], 1e-9),
                )
                is_duplicate = (
                    policy == SAFETY_POLICIES[3]
                    and index != fast_audio_paths[0]
                )
                if is_duplicate:
                    duplicate_packet_load = (
                        AUDIO_MEDIA_BITRATE_MBPS / AUDIO_PACKETS_PER_SECOND
                    )
                    utilization = min(
                        1.0,
                        (
                            allocations[index]
                            + duplicate_load_mbps[index]
                            + duplicate_packet_load
                        )
                        / max(capacities[index], 1e-9),
                    )
                    duplicate_load_mbps[index] += duplicate_packet_load
                delay, received = _sample_media_packet(
                    paths[index],
                    utilization,
                    media_rng,
                )
                media_packets_sent += 1
                if is_duplicate:
                    media_packets_duplicated += 1
                if received:
                    arrivals.append(delay)
            first_arrival = min(arrivals, default=float("inf"))
            packet_received = bool(arrivals)
            packet_on_time = (
                packet_received and first_arrival <= AUDIO_PACKET_DEADLINE_MS
            )
            audio_packet_successes.append(packet_on_time)
            tick_audio_successes += int(packet_on_time)
            if packet_received:
                if previous_audio_delay is not None:
                    audio_jitter_samples.append(
                        abs(first_arrival - previous_audio_delay)
                    )
                previous_audio_delay = first_arrival

        video_frame_success_samples.append(
            tick_video_successes / VIDEO_FRAMES_PER_SECOND * 100.0
        )
        audio_packet_success_samples.append(
            tick_audio_successes / AUDIO_PACKETS_PER_SECOND * 100.0
        )
        video_stall_samples.append(
            (VIDEO_FRAMES_PER_SECOND - tick_video_successes)
            / VIDEO_FRAMES_PER_SECOND
        )

        requested_critical += critical_demand
        delivered_critical += tick_critical_delivered
        delivered_total += tick_total_delivered
        duplicate_payload_mbps_seconds += float(duplicate_load_mbps.sum())
        meets_critical_slo = tick_critical_delivered >= 0.99 * critical_demand
        available_samples.append(meets_critical_slo)
        if meets_critical_slo:
            outage_run = 0
        else:
            outage_run += 1
            longest_outage = max(longest_outage, outage_run)
        concurrent_samples.append(
            sum(allocations[index] > 1e-9 for index in range(len(paths))) > 1
        )
        demand_samples.append(total_demand)
        critical_delivery_samples.append(
            100.0 * tick_critical_delivered / critical_demand
        )
        active_capacity_samples.append(
            sum(capacities[index] for index in service_indices)
        )
        secondary_samples.append(
            sum(allocations[index] > 1e-9 for index in range(len(paths))) > 1
        )
        degraded_samples.append(degraded)

    metrics = SafetyMetrics(
        critical_delivery_percent=100.0 * delivered_critical / requested_critical,
        critical_service_availability_percent=100.0
        * float(np.mean(available_samples)),
        longest_critical_outage_seconds=float(longest_outage),
        delivered_goodput_mbps=delivered_total / SAFETY_DURATION_SECONDS,
        secondary_activation_seconds=float(secondary_activation),
        concurrent_media_percent=100.0 * float(np.mean(concurrent_samples)),
        video_frames_on_time_percent=100.0
        * float(np.mean(video_frame_successes)),
        audio_packets_on_time_percent=100.0
        * float(np.mean(audio_packet_successes)),
        video_stall_seconds=float(
            np.sum(np.logical_not(video_frame_successes))
            / VIDEO_FRAMES_PER_SECOND
        ),
        longest_video_freeze_seconds=_longest_failed_run(
            video_frame_successes
        )
        / VIDEO_FRAMES_PER_SECOND,
        video_freeze_events=float(
            _count_freeze_events(
                video_frame_successes,
                minimum_frames=int(
                    np.ceil(0.15 * VIDEO_FRAMES_PER_SECOND)
                ),
            )
        ),
        p95_video_frame_delay_ms=_finite_percentile(video_frame_delays, 95.0),
        p95_audio_jitter_ms=_finite_percentile(audio_jitter_samples, 95.0),
        handover_interruption_seconds=handover_interruption_seconds,
        handover_missed_video_frames=float(handover_missed_video_frames),
        media_assist_overhead_percent=(
            100.0 * media_packets_duplicated / media_packets_original
            if media_packets_original
            else 0.0
        ),
        media_assist_duplicate_mbps=(
            duplicate_payload_mbps_seconds / SAFETY_DURATION_SECONDS
        ),
    )
    trace = (
        SafetyTrace(
            demand_mbps=np.asarray(demand_samples),
            critical_delivery_percent=np.asarray(critical_delivery_samples),
            active_capacity_mbps=np.asarray(active_capacity_samples),
            secondary_active=np.asarray(secondary_samples),
            primary_degraded=np.asarray(degraded_samples),
            video_frames_on_time_percent=np.asarray(
                video_frame_success_samples
            ),
            audio_packets_on_time_percent=np.asarray(
                audio_packet_success_samples
            ),
            video_stall_seconds=np.asarray(video_stall_samples),
            transport_assist_active=np.full(
                SAFETY_DURATION_SECONDS,
                policy == SAFETY_POLICIES[3],
                dtype=bool,
            ),
        )
        if retain_trace
        else None
    )
    return metrics, trace


def run_public_safety_benchmark(
    output_dir: Path,
    replicates: int = 30,
    seed: int = 2026,
) -> list[dict[str, object]]:
    if replicates < 2:
        raise ValueError("At least two independent replicates are required.")
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed + 1)
    seeds = [int(value) for value in rng.integers(0, 2**31 - 1, size=replicates)]
    metric_names = tuple(SafetyMetrics.__dataclass_fields__)
    rows: list[dict[str, object]] = []
    for policy in SAFETY_POLICIES:
        observations = {name: [] for name in metric_names}
        for replicate_seed in seeds:
            metrics, _ = simulate_public_safety(policy, replicate_seed)
            for name in metric_names:
                observations[name].append(float(getattr(metrics, name)))
        row: dict[str, object] = {
            "scenario": "public_safety_congestion_wave",
            "policy": policy,
            "replicates": replicates,
        }
        for metric_name, samples in observations.items():
            mean, ci95 = _mean_ci(samples)
            row[metric_name] = mean
            row[f"{metric_name}_ci95"] = ci95
        rows.append(row)

    summary_path = output_dir / "public_safety_benchmark_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    _plot_public_safety(rows, output_dir)
    _plot_public_safety_trace(seeds[0], output_dir)
    print(f"Public-safety replicates per policy: {replicates}")
    print(f"Public-safety random seed: {seed}")
    print(f"Public-safety summary CSV: {summary_path}")
    for row in rows:
        print(
            f"{row['policy']} | video on-time="
            f"{row['video_frames_on_time_percent']:.2f}% | "
            f"audio on-time={row['audio_packets_on_time_percent']:.2f}% | "
            f"video stall={row['video_stall_seconds']:.2f}s | "
            f"longest freeze={row['longest_video_freeze_seconds']:.2f}s | "
            f"video p95={row['p95_video_frame_delay_ms']:.1f}ms | "
            f"audio jitter p95={row['p95_audio_jitter_ms']:.1f}ms | "
            f"standby activation={row['secondary_activation_seconds']:.1f}s | "
            f"assist overhead={row['media_assist_overhead_percent']:.1f}% "
            f"({row['media_assist_duplicate_mbps']:.2f} Mbps duplicated)"
        )
    return rows


def _plot_public_safety(
    rows: list[dict[str, object]],
    output_dir: Path,
) -> None:
    colors = ("#4C78A8", "#F2A541", "#3A9D78", "#8055A5")
    metric_specs = (
        (
            "video_frames_on_time_percent",
            "Video frames on time (%)",
            "Higher is better",
        ),
        (
            "audio_packets_on_time_percent",
            "Audio packets on time (%)",
            "Higher is better",
        ),
        (
            "video_stall_seconds",
            "Cumulative video stall (s)",
            "Lower is better",
        ),
        (
            "longest_video_freeze_seconds",
            "Longest video freeze (s)",
            "Lower is better",
        ),
        (
            "p95_video_frame_delay_ms",
            "p95 received video-frame delay (ms)",
            "Lower is better",
        ),
        (
            "p95_audio_jitter_ms",
            "p95 audio delay variation (ms)",
            "Lower is better",
        ),
        (
            "handover_interruption_seconds",
            "Modeled handover interruption (s)",
            "Lower is better",
        ),
        (
            "handover_missed_video_frames",
            "Video frames lost during handover",
            "Lower is better",
        ),
        (
            "media_assist_overhead_percent",
            "Duplicated media packets (% of originals)",
            "Lower is better",
        ),
    )
    figure, axes = plt.subplots(3, 3, figsize=(18, 12), layout="constrained")
    x = np.arange(len(SAFETY_POLICIES))
    for axis, (metric, ylabel, note) in zip(axes.flat, metric_specs):
        means = [float(row[metric]) for row in rows]
        errors = [float(row[f"{metric}_ci95"]) for row in rows]
        bars = axis.bar(
            x,
            means,
            yerr=errors,
            capsize=4,
            color=colors,
            edgecolor="white",
            linewidth=0.6,
        )
        for bar, mean, error in zip(bars, means, errors):
            axis.annotate(
                f"{mean:.2f}",
                xy=(bar.get_x() + bar.get_width() / 2.0, mean + error),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
                clip_on=False,
            )
        axis.set_ylim(
            bottom=0.0,
            top=max(
                1.0,
                max(mean + error for mean, error in zip(means, errors)) * 1.18,
            ),
        )
        axis.set_ylabel(ylabel)
        axis.set_title(note)
        axis.set_xticks(
            x,
            [
                "Single-path\nhandover",
                "Reactive\nmultipath",
                "Predictive\noverflow",
                "Predictive +\nmedia assist",
            ],
        )
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle(
        f"Synthetic real-time multimedia QoS; mean and 95% normal CI (n={rows[0]['replicates']})"
    )
    figure.savefig(
        output_dir / "public_safety_multimedia_qos.png",
        dpi=180,
    )
    plt.close(figure)


def _plot_public_safety_trace(seed: int, output_dir: Path) -> None:
    colors = ("#4C78A8", "#F2A541", "#3A9D78", "#8055A5")
    figure, (capacity_axis, qos_axis) = plt.subplots(
        2,
        1,
        figsize=(11, 7),
        sharex=True,
        layout="constrained",
    )
    seconds = np.arange(SAFETY_DURATION_SECONDS)
    for policy, color in zip(SAFETY_POLICIES, colors):
        _, trace = simulate_public_safety(policy, seed, retain_trace=True)
        if trace is None:
            raise RuntimeError("Expected a trace for the public-safety plot.")
        capacity_axis.plot(
            seconds,
            trace.active_capacity_mbps,
            color=color,
            linewidth=1.6,
            label=f"{policy}: active capacity",
        )
        qos_axis.plot(
            seconds,
            trace.video_frames_on_time_percent,
            color=color,
            linewidth=1.4,
            label=f"{policy}: video on time",
        )
        qos_axis.plot(
            seconds,
            trace.audio_packets_on_time_percent,
            color=color,
            linewidth=1.0,
            linestyle=":",
            label=f"{policy}: audio on time",
        )
    _, exemplar = simulate_public_safety(
        SAFETY_POLICIES[0],
        seed,
        retain_trace=True,
    )
    if exemplar is None:
        raise RuntimeError("Expected demand data for the public-safety plot.")
    capacity_axis.plot(
        seconds,
        exemplar.demand_mbps,
        color="#444444",
        linestyle="--",
        linewidth=1.4,
        label="Offered traffic",
    )
    for axis in (capacity_axis, qos_axis):
        axis.axvspan(50, 65, color="#D9534F", alpha=0.12, label="Wi-Fi outage")
        axis.grid(alpha=0.25)
    capacity_axis.set_ylabel("Rate / capacity (Mbps)")
    capacity_axis.set_title(
        f"Congestion-wave growth and transport overflow (one run, seed={seed})"
    )
    capacity_axis.legend(frameon=False, ncol=2)
    qos_axis.set_ylabel("On-time media packets / frames (%)")
    qos_axis.set_xlabel("Synthetic scenario time (s)")
    qos_axis.set_ylim(-2, 105)
    qos_axis.legend(frameon=False, ncol=2)
    figure.savefig(
        output_dir / "public_safety_overflow_timeseries.png",
        dpi=180,
    )
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    parser.add_argument("--replicates", type=int, default=30)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    run_benchmark(args.output_dir, replicates=args.replicates, seed=args.seed)
    run_public_safety_benchmark(
        args.output_dir,
        replicates=args.replicates,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
