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

"""Compare the Python and ns-3 implementations of RFMP v0.1 (scenario RT1).

The two implementations are independent: ``simulation/rfmp.py`` is a discrete
event loop and ``validation/ns3/rfmp-role-transition.cc`` is a packet-level
ns-3.49 model. Both use the same specification (``docs/rfmp-protocol.md``), the
same constants and a deterministic seed-keyed jitter, so seeds are paired.

Usage::

    # 1. build and run the ns-3 half (Linux/WSL)
    NS3_DIR=~/ns-3-dev SEEDS=5 ./validation/ns3/run-rfmp.sh

    # 2. run the Python half and the comparison
    py -3 -m validation.run_rfmp_experiment \
        --ns3-csv output/validation/rfmp_ns3.csv \
        --seeds 1 2 3 4 5 --output-dir output/validation
"""

from __future__ import annotations

import argparse
import csv
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from simulation.rfmp import simulate
from tools.validation_io import (
    compare_normalized_results,
    export_simulation_replicates,
    normalize_external_results,
)

METRICS: tuple[str, ...] = (
    "in_order_delivery_percent",
    "duplicate_percent",
    "handoff_duplicate_percent",
    "transition_gap_6s_ms",
    "transition_gap_12s_ms",
    "reorder_stall_p95_ms",
    "reorder_stall_max_ms",
    "mean_delivery_delay_ms",
    "late_drop_percent",
)

#: The acceptance criteria fixed in docs/rfmp-protocol.md §12.
ACCEPTANCE = {
    "in_order_delivery_percent": 0.5,  # absolute percentage points
    "duplicate_percent": 0.1,  # absolute percentage points
    "reorder_stall_p95_ms": 15.0,  # relative percent
    "transition_gap_6s_ms": 5.0,  # absolute milliseconds
    "transition_gap_12s_ms": 5.0,  # absolute milliseconds
}


def _python_replicates(path: Path, seeds: Sequence[int]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for seed in seeds:
        metrics = asdict(simulate(seed))
        row: dict[str, object] = {
            "scenario": "rt1_role_transition",
            "policy": "rfmp_python",
            "seed": seed,
        }
        for name in METRICS:
            row[name] = float(metrics[name])
        rows.append(row)
    with path.open("w", newline="", encoding="utf-8") as file:
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
    python_csv = output_dir / "rfmp_python.csv"
    _python_replicates(python_csv, seeds)

    mapping = Path(__file__).resolve().parent / "rfmp" / "rt1_mapping.json"
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory)
        ns3_normalized = scratch / "ns3.csv"
        python_normalized = scratch / "python.csv"
        normalize_external_results(ns3_csv, ns3_normalized, mapping, "ns3")
        export_simulation_replicates(
            python_csv, python_normalized, source="python_simpy", metrics=METRICS
        )
        raw = compare_normalized_results(
            ns3_normalized,
            python_normalized,
            scratch / "comparison.csv",
            left_policy="rfmp_ns3",
            right_policy="rfmp_python",
        )

    rows: list[dict[str, object]] = []
    for row in raw:
        expected = float(row["right_mean"])
        delta = float(row["left_minus_right_mean"])
        relative = 100.0 * delta / expected if expected != 0.0 else 0.0
        rows.append(
            {
                "metric": row["metric"],
                "unit": row["unit"],
                "paired_seeds": row["paired_seeds"],
                "ns3_mean": row["left_mean"],
                "python_mean": row["right_mean"],
                "ns3_minus_python": delta,
                "paired_ci95": row["paired_ci95"],
                "relative_difference_percent": relative,
            }
        )
    report = output_dir / "rfmp_comparison.csv"
    with report.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    verdicts = _verdicts(rows)
    for row in rows:
        print(
            f"{row['metric']:28s} | ns-3 {float(row['ns3_mean']):10.4f} | "
            f"python {float(row['python_mean']):10.4f} | "
            f"delta {float(row['ns3_minus_python']):+9.4f} "
            f"({float(row['relative_difference_percent']):+6.2f}%) | "
            f"{verdicts.get(str(row['metric']), '')}"
        )
    print(f"Comparison CSV: {report}")
    print(f"Python replicates: {python_csv}")
    return rows


def _verdicts(rows: Sequence[dict[str, object]]) -> dict[str, str]:
    verdicts: dict[str, str] = {}
    for row in rows:
        metric = str(row["metric"])
        if metric not in ACCEPTANCE:
            continue
        tolerance = ACCEPTANCE[metric]
        if metric.endswith("_ms") and metric.startswith("transition_gap"):
            measured = abs(float(row["ns3_minus_python"]))
            passed = measured <= tolerance
            verdicts[metric] = (
                f"{'PASS' if passed else 'FAIL'} (gap <= {tolerance:g} ms)"
            )
        elif metric == "reorder_stall_p95_ms":
            measured = abs(float(row["relative_difference_percent"]))
            passed = measured <= tolerance
            verdicts[metric] = (
                f"{'PASS' if passed else 'FAIL'} (<= {tolerance:g} % relative)"
            )
        else:
            measured = abs(float(row["ns3_minus_python"]))
            passed = measured <= tolerance
            verdicts[metric] = (
                f"{'PASS' if passed else 'FAIL'} (<= {tolerance:g} pp)"
            )
    return verdicts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns3-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("output/validation"))
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    args = parser.parse_args()
    run_experiment(args.ns3_csv, args.output_dir, args.seeds)


if __name__ == "__main__":
    main()
