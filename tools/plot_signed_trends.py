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

"""Plot the signed-trend comparison from the committed CSVs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COLORS = {"positive": "#1f77b4", "signed": "#ff7f0e", "signed_release": "#d62728"}
RAMP_UP = (40, 55)
PLATEAU = (55, 85)
DECAY = (85, 100)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("figures"))
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    alpha = _read(args.input_dir / "signed_trends_alpha.csv")
    summary = _read(args.input_dir / "signed_trends_summary.csv")

    figure, (left, right) = plt.subplots(1, 2, figsize=(11.5, 3.9))
    for arm in ("positive", "signed", "signed_release"):
        selected = [row for row in alpha if row["arm"] == arm]
        selected.sort(key=lambda row: int(row["tick"]))
        ticks = [int(row["tick"]) for row in selected]
        values = [float(row["alpha_E2_mean"]) for row in selected]
        left.plot(ticks, values, color=COLORS[arm], label=f"{arm}")
    for window, label, shade in (
        (RAMP_UP, "ramp up", "#2ca02c"),
        (PLATEAU, "plateau", "#7f7f7f"),
        (DECAY, "ramp down", "#d62728"),
    ):
        left.axvspan(*window, color=shade, alpha=0.10)
        left.text(
            window[0] + 0.5,
            0.98,
            label,
            fontsize=7,
            color=shade,
            rotation=90,
            va="top",
        )
    left.set_xlabel("tick (s)")
    left.set_ylabel("mean alpha at E2")
    left.set_title("serve share at the flooded node")
    left.grid(alpha=0.3)
    left.legend(fontsize=8)

    arms = ("positive", "signed_release", "separated")
    labels = ("positive", "signed release", "separated")
    values = [
        float(
            next(
                row["mean"]
                for row in summary
                if row["arm"] == arm and row["metric"] == "e3_decay"
            )
        )
        for arm in arms
    ]
    bars = right.bar(
        labels,
        values,
        color=["#1f77b4", "#d62728", "#7f7f7f"],
    )
    right.axhline(95.0, color="black", linestyle="--", linewidth=1)
    for bar, value in zip(bars, values):
        right.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.3,
            f"{value:.1f}",
            ha="center",
            fontsize=8,
        )
    right.set_ylim(75, 102)
    right.set_ylabel("legitimate delivery, E3 (%)")
    right.set_title("unattacked target during flood decay [85,105)")
    right.grid(axis="y", alpha=0.3)
    figure.tight_layout()
    figure.savefig(args.output_dir / "signed_trends_alpha.png", dpi=150)
    plt.close(figure)
    print(f"Figure: {args.output_dir}/signed_trends_alpha.png")


if __name__ == "__main__":
    main()
