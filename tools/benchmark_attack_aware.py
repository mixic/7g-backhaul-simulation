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

"""Test attack-aware name-class admission against the pre-registered claim.

The claim is in ``docs/attack-aware.md``.  The experiment compares the
unclassified fluid controller with an authenticated-admission variant over a
grid of stipulated classifier false-negative rates, holding the false-positive
rate at 2 %.  It writes:

* ``attack_aware_summary.csv`` -- per arm and target, mean and 95 % interval;
* ``attack_aware_sweep.csv``   -- legitimate delivery versus false-negative rate;
* ``attack_aware_verdict.csv`` -- the pre-registered acceptance tests.

Everything is conditional on the stipulated topology, demand, controller and
classifier; none of the parameters are fitted to the result.
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

from simulation.dual_role import Classifier, simulate_run  # noqa: E402

TARGETS = ("E1", "E2", "E3")
ATTACKED = "E2"
UNATTACKED = ("E1", "E3")
FALSE_POSITIVE = 0.02
FALSE_NEGATIVES = tuple(round(0.1 * index, 1) for index in range(10))
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


def _run_arm(
    mode: str,
    admission: str,
    false_negative: float | None,
    seeds: Sequence[int],
) -> tuple[dict[str, object], dict[str, list[float]]]:
    classifier = (
        Classifier(FALSE_POSITIVE, float(false_negative))
        if false_negative is not None
        else Classifier()
    )
    runs = [
        simulate_run(
            "ddos",
            mode,
            seed,
            admission=admission,
            classifier=classifier,
        )
        for seed in seeds
    ]
    row: dict[str, object] = {
        "mode": mode,
        "admission": admission,
        "false_negative": "" if false_negative is None else float(false_negative),
        "false_positive": FALSE_POSITIVE if admission == "authenticated" else 0.0,
        "replicates": len(seeds),
    }
    per_seed: dict[str, list[float]] = {}
    for target in TARGETS:
        values = [
            run.target_legit_delivered_percent.get(target, 0.0) for run in runs
        ]
        per_seed[target] = values
        mean, interval = _mean_ci(values)
        row[f"{target}_legit_mean"] = mean
        row[f"{target}_legit_ci95"] = interval
    row["total_delivered_percent_mean"] = float(
        np.mean([run.delivered_percent for run in runs])
    )
    return row, per_seed


def run_benchmark(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    seeds = [int(value) for value in rng.integers(0, 2**31 - 1, size=REPLICATES)]

    separated, _ = _run_arm("separated", "open", None, seeds)
    unclassified, unclassified_seed = _run_arm("fluid", "open", None, seeds)
    arms: list[dict[str, object]] = [separated, unclassified]
    sweep: list[dict[str, object]] = []
    for false_negative in FALSE_NEGATIVES:
        row, seed_values = _run_arm(
            "fluid", "authenticated", false_negative, seeds
        )
        gains = [
            seed_values["E3"][index] - unclassified_seed["E3"][index]
            for index in range(len(seeds))
        ]
        gain_mean, gain_interval = _mean_ci(gains)
        row["E3_gain_mean"] = gain_mean
        row["E3_gain_ci95"] = gain_interval
        row["all_targets_over_95"] = all(
            float(row[f"{target}_legit_mean"]) >= 95.0 for target in TARGETS
        )
        arms.append(row)
        sweep.append(row)

    verdict = _verdict(sweep, unclassified, separated)
    _write_csv(output_dir / "attack_aware_summary.csv", arms)
    _write_csv(output_dir / "attack_aware_sweep.csv", sweep)
    _write_csv(output_dir / "attack_aware_verdict.csv", verdict)
    _print(arms, verdict)
    return {"arms": arms, "verdict": verdict}


def _verdict(
    sweep: Sequence[dict[str, object]],
    unclassified: dict[str, object],
    separated: dict[str, object],
) -> list[dict[str, object]]:
    base_e3 = float(unclassified["E3_legit_mean"])
    base_e1 = float(unclassified["E1_legit_mean"])
    rows: list[dict[str, object]] = []
    qualifying = [
        row
        for row in sweep
        if bool(row["all_targets_over_95"])
        and float(row["E3_gain_mean"]) >= 5.0
    ]
    threshold = max((float(row["false_negative"]) for row in qualifying), default=None)
    rows.append(
        {
            "test": "classifier_leakage_threshold",
            "value": "" if threshold is None else threshold,
            "threshold": ">= 50 % retention of the 95 % bar and 5 pp gain",
            "passed": threshold is not None and threshold >= 0.5,
            "detail": (
                "largest false-negative rate on the grid that keeps every target "
                ">= 95 % legit delivery and E3 >= unclassified + 5 pp"
            ),
        }
    )
    half = next(
        (row for row in sweep if abs(float(row["false_negative"]) - 0.5) < 1e-9),
        None,
    )
    if half is None:
        rows.append(
            {
                "test": "claim_at_fn_0.5",
                "value": "",
                "threshold": "all targets >= 95 % and E3 gain >= 5 pp",
                "passed": False,
                "detail": "fn = 0.5 was not run",
            }
        )
        return rows
    e3_gain = float(half["E3_gain_mean"])
    per_target_ok = all(
        float(half[f"{target}_legit_mean"]) >= 95.0 for target in TARGETS
    )
    rows.append(
        {
            "test": "claim_at_fn_0.5",
            "value": e3_gain,
            "threshold": "all targets >= 95 % and E3 gain >= 5 pp",
            "passed": per_target_ok and e3_gain >= 5.0,
            "detail": (
                f"E1={float(half['E1_legit_mean']):.2f}, "
                f"E2={float(half['E2_legit_mean']):.2f}, "
                f"E3={float(half['E3_legit_mean']):.2f}; "
                f"E3 gain over unclassified = {e3_gain:+.2f} pp "
                f"+/- {float(half['E3_gain_ci95']):.2f}"
            ),
        }
    )
    zero = next(
        (row for row in sweep if abs(float(row["false_negative"])) < 1e-9), None
    )
    if zero is not None:
        rows.append(
            {
                "test": "perfect_classifier_gain",
                "value": float(zero["E3_gain_mean"]),
                "threshold": ">= 5 pp",
                "passed": float(zero["E3_gain_mean"]) >= 5.0,
                "detail": (
                    f"fn=0: E3 legit {float(zero['E3_legit_mean']):.2f} % "
                    f"vs unclassified {base_e3:.2f} %; gain "
                    f"{float(zero['E3_gain_mean']):+.2f} +/- "
                    f"{float(zero['E3_gain_ci95']):.2f} pp"
                ),
            }
        )
    rows.append(
        {
            "test": "reference_unclassified",
            "value": base_e3,
            "threshold": "",
            "passed": True,
            "detail": (
                f"unclassified E1={base_e1:.2f}, E3={base_e3:.2f}; "
                f"separated E3={float(separated['E3_legit_mean']):.2f}"
            ),
        }
    )
    return rows


def _print(
    arms: Sequence[dict[str, object]], verdict: Sequence[dict[str, object]]
) -> None:
    print("Attack-aware admission (legitimate delivery, %):")
    for row in arms:
        fn = row["false_negative"]
        label = (
            f"{row['mode']}/{row['admission']}"
            + ("" if fn == "" else f" fn={float(fn):.1f}")
        )
        print(
            f"  {label:26s} E1={float(row['E1_legit_mean']):6.2f} "
            f"E2={float(row['E2_legit_mean']):6.2f} "
            f"E3={float(row['E3_legit_mean']):6.2f} "
            f"| total={float(row['total_delivered_percent_mean']):6.2f}"
        )
    print("\nPre-registered tests:")
    for row in verdict:
        print(
            f"  {row['test']:32s} value={row['value']} "
            f"{'PASS' if row['passed'] else 'FAIL'}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args()
    run_benchmark(args.output_dir)
    print(f"\nCSVs: {args.output_dir}/attack_aware_*.csv")


if __name__ == "__main__":
    main()
