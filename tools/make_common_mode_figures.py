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


DEFAULT_PER_SEED = REPO / "docs" / "paper-tables" / "common-mode-per-seed.csv"
DEFAULT_SENSITIVITY = REPO / "docs" / "paper-tables" / "common-mode-sensitivity.csv"
DEFAULT_BREAK_EVEN = REPO / "docs" / "paper-tables" / "common-mode-break-even.csv"


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _seed_index(
    rows: list[dict[str, str]],
) -> dict[tuple[int, str, str], float]:
    return {
        (int(row["seed"]), row["event"], row["arm"]): float(
            row["availability_event_pct"]
        )
        for row in rows
    }


def _paired(
    index: dict[tuple[int, str, str], float],
    event: str,
    left: str,
    right: str,
) -> list[float]:
    seeds = sorted({seed for seed, kind, _ in index if kind == event})
    return [index[(seed, event, left)] - index[(seed, event, right)] for seed in seeds]


def _interaction(index: dict[tuple[int, str, str], float]) -> list[float]:
    seeds = sorted({seed for seed, kind, _ in index if kind == "ai_link"})
    return [
        (index[(seed, "ai_link", "A6")] - index[(seed, "ai_link", "A3")])
        - (index[(seed, "ai_link", "A9")] - index[(seed, "ai_link", "A1")])
        for seed in seeds
    ]


def _strip_box(
    ax: plt.Axes,
    values: list[float],
    title: str,
    threshold: float,
    colour: str,
) -> None:
    box_style = {
        "widths": 0.45,
        "patch_artist": True,
        "boxprops": {"facecolor": colour, "alpha": 0.25, "linewidth": 0.8},
        "medianprops": {"color": colour, "linewidth": 1.2},
        "whiskerprops": {"linewidth": 0.8},
        "capprops": {"linewidth": 0.8},
        "flierprops": {"marker": "", "linestyle": "none"},
    }
    try:
        # Matplotlib >= 3.10 renamed ``vert`` to ``orientation``.
        ax.boxplot(values, orientation="vertical", **box_style)
    except TypeError:  # pragma: no cover - old Matplotlib
        ax.boxplot(values, vert=True, **box_style)
    rng = np.random.default_rng(2026)
    jitter = rng.uniform(-0.09, 0.09, size=len(values))
    ax.scatter(
        np.ones(len(values)) + jitter,
        values,
        s=10,
        color=colour,
        alpha=0.55,
        linewidths=0,
        zorder=3,
    )
    centre = float(np.mean(values))
    ax.axhline(threshold, color="#444444", linestyle="--", linewidth=0.8)
    ax.axhline(centre, color=colour, linestyle="-", linewidth=1.0)
    ax.set_xticks([1], ["30 seeds"])
    ax.set_title(title, fontsize=8.5)
    ax.set_ylabel("percentage points", fontsize=7.5)
    ax.tick_params(axis="both", labelsize=7)
    ax.grid(axis="y", alpha=0.22, linewidth=0.5)
    ax.text(
        1.02,
        centre,
        f"mean {centre:.1f}",
        transform=ax.get_yaxis_transform(),
        fontsize=7,
        va="center",
    )


def seed_distributions(rows: list[dict[str, str]]) -> None:
    """Per-seed paired differences for the six mechanism comparisons."""
    index = _seed_index(rows)
    panels = [
        (
            "Tenant isolation: tenant gateway",
            _paired(index, "tenant_gw", "A4", "A3"),
            50.0,
            "#2166ac",
        ),
        (
            "Disjoint multipath: conduit SRLG",
            _paired(index, "srlg", "A3", "A2"),
            20.0,
            "#1b7837",
        ),
        (
            "One-way boundary + fallback: AI",
            _paired(index, "ai", "A6", "A5"),
            50.0,
            "#1b7837",
        ),
        (
            "Tested minus untested: backhaul cut",
            _paired(index, "backhaul_cut", "A6", "A7"),
            0.0,
            "#d6604d",
        ),
        (
            "Local minus global controller: controller + link",
            _paired(index, "controller_link", "A5", "A8"),
            50.0,
            "#1b7837",
        ),
        (
            "Isolation x multipath interaction: AI + link",
            _interaction(index),
            20.0,
            "#762a83",
        ),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(10.2, 5.6))
    for ax, (title, values, threshold, colour) in zip(axes.reshape(-1), panels):
        _strip_box(ax, values, title, threshold, colour)
    fig.suptitle(
        "Per-seed paired differences (30 seeds); dashed line = frozen threshold",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    _save(fig, "common_mode_seed_distributions")


def _sensitivity_rows(
    rows: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["parameter"], []).append(row)
    for values in grouped.values():
        values.sort(key=lambda item: float(item["value"]))
    return grouped


def _break_even(
    rows: list[dict[str, str]], parameter: str, criterion: str
) -> float | None:
    for row in rows:
        if row["parameter"] == parameter and row["criterion"] == criterion:
            if row["break_even_value"] == "":
                return None
            return float(row["break_even_value"])
    return None


def _plot_series(
    ax: plt.Axes,
    points: list[dict[str, str]],
    field: str,
    label: str,
    colour: str,
    style: str = "-",
) -> None:
    ax.plot(
        [float(point["value"]) for point in points],
        [float(point[field]) for point in points],
        style,
        color=colour,
        linewidth=1.3,
        label=label,
    )


def _mark(
    ax: plt.Axes,
    break_even: float | None,
    current: float,
    label: str,
) -> None:
    ax.axvline(current, color="#777777", linestyle=":", linewidth=0.9)
    if break_even is not None:
        ax.axvline(break_even, color="#b2182b", linestyle="--", linewidth=1.0)
        ax.annotate(
            f"{label} {break_even:g}",
            xy=(break_even, 0.02),
            xycoords=("data", "axes fraction"),
            fontsize=7,
            color="#b2182b",
            rotation=90,
            ha="right",
            va="bottom",
        )


def sensitivity_figure(
    rows: list[dict[str, str]], break_rows: list[dict[str, str]]
) -> None:
    grouped = _sensitivity_rows(rows)
    fig, axes = plt.subplots(2, 2, figsize=(10.2, 6.0))

    ax = axes[0, 0]
    points = grouped["one_way_efficiency"]
    _plot_series(ax, points, "a6_ai", "A6 under AI", "#1b7837")
    _plot_series(ax, points, "a6_ai_link", "A6 under AI + link", "#1b7837", "--")
    _plot_series(ax, points, "a5_ai", "A5 under AI", "#b2182b")
    ax.axhline(80, color="#444444", linestyle="--", linewidth=0.8)
    _mark(
        ax,
        _break_even(break_rows, "one_way_efficiency", "H18_normal_cost"),
        0.90,
        "break-even",
    )
    ax.set_title("Efficiency of the one-way boundary (H18)", fontsize=8.5)
    ax.set_xlabel("local-policy efficiency", fontsize=7.5)
    ax.set_ylabel("availability during event (%)", fontsize=7.5)
    ax.legend(fontsize=6.5, frameon=False, loc="lower right")

    ax = axes[0, 1]
    points = grouped["fallback_tested_probability"]
    _plot_series(ax, points, "a6_backhaul", "A6 tested", "#1b7837")
    _plot_series(ax, points, "a7_backhaul", "A7 untested", "#d6604d")
    _plot_series(ax, points, "a9_link", "A9 under link", "#2166ac")
    _mark(
        ax,
        _break_even(break_rows, "fallback_tested_probability", "fallback_gap"),
        0.98,
        "break-even",
    )
    ax.set_title("Tested fallback activation probability", fontsize=8.5)
    ax.set_xlabel("activation probability", fontsize=7.5)
    ax.set_ylabel("availability during event (%)", fontsize=7.5)
    ax.legend(fontsize=6.5, frameon=False, loc="lower right")

    ax = axes[1, 0]
    points = grouped["fallback_tested_delay_s"]
    _plot_series(ax, points, "a6_backhaul", "A6 tested", "#1b7837")
    _plot_series(ax, points, "a7_backhaul", "A7 untested", "#d6604d")
    _plot_series(ax, points, "a9_link", "A9 under link", "#2166ac")
    _mark(
        ax,
        _break_even(break_rows, "fallback_tested_delay_s", "fallback_gap"),
        2.0,
        "break-even",
    )
    ax.set_title("Tested fallback activation delay", fontsize=8.5)
    ax.set_xlabel("delay (s)", fontsize=7.5)
    ax.set_ylabel("availability during event (%)", fontsize=7.5)
    ax.legend(fontsize=6.5, frameon=False, loc="lower right")

    ax = axes[1, 1]
    points = grouped["fallback_tested_capacity_gbps"]
    _plot_series(ax, points, "a6_backhaul", "A6 tested", "#1b7837")
    _plot_series(ax, points, "a7_backhaul", "A7 untested", "#d6604d")
    _plot_series(ax, points, "a9_link", "A9 under link", "#2166ac")
    _mark(
        ax,
        _break_even(break_rows, "fallback_tested_capacity_gbps", "fallback_gap"),
        0.50,
        "gap",
    )
    twin = ax.twinx()
    twin.plot(
        [float(point["value"]) for point in points],
        [float(point["interaction"]) for point in points],
        color="#762a83",
        linewidth=1.0,
        linestyle=":",
        label="H19 interaction (right)",
    )
    twin.axhline(20, color="#762a83", linestyle="--", linewidth=0.6)
    h19 = _break_even(break_rows, "fallback_tested_capacity_gbps", "H19_interaction")
    _mark(ax, h19, 0.50, "H19")
    twin.set_ylabel("interaction (points)", fontsize=7, color="#762a83")
    twin.tick_params(axis="y", labelsize=6.5, colors="#762a83")
    ax.set_title("Tested fallback capacity", fontsize=8.5)
    ax.set_xlabel("capacity (Gbps)", fontsize=7.5)
    ax.set_ylabel("availability during event (%)", fontsize=7.5)
    ax.legend(fontsize=6.5, frameon=False, loc="lower right")

    for ax in axes.reshape(-1):
        ax.grid(alpha=0.22, linewidth=0.5)
        ax.tick_params(axis="both", labelsize=7)
    fig.suptitle(
        "Sensitivity of the model checks to the stipulated constants "
        "(dotted = stipulated, dashed = break-even)",
        fontsize=9.5,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    _save(fig, "common_mode_sensitivity")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--per-seed", type=Path, default=DEFAULT_PER_SEED)
    parser.add_argument("--sensitivity", type=Path, default=DEFAULT_SENSITIVITY)
    parser.add_argument("--break-even", type=Path, default=DEFAULT_BREAK_EVEN)
    args = parser.parse_args(argv)
    _ensure_summary(args.summary)
    rows = _read(args.summary)
    heatmap(rows)
    mechanisms(rows)
    cost_resilience(rows)
    if args.per_seed.exists():
        seed_distributions(_read_rows(args.per_seed))
    else:
        print(f"{args.per_seed} missing; skipped seed distributions")
    if args.sensitivity.exists() and args.break_even.exists():
        sensitivity_figure(
            _read_rows(args.sensitivity), _read_rows(args.break_even)
        )
    else:
        print("sensitivity artifacts missing; skipped sensitivity figure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
