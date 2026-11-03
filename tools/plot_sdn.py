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

"""Plot the SDN control-plane comparison from the committed CSVs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ARMS = ("separated", "local", "sdn")
COLORS = {"separated": "#7f7f7f", "local": "#1f77b4", "sdn": "#2ca02c"}
LABELS = {
    "separated": "separated roles",
    "local": "local fluid",
    "sdn": "SDN override",
}


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def _mean(rows, arm: str, metric: str) -> float:
    return float(
        next(
            row["mean"]
            for row in rows
            if row["arm"] == arm and row["metric"] == metric
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("figures"))
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows = _read(args.input_dir / "sdn_summary.csv")
    figure, (left, right) = plt.subplots(1, 2, figsize=(11, 3.9))

    targets = ("E1", "E2", "E3")
    width = 0.26
    for offset, arm in enumerate(ARMS):
        values = [_mean(rows, arm, target.lower()) for target in targets]
        left.bar(
            [index + (offset - 1) * width for index in range(len(targets))],
            values,
            width,
            color=COLORS[arm],
            label=LABELS[arm],
        )
    left.axhline(95.0, color="black", linestyle="--", linewidth=1)
    left.set_xticks(range(len(targets)))
    left.set_xticklabels(["E1", "E2 (attacked)", "E3"])
    left.set_ylabel("legitimate delivery (%)")
    left.set_ylim(0, 105)
    left.set_title("DDoS flood: delivery by target")
    left.grid(axis="y", alpha=0.3)
    left.legend(fontsize=7)

    steady = [_mean(rows, arm, "steady") for arm in ARMS]
    bars = right.bar(
        [LABELS[arm] for arm in ARMS], steady, color=[COLORS[arm] for arm in ARMS]
    )
    for bar, value in zip(bars, steady):
        right.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.05,
            f"{value:.2f}",
            ha="center",
            fontsize=8,
        )
    right.set_ylim(98.5, 99.8)
    right.set_ylabel("delivered demand (%)")
    right.set_title("steady state: no role override")
    right.grid(axis="y", alpha=0.3)
    figure.tight_layout()
    figure.savefig(args.output_dir / "sdn_control.png", dpi=150)
    plt.close(figure)
    print(f"Figure: {args.output_dir}/sdn_control.png")


if __name__ == "__main__":
    main()
