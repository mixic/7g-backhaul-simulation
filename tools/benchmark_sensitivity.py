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

"""Run paired one-factor-at-a-time sensitivity checks on the cooperative model."""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from pathlib import Path

import numpy as np

if __package__:
    from tools.benchmark_brain_inspired import (
        POLICIES,
        SCENARIOS,
        Metrics,
        Scenario,
        _simulate,
    )
else:
    from benchmark_brain_inspired import (
        POLICIES,
        SCENARIOS,
        Metrics,
        Scenario,
        _simulate,
    )

SENSITIVITY_LEVELS: dict[str, tuple[float | int, ...]] = {
    "demand_scale": (0.8, 1.0, 1.2),
    "path_capacity_scale": (0.8, 1.0, 1.2),
    "path_delay_scale": (0.8, 1.0, 1.2),
    "path_loss_scale": (0.5, 1.0, 2.0),
    "setup_delay_scale": (0.5, 1.0, 2.0),
    "cloud_startup_scale": (0.5, 1.0, 2.0),
    "forecast_horizon_seconds": (4, 8, 16),
}
BASELINE_VALUES: dict[str, float | int] = {
    "demand_scale": 1.0,
    "path_capacity_scale": 1.0,
    "path_delay_scale": 1.0,
    "path_loss_scale": 1.0,
    "setup_delay_scale": 1.0,
    "cloud_startup_scale": 1.0,
    "forecast_horizon_seconds": 8,
}


def _mean_ci(values: list[float]) -> tuple[float, float]:
    samples = np.asarray(values, dtype=float)
    if samples.size == 0:
        raise ValueError("Cannot summarize an empty sensitivity sample.")
    interval = (
        1.96 * float(np.std(samples, ddof=1)) / np.sqrt(samples.size)
        if samples.size > 1
        else 0.0
    )
    return float(np.mean(samples)), float(interval)


def run_sensitivity(
    output_path: Path,
    parameters: tuple[str, ...],
    scenario_names: tuple[str, ...] = ("nominal",),
    policies: tuple[str, ...] = (POLICIES[0], POLICIES[1]),
    replicates: int = 5,
    seed: int = 2026,
) -> list[dict[str, object]]:
    if replicates < 2:
        raise ValueError("At least two independent replicates are required.")
    if not parameters:
        raise ValueError("Select at least one sensitivity parameter.")
    for parameter in parameters:
        if parameter not in SENSITIVITY_LEVELS:
            raise ValueError(f"Unknown sensitivity parameter: {parameter}")
    scenario_by_name = {scenario.name: scenario for scenario in SCENARIOS}
    unknown_scenarios = set(scenario_names) - set(scenario_by_name)
    if unknown_scenarios:
        raise ValueError(
            "Unknown scenarios: " + ", ".join(sorted(unknown_scenarios))
        )
    unknown_policies = set(policies) - set(POLICIES)
    if unknown_policies:
        raise ValueError("Unknown policies: " + ", ".join(sorted(unknown_policies)))

    seed_rng = np.random.default_rng(seed)
    seeds = [
        int(value)
        for value in seed_rng.integers(0, 2**31 - 1, replicates)
    ]
    metric_names = tuple(Metrics.__dataclass_fields__)
    cache: dict[
        tuple[str, str, str, float | int, int],
        Metrics,
    ] = {}

    def run_case(
        scenario: Scenario,
        policy: str,
        parameter: str,
        value: float | int,
    ) -> list[Metrics]:
        varied_value = (
            value
            if parameter == "forecast_horizon_seconds"
            else getattr(scenario, parameter) * value
        )
        varied_scenario = replace(scenario, **{parameter: varied_value})
        case_results: list[Metrics] = []
        for replicate_seed in seeds:
            key = (
                scenario.name,
                policy,
                parameter,
                value,
                replicate_seed,
            )
            metrics = cache.get(key)
            if metrics is None:
                metrics, _ = _simulate(policy, replicate_seed, varied_scenario)
                cache[key] = metrics
            case_results.append(metrics)
        return case_results

    rows: list[dict[str, object]] = []
    for scenario_name in scenario_names:
        scenario = scenario_by_name[scenario_name]
        for parameter in parameters:
            baseline_value = BASELINE_VALUES[parameter]
            baseline_by_policy = {
                policy: run_case(
                    scenario,
                    policy,
                    parameter,
                    baseline_value,
                )
                for policy in policies
            }
            for value in SENSITIVITY_LEVELS[parameter]:
                for policy in policies:
                    case = run_case(scenario, policy, parameter, value)
                    baseline = baseline_by_policy[policy]
                    paired_by_metric = {
                        metric: [
                            float(getattr(case_item, metric))
                            - float(getattr(base_item, metric))
                            for case_item, base_item in zip(case, baseline)
                        ]
                        for metric in metric_names
                    }
                    for metric in metric_names:
                        samples = [
                            float(getattr(item, metric))
                            for item in case
                        ]
                        mean, ci95 = _mean_ci(samples)
                        paired_delta, paired_ci95 = _mean_ci(
                            paired_by_metric[metric]
                        )
                        rows.append(
                            {
                                "scenario": scenario_name,
                                "parameter": parameter,
                                "value": value,
                                "policy": policy,
                                "metric": metric,
                                "replicates": replicates,
                                "mean": mean,
                                "ci95": ci95,
                                "paired_delta_vs_default": paired_delta,
                                "paired_ci95_vs_default": paired_ci95,
                            }
                        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("figures/sensitivity.csv"))
    parser.add_argument("--replicates", type=int, default=5)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument(
        "--scenario",
        nargs="+",
        choices=[scenario.name for scenario in SCENARIOS],
        default=["nominal"],
    )
    parser.add_argument(
        "--policy",
        nargs="+",
        choices=POLICIES,
        default=[POLICIES[0], POLICIES[1]],
    )
    parser.add_argument(
        "--parameter",
        nargs="+",
        choices=tuple(SENSITIVITY_LEVELS),
        default=[
            "demand_scale",
            "path_capacity_scale",
            "path_delay_scale",
            "path_loss_scale",
            "forecast_horizon_seconds",
        ],
    )
    args = parser.parse_args()
    rows = run_sensitivity(
        args.output,
        tuple(args.parameter),
        tuple(args.scenario),
        tuple(args.policy),
        args.replicates,
        args.seed,
    )
    print(f"Sensitivity records: {len(rows)}")
    print(f"CSV: {args.output}")


if __name__ == "__main__":
    main()
