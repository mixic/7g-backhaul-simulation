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

"""Generate the common-mode paper figures from the 30-seed summary CSV.

The summary is produced by ``tools/benchmark_common_mode.py``.  If it is
missing, this script runs the benchmark first.  The figures are written to
``figures/`` as PNG (Markdown preview) and PDF (paper inclusion).
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = REPO / "output" / "common-mode" / "common_mode_summary.csv"

EVENTS = (
    "none",
    "link",
    "srlg",
    "backhaul_cut",
    "provider_cp",
    "idp",
    "ai",
    "tenant_gw",
    "controller_link",
    "ai_link",
)
ARMS = ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9")
ARM_LABELS = {
    "A1": "A1 single",
    "A2": "A2 shared-fate",
    "A3": "A3 disjoint",
    "A4": "A4 tenant iso.",
    "A5": "A5 independent",
    "A6": "A6 one-way+fb",
    "A7": "A7 untested fb",
    "A8": "A8 global ctrl",
    "A9": "A9 iso. only",
}
EVENT_LABELS = {
    "none": "no failure",
    "link": "link",
    "srlg": "conduit SRLG",
    "backhaul_cut": "backhaul cut",
    "provider_cp": "provider CP",
    "idp": "identity",
    "ai": "AI",
    "tenant_gw": "tenant gateway",
    "controller_link": "controller + link",
    "ai_link": "AI + link",
}


def _ensure_summary(path: Path) -> None:
    if path.exists():
        return
    print(f"{path} missing; running the 30-seed benchmark")
    subprocess.run(
        [sys.executable, str(REPO / "tools" / "benchmark_common_mode.py"), "--seeds", "30"],
        check=True,
        cwd=REPO,
    )


def _read(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {(row["event"], row["arm"]): row for row in rows}


def _value(
    rows: dict[tuple[str, str], dict[str, str]], event: str, arm: str
) -> float:
    return float(rows[(event, arm)]["availability_event_mean_pct"])


def _save(fig: plt.Figure, stem: str) -> None:
    output = REPO / "figures"
    output.mkdir(exist_ok=True)
    for suffix in ("png", "pdf"):
        fig.savefig(
            output / f"{stem}.{suffix}",
            dpi=220 if suffix == "png" else None,
            bbox_inches="tight",
        )
    plt.close(fig)
    print(f"wrote figures/{stem}.png and figures/{stem}.pdf")


def heatmap(rows: dict[tuple[str, str], dict[str, str]]) -> None:
    matrix = np.array(
        [[_value(rows, event, arm) for arm in ARMS] for event in EVENTS]
    )
    fig, ax = plt.subplots(figsize=(9.4, 4.9))
    image = ax.imshow(matrix, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(ARMS)), ARMS)
    ax.set_yticks(range(len(EVENTS)), [EVENT_LABELS[e] for e in EVENTS])
    ax.set_xlabel("arm")
    ax.set_title("Availability during the event (%, 30-seed mean)", pad=10)
    for row in range(len(EVENTS)):
        for column in range(len(ARMS)):
            value = matrix[row, column]
            colour = "black" if 25 < value < 85 else "white"
            ax.text(
                column,
                row,
                f"{value:.0f}",
                ha="center",
                va="center",
                fontsize=8,
                color=colour,
            )
    colourbar = fig.colorbar(image, ax=ax, fraction=0.025, pad=0.02)
    colourbar.set_label("availability (%)")
    fig.tight_layout()
    _save(fig, "common_mode_availability")


def _panel(
    ax: plt.Axes,
    title: str,
    labels: list[str],
    values: list[float],
    colours: list[str],
) -> None:
    positions = np.arange(len(labels))
    bars = ax.bar(positions, values, color=colours, width=0.62)
    ax.set_title(title, fontsize=9)
    ax.set_xticks(positions, labels, rotation=0, fontsize=7)
    ax.set_ylim(0, 105)
    ax.set_ylabel("availability (%)", fontsize=8)
    ax.tick_params(axis="y", labelsize=7)
    ax.grid(axis="y", alpha=0.25, linewidth=0.6)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 2,
            f"{value:.0f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )


def mechanisms(rows: dict[tuple[str, str], dict[str, str]]) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(9.4, 5.2))

    _panel(
        axes[0, 0],
        "Tenant-shared fault",
        ["no isolation\n(A3)", "+ tenant iso.\n(A4)"],
        [_value(rows, "tenant_gw", "A3"), _value(rows, "tenant_gw", "A4")],
        ["#b2182b", "#2166ac"],
    )
    _panel(
        axes[0, 1],
        "Conduit failure",
        ["shared fate\n(A2)", "SRLG-disjoint\n(A3)"],
        [_value(rows, "srlg", "A2"), _value(rows, "srlg", "A3")],
        ["#b2182b", "#2166ac"],
    )
    _panel(
        axes[0, 2],
        "AI control-plane failure",
        ["AI required\n(A5)", "one-way + fb\n(A6)"],
        [_value(rows, "ai", "A5"), _value(rows, "ai", "A6")],
        ["#b2182b", "#1b7837"],
    )
    _panel(
        axes[1, 0],
        "Controller + link failure",
        ["global ctrl\n(A8)", "local\n(A5)"],
        [
            _value(rows, "controller_link", "A8"),
            _value(rows, "controller_link", "A5"),
        ],
        ["#b2182b", "#1b7837"],
    )
    _panel(
        axes[1, 1],
        "AI + link failure",
        ["single\n(A1)", "disjoint\n(A3)", "iso. only\n(A9)", "both\n(A6)"],
        [
            _value(rows, "ai_link", "A1"),
            _value(rows, "ai_link", "A3"),
            _value(rows, "ai_link", "A9"),
            _value(rows, "ai_link", "A6"),
        ],
        ["#b2182b", "#d6604d", "#f4a582", "#1b7837"],
    )
    _panel(
        axes[1, 2],
        "Full backhaul cut",
        ["tested fb\n(A6)", "untested fb\n(A7)"],
        [_value(rows, "backhaul_cut", "A6"), _value(rows, "backhaul_cut", "A7")],
        ["#1b7837", "#f4a582"],
    )
    fig.suptitle("Mechanism comparisons (availability during the event, %)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    _save(fig, "common_mode_mechanisms")


def cost_resilience(rows: dict[tuple[str, str], dict[str, str]]) -> None:
    common_mode_events = ("idp", "ai", "tenant_gw", "backhaul_cut")
    mean_availability = {
        arm: float(
            np.mean([_value(rows, event, arm) for event in common_mode_events])
        )
        for arm in ARMS
    }
    costs = {arm: float(rows[("none", arm)]["cost_index"]) for arm in ARMS}
    colours = {
        "A1": "#777777",
        "A2": "#777777",
        "A3": "#777777",
        "A4": "#777777",
        "A5": "#777777",
        "A6": "#1b7837",
        "A7": "#f4a582",
        "A8": "#b2182b",
        "A9": "#d6604d",
    }
    offsets = {
        "A1": (6, 4),
        "A2": (-20, 8),
        "A3": (6, -12),
        "A4": (6, 4),
        "A5": (6, 4),
        "A6": (6, 4),
        "A7": (6, -12),
        "A8": (-30, 8),
        "A9": (6, 4),
    }
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    for arm in ARMS:
        ax.scatter(
            costs[arm],
            mean_availability[arm],
            s=72,
            color=colours[arm],
            edgecolor="black",
            linewidth=0.5,
            zorder=3,
        )
        ax.annotate(
            arm,
            (costs[arm], mean_availability[arm]),
            textcoords="offset points",
            xytext=offsets[arm],
            fontsize=9,
        )
    ax.set_xlabel("cost index (stipulated)")
    ax.set_ylabel("mean availability over the 4 common-mode events (%)")
    ax.set_title("Cost and common-mode resilience", pad=10)
    ax.set_ylim(-4, 88)
    ax.grid(alpha=0.25, linewidth=0.6)
    fig.tight_layout()
    _save(fig, "common_mode_cost_resilience")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args(argv)
    _ensure_summary(args.summary)
    rows = _read(args.summary)
    heatmap(rows)
    mechanisms(rows)
    cost_resilience(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
