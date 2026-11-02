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

"""Run the S1 cross-validation experiment and write the comparison report.

Steps:
1. run both Python model variants for the requested seeds;
2. normalize them and the ns-3 replicate CSV produced by
   ``validation/ns3/run-s1.sh``;
3. write paired ns-3-versus-model comparisons with 95% intervals.

Example (after the ns-3 CSV exists)::

    py -3 -m validation.run_s1_experiment \
        --ns3-csv output/validation/ns3_s1.csv \
        --seeds 1 2 3 4 5 6 7 8 \
        --output-dir output/validation
"""

from __future__ import annotations

import argparse
import csv
import tempfile
from pathlib import Path
from typing import Sequence

from tools.validation_io import (
    compare_normalized_results,
    export_simulation_replicates,
    normalize_external_results,
)
from validation.scenario_s1 import (
    METRIC_COLUMNS,
    POLICIES,
    SCENARIOS,
    run_scenario,
)


def _write_comparison(
    ns3_normalized: Path,
    model_normalized: Path,
    policy: str,
    output_path: Path,
) -> list[dict[str, object]]:
    with tempfile.TemporaryDirectory() as directory:
        raw = compare_normalized_results(
            ns3_normalized,
            model_normalized,
            Path(directory) / "comparison.csv",
            left_policy="capacity_weighted_swrr",
            right_policy=policy,
        )
    rows: list[dict[str, object]] = []
    for row in raw:
        relative = (
            100.0 * float(row["left_minus_right_mean"]) / float(row["right_mean"])
            if float(row["right_mean"]) != 0.0
            else 0.0
        )
        rows.append(
            {
                "model": policy,
                "scenario": row["scenario"],
                "metric": row["metric"],
                "unit": row["unit"],
                "paired_seeds": row["paired_seeds"],
                "ns3_mean": row["left_mean"],
                "model_mean": row["right_mean"],
                "ns3_minus_model": row["left_minus_right_mean"],
                "paired_ci95": row["paired_ci95"],
                "relative_difference_percent": relative,
            }
        )
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def run_experiment(
    ns3_csv: Path,
    output_dir: Path,
    seeds: Sequence[int],
) -> list[dict[str, object]]:
    if len(set(seeds)) < 2:
        raise ValueError("At least two distinct seeds are required.")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory)
        mapping = Path(__file__).resolve().parent / "ns3" / "s1_mapping.json"
        ns3_normalized = scratch / "ns3_normalized.csv"
        normalize_external_results(ns3_csv, ns3_normalized, mapping, "ns3")
        all_rows: list[dict[str, object]] = []
        for scenario in SCENARIOS:
            for policy in POLICIES:
                csv_path = output_dir / f"python_{scenario}_{policy.replace('.', '')}.csv"
                run_scenario(csv_path, scenario, policy, seeds)
                normalized = scratch / f"{policy}.csv"
                export_simulation_replicates(
                    csv_path,
                    normalized,
                    source="python_simpy",
                    metrics=METRIC_COLUMNS,
                )
                rows = _write_comparison(
                    ns3_normalized,
                    normalized,
                    policy,
                    scratch / "pair.csv",
                )
                all_rows.extend(rows)
    report = output_dir / "s1_comparison.csv"
    with report.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)

    for row in all_rows:
        print(
            f"{row['scenario']:12s} | {row['model']:34s} | {row['metric']:24s} | "
            f"ns-3 {row['ns3_mean']:9.3f} | model {row['model_mean']:9.3f} | "
            f"delta {row['ns3_minus_model']:+8.3f} ({row['relative_difference_percent']:+6.2f}%)"
        )
    print(f"Comparison CSV: {report}")
    return all_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns3-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("output/validation"))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(1, 9)))
    args = parser.parse_args()
    run_experiment(args.ns3_csv, args.output_dir, args.seeds)


if __name__ == "__main__":
    main()
