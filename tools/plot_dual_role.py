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

"""Plot the dual-role comparison from the committed benchmark CSVs.

Produces the four requested visuals plus the DDoS-isolation chart:

* ``dual_role_alpha.png``      -- alpha(t) and 1-alpha(t), fluid vs fixed;
* ``dual_role_throughput.png`` -- goodput and delivery versus offered load;
* ``dual_role_latency_cdf.png``-- volume-weighted latency CDF;
* ``dual_role_stability.png``  -- mean |delta alpha| per tick;
* ``dual_role_ddos.png``       -- delivery to attacked and unattacked targets.

The CSVs are written by ``tools/benchmark_dual_role.py``.  All inputs are
simulation outputs; the plots do not add claims beyond the CSV values.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

FLUID = "#1f77b4"
SEPARATED = "#d62728"
SPIKE = (40, 80)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def _trace(rows, mode: str, node: str) -> tuple[list[int], list[float]]:
    selected = [
        row
        for row in rows
        if row["mode"] == mode and row["node"] == node
    ]
    selected.sort(key=lambda row: int(row["tick"]))
    return (
        [int(row["tick"]) for row in selected],
        [float(row["alpha"]) for row in selected],
    )


def plot_alpha_with_node_levels(rows, path: Path) -> None:
    """Alpha for E2 (separated 1.0) and M1 (separated 0.0)."""
    figure, (left, right) = plt.subplots(1, 2, figsize=(11, 3.8), sharex=True)
    node_colors = {"E2": FLUID, "M1": "#ff7f0e"}
    for node, separated_level in (("E2", 1.0), ("M1", 0.0)):
        color = node_colors[node]
        ticks, values = _trace(rows, "fluid", node)
        left.plot(ticks, values, color=color, label=f"fluid alpha, {node}")
        left.plot(
            ticks,
            [separated_level for _ in ticks],
            "--",
            color=color,
            alpha=0.55,
            label=f"separated alpha, {node}",
        )
        right.plot(
            ticks,
            [1.0 - value for value in values],
            color=color,
            label=f"fluid 1-alpha, {node}",
        )
    for axis in (left, right):
        axis.axvspan(*SPIKE, color="grey", alpha=0.12)
        axis.set_xlabel("tick (s)")
        axis.grid(alpha=0.3)
    left.set_ylabel("serving share alpha")
    right.set_ylabel("forwarding share 1 - alpha")
    left.set_title("alpha during the flash crowd")
    right.set_title("forwarding share during the flash crowd")
    left.legend(fontsize=7)
    right.legend(fontsize=7)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def plot_throughput(rows, load_star: float | None, path: Path) -> None:
    figure, (left, right) = plt.subplots(1, 2, figsize=(11, 3.8))
    for mode, color, label in (
        ("fluid", FLUID, "fluid dual-role"),
        ("separated", SEPARATED, "separated roles"),
    ):
        selected = [row for row in rows if row["mode"] == mode]
        selected.sort(key=lambda row: float(row["load_multiplier"]))
        loads = [float(row["load_multiplier"]) for row in selected]
        goodput = [float(row["delivered_goodput_mean"]) for row in selected]
        delivered = [float(row["delivered_percent_mean"]) for row in selected]
        left.plot(loads, goodput, marker="o", markersize=3, color=color, label=label)
        right.plot(loads, delivered, marker="o", markersize=3, color=color, label=label)
    if load_star is not None:
        for axis in (left, right):
            axis.axvline(load_star, color="black", linestyle=":", alpha=0.6)
    right.axhline(95.0, color="grey", linestyle="--", linewidth=1)
    left.set_xlabel("offered load (x nominal)")
    left.set_ylabel("delivered goodput (Mbps)")
    left.set_title("throughput vs load")
    right.set_xlabel("offered load (x nominal)")
    right.set_ylabel("delivered demand (%)")
    right.set_title("delivery vs load")
    left.grid(alpha=0.3)
    right.grid(alpha=0.3)
    left.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def plot_latency(rows, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(6.4, 3.8))
    for mode, color, label in (
        ("fluid", FLUID, "fluid dual-role"),
        ("separated", SEPARATED, "separated roles"),
    ):
        selected = [row for row in rows if row["mode"] == mode]
        selected.sort(key=lambda row: float(row["quantile"]))
        quantiles = [float(row["quantile"]) for row in selected]
        latency = [float(row["latency_ms"]) for row in selected]
        axis.step(latency, quantiles, where="post", color=color, label=label)
    axis.axhline(0.95, color="grey", linestyle="--", linewidth=1)
    axis.set_xlabel("one-way latency (ms)")
    axis.set_ylabel("fraction of delivered volume")
    axis.set_title("latency CDF (flash crowd)")
    axis.grid(alpha=0.3)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def plot_stability(rows, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(7.0, 3.6))
    for mode, color, label in (
        ("fluid", FLUID, "fluid dual-role"),
        ("separated", SEPARATED, "separated roles"),
    ):
        selected = [row for row in rows if row["mode"] == mode]
        selected.sort(key=lambda row: int(row["tick"]))
        ticks = [int(row["tick"]) for row in selected]
        delta = [float(row["mean_abs_delta"]) for row in selected]
        axis.plot(ticks, delta, color=color, label=label)
    axis.axvspan(*SPIKE, color="grey", alpha=0.12)
    axis.set_xlabel("tick (s)")
    axis.set_ylabel("mean |delta alpha| per control step")
    axis.set_title("role stability: adaptation, not churn")
    axis.grid(alpha=0.3)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def plot_ddos(rows, path: Path) -> None:
    targets = ("E1", "E2", "E3")
    figure, axis = plt.subplots(figsize=(6.4, 3.8))
    width = 0.35
    for offset, mode, color, label in (
        (-width / 2, "fluid", FLUID, "fluid dual-role"),
        (width / 2, "separated", SEPARATED, "separated roles"),
    ):
        means = []
        errors = []
        for target in targets:
            row = next(
                row
                for row in rows
                if row["mode"] == mode and row["metric"] == f"target_{target}_delivered_percent"
            )
            means.append(float(row["mean"]))
            errors.append(float(row["ci95"]))
        axis.bar(
            [index + offset for index in range(len(targets))],
            means,
            width,
            yerr=errors,
            color=color,
            label=label,
            capsize=3,
        )
    axis.set_xticks(range(len(targets)))
    axis.set_xticklabels([f"{target}\n(attacked)" if target == "E2" else target for target in targets])
    axis.set_ylabel("delivered demand (%)")
    axis.set_ylim(0, 105)
    axis.set_title("DDoS demand flood at E2: delivery by target")
    axis.grid(axis="y", alpha=0.3)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def _load_star(verdict_path: Path) -> float | None:
    if not verdict_path.exists():
        return None
    for row in _read(verdict_path):
        if row["test"] == "L_star" and row["value"]:
            return float(row["value"])
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("figures"))
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    alpha = _read(args.input_dir / "dual_role_alpha_trace.csv")
    sweep = _read(args.input_dir / "dual_role_sweep.csv")
    latency = _read(args.input_dir / "dual_role_latency_cdf.csv")
    stability = _read(args.input_dir / "dual_role_stability.csv")
    ddos = _read(args.input_dir / "dual_role_ddos.csv")
    load_star = _load_star(args.input_dir / "dual_role_verdict.csv")

    plot_alpha_with_node_levels(alpha, args.output_dir / "dual_role_alpha.png")
    plot_throughput(sweep, load_star, args.output_dir / "dual_role_throughput.png")
    plot_latency(latency, args.output_dir / "dual_role_latency_cdf.png")
    plot_stability(stability, args.output_dir / "dual_role_stability.png")
    plot_ddos(ddos, args.output_dir / "dual_role_ddos.png")
    print(f"Figures: {args.output_dir}/dual_role_*.png")


if __name__ == "__main__":
    main()
