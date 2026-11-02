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

"""Independent-policy benchmark for the predictive-versus-reactive question.

The earlier vision benchmark (``tools/benchmark_vision.py``) has a comparison
design flaw that is acknowledged in the README: every policy is evaluated with
the same allocation function, and the "proposed" arm additionally uses
different cache-controller gains than the reactive arm. A goodput difference
between the arms therefore cannot be attributed to the predictor, because the
allocator is common to both and the cache controller is not held constant.

This module replaces that comparison with a design in which:

* every arm owns an **allocator instance with its own state**; two arms never
  mutate the same allocation object, so an arm's result cannot depend on the
  other arm's predictor;
* the per-tick link and cache physics is identical across arms and identical to
  ``tools/benchmark_vision.py`` (same loss, queue-delay and pressure formulas),
  so the only differences between arms are the predictors and the cache gains;
* the treatment is isolated by a 2x2 ablation over
  {pressure: reactive, predictive} x {cache: reactive, predictive} with the
  cache gains held equal inside each comparison;
* the legacy shared-allocator artifact is retained as its own pair of arms so
  that its effect can be quantified instead of assumed.

Statistical claims are limited to what the design supports: paired differences
over common seeds with 95 % normal-approximation intervals and an exact paired
sign test. A difference is only called an advantage when the interval excludes
zero and the sign test agrees.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from tools.benchmark_vision import (
    PREDICTION_HORIZON_TICKS,
    SIMULATION_TICKS,
    TICK_SECONDS,
    Link,
    Scenario,
    _forecast,
    _forecast_demand,
    _weighted_percentile,
    build_scenarios,
)

#: Cache-controller gains per cache policy. Held equal across arms that share a
#: cache policy, so that only the pressure predictor changes in ablation A->B.
CACHE_GAINS = {
    "reactive": {"slope": 0.13, "step_down": 0.035, "step_up": 0.065, "cap": 0.34},
    "predictive": {"slope": 0.19, "step_down": 0.035, "step_up": 0.11, "cap": 0.48},
}


@dataclass(frozen=True)
class Arm:
    """One fully specified controller: its predictors, gains and allocator."""

    name: str
    predict_pressure: bool
    cache_policy: str
    shared_allocator: str | None = None


ARMS: tuple[Arm, ...] = (
    Arm("A reactive pressure + reactive cache", False, "reactive"),
    Arm("B predictive pressure + reactive cache", True, "reactive"),
    Arm("C reactive pressure + predictive cache", False, "predictive"),
    Arm("D predictive pressure + predictive cache", True, "predictive"),
    Arm(
        "E legacy shared allocator: reactive",
        False,
        "reactive",
        shared_allocator="legacy",
    ),
    Arm(
        "F legacy shared allocator: predictive",
        True,
        "predictive",
        shared_allocator="legacy",
    ),
)

#: Paired comparisons reported by the benchmark: (name, left arm, right arm).
COMPARISONS: tuple[tuple[str, int, int], ...] = (
    ("ablation: prediction only (B - A)", 1, 0),
    ("ablation: cache only (C - A)", 2, 0),
    ("ablation: both (D - A)", 3, 0),
    ("cache effect under prediction (D - B)", 3, 1),
    ("legacy shared-allocator pair (F - E)", 5, 4),
)


class ProportionalAllocator:
    """Capacity-aware proportional allocator with per-instance smoothing state.

    The smoothing cache is what makes allocator *sharing* observable: an
    allocator instance remembers the weights it used on the previous tick, so
    two arms that share an instance influence each other. Independent instances
    cannot.
    """

    def __init__(self, smoothing: float = 0.35) -> None:
        if not 0.0 <= smoothing < 1.0:
            raise ValueError("Smoothing must be in [0, 1).")
        self.smoothing = smoothing
        self._previous: dict[str, float] | None = None

    def allocate(
        self,
        demand_mbps: float,
        links: Sequence[Link],
        scores: np.ndarray,
    ) -> np.ndarray:
        if len(links) != len(scores):
            raise ValueError("One score per link is required.")
        weights = {}
        for link, score in zip(links, scores):
            weights[link.name] = max(0.0, float(score))
        if self._previous is not None:
            blended = {}
            for name in weights:
                previous = self._previous.get(name, weights[name])
                blended[name] = (
                    self.smoothing * previous + (1.0 - self.smoothing) * weights[name]
                )
            weights = blended
        total = sum(weights.values())
        if total <= 0.0:
            self._previous = weights
            return np.zeros(len(links), dtype=float)
        weights = {name: value / total for name, value in weights.items()}
        self._previous = weights

        allocation = np.zeros(len(links), dtype=float)
        remaining = max(0.0, demand_mbps)
        eligible = set(range(len(links)))
        while eligible and remaining > 1e-9:
            indices = sorted(eligible)
            share = sum(weights[links[index].name] for index in indices)
            if share <= 0.0:
                break
            saturated: list[int] = []
            delivered = 0.0
            for index in indices:
                proposed = remaining * weights[links[index].name] / share
                room = links[index].capacity_mbps - allocation[index]
                accepted = min(max(0.0, room), proposed)
                allocation[index] += accepted
                delivered += accepted
                if room <= proposed + 1e-9:
                    saturated.append(index)
            remaining -= delivered
            eligible.difference_update(saturated)
            if not saturated or delivered <= 1e-12:
                break
        return allocation


@dataclass(frozen=True)
class ArmMetrics:
    delivered_goodput_mbps: float
    p95_latency_ms: float
    continuity_percent: float
    cache_hit_percent: float
    cost_usd_per_delivered_gb: float


def build_allocators(arms: Sequence[Arm]) -> dict[str, object]:
    """Give each arm its own allocator instance, except explicitly shared ones."""
    shared: dict[str, object] = {}
    allocators: dict[str, object] = {}
    for arm in arms:
        if arm.shared_allocator is None:
            allocators[arm.name] = ProportionalAllocator()
        else:
            allocators[arm.name] = shared.setdefault(
                arm.shared_allocator,
                ProportionalAllocator(),
            )
    return allocators


def simulate_arm(
    scenario: Scenario,
    arm: Arm,
    seed: int,
    allocator: object,
) -> ArmMetrics:
    """Run one replicate with the arm's predictor, cache gains and allocator."""
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
    gains = CACHE_GAINS[arm.cache_policy]

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

        if arm.predict_pressure:
            scores = np.asarray(
                [
                    link.capacity_mbps
                    / (
                        link.latency_ms
                        + 12.0
                        + 55.0
                        * _forecast(
                            pressure_histories[index],
                            PREDICTION_HORIZON_TICKS,
                        )
                    )
                    / (1.0 + 0.5 * link.cost_per_gb / 0.16)
                    for link, index in zip(available_links, available_indices)
                ],
                dtype=float,
            )
        else:
            scores = np.asarray(
                [
                    link.capacity_mbps
                    / (link.latency_ms + 12.0 + 55.0 * pressure)
                    / (1.0 + 0.5 * link.cost_per_gb / 0.16)
                    for link, pressure in zip(available_links, current_pressures)
                ],
                dtype=float,
            )

        demand_history.append(demand / max(scenario.base_demand_mbps, 1.0))
        demand_history = demand_history[-5:]
        if arm.cache_policy == "predictive":
            predicted_demand = _forecast_demand(
                demand_history,
                PREDICTION_HORIZON_TICKS,
            )
        else:
            predicted_demand = float(np.mean(demand_history))
        target_cache_hit = float(
            np.clip(
                scenario.initial_cache_hit
                + gains["slope"] * max(0.0, predicted_demand - 1.0),
                scenario.initial_cache_hit,
                gains["cap"],
            )
        )
        cache_delta = target_cache_hit - current_cache_hit
        cache_step = float(
            np.clip(cache_delta, -gains["step_down"], gains["step_up"])
        )
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
        allocations = allocator.allocate(backhaul_demand, available_links, scores)
        successful_remote = 0.0
        remote_latency_values: list[float] = []
        remote_latency_weights: list[float] = []
        allocated_by_link = np.zeros(len(scenario.links), dtype=float)

        for global_index, link, amount in zip(
            available_indices,
            available_links,
            allocations,
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
            utilization = min(
                1.0,
                allocated_by_link[global_index] / link.capacity_mbps,
            )
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
        total_delivered_gb += total_delivered * TICK_SECONDS / 8000.0
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
    return ArmMetrics(
        delivered_goodput_mbps=mean_goodput,
        p95_latency_ms=_weighted_percentile(latency_samples, latency_weights, 95.0),
        continuity_percent=float(np.mean(continuity_samples) * 100.0),
        cache_hit_percent=float(np.mean(cache_samples) * 100.0),
        cost_usd_per_delivered_gb=float(cost_per_gb),
    )


METRIC_NAMES: tuple[str, ...] = tuple(ArmMetrics.__dataclass_fields__)


def _mean_ci(values: Sequence[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if array.size < 2:
        raise ValueError("At least two replicates are required for an interval.")
    return (
        float(np.mean(array)),
        1.96 * float(np.std(array, ddof=1)) / math.sqrt(array.size),
    )


def sign_test_p_value(differences: Sequence[float]) -> float:
    """Two-sided exact sign test for a zero median difference."""
    non_zero = [value for value in differences if value != 0.0]
    if not non_zero:
        return 1.0
    positives = sum(1 for value in non_zero if value > 0)
    total = len(non_zero)
    tail = sum(math.comb(total, k) for k in range(min(positives, total - positives) + 1))
    return min(1.0, 2.0 * tail / (2**total))


def run_benchmark(
    output_dir: Path,
    replicates: int = 30,
    seed: int = 2026,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if replicates < 2:
        raise ValueError("At least two independent replicates are required.")
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = build_scenarios()
    rng = np.random.default_rng(seed)
    seeds = [int(value) for value in rng.integers(0, 2**31 - 1, size=replicates)]
    allocators = build_allocators(ARMS)

    per_seed: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []
    for scenario in scenarios:
        observations: dict[str, dict[str, list[float]]] = {
            arm.name: {metric: [] for metric in METRIC_NAMES} for arm in ARMS
        }
        for arm in ARMS:
            for replicate_seed in seeds:
                metrics = simulate_arm(
                    scenario,
                    arm,
                    replicate_seed,
                    allocators[arm.name],
                )
                for metric in METRIC_NAMES:
                    value = float(getattr(metrics, metric))
                    observations[arm.name][metric].append(value)
                    per_seed.append(
                        {
                            "scenario": scenario.key,
                            "arm": arm.name,
                            "seed": replicate_seed,
                            "metric": metric,
                            "value": value,
                        }
                    )
        for arm in ARMS:
            row: dict[str, object] = {
                "scenario": scenario.key,
                "scenario_title": scenario.title,
                "arm": arm.name,
                "predict_pressure": arm.predict_pressure,
                "cache_policy": arm.cache_policy,
                "shared_allocator": arm.shared_allocator or "independent",
                "replicates": replicates,
            }
            for metric in METRIC_NAMES:
                mean, ci95 = _mean_ci(observations[arm.name][metric])
                row[metric] = mean
                row[f"{metric}_ci95"] = ci95
            summary.append(row)

    paired = _paired_differences(summary, seeds, scenarios, per_seed)
    _write_csv(output_dir / "vision_fair_summary.csv", summary)
    _write_csv(output_dir / "vision_fair_paired.csv", paired)
    _write_csv(output_dir / "vision_fair_per_seed.csv", per_seed)
    _print_summary(summary, paired)
    return summary, paired


def _paired_differences(
    summary: list[dict[str, object]],
    seeds: Sequence[int],
    scenarios: tuple[Scenario, ...],
    per_seed: list[dict[str, object]],
) -> list[dict[str, object]]:
    lookup = {
        (str(row["scenario"]), str(row["arm"])): row for row in summary
    }
    samples = {
        (str(row["scenario"]), str(row["arm"]), str(row["metric"]), int(row["seed"])):
        float(row["value"])
        for row in per_seed
    }
    rows: list[dict[str, object]] = []
    for label, left_index, right_index in COMPARISONS:
        left_arm = ARMS[left_index].name
        right_arm = ARMS[right_index].name
        for scenario in scenarios:
            for metric in METRIC_NAMES:
                differences = [
                    samples[(scenario.key, left_arm, metric, int(seed))]
                    - samples[(scenario.key, right_arm, metric, int(seed))]
                    for seed in seeds
                ]
                mean, ci95 = _mean_ci(differences)
                rows.append(
                    {
                        "comparison": label,
                        "scenario": scenario.key,
                        "metric": metric,
                        "left_arm": left_arm,
                        "right_arm": right_arm,
                        "paired_seeds": len(differences),
                        "left_mean": float(lookup[(scenario.key, left_arm)][metric]),
                        "right_mean": float(lookup[(scenario.key, right_arm)][metric]),
                        "paired_difference": mean,
                        "paired_ci95": ci95,
                        "ci_excludes_zero": bool(abs(mean) > ci95),
                        "sign_test_p": sign_test_p_value(differences),
                    }
                )
    return rows


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _print_summary(
    summary: Sequence[dict[str, object]],
    paired: Sequence[dict[str, object]],
) -> None:
    print("Per-arm means (independent allocators unless noted):")
    for row in summary:
        print(
            f"  {row['scenario']:16s} | {row['arm']:46s} | "
            f"goodput={float(row['delivered_goodput_mbps']):7.2f} | "
            f"p95={float(row['p95_latency_ms']):7.2f} | "
            f"continuity={float(row['continuity_percent']):5.2f}% | "
            f"cache={float(row['cache_hit_percent']):5.2f}% | "
            f"cost=${float(row['cost_usd_per_delivered_gb']):.4f}"
        )
    print("\nPaired differences (left - right), 95% CI, exact sign test:")
    for row in paired:
        if row["metric"] != "delivered_goodput_mbps":
            continue
        verdict = (
            "distinguishable"
            if row["ci_excludes_zero"] and float(row["sign_test_p"]) < 0.05
            else "not distinguishable"
        )
        print(
            f"  {row['scenario']:16s} | {row['comparison']:38s} | "
            f"delta={float(row['paired_difference']):+7.3f} Mbps "
            f"± {float(row['paired_ci95']):5.3f} | p={float(row['sign_test_p']):.4f} | {verdict}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--replicates", type=int, default=30)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    run_benchmark(args.output_dir, args.replicates, args.seed)


if __name__ == "__main__":
    main()
