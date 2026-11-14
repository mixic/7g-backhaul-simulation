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

"""Compare two real-stack result directories, one per kernel.

The frozen round-2 clause asks for a second kernel and says a disagreement is a
finding, not a harness failure.  This tool makes the comparison mechanical:

* per-case verdicts side by side;
* every observation key that differs, with the seed and metric named;
* a summary count, plus a Markdown report.

It is deliberately data-driven: it does not decide which kernel is "right".  The
human writes that interpretation in the results document.

Usage::

    py tools/compare_kernels.py \\
        --left validation/round2/results \\
        --right results/<kernel-id>/round2 \\
        --out results/<kernel-id>/comparison.md
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Observation:
    scenario: str
    policy: str
    seed: str
    metric: str
    value: float
    unit: str


@dataclass(frozen=True)
class Verdict:
    prediction: str
    case: str
    verdict: str
    detail: str = ""


def read_observations(path: Path) -> dict[tuple[str, str, str, str], Observation]:
    observations: dict[tuple[str, str, str, str], Observation] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row["scenario"], row["policy"], row["seed"], row["metric"])
            observations[key] = Observation(
                scenario=row["scenario"],
                policy=row["policy"],
                seed=row["seed"],
                metric=row["metric"],
                value=float(row["value"]),
                unit=row.get("unit", ""),
            )
    return observations


def read_verdicts(path: Path) -> dict[tuple[str, str], Verdict]:
    verdicts: dict[tuple[str, str], Verdict] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("prediction", ""), row.get("case", ""))
            verdicts[key] = Verdict(
                prediction=row.get("prediction", ""),
                case=row.get("case", ""),
                verdict=row.get("verdict", ""),
                detail=row.get("detail", ""),
            )
    return verdicts


def _same(left: float, right: float, tolerance: float) -> bool:
    if math.isnan(left) and math.isnan(right):
        return True
    return abs(left - right) <= tolerance


def compare(
    left_dir: Path,
    right_dir: Path,
    tolerance: float = 0.0,
) -> dict[str, object]:
    left_obs = read_observations(left_dir / "observations.csv")
    right_obs = read_observations(right_dir / "observations.csv")
    left_verdicts = read_verdicts(left_dir / "verdicts.csv")
    right_verdicts = read_verdicts(right_dir / "verdicts.csv")

    keys = sorted(set(left_obs) | set(right_obs))
    mismatches = []
    missing = []
    for key in keys:
        if key not in left_obs or key not in right_obs:
            missing.append(key)
            continue
        if not _same(left_obs[key].value, right_obs[key].value, tolerance):
            mismatches.append(
                {
                    "scenario": key[0],
                    "policy": key[1],
                    "seed": key[2],
                    "metric": key[3],
                    "left": left_obs[key].value,
                    "right": right_obs[key].value,
                    "unit": left_obs[key].unit or right_obs[key].unit,
                }
            )
    verdict_keys = sorted(set(left_verdicts) | set(right_verdicts))
    verdict_rows = []
    for key in verdict_keys:
        left = left_verdicts.get(key)
        right = right_verdicts.get(key)
        verdict_rows.append(
            {
                "prediction": key[0],
                "case": key[1] or (left.case if left else right.case if right else ""),
                "left": left.verdict if left else "MISSING",
                "right": right.verdict if right else "MISSING",
                "agree": bool(left and right and left.verdict == right.verdict),
            }
        )
    return {
        "left": str(left_dir),
        "right": str(right_dir),
        "n_keys": len(keys),
        "n_mismatches": len(mismatches),
        "n_missing": len(missing),
        "mismatches": mismatches,
        "missing": [
            {"scenario": key[0], "policy": key[1], "seed": key[2], "metric": key[3]}
            for key in missing
        ],
        "verdicts": verdict_rows,
        "verdict_disagreements": [row for row in verdict_rows if not row["agree"]],
    }


def render_markdown(result: dict[str, object]) -> str:
    lines = [
        "# Cross-kernel comparison",
        "",
        f"- Left: `{result['left']}`",
        f"- Right: `{result['right']}`",
        f"- Observation keys: {result['n_keys']}",
        f"- Differing keys: {result['n_mismatches']}",
        f"- Missing keys: {result['n_missing']}",
        "",
        "## Verdicts by case",
        "",
        "| Prediction | Case | Left | Right | Agree |",
        "|---|---|---|---|---|",
    ]
    for row in result["verdicts"]:
        lines.append(
            f"| {row['prediction']} | {row['case']} | {row['left']} | {row['right']} | "
            f"{'yes' if row['agree'] else 'NO'} |"
        )
    lines += ["", "## Observation differences", ""]
    if result["mismatches"]:
        lines += [
            "| Scenario | Policy | Seed | Metric | Left | Right | Unit |",
            "|---|---|---|---|---:|---:|---|",
        ]
        for row in result["mismatches"]:
            lines.append(
                f"| {row['scenario']} | {row['policy']} | {row['seed']} | {row['metric']} | "
                f"{row['left']} | {row['right']} | {row['unit']} |"
            )
    else:
        lines.append("No observation differences at the chosen tolerance.")
    if result["missing"]:
        lines += ["", "## Missing keys", ""]
        for row in result["missing"]:
            lines.append(
                f"- {row['scenario']}/{row['policy']}/seed {row['seed']}/{row['metric']}"
            )
    lines += [
        "",
        "A verdict disagreement is a finding for the human to interpret, not a "
        "harness failure by itself. The frozen predictions are not edited.",
        "",
    ]
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help="absolute tolerance for observation values (default exact)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    for label, directory in (("left", args.left), ("right", args.right)):
        for name in ("observations.csv", "verdicts.csv"):
            if not (directory / name).exists():
                print(f"missing {label} {name}: {directory / name}")
                return 2
    result = compare(args.left, args.right, args.tolerance)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_markdown(result), encoding="utf-8")
    print(
        f"{result['n_mismatches']} differing keys, "
        f"{len(result['verdict_disagreements'])} verdict disagreements; "
        f"wrote {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
