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

"""Test the pre-registered signed-trend claim from ``docs/signed-trends.md``.

The arms differ only in whether negative velocity/acceleration contribute to
the serve signal and how strongly.  The shaped ``flood_wave`` scenario gives
the trend estimator a real ramp-down to observe.  Outputs:

* ``signed_trends_summary.csv`` -- per-arm means and intervals;
* ``signed_trends_verdict.csv`` -- the pre-registered tests;
* ``signed_trends_alpha.csv``   -- mean E2 alpha trace for plotting.

All parameters except the trend treatment are frozen.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulation.dual_role import (  # noqa: E402
    DEFAULT_CONTROLLER,
    simulate_run,
)

DECAY = (85, 105)
PRE_FLOOD = (30, 40)
FLOOD_END = 100
RECOVERY_TOLERANCE = 0.05
ARMS = {
    "positive": DEFAULT_CONTROLLER,
    "signed": replace(DEFAULT_CONTROLLER, signed_trends=True),
    "signed_release": replace(
        DEFAULT_CONTROLLER, signed_trends=True, release_gain=2.0
    ),
}
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


def _window_delivery(metrics, target: str, window: tuple[int, int]) -> float:
    low, high = window
    delivered = sum(metrics.legit_delivered_trace[target][low:high])
    offered = sum(metrics.legit_offered_trace[target][low:high])
    return 100.0 * delivered / max(1e-9, offered)


def _recovery_ticks(metrics) -> float:
    pre = float(np.mean(metrics.alpha_trace["E2"][PRE_FLOOD[0] : PRE_FLOOD[1]]))
    for tick in range(FLOOD_END, len(metrics.alpha_trace["E2"])):
        if metrics.alpha_trace["E2"][tick] <= pre + RECOVERY_TOLERANCE:
            return float(tick - FLOOD_END)
    return float(len(metrics.alpha_trace["E2"]) - FLOOD_END)


def run_benchmark(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    seeds = [int(value) for value in rng.integers(0, 2**31 - 1, size=REPLICATES)]

    summary: list[dict[str, object]] = []
    alpha_trace: list[dict[str, object]] = []
    per_arm: dict[str, dict[str, list[float]]] = {}
    for arm, controller in ARMS.items():
        values = {
            "e3_decay": [],
            "e2_recovery": [],
            "e3_overall": [],
            "steady_delivered": [],
        }
        alpha_sum = np.zeros(120)
        for seed in seeds:
            flood = simulate_run(
                "flood_wave", "fluid", seed, controller=controller
            )
            steady = simulate_run("steady", "fluid", seed, controller=controller)
            values["e3_decay"].append(_window_delivery(flood, "E3", DECAY))
            values["e2_recovery"].append(_recovery_ticks(flood))
            values["e3_overall"].append(
                flood.target_legit_delivered_percent["E3"]
            )
            values["steady_delivered"].append(steady.delivered_percent)
            alpha_sum += np.asarray(flood.alpha_trace["E2"], dtype=float)
        alpha_mean = alpha_sum / len(seeds)
        for tick in range(0, 120):
            alpha_trace.append(
                {
                    "arm": arm,
                    "tick": tick,
                    "alpha_E2_mean": float(alpha_mean[tick]),
                }
            )
        for metric, samples in values.items():
            mean, interval = _mean_ci(samples)
            summary.append(
                {
                    "arm": arm,
                    "metric": metric,
                    "replicates": len(seeds),
                    "mean": mean,
                    "ci95": interval,
                }
            )
        per_arm[arm] = values

    separated = {
        "e3_decay": [],
        "steady_delivered": [],
        "e3_overall": [],
    }
    for seed in seeds:
        flood = simulate_run("flood_wave", "separated", seed)
        steady = simulate_run("steady", "separated", seed)
        separated["e3_decay"].append(_window_delivery(flood, "E3", DECAY))
        separated["e3_overall"].append(flood.target_legit_delivered_percent["E3"])
        separated["steady_delivered"].append(steady.delivered_percent)
    for metric, samples in separated.items():
        mean, interval = _mean_ci(samples)
        summary.append(
            {
                "arm": "separated",
                "metric": metric,
                "replicates": len(seeds),
                "mean": mean,
                "ci95": interval,
            }
        )

    verdict = _verdict(per_arm)
    _write_csv(output_dir / "signed_trends_summary.csv", summary)
    _write_csv(output_dir / "signed_trends_verdict.csv", verdict)
    _write_csv(output_dir / "signed_trends_alpha.csv", alpha_trace)
    _print(summary, verdict)
    return {"summary": summary, "verdict": verdict}


def _verdict(
    per_arm: dict[str, dict[str, list[float]]]
) -> list[dict[str, object]]:
    positive = per_arm["positive"]
    release = per_arm["signed_release"]
    decay_gain = float(
        np.mean(release["e3_decay"]) - np.mean(positive["e3_decay"])
    )
    positive_recovery = max(1e-9, float(np.mean(positive["e2_recovery"])))
    release_recovery = float(np.mean(release["e2_recovery"]))
    recovery_reduction = 1.0 - release_recovery / positive_recovery
    steady_loss = float(
        np.mean(positive["steady_delivered"])
        - np.mean(release["steady_delivered"])
    )
    return [
        {
            "test": "e3_decay_gain",
            "value": decay_gain,
            "threshold": 2.0,
            "passed": decay_gain >= 2.0,
            "detail": "E3 legit delivery in [85,105): signed_release - positive",
        },
        {
            "test": "recovery_time_reduction",
            "value": recovery_reduction,
            "threshold": 0.15,
            "passed": recovery_reduction >= 0.15,
            "detail": (
                f"positive {positive_recovery:.2f} ticks, "
                f"signed_release {release_recovery:.2f} ticks"
            ),
        },
        {
            "test": "steady_guard",
            "value": steady_loss,
            "threshold": 1.0,
            "passed": steady_loss <= 1.0,
            "detail": "positive steady delivery - signed_release steady delivery",
        },
    ]


def _print(
    summary: Sequence[dict[str, object]],
    verdict: Sequence[dict[str, object]],
) -> None:
    print("Signed-trend comparison (flood_wave, 12 paired seeds):")
    for row in summary:
        if row["metric"] in {"e3_decay", "e2_recovery", "steady_delivered"}:
            print(
                f"  {row['arm']:15s} {row['metric']:18s} "
                f"{float(row['mean']):8.3f} +/- {float(row['ci95']):6.3f}"
            )
    print("\nPre-registered tests:")
    for row in verdict:
        print(
            f"  {row['test']:26s} value={row['value']} "
            f"threshold={row['threshold']} "
            f"{'PASS' if row['passed'] else 'FAIL'}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args()
    run_benchmark(args.output_dir)
    print(f"\nCSVs: {args.output_dir}/signed_trends_*.csv")


if __name__ == "__main__":
    main()
