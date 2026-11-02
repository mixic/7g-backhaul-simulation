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

"""Compare role-fluid controllers on the potential-field paradigm.

Arms (all share the same physics, topology and demand):

* ``static_design``   — fixed roles chosen at design time.
* ``centralized_greedy`` — sees the whole network and minimises the true
  one-tick objective; a myopic upper bound, not an oracle.
* ``local_fluid``     — local rule using incident utilisation and its own unmet
  demand, damped shares and role hysteresis.
* ``local_congestion`` — identical but ignores its own unmet demand: the control
  that shows what happens when roles are priced by congestion alone.
* ``local_reactive``  — same signal as ``local_fluid`` with no memory.

The benchmark also reports three sweeps that decide whether the paradigm is
viable at all: the price of the potential's cost term, the damping/stability
boundary, and the hysteresis/churn trade-off.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import asdict, replace
from pathlib import Path
from typing import Sequence

import numpy as np

from simulation.role_fluid import (
    DEFAULT_WEIGHTS,
    POLICIES,
    SCENARIOS,
    FlowWeights,
    RoleFluidSimulation,
    build_links,
    build_nodes,
    simulate_run,
)

METRIC_NAMES: tuple[str, ...] = (
    "delivered_percent",
    "p95_latency_ms",
    "total_cost_usd",
    "role_switches",
    "oscillation_index",
    "local_serve_percent",
    "cache_fill_gb",
)

#: Pairs reported as paired differences (left - right).
PAIRS: tuple[tuple[str, str, str], ...] = (
    ("fluid versus static", "local_fluid", "static_design"),
    ("fluid versus centralised", "local_fluid", "centralized_greedy"),
    ("congestion-only versus fluid", "local_congestion", "local_fluid"),
    ("reactive versus fluid", "local_reactive", "local_fluid"),
)


def _mean_ci(values: Sequence[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if array.size < 2:
        raise ValueError("At least two replicates are required for an interval.")
    return float(array.mean()), float(1.96 * array.std(ddof=1) / math.sqrt(array.size))


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_benchmark(
    output_dir: Path,
    replicates: int = 6,
    seed: int = 2026,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if replicates < 2:
        raise ValueError("At least two independent replicates are required.")
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    seeds = [int(value) for value in rng.integers(0, 2**31 - 1, size=replicates)]

    per_seed: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []
    for scenario_key in SCENARIOS:
        samples: dict[tuple[str, str], list[float]] = {}
        for policy in POLICIES:
            for replicate_seed in seeds:
                metrics = asdict(simulate_run(scenario_key, policy, replicate_seed))
                for name in METRIC_NAMES:
                    per_seed.append(
                        {
                            "scenario": scenario_key,
                            "policy": policy,
                            "seed": replicate_seed,
                            "metric": name,
                            "value": float(metrics[name]),
                        }
                    )
                    samples.setdefault((policy, name), []).append(float(metrics[name]))
        for policy in POLICIES:
            row: dict[str, object] = {
                "scenario": scenario_key,
                "scenario_title": SCENARIOS[scenario_key].title,
                "policy": policy,
                "replicates": replicates,
            }
            for name in METRIC_NAMES:
                mean, interval = _mean_ci(samples[(policy, name)])
                row[name] = mean
                row[f"{name}_ci95"] = interval
            summary.append(row)

    paired = _paired_rows(per_seed, seeds)
    _write_csv(output_dir / "role_fluid_summary.csv", summary)
    _write_csv(output_dir / "role_fluid_per_seed.csv", per_seed)
    _write_csv(output_dir / "role_fluid_paired.csv", paired)
    _print_summary(summary, paired)
    return summary, paired


def _paired_rows(
    per_seed: Sequence[dict[str, object]],
    seeds: Sequence[int],
) -> list[dict[str, object]]:
    lookup = {
        (row["scenario"], row["policy"], row["metric"], int(row["seed"])): float(row["value"])
        for row in per_seed
    }
    rows: list[dict[str, object]] = []
    for scenario_key in SCENARIOS:
        for label, left, right in PAIRS:
            for metric in METRIC_NAMES:
                differences = [
                    lookup[(scenario_key, left, metric, int(seed))]
                    - lookup[(scenario_key, right, metric, int(seed))]
                    for seed in seeds
                ]
                mean, interval = _mean_ci(differences)
                rows.append(
                    {
                        "scenario": scenario_key,
                        "comparison": label,
                        "metric": metric,
                        "left_policy": left,
                        "right_policy": right,
                        "paired_seeds": len(seeds),
                        "paired_difference": mean,
                        "paired_ci95": interval,
                    }
                )
    return rows


def _print_summary(
    summary: Sequence[dict[str, object]],
    paired: Sequence[dict[str, object]],
) -> None:
    print("Role-fluid controller comparison (mean over paired seeds):")
    for row in summary:
        print(
            f"  {row['scenario']:16s} | {row['policy']:19s} | "
            f"delivered={float(row['delivered_percent']):6.2f}% | "
            f"p95={float(row['p95_latency_ms']):7.2f} ms | "
            f"cost=${float(row['total_cost_usd']):7.3f} | "
            f"switches={float(row['role_switches']):5.1f} | "
            f"osc={float(row['oscillation_index']):.3f} | "
            f"serve={float(row['local_serve_percent']):5.1f}%"
        )
    print("\nPaired differences (left - right):")
    for row in paired:
        if row["metric"] not in {"delivered_percent", "total_cost_usd"}:
            continue
        print(
            f"  {row['scenario']:16s} | {row['comparison']:30s} | "
            f"{row['metric']:18s} {float(row['paired_difference']):+9.4f} "
            f"(+/- {float(row['paired_ci95']):.4f})"
        )


def run_cost_calibration(
    output_dir: Path,
    replicates: int = 4,
    seed: int = 2026,
) -> list[dict[str, object]]:
    """How much does the potential's cost weight matter?

    The local rule trades congestion, latency, fragmentation and money with
    fixed weights. If those weights are wrong, the rule chooses expensive paths
    and loses to the centralised controller. This sweep quantifies it.
    """
    rng = np.random.default_rng(seed)
    seeds = [int(value) for value in rng.integers(0, 2**31 - 1, size=replicates)]
    rows: list[dict[str, object]] = []
    for scenario_key in ("steady", "flash_crowd"):
        for weight in (0.3, 1.0, 3.0):
            weights = replace(DEFAULT_WEIGHTS, w_cost=weight)
            for policy in ("local_fluid", "centralized_greedy"):
                costs = []
                delivered = []
                for replicate_seed in seeds:
                    metrics = simulate_run(scenario_key, policy, replicate_seed, weights)
                    costs.append(metrics.total_cost_usd)
                    delivered.append(metrics.delivered_percent)
                rows.append(
                    {
                        "scenario": scenario_key,
                        "policy": policy,
                        "w_cost": weight,
                        "replicates": replicates,
                        "cost_mean": float(np.mean(costs)),
                        "delivered_mean": float(np.mean(delivered)),
                    }
                )
    _write_csv(output_dir / "role_fluid_cost_calibration.csv", rows)
    return rows


def run_stability_sweep(
    output_dir: Path,
    replicates: int = 4,
    seed: int = 2026,
) -> list[dict[str, object]]:
    """Damping versus path-latency spread: where does the water rule oscillate?"""
    rng = np.random.default_rng(seed)
    seeds = [int(value) for value in rng.integers(0, 2**31 - 1, size=replicates)]
    nodes = build_nodes()
    base_links = build_links()
    rows: list[dict[str, object]] = []
    for latency_scale in (1.0, 2.0, 4.0):
        links = tuple(
            replace(link, latency_ms=link.latency_ms * latency_scale) for link in base_links
        )
        for damping in (1.0, 0.6, 0.3):
            weights = replace(DEFAULT_WEIGHTS, damping=damping)
            oscillations = []
            switches = []
            delivered = []
            for replicate_seed in seeds:
                simulation = RoleFluidSimulation(
                    SCENARIOS["steady"],
                    "local_fluid",
                    replicate_seed,
                    weights,
                    nodes=nodes,
                    links=links,
                )
                metrics = simulation.run()
                oscillations.append(metrics.oscillation_index)
                switches.append(metrics.role_switches)
                delivered.append(metrics.delivered_percent)
            rows.append(
                {
                    "latency_scale": latency_scale,
                    "damping": damping,
                    "replicates": replicates,
                    "oscillation_mean": float(np.mean(oscillations)),
                    "switches_mean": float(np.mean(switches)),
                    "delivered_mean": float(np.mean(delivered)),
                }
            )
    _write_csv(output_dir / "role_fluid_stability.csv", rows)
    return rows


def run_hysteresis_sweep(
    output_dir: Path,
    replicates: int = 4,
    seed: int = 2026,
) -> list[dict[str, object]]:
    """Hysteresis is the churn control: less flapping, slower response."""
    rng = np.random.default_rng(seed)
    seeds = [int(value) for value in rng.integers(0, 2**31 - 1, size=replicates)]
    rows: list[dict[str, object]] = []
    for hysteresis in (0.0, 0.004, 0.02, 0.05):
        weights = replace(DEFAULT_WEIGHTS, hysteresis_usd=hysteresis)
        switches = []
        delivered = []
        costs = []
        for replicate_seed in seeds:
            metrics = simulate_run("flash_crowd", "local_fluid", replicate_seed, weights)
            switches.append(metrics.role_switches)
            delivered.append(metrics.delivered_percent)
            costs.append(metrics.total_cost_usd)
        rows.append(
            {
                "hysteresis_usd": hysteresis,
                "replicates": replicates,
                "switches_mean": float(np.mean(switches)),
                "delivered_mean": float(np.mean(delivered)),
                "cost_mean": float(np.mean(costs)),
            }
        )
    _write_csv(output_dir / "role_fluid_hysteresis.csv", rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    parser.add_argument("--replicates", type=int, default=6)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    summary, paired = run_benchmark(args.output_dir, args.replicates, args.seed)
    calibration = run_cost_calibration(args.output_dir)
    stability = run_stability_sweep(args.output_dir)
    hysteresis = run_hysteresis_sweep(args.output_dir)
    print("\nCost calibration (local rule vs centralised):")
    for row in calibration:
        print(
            f"  {row['scenario']:12s} | w_cost={float(row['w_cost']):4.1f} | "
            f"{row['policy']:19s} | cost=${float(row['cost_mean']):7.3f} | "
            f"delivered={float(row['delivered_mean']):6.2f}%"
        )
    print("\nStability sweep (local_fluid, steady scenario):")
    for row in stability:
        print(
            f"  latency x{float(row['latency_scale']):3.1f} | damping={float(row['damping']):3.1f} | "
            f"oscillation={float(row['oscillation_mean']):.3f} | "
            f"switches={float(row['switches_mean']):5.1f} | "
            f"delivered={float(row['delivered_mean']):6.2f}%"
        )
    print("\nHysteresis sweep (flash crowd):")
    for row in hysteresis:
        print(
            f"  hysteresis=${float(row['hysteresis_usd']):.3f} | "
            f"switches={float(row['switches_mean']):5.1f} | "
            f"delivered={float(row['delivered_mean']):6.2f}% | "
            f"cost=${float(row['cost_mean']):7.3f}"
        )
    print(f"\nCSVs: {args.output_dir}/role_fluid_*.csv")


if __name__ == "__main__":
    main()
