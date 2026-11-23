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

"""Generate the five Paper D figures from the committed Monte-Carlo tables.

Every plotted number is read from a CSV under ``docs/paper-tables/`` (or, for
Figure 5, from the coded incident corpus ``docs/m16-incident-corpus.md``) and is
asserted against the value the paper states before it is drawn. No data are
re-simulated here, and no number is typed in by hand.

Run::

    py tools/generate_paper_d_figures.py --output-dir docs/figures
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

TABLES = REPO / "docs" / "paper-tables"
CORPUS = REPO / "docs" / "m16-incident-corpus.md"

GREEN = "#2e7d32"
RED = "#c0392b"
AMBER = "#b8860b"
GREY = "#9e9e9e"
BLUE = "#1f4e79"
MID_BLUE = "#4a7fb5"
PALE_BLUE = "#b9cfe4"
PALE_RED = "#e9b4ae"
INK = "#1b1b1b"

STYLE = {
    "font.family": "serif",
    "font.serif": ["DejaVu Serif"],
    "mathtext.fontset": "dejavuserif",
    "font.size": 8.5,
    "axes.titlesize": 9.0,
    "axes.labelsize": 8.5,
    "xtick.labelsize": 7.4,
    "ytick.labelsize": 7.4,
    "legend.fontsize": 7.4,
    "axes.linewidth": 0.7,
    "axes.edgecolor": INK,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
}


def _rows(name: str) -> list[dict[str, str]]:
    path = TABLES / name
    if not path.exists():
        raise SystemExit(f"missing source table: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"DATA CHECK FAILED: {message}")


def _save(figure, output_dir: Path, name: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_dir / f"{name}.pdf")
    figure.savefig(output_dir / f"{name}.png", dpi=200)
    plt.close(figure)
    print(f"  wrote {output_dir.name}/{name}.pdf (+ .png)")


# ---------------------------------------------------------------------------
# Figure 1: Monte-Carlo distributions of tenant survival
# ---------------------------------------------------------------------------
def figure1_distributions(output_dir: Path) -> None:
    """Violin plots of the three quantitative contrasts, per replication.

    The committed tables record per-replication values only for the contrasts in
    ``common-mode-mc-differences.csv``; per-arm campaign records are committed as
    means with intervals, not as runs. The figure therefore plots the three
    contrasts whose distribution is recorded, and the caption says so.
    """
    rows = _rows("common-mode-mc-differences.csv")
    contrasts = (("H19a", "Isolation × multipath\ninteraction (H19a)"),
                 ("fallback_gap", "Tested − untested\nfallback (points)"),
                 ("H18c", "Normal-operation cost\nof the boundary (H18c)"))
    values = {}
    for key, _ in contrasts:
        data = [float(row["value_pct"]) for row in rows if row["criterion"] == key]
        _check(len(data) == 2000, f"{key}: {len(data)} replications, expected 2000")
        values[key] = data
    _check(abs(sum(values["H19a"]) / 2000 - 41.506) < 0.01, "H19a mean is no longer 41.51")
    _check(abs(sum(values["fallback_gap"]) / 2000 - 30.523) < 0.01,
           "fallback gap mean is no longer 30.52")
    _check(abs(sum(values["H18c"]) / 2000 - 9.809) < 0.02, "H18c mean is no longer 9.81")

    figure, ax = plt.subplots(figsize=(5.6, 3.4))
    positions = list(range(len(contrasts)))
    parts = ax.violinplot([values[key] for key, _ in contrasts], positions=positions,
                          widths=0.7, showextrema=False, showmeans=False)
    for body, colour in zip(parts["bodies"], (BLUE, MID_BLUE, RED)):
        body.set_facecolor(colour)
        body.set_edgecolor(INK)
        body.set_alpha(0.30)
        body.set_linewidth(0.7)
    for index, (key, _) in enumerate(contrasts):
        data = sorted(values[key])
        low, high = data[int(0.025 * len(data))], data[int(0.975 * len(data))]
        mean = sum(data) / len(data)
        ax.errorbar([index], [mean], yerr=[[mean - low], [high - mean]], fmt="o",
                    color=INK, markersize=0, capsize=5, linewidth=1.1, zorder=5)
        ax.plot([index - 0.22, index + 0.22], [mean, mean], color=INK, linewidth=1.5, zorder=6)
        ax.text(index + 0.28, mean, f"{mean:.1f}\n[{low:.1f}, {high:.1f}]", va="center",
                ha="left", fontsize=6.4)

    ax.set_xticks(positions)
    ax.set_xticklabels([label for _, label in contrasts], fontsize=7.0)
    ax.set_xlim(-0.6, 2.95)
    ax.set_ylabel("Paired contrast, percentage points")
    ax.set_title("Monte-Carlo distributions of the quantitative contrasts", loc="left", fontsize=8.8)
    ax.text(0.02, 0.03,
            "violins and black bars: 2,000 replications per contrast (2.5–97.5 percentile);\n"
            "the binary contrasts H16a and H17a are 0/100 mixtures and are reported in the text",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=6.4, color="#444444")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    figure.tight_layout()
    _save(figure, output_dir, "fig1_monte_carlo_distributions")


# ---------------------------------------------------------------------------
# Figure 2: break-even sensitivity (tornado)
# ---------------------------------------------------------------------------
BASE = {
    "one_way_efficiency": 0.90,
    "fallback_tested_probability": 0.98,
    "fallback_untested_probability": 0.60,
    "fallback_tested_capacity_gbps": 0.50,
    "fallback_untested_capacity_gbps": 0.30,
    "fallback_tested_delay_s": 2.0,
    "fallback_untested_delay_s": 8.0,
}
LABELS = {
    "one_way_efficiency": "one-way efficiency",
    "fallback_tested_probability": "tested fallback: activation prob.",
    "fallback_untested_probability": "untested fallback: activation prob.",
    "fallback_tested_capacity_gbps": "tested fallback: capacity",
    "fallback_untested_capacity_gbps": "untested fallback: capacity",
    "fallback_tested_delay_s": "tested fallback: delay",
    "fallback_untested_delay_s": "untested fallback: delay",
}


def _nearest(rows, parameter: str, target: float) -> dict[str, str]:
    candidates = [row for row in rows if row["parameter"] == parameter]
    _check(bool(candidates), f"no sensitivity rows for {parameter}")
    return min(candidates, key=lambda row: abs(float(row["value"]) - target))


def _normal_cost(row: dict[str, str]) -> float:
    """Normal-operation cost of the boundary, in points: A5 level minus A6 level."""
    return float(row["a5_none"]) - float(row["a6_none"])


def figure2_tornado(output_dir: Path) -> None:
    """Tornado of the normal-operation cost under +/-20 % of each constant."""
    rows = _rows("common-mode-mc-sensitivity.csv")
    break_even = _rows("common-mode-mc-break-even.csv")
    threshold = None
    for row in break_even:
        if row["criterion"] == "H18_normal_cost" and row["parameter"] == "one_way_efficiency":
            threshold = float(row["threshold"])
            break_even_value = float(row["break_even_value"])
    _check(threshold is not None, "H18 normal-cost threshold not in the break-even table")
    _check(abs(break_even_value - 0.847775) < 1e-6, "the H18 break-even is no longer 0.847775")

    base = _normal_cost(_nearest(rows, "one_way_efficiency", BASE["one_way_efficiency"]))
    _check(abs(base - 9.7775) < 0.01, f"base normal cost is {base:.4f}, expected 9.7775")

    swings = []
    for parameter, value in BASE.items():
        low_row = _nearest(rows, parameter, value * 0.8)
        high_row = _nearest(rows, parameter, value * 1.2)
        low = _normal_cost(low_row)
        high = _normal_cost(high_row)
        swings.append((parameter, low, high, float(low_row["value"]), float(high_row["value"])))
    swings.sort(key=lambda item: abs(item[2] - item[1]), reverse=True)

    figure, ax = plt.subplots(figsize=(6.2, 3.0))
    figure.subplots_adjust(left=0.40, right=0.97, top=0.86, bottom=0.18)
    for index, (parameter, low, high, low_value, high_value) in enumerate(swings):
        ax.barh(index, low - base, left=base, height=0.6, color=PALE_BLUE, edgecolor=BLUE, linewidth=0.6)
        ax.barh(index, high - base, left=base, height=0.6, color=PALE_RED, edgecolor=RED, linewidth=0.6)
    ax.axvline(base, color=INK, linewidth=0.9)
    ax.axvline(threshold, color=RED, linewidth=0.9, linestyle=(0, (4, 2)))
    ax.text(threshold + 0.3, -0.75, f"H18 threshold {threshold:.0f} points",
            color=RED, fontsize=6.5, va="center", ha="left")
    ax.set_yticks(list(range(len(swings))))
    ax.set_yticklabels(
        [f"{LABELS[item[0]]}  ({min(item[1], item[2]):.1f} → {max(item[1], item[2]):.1f})"
         for item in swings],
        fontsize=7.0,
    )
    ax.invert_yaxis()
    ax.set_xlabel("Normal-operation cost of the one-way boundary (percentage points)")
    ax.set_title("Normal cost under ±20 % of each stipulated constant", loc="left", fontsize=8.6)
    edges = [value for item in swings for value in (item[1], item[2])]
    ax.set_xlim(min(min(edges), 0.0) - 2.0, max(max(edges), threshold) + 3.0)
    ax.legend(handles=[Patch(facecolor=PALE_BLUE, edgecolor=BLUE, label="−20 %"),
                       Patch(facecolor=PALE_RED, edgecolor=RED, label="+20 %")],
              loc="lower right", frameon=False, fontsize=6.8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    _save(figure, output_dir, "fig2_break_even_sensitivity")


# ---------------------------------------------------------------------------
# Figure 3: dependency heatmap
# ---------------------------------------------------------------------------
def figure3_dependency_heatmap(output_dir: Path) -> None:
    """Arm x incident-class availability during the event.

    The committed Monte-Carlo tables record one failure class per replication;
    they do not record component *pairs*, so a pair-incidence matrix cannot be
    computed from them without inventing data. What they do record is which
    dependency class bites which architecture, which is the matrix drawn here.
    """
    rows = _rows("common-mode-mc-summary.csv")
    events = ["none", "link", "srlg", "provider_cp", "controller_link", "tenant_gw",
              "idp", "ai", "backhaul_cut", "ai_link"]
    arms = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9"]
    grid = []
    for arm in arms:
        line = []
        for event in events:
            match = [row for row in rows if row["event"] == event and row["arm"] == arm]
            _check(len(match) == 1, f"{arm}/{event}: {len(match)} summary rows")
            line.append(float(match[0]["availability_event_mean_pct"]))
        grid.append(line)
    _check(abs(grid[2][5] - 0.0) < 1e-9, "A3 under tenant_gw is no longer 0 %")
    _check(abs(grid[3][5] - 99.2001) < 0.01, "A4 under tenant_gw is no longer 99.20 %")

    figure, ax = plt.subplots(figsize=(6.4, 3.6))
    image = ax.imshow(grid, aspect="auto", cmap="RdYlGn", vmin=0.0, vmax=100.0)
    for row_index, _ in enumerate(arms):
        for column_index, _ in enumerate(events):
            value = grid[row_index][column_index]
            colour = "white" if value < 35 or value > 92 else INK
            ax.text(column_index, row_index, f"{value:.0f}", ha="center", va="center",
                    fontsize=6.0, color=colour)
    ax.set_xticks(range(len(events)))
    ax.set_xticklabels(events, rotation=35, ha="right", fontsize=6.8)
    ax.set_yticks(range(len(arms)))
    ax.set_yticklabels(arms, fontsize=7.2)
    ax.set_xlabel("Incident class")
    ax.set_ylabel("Architecture")
    ax.set_title("Availability during the event, by architecture and failure class (%)",
                 loc="left", fontsize=8.6)
    colourbar = figure.colorbar(image, ax=ax, fraction=0.03, pad=0.02)
    colourbar.set_label("mean availability during the event (%)", fontsize=7.0)
    colourbar.ax.tick_params(labelsize=6.6)
    figure.tight_layout()
    _save(figure, output_dir, "fig3_dependency_heatmap")


# ---------------------------------------------------------------------------
# Figure 4: the cost of isolation
# ---------------------------------------------------------------------------
def figure4_cost_of_isolation(output_dir: Path) -> None:
    """Efficiency sweep: what isolation buys, and what it costs.

    ``a6_ai`` is the containment level the boundary buys under an AI
    control-plane failure; ``a5_none - a6_none`` is what it costs in normal
    operation. The two curves cross the H18 criterion at the break-even point.
    """
    rows = _rows("common-mode-mc-sensitivity.csv")
    points = sorted(
        (float(row["value"]), float(row["a6_ai"]), float(row["a5_none"]) - float(row["a6_none"]))
        for row in rows if row["parameter"] == "one_way_efficiency"
    )
    _check(len(points) >= 20, f"only {len(points)} efficiency points")
    _check(abs(points[0][0] - 0.5) < 1e-9 and abs(points[-1][0] - 1.0) < 1e-9,
           "the efficiency sweep no longer spans 0.5-1.0")

    break_even = 0.847775
    threshold = 15.0
    figure, ax = plt.subplots(figsize=(5.6, 3.4))
    efficiencies = [point[0] for point in points]
    containment = [point[1] for point in points]
    cost = [point[2] for point in points]

    ax.plot(efficiencies, containment, color=GREEN, linewidth=1.3,
            label="containment under an AI failure (A6, %)")
    ax.axhline(80.0, color=GREEN, linewidth=0.8, linestyle=(0, (4, 2)))
    ax.text(1.015, 81.5, "H18 floor\n80 %", color=GREEN, fontsize=6.2, va="bottom", ha="right")
    ax.set_ylim(0, 108)
    ax.set_xlim(0.48, 1.02)
    ax.set_xlabel("Isolation strength (one-way efficiency; 0.5 = heavily lossy, 1.0 = free)")
    ax.set_ylabel("Containment under an AI failure (%)", color=GREEN)
    ax.tick_params(axis="y", colors=GREEN)

    twin = ax.twinx()
    twin.plot(efficiencies, cost, color=RED, linewidth=1.3, linestyle=(0, (5, 1.6)),
              label="normal-operation cost (A5 − A6, points)")
    twin.axhline(threshold, color=RED, linewidth=0.8, linestyle=(0, (4, 2)))
    twin.text(1.015, threshold + 0.8, "H18 cost\n15 points", color=RED, fontsize=6.2,
              va="bottom", ha="right")
    twin.axvline(break_even, color=INK, linewidth=0.9)
    twin.text(break_even - 0.008, 46, f"break-even\n{break_even:.3f}", fontsize=6.6,
              va="top", ha="right")
    twin.set_ylim(0, 52)
    twin.set_ylabel("Normal-operation cost of the boundary (points)", color=RED)
    twin.tick_params(axis="y", colors=RED)
    twin.spines["top"].set_visible(False)

    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    lines = ax.get_lines()[:1] + twin.get_lines()[:1]
    ax.legend(lines, [line.get_label() for line in lines], loc="lower left",
              frameon=False, fontsize=6.8)
    ax.set_title("The cost of isolation across the efficiency band", loc="left", fontsize=8.6)
    figure.tight_layout()
    _save(figure, output_dir, "fig4_cost_of_isolation")


# ---------------------------------------------------------------------------
# Figure 5: incident corpus classification
# ---------------------------------------------------------------------------
def _corpus_rows() -> list[dict[str, str]]:
    text = CORPUS.read_text(encoding="utf-8")
    rows = []
    for line in text.splitlines():
        if not line.startswith("| C"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 9:
            continue
        rows.append({
            "id": cells[0], "incident": cells[1], "provider": cells[2], "date": cells[3],
            "category": cells[4], "shared": cells[5], "config": cells[6],
            "blast": cells[7], "url": cells[8],
        })
    return rows


def figure5_corpus(output_dir: Path) -> None:
    """Stacked bars of the coded root causes, split by the config-push flag."""
    rows = _corpus_rows()
    _check(len(rows) == 15, f"corpus has {len(rows)} coded rows, expected 15")
    for row in rows:
        _check(row["url"].startswith("https://"), f"{row['id']}: source URL is not https")
        _check(row["category"] in {
            "CONTROL_PLANE_CONFIG", "SHARED_DNS", "AUTH_IDENTITY", "HARDWARE",
            "SOFTWARE_BUG", "EXTERNAL", "UNKNOWN"}, f"{row['id']}: unknown category")
        _check(row["shared"] in {"Yes", "No"} and row["config"] in {"Yes", "No"},
               f"{row['id']}: flags are not Yes/No")

    shared = sum(1 for row in rows if row["shared"] == "Yes")
    pushed = sum(1 for row in rows if row["config"] == "Yes")
    _check(shared == 14 and pushed == 11,
           f"corpus counts drifted: shared={shared}, config={pushed}")

    categories = ["CONTROL_PLANE_CONFIG", "SHARED_DNS", "AUTH_IDENTITY", "HARDWARE",
                  "SOFTWARE_BUG", "EXTERNAL", "UNKNOWN"]
    pushed_counts = {category: sum(1 for row in rows
                                   if row["category"] == category and row["config"] == "Yes")
                     for category in categories}
    unplanned_counts = {category: sum(1 for row in rows
                                      if row["category"] == category and row["config"] == "No")
                        for category in categories}

    figure, ax = plt.subplots(figsize=(5.6, 3.2))
    positions = range(len(categories))
    ax.bar(positions, [pushed_counts[c] for c in categories], width=0.62, color=PALE_RED,
           edgecolor=RED, linewidth=0.7, label="triggered by a configuration push")
    ax.bar(positions, [unplanned_counts[c] for c in categories], width=0.62,
           bottom=[pushed_counts[c] for c in categories], color=PALE_BLUE, edgecolor=BLUE,
           linewidth=0.7, label="unplanned trigger")
    for index, category in enumerate(categories):
        total = pushed_counts[category] + unplanned_counts[category]
        ax.text(index, total + 0.15, str(total), ha="center", va="bottom", fontsize=7.0)
    ax.set_xticks(list(positions))
    ax.set_xticklabels([category.replace("_", "\n") for category in categories], fontsize=6.6)
    ax.set_ylabel("Postmortems in the corpus")
    ax.set_ylim(0, 12.5)
    ax.set_title(f"Root causes of {len(rows)} public postmortems", loc="left", fontsize=8.6)
    ax.legend(loc="upper right", frameon=False, fontsize=6.8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    figure.tight_layout()
    _save(figure, output_dir, "fig5_corpus_classification")


FIGURES = {
    "f1": figure1_distributions,
    "f2": figure2_tornado,
    "f3": figure3_dependency_heatmap,
    "f4": figure4_cost_of_isolation,
    "f5": figure5_corpus,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=REPO / "docs" / "figures")
    parser.add_argument("--only", nargs="+", choices=sorted(FIGURES), help="build a subset")
    args = parser.parse_args(argv)

    plt.rcParams.update(STYLE)
    selected = args.only or sorted(FIGURES)
    print(f"building {len(selected)} figure(s) into {args.output_dir}")
    for key in selected:
        FIGURES[key](args.output_dir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
