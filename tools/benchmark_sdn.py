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

"""Compare the SDN role-override policy with the local and separated arms.

Implements the pre-registered test in ``docs/sdn-mapping.md`` §6.  The SDN arm
uses a stipulated perfect attack alert and a southbound ``set_alpha`` policy;
everything else (topology, demand, flow allocator) is frozen.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulation.dual_role import simulate_run  # noqa: E402
from simulation.sdn_plane import simulate_sdn  # noqa: E402

TARGETS = ("E1", "E2", "E3")
REPLICATES = 12
SEED = 2026


def _mean_ci(values: Sequence[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if array.size < 2:
        return float(array.mean()), 0.0
    return float(array.mean()), float(
        1.96 * array.std(ddof=1) / math.sqrt(array.size)
    )


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _collect(seeds: Sequence[int]) -> dict[str, dict[str, list[float]]]:
    arms: dict[str, dict[str, list[float]]] = {
        "separated": {"steady": [], "e1": [], "e2": [], "e3": [], "flood_total": []},
        "local": {"steady": [], "e1": [], "e2": [], "e3": [], "flood_total": []},
        "sdn": {"steady": [], "e1": [], "e2": [], "e3": [], "flood_total": []},
    }
    for seed in seeds:
        separated_steady = simulate_run("steady", "separated", seed)
        local_steady = simulate_run("steady", "fluid", seed)
        sdn_steady = simulate_sdn("steady", seed)
        flood_separated = simulate_run("ddos", "separated", seed)
        flood_local = simulate_run("ddos", "fluid", seed)
        flood_sdn = simulate_sdn("ddos", seed)
        for arm, steady, flood in (
            ("separated", separated_steady, flood_separated),
            ("local", local_steady, flood_local),
            ("sdn", sdn_steady, flood_sdn),
        ):
            arms[arm]["steady"].append(steady.delivered_percent)
            arms[arm]["e1"].append(
                flood.target_legit_delivered_percent.get("E1", 0.0)
            )
            arms[arm]["e2"].append(
                flood.target_legit_delivered_percent.get("E2", 0.0)
            )
            arms[arm]["e3"].append(
                flood.target_legit_delivered_percent.get("E3", 0.0)
            )
            arms[arm]["flood_total"].append(flood.delivered_percent)
    return arms


def run_benchmark(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    seeds = [int(value) for value in rng.integers(0, 2**31 - 1, size=REPLICATES)]
    arms = _collect(seeds)

    summary: list[dict[str, object]] = []
    for arm, metrics in arms.items():
        for metric, values in metrics.items():
            mean, interval = _mean_ci(values)
            summary.append(
                {
                    "arm": arm,
                    "metric": metric,
                    "replicates": len(seeds),
                    "mean": mean,
                    "ci95": interval,
                }
            )
    verdict = _verdict(arms)
    _write_csv(output_dir / "sdn_summary.csv", summary)
    _write_csv(output_dir / "sdn_verdict.csv", verdict)
    _print(summary, verdict)
    return {"summary": summary, "verdict": verdict}


def _mean(arms, arm: str, metric: str) -> float:
    return float(np.mean(arms[arm][metric]))


def _verdict(arms) -> list[dict[str, object]]:
    local_steady = _mean(arms, "local", "steady")
    sdn_steady = _mean(arms, "sdn", "steady")
    steady_loss = local_steady - sdn_steady
    local_e3 = _mean(arms, "local", "e3")
    sdn_e3 = _mean(arms, "sdn", "e3")
    gain = sdn_e3 - local_e3
    return [
        {
            "test": "steady_guard",
            "value": steady_loss,
            "threshold": 0.5,
            "passed": steady_loss <= 0.5,
            "detail": (
                f"local steady {local_steady:.2f} %, "
                f"SDN steady {sdn_steady:.2f} %"
            ),
        },
        {
            "test": "flood_isolation",
            "value": gain,
            "threshold": "SDN E3 >= 95 % and >= local + 5 pp",
            "passed": sdn_e3 >= 95.0 and gain >= 5.0,
            "detail": (
                f"local E3 {local_e3:.2f} %, SDN E3 {sdn_e3:.2f} %, "
                f"gain {gain:+.2f} pp"
            ),
        },
    ]


def _print(
    summary: Sequence[dict[str, object]],
    verdict: Sequence[dict[str, object]],
) -> None:
    print("SDN control-plane comparison (12 paired seeds):")
    for row in summary:
        if row["metric"] in {"steady", "e3", "flood_total"}:
            print(
                f"  {row['arm']:10s} {row['metric']:12s} "
                f"{float(row['mean']):8.3f} +/- {float(row['ci95']):6.3f}"
            )
    print("\nPre-registered tests:")
    for row in verdict:
        print(
            f"  {row['test']:18s} value={row['value']} "
            f"{'PASS' if row['passed'] else 'FAIL'} | {row['detail']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args()
    run_benchmark(args.output_dir)
    print(f"\nCSVs: {args.output_dir}/sdn_*.csv")


if __name__ == "__main__":
    main()
