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

"""Generate the Monte Carlo common-mode paper figures from the committed tables.

The tables are written by ``tools/benchmark_common_mode_mc.py`` under
``docs/paper-tables/``.  The figures are written to ``figures/`` as PNG (Markdown
preview) and PDF (paper inclusion).  Nothing is recomputed from the simulator:
every panel is derived from a committed CSV, so a figure can be regenerated from
the artifact alone.

Usage::

    py -3 tools/make_common_mode_mc_figures.py
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
TABLE_DIR = REPO / "docs" / "paper-tables"
FIGURE_DIR = REPO / "figures"

ARMS = ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9")
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
ARM_LABELS = {
    "A1": "A1 single",
    "A2": "A2 shared-fate",
    "A3": "A3 disjoint",
    "A4": "A4 + tenant iso.",
    "A5": "A5 + indep. control",
    "A6": "A6 + one-way + tested fb",
    "A7": "A7 untested fallback",
    "A8": "A8 global controller",
    "A9": "A9 isolation only",
}

PLOT_STYLE = {
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "figure.dpi": 110,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
}

MECHANISM_PANELS = (
    ("H16a", "H16: A4 - A3 under tenant gateway", 50.0),
    ("H17a", "H17: A3 - A2 under conduit (SRLG)", 20.0),
    ("H17b", "H17: A2 - A1 under a link failure", 50.0),
    ("H18a", "H18: A6 - A5 under an AI failure", 50.0),
    ("H19a", "H19: (A6-A3)-(A9-A1) under AI + link", 20.0),
    ("H20a", "H20: A5 - A8 under controller + link", 50.0),
    ("fallback_gap", "tested - untested under the cut", 0.0),
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def _save(figure: plt.Figure, name: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    # The PDF metadata timestamp would make the artifact change on every run
    # even when the data did not; drop it so the figures are reproducible.
    figure.savefig(output_dir / f"{name}.png")
    figure.savefig(
        output_dir / f"{name}.pdf",
        metadata={"CreationDate": None, "ModDate": None},
    )
    plt.close(figure)
    print(f"wrote {output_dir / (name + '.png')}")


def figure_availability(table_dir: Path, output_dir: Path) -> None:
    rows = read_csv(table_dir / "common-mode-mc-summary.csv")
    means = {(row["event"], row["arm"]): _float(row, "availability_event_mean_pct") for row in rows}
    half = {(row["event"], row["arm"]): _float(row, "availability_event_ci95_pct") for row in rows}
    matrix = np.array([[means[(event, arm)] for arm in ARMS] for event in EVENTS])

    figure, axis = plt.subplots(figsize=(9.2, 5.4))
    image = axis.imshow(matrix, cmap="viridis", vmin=0.0, vmax=100.0, aspect="auto")
    for row_index, event in enumerate(EVENTS):
        for column_index, arm in enumerate(ARMS):
            value = means[(event, arm)]
            colour = "white" if value < 55 else "black"
            axis.text(
                column_index,
                row_index,
                f"{value:.1f}\n\u00b1{half[(event, arm)]:.1f}",
                ha="center",
                va="center",
                fontsize=7.2,
                color=colour,
            )
    axis.set_xticks(range(len(ARMS)))
    axis.set_xticklabels([ARM_LABELS[arm] for arm in ARMS], rotation=28, ha="right")
    axis.set_yticks(range(len(EVENTS)))
    axis.set_yticklabels(EVENTS)
    axis.set_title(
        "Availability during the event (%, mean over replications, \u00b1 half-width of the 95 % interval)"
    )
    colour_bar = figure.colorbar(image, ax=axis, fraction=0.03, pad=0.02)
    colour_bar.set_label("availability (%)")
    figure.tight_layout()
    _save(figure, "common_mode_mc_availability", output_dir)


def figure_mechanisms(table_dir: Path, output_dir: Path) -> None:
    rows = read_csv(table_dir / "common-mode-mc-differences.csv")
    series: dict[str, list[float]] = {}
    for row in rows:
        series.setdefault(row["criterion"], []).append(_float(row, "value_pct"))

    figure, axes = plt.subplots(2, 4, figsize=(13.0, 6.2))
    axes = axes.ravel()
    rng = np.random.default_rng(7)
    for axis, (key, title, threshold) in zip(axes, MECHANISM_PANELS):
        values = np.asarray(series[key], dtype=float)
        axis.axhline(threshold, color="#b22222", linestyle="--", linewidth=1.0)
        axis.boxplot(
            values, widths=0.45, showfliers=False, patch_artist=True,
            boxprops={"facecolor": "#cfe3f3", "edgecolor": "#1f4e79"},
            medianprops={"color": "#1f4e79"},
            whiskerprops={"color": "#1f4e79"},
            capprops={"color": "#1f4e79"},
        )
        sample = rng.choice(values, size=min(250, values.size), replace=False)
        axis.scatter(
            np.full(sample.size, 1.0) + rng.uniform(-0.16, 0.16, sample.size),
            sample,
            s=3.5,
            color="#333333",
            alpha=0.35,
            linewidths=0,
        )
        axis.set_title(title, fontsize=9)
        axis.set_xticks([])
        axis.set_ylabel("percentage points")
        axis.grid(axis="y", alpha=0.25)
        axis.margins(x=0.25)
    axes[-1].axis("off")
    figure.suptitle(
        "Per-replication mechanism differences; the dashed line is the frozen threshold",
        fontsize=10.5,
    )
    figure.tight_layout()
    _save(figure, "common_mode_mc_mechanisms", output_dir)


def figure_campaign(table_dir: Path, output_dir: Path) -> None:
    rows = {row["arm"]: row for row in read_csv(table_dir / "common-mode-mc-campaign.csv")}
    arms = list(ARMS)
    policy = [_float(rows[arm], "policy_loss_pct") for arm in arms]
    congestion = [_float(rows[arm], "congestion_loss_pct") for arm in arms]
    dependency = [_float(rows[arm], "dependency_loss_pct") for arm in arms]
    attribution = [_float(rows[arm], "shared_attrib") for arm in arms]
    figure, (left, right) = plt.subplots(1, 2, figsize=(12.6, 4.4), gridspec_kw={"width_ratios": [3, 2]})
    positions = np.arange(len(arms))
    left.bar(positions, policy, 0.62, label="policy efficiency (one-way 0.9)", color="#d9a441")
    left.bar(positions, congestion, 0.62, bottom=policy, label="congestion", color="#5f8db5")
    left.bar(
        positions,
        dependency,
        0.62,
        bottom=np.array(policy) + np.array(congestion),
        label="dependency failures",
        color="#b22222",
    )
    for position, total in zip(
        positions, np.array(policy) + congestion + dependency
    ):
        left.text(
            position,
            total + 0.35,
            f"{total:.1f}",
            ha="center",
            va="bottom",
            fontsize=7.5,
        )
    left.set_xticks(positions)
    left.set_xticklabels(arms, fontsize=8)
    left.set_ylabel("percent of the 30-day campaign lost")
    left.set_title("Unavailability decomposition (availability in the caption)")
    left.legend(loc="upper left", ncol=2)
    left.grid(axis="y", alpha=0.25)
    left.set_ylim(0, max(np.array(policy) + congestion + dependency) * 1.35)

    right.bar(positions, attribution, 0.62, color="#4a7a52")
    right.set_xticks(positions)
    right.set_xticklabels(arms)
    right.set_ylabel("share of dependency loss")
    right.set_title("Share of dependency-driven unavailability\nattributable to shared control")
    right.set_ylim(0, 1.05)
    right.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    _save(figure, "common_mode_mc_campaign", output_dir)


def figure_sensitivity(table_dir: Path, output_dir: Path) -> None:
    rows = read_csv(table_dir / "common-mode-mc-sensitivity.csv")
    breaks = read_csv(table_dir / "common-mode-mc-break-even.csv")
    by_parameter: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_parameter.setdefault(row["parameter"], []).append(row)
    break_by_key = {(row["parameter"], row["criterion"]): row for row in breaks}

    panels = (
        ("one_way_efficiency", "one-way efficiency", "normal_cost", 15.0, 0.90),
        ("fallback_tested_probability", "tested activation p", "fallback_gap", 0.0, 0.98),
        ("fallback_untested_probability", "untested activation p", "fallback_gap", 0.0, 0.60),
        ("fallback_tested_delay_s", "tested delay (s)", "fallback_gap", 0.0, 2.0),
        ("fallback_untested_delay_s", "untested delay (s)", "fallback_gap", 0.0, 8.0),
        ("fallback_tested_capacity_gbps", "tested capacity (Gbps)", "fallback_gap", 0.0, 0.50),
        ("fallback_untested_capacity_gbps", "untested capacity (Gbps)", "fallback_gap", 0.0, 0.30),
    )
    figure, axes = plt.subplots(2, 4, figsize=(13.2, 6.0))
    axes = axes.ravel()

    def metric_value(row: dict[str, str], metric: str) -> float:
        if metric == "normal_cost":
            return _float(row, "a5_none") - _float(row, "a6_none")
        if metric == "fallback_gap":
            return _float(row, "a6_backhaul") - _float(row, "a7_backhaul")
        return _float(row, metric)

    for axis, (parameter, label, metric, threshold, current) in zip(axes, panels):
        grid = sorted(by_parameter[parameter], key=lambda row: _float(row, "value"))
        values = [_float(row, "value") for row in grid]
        metrics = [metric_value(row, metric) for row in grid]
        axis.plot(values, metrics, color="#1f4e79", linewidth=1.4, marker="o", markersize=2.5)
        axis.axhline(threshold, color="#b22222", linestyle="--", linewidth=1.0)
        axis.axvline(current, color="#666666", linestyle=":", linewidth=1.0)
        break_row = break_by_key.get((parameter, "fallback_gap" if metric == "fallback_gap" else "H18_normal_cost"))
        if break_row is not None and break_row["break_even_value"] != "":
            axis.axvline(
                float(break_row["break_even_value"]),
                color="#b22222",
                linestyle="--",
                linewidth=0.9,
            )
        axis.set_title(label, fontsize=9)
        axis.set_ylabel("percentage points")
        axis.grid(alpha=0.25)
    axes[-1].axis("off")
    figure.suptitle(
        "One-factor sensitivity under the Monte Carlo engine (25 grid points, "
        "500 replications each)",
        fontsize=10.5,
    )
    figure.tight_layout()
    _save(figure, "common_mode_mc_sensitivity", output_dir)


def figure_sobol(table_dir: Path, output_dir: Path) -> None:
    path = table_dir / "common-mode-mc-sobol.csv"
    if not path.exists():
        print("skipping the Sobol figure: run --sobol first")
        return
    rows = read_csv(path)
    outputs = []
    for row in rows:
        if row["output"] not in outputs:
            outputs.append(row["output"])
    parameters = []
    for row in rows:
        if row["parameter"] not in parameters:
            parameters.append(row["parameter"])

    figure, axes = plt.subplots(1, len(outputs), figsize=(13.0, 3.9), sharey=True)
    if len(outputs) == 1:
        axes = [axes]
    titles = {
        "a6_ai": "A6 under AI failure",
        "a6_cut": "A6 under backhaul cut",
        "a7_cut": "A7 under backhaul cut",
        "interaction": "H19 interaction",
    }
    for axis, output in zip(axes, outputs):
        selected = [row for row in rows if row["output"] == output]
        selected.sort(key=lambda row: parameters.index(row["parameter"]))
        names = [row["parameter"] for row in selected]
        totals = [_float(row, "total_order") for row in selected]
        first = [_float(row, "first_order") for row in selected]
        positions = np.arange(len(names))
        axis.barh(positions - 0.2, first, 0.38, label="first order", color="#5f8db5")
        axis.barh(positions + 0.2, totals, 0.38, label="total order", color="#b22222")
        axis.set_yticks(positions)
        axis.set_yticklabels(names, fontsize=7)
        axis.invert_yaxis()
        axis.set_title(titles.get(output, output), fontsize=9)
        axis.grid(axis="x", alpha=0.25)
        axis.set_xlim(0, 1.05)
    axes[0].set_xlabel("Sobol index")
    axes[0].legend(loc="lower right")
    figure.suptitle("Global sensitivity of the Monte Carlo outputs (Saltelli, base 256)", fontsize=10.5)
    figure.tight_layout()
    _save(figure, "common_mode_mc_sobol", output_dir)


def figure_convergence(table_dir: Path, output_dir: Path) -> None:
    rows = read_csv(table_dir / "common-mode-mc-differences.csv")
    series: dict[str, list[float]] = {}
    for row in rows:
        series.setdefault(row["criterion"], []).append(_float(row, "value_pct"))
    chosen = (
        ("H19a", "H19 interaction (points)", 20.0),
        ("H18a", "H18: A6 - A5 under AI (points)", 50.0),
        ("fallback_gap", "tested - untested gap (points)", 0.0),
    )
    figure, axes = plt.subplots(1, 3, figsize=(12.6, 3.6), sharex=True)
    for axis, (key, title, threshold) in zip(axes, chosen):
        values = np.asarray(series[key], dtype=float)
        running = np.cumsum(values) / np.arange(1, values.size + 1)
        window = 20
        band = np.zeros(values.size)
        for index in range(1, values.size):
            sample = values[max(0, index - window) : index + 1]
            band[index] = 1.96 * float(np.sqrt(np.var(sample, ddof=1) / (index + 1)))
        index = np.arange(1, values.size + 1)
        axis.fill_between(index, running - band, running + band, color="#cfe3f3", alpha=0.8)
        axis.plot(index, running, color="#1f4e79", linewidth=1.3)
        axis.axhline(threshold, color="#b22222", linestyle="--", linewidth=1.0)
        axis.set_title(title, fontsize=9)
        axis.set_xlabel("replications")
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("running mean (95 % band)")
    figure.suptitle("Monte Carlo convergence of the reported contrasts", fontsize=10.5)
    figure.tight_layout()
    _save(figure, "common_mode_mc_convergence", output_dir)


def figure_cost_resilience(table_dir: Path, output_dir: Path) -> None:
    rows = read_csv(table_dir / "common-mode-mc-summary.csv")
    common_mode_events = ("idp", "ai", "tenant_gw", "backhaul_cut")
    by_arm: dict[str, dict[str, float]] = {}
    for row in rows:
        arm = row["arm"]
        entry = by_arm.setdefault(arm, {"cost": _float(row, "cost_index"), "total": 0.0})
        if row["event"] in common_mode_events:
            entry["total"] += _float(row, "availability_event_mean_pct") / len(
                common_mode_events
            )
    figure, axis = plt.subplots(figsize=(6.4, 4.2))
    for arm, entry in by_arm.items():
        axis.scatter(entry["cost"], entry["total"], s=55, color="#1f4e79", zorder=3)
        axis.annotate(
            arm,
            (entry["cost"], entry["total"]),
            textcoords="offset points",
            xytext=(6, 4),
            fontsize=8,
        )
    axis.set_xlabel("cost index (stipulated accounting device)")
    axis.set_ylabel("mean availability over the four common-mode events (%)")
    axis.set_title("Cost against common-mode resilience (Monte Carlo)")
    axis.grid(alpha=0.25)
    figure.tight_layout()
    _save(figure, "common_mode_mc_cost_resilience", output_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table-dir", type=Path, default=TABLE_DIR)
    parser.add_argument("--output-dir", type=Path, default=FIGURE_DIR)
    args = parser.parse_args(argv)
    with plt.rc_context(PLOT_STYLE):
        figure_availability(args.table_dir, args.output_dir)
        figure_mechanisms(args.table_dir, args.output_dir)
        figure_campaign(args.table_dir, args.output_dir)
        figure_cost_resilience(args.table_dir, args.output_dir)
        figure_sensitivity(args.table_dir, args.output_dir)
        figure_sobol(args.table_dir, args.output_dir)
        figure_convergence(args.table_dir, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
