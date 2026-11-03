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

"""Plot attack-aware admission from the committed benchmark CSVs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TARGET_COLORS = {"E1": "#2ca02c", "E2": "#d62728", "E3": "#1f77b4"}


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("figures"))
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    sweep = _read(args.input_dir / "attack_aware_sweep.csv")
    summary = _read(args.input_dir / "attack_aware_summary.csv")
    unclassified = next(
        row
        for row in summary
        if row["mode"] == "fluid" and row["admission"] == "open"
    )
    separated = next(
        row
        for row in summary
        if row["mode"] == "separated" and row["admission"] == "open"
    )

    figure, axis = plt.subplots(figsize=(7.2, 4.2))
    ratings = sorted(float(row["false_negative"]) for row in sweep)
    for target in ("E1", "E2", "E3"):
        values = [
            float(row[f"{target}_legit_mean"])
            for row in sorted(sweep, key=lambda item: float(item["false_negative"]))
        ]
        axis.plot(
            ratings,
            values,
            marker="o",
            markersize=3.5,
            color=TARGET_COLORS[target],
            label=f"authenticated admission, {target}",
        )
    axis.axhline(
        float(unclassified["E3_legit_mean"]),
        color="#1f77b4",
        linestyle="--",
        alpha=0.6,
        label="E3, unclassified fluid",
    )
    axis.axhline(
        float(separated["E3_legit_mean"]),
        color="#7f7f7f",
        linestyle=":",
        alpha=0.7,
        label="E3, separated roles",
    )
    axis.axhline(95.0, color="black", linewidth=1, alpha=0.5)
    axis.axvline(0.5, color="black", linestyle=":", alpha=0.6)
    axis.text(0.51, 88.5, "pre-registered fn = 0.5", fontsize=7)
    qualifying = [
        float(row["false_negative"])
        for row in sweep
        if all(float(row[f"{target}_legit_mean"]) >= 95.0 for target in ("E1", "E2", "E3"))
    ]
    if qualifying:
        axis.axvspan(0.0, max(qualifying), color="green", alpha=0.06)
        axis.text(0.02, 100.2, "all targets >= 95 %", fontsize=7, color="green")
    axis.set_xlabel("classifier false-negative rate (fraction of flood admitted)")
    axis.set_ylabel("legitimate delivery (%)")
    axis.set_title("DDoS flood at E2: authenticated name-class admission")
    axis.set_ylim(65, 102)
    axis.grid(alpha=0.3)
    axis.legend(fontsize=7, ncol=2, loc="lower left")
    figure.tight_layout()
    figure.savefig(args.output_dir / "attack_aware_ddos.png", dpi=150)
    plt.close(figure)
    print(f"Figure: {args.output_dir}/attack_aware_ddos.png")


if __name__ == "__main__":
    main()
