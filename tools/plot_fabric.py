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

"""Generate the publication figures for the fabric and its comparisons.

Reads the committed CSVs (figures/*.csv) plus the ns-3 time series
(output/validation/fabric_summary.csv.timeseries.csv) and writes PNGs into
figures/. Every figure states, in its title, whether it is a model result or a
cross-validated measurement; the script does not editorialise beyond the data.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

COLORS = {
    "static": "#4C78A8",
    "turbo": "#F2A541",
    "dns": "#E45756",
    "gradient": "#3A9D78",
    "dht": "#B279A2",
    "immutable": "#54A24B",
    "service": "#F2A541",
    "external": "#E45756",
}


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _mean_band(values_by_key):
    keys = sorted(values_by_key)
    means = [float(np.mean(values_by_key[key])) for key in keys]
    stds = [float(np.std(values_by_key[key])) for key in keys]
    return keys, means, stds


def shockwave_figure(timeseries: Path, out: Path) -> None:
    rows = _read(timeseries)
    by_scenario = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_scenario[row["scenario"]][float(row["time_s"])].append(float(row["queue_mean_ms"]))

    figure, axis = plt.subplots(figsize=(8.5, 4.4), layout="constrained")
    for scenario, color in (("A_static", COLORS["static"]), ("A_turbo", COLORS["turbo"])):
        values = by_scenario[scenario]
        times = sorted(values)
        means = [float(np.mean(values[time])) for time in times]
        stds = [float(np.std(values[time])) for time in times]
        label = "static gradient" if scenario == "A_static" else "Turbo kinematic"
        axis.plot(times, means, color=color, linewidth=1.8, label=label)
        axis.fill_between(times, [m - s for m, s in zip(means, stds)],
                          [m + s for m, s in zip(means, stds)], color=color, alpha=0.18)
    axis.axvspan(50.0, 60.0, color="#888888", alpha=0.20, label="shockwave (12x)")
    axis.set_xlabel("Simulated time (s)")
    axis.set_ylabel("Mean queue delay (ms)")
    axis.set_title("H1: shockwave queue delay — Turbo does not flatten the spike (ns-3, 5 seeds)")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False, loc="upper left")
    figure.savefig(out, dpi=180)
    plt.close(figure)


def transition_figure(path: Path, out: Path) -> None:
    rows = _read(path)
    by_strategy = defaultdict(list)
    for row in rows:
        by_strategy[row["strategy"]].append((float(row["dns_ttl_s"]), float(row["p95_ms"])))
    figure, axis = plt.subplots(figsize=(7.6, 4.2), layout="constrained")
    for strategy, color in (("dns", COLORS["dns"]), ("gradient", COLORS["gradient"])):
        pairs = sorted(by_strategy[strategy])
        ttls = [f"{int(ttl)} s" for ttl, _ in pairs]
        values = [p95 for _, p95 in pairs]
        axis.bar([f"{ttl}\n{strategy}" for ttl in ttls], values,
                 color=color, label=strategy, alpha=0.85)
    axis.set_ylabel("p95 time to first success (ms)")
    axis.set_title("H2: role-transition observation floor (model)")
    axis.set_yscale("log")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False)
    figure.savefig(out, dpi=180)
    plt.close(figure)


def latency_figure(path: Path, out: Path) -> None:
    rows = _read(path)
    figure, axis = plt.subplots(figsize=(7.6, 4.2), layout="constrained")
    strategies = [row["strategy"] for row in rows]
    x = np.arange(len(strategies))
    for offset, (percentile, color) in enumerate((("p50_ms", "#54A24B"), ("p95_ms", "#F2A541"), ("p99_ms", "#E45756"))):
        values = [float(row[percentile]) for row in rows]
        axis.bar(x + 0.25 * (offset - 1), values, 0.25, color=color,
                 label=percentile.replace("_ms", ""))
    axis.set_xticks(x, [s.replace(" ", "\n") for s in strategies], fontsize=8)
    axis.set_ylabel("Latency (ms)")
    axis.set_title("Name-fabric latency distributions (model)")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False)
    figure.savefig(out, dpi=180)
    plt.close(figure)


def poisoning_figure(path: Path, out: Path) -> None:
    rows = _read(path)
    figure, axis = plt.subplots(figsize=(7.6, 4.2), layout="constrained")
    labels = []
    values = []
    errors = []
    color_map = {"immutable": COLORS["immutable"], "service": COLORS["service"], "external": COLORS["external"]}
    for row in rows:
        labels.append(f"{row['name_class']}\n{row['variant']}")
        values.append(float(row["acceptance_percent"]))
        errors.append(float(row["ci95_percent"]))
        color = color_map[row["name_class"]]
    positions = np.arange(len(rows))
    axis.bar(positions, values, yerr=errors, capsize=3, color=[
        color_map[row["name_class"]] for row in rows
    ], alpha=0.85)
    axis.set_xticks(positions, labels, fontsize=7, rotation=20, ha="right")
    axis.set_ylabel("Forgery acceptance (%)")
    axis.set_title("Name-fabric poisoning by name class (model)")
    axis.grid(axis="y", alpha=0.25)
    figure.savefig(out, dpi=180)
    plt.close(figure)


def flooding_figure(path: Path, out: Path) -> None:
    rows = _read(path)
    figure, axis = plt.subplots(figsize=(7.6, 4.2), layout="constrained")
    rates = [float(row["offered_rps"]) for row in rows]
    dns = [float(row["dns_failure_percent"]) for row in rows]
    pit = [float(row["pit_failure_percent"]) for row in rows]
    axis.plot(rates, dns, "-o", color=COLORS["dns"], label="DNS resolver")
    axis.plot(rates, pit, "-s", color=COLORS["gradient"], label="pending table")
    axis.set_xscale("log")
    axis.set_xlabel("Offered load (requests/s)")
    axis.set_ylabel("Failure rate (%)")
    axis.set_title("Flooding: resolver versus pending-request table (model)")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False)
    figure.savefig(out, dpi=180)
    plt.close(figure)


def role_fluid_figure(path: Path, out: Path) -> None:
    rows = _read(path)
    scenarios = sorted({row["scenario"] for row in rows})
    policies = sorted({row["policy"] for row in rows})
    figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.0), layout="constrained")
    x = np.arange(len(scenarios))
    width = 0.16
    for metric, axis, note in (
        ("delivered_percent", axes[0], "higher is better"),
        ("total_cost_usd", axes[1], "lower is better"),
    ):
        for index, policy in enumerate(policies):
            values = []
            for scenario in scenarios:
                match = next(row for row in rows if row["scenario"] == scenario and row["policy"] == policy)
                values.append(float(match[metric]))
            axis.bar(x + (index - 2) * width, values, width, label=policy)
        axis.set_xticks(x, [s.replace("_", "\n") for s in scenarios], fontsize=8)
        axis.set_ylabel(metric.replace("_", " "))
        axis.set_title(f"{metric.replace('_', ' ')} ({note})")
        axis.grid(axis="y", alpha=0.25)
    axes[0].legend(frameon=False, fontsize=7, loc="lower left")
    figure.suptitle("Role-fluid controllers (model)")
    figure.savefig(out, dpi=180)
    plt.close(figure)


def rfmp_figure(path: Path, out: Path) -> None:
    rows = _read(path)
    figure, axis = plt.subplots(figsize=(7.6, 4.2), layout="constrained")
    metrics = sorted({row["metric"] for row in rows})
    ns3 = [float(next(row for row in rows if row["metric"] == m)["ns3_mean"]) for m in metrics]
    py = [float(next(row for row in rows if row["metric"] == m)["python_mean"]) for m in metrics]
    x = np.arange(len(metrics))
    axis.bar(x - 0.2, ns3, 0.4, color="#4C78A8", label="ns-3.49")
    axis.bar(x + 0.2, py, 0.4, color="#3A9D78", label="Python reference")
    axis.set_xticks(x, [m.replace("_", "\n") for m in metrics], fontsize=7)
    axis.set_ylabel("Value")
    axis.set_title("RFMP role transition: ns-3 versus Python (cross-validated)")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False)
    figure.savefig(out, dpi=180)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("figures"))
    parser.add_argument("--timeseries", type=Path,
                        default=Path("output/validation/fabric_summary.csv.timeseries.csv"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.timeseries.is_file():
        shockwave_figure(args.timeseries, args.out_dir / "fabric_shockwave.png")
        print("fabric_shockwave.png")
    for name, function in (
        ("name_fabric_transition.csv", transition_figure),
        ("name_fabric_latency.csv", latency_figure),
        ("name_fabric_poisoning.csv", poisoning_figure),
        ("name_fabric_flooding.csv", flooding_figure),
    ):
        path = args.out_dir / name
        if path.is_file():
            function(path, args.out_dir / name.replace(".csv", ".png"))
            print(name.replace(".csv", ".png"))
    if (args.out_dir / "role_fluid_summary.csv").is_file():
        role_fluid_figure(args.out_dir / "role_fluid_summary.csv", args.out_dir / "role_fluid_comparison.png")
        print("role_fluid_comparison.png")
    if (args.out_dir / "rfmp_comparison.csv").is_file():
        rfmp_figure(args.out_dir / "rfmp_comparison.csv", args.out_dir / "rfmp_validation.png")
        print("rfmp_validation.png")


if __name__ == "__main__":
    main()
