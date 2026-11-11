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

"""Run the CRMR experiment (H15): flapping and sustained DDoS regimes.

The 30 evaluation seeds are 2030–2059; the pilot seed 2026 is excluded and was
used only to freeze the thresholds in ``docs/crmr-predictions.md``.  A burst
duration sweep (1–15 s, 10 seeds each) locates where the rotation stops paying
for itself.

Outputs: CSVs and PDF/PNG figures under the output directory.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulation import crmr_scenario as scenario  # noqa: E402
from simulation import ddmr  # noqa: E402

#: Evaluation seeds exclude the pilot seed 2026.
BASE_SEED = 2030
SEEDS = 30
SWEEP_LENGTHS = (1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 15.0)
SWEEP_SEEDS = 10
SWEEP_BASE_SEED = 3000

STYLE = {
    "static": ("Static T-NDN", "#777777"),
    "ddmr": ("DDMR (discrete)", "#1f4e9c"),
    "crmr": ("CRMR (continuous)", "#c0392b"),
}


def mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items)


def ci95(values: Iterable[float]) -> float:
    items = list(values)
    if len(items) < 2:
        return 0.0
    centre = mean(items)
    variance = sum((value - centre) ** 2 for value in items) / (len(items) - 1)
    return 1.96 * math.sqrt(variance / len(items))


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def collect(scenario_name: str) -> list[scenario.SeedResult]:
    return [
        scenario.run_seed(BASE_SEED + offset, scenario_name)
        for offset in range(SEEDS)
    ]


def collect_sweep() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for length in SWEEP_LENGTHS:
        windows = [(30.0, 30.0 + length)]
        for offset in range(SWEEP_SEEDS):
            seed = SWEEP_BASE_SEED + offset
            result = scenario.run_seed(seed, windows)
            for strategy in scenario.STRATEGIES:
                run = result.runs[strategy]
                rows.append(
                    {
                        "burst_s": length,
                        "seed": seed,
                        "strategy": strategy,
                        "cdr_block0": round(run.cdr_block0, 3),
                        "cdr_overall": round(run.cdr_overall, 3),
                        "peak_churn": round(run.peak_churn, 4),
                    }
                )
    return rows


def per_seed_rows(results_by_scenario) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scenario_name, results in results_by_scenario.items():
        for result in results:
            for strategy in scenario.STRATEGIES:
                run = result.runs[strategy]
                rows.append(
                    {
                        "scenario": scenario_name,
                        "seed": result.seed,
                        "strategy": strategy,
                        "cdr_mean": round(run.cdr_mean, 3),
                        "cdr_block0": round(run.cdr_block0, 3),
                        "cdr_overall": round(run.cdr_overall, 3),
                        "cdr_std": round(run.cdr_std, 3),
                        "p95_ms": round(run.p95_ms, 2),
                        "peak_churn": round(run.peak_churn, 4),
                        "tv_churn": round(run.tv_churn, 4),
                        "switches": run.switches,
                        "cpu_4d_ms": round(run.cpu_4d_ms, 3),
                        "calls_4d": run.calls_4d,
                        "legit_window": run.legit_window,
                        "delivered_window": run.delivered_window,
                    }
                )
    return rows


def cycle_rows(results_by_scenario) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scenario_name, results in results_by_scenario.items():
        for result in results:
            for strategy in scenario.STRATEGIES:
                for index, cdr in enumerate(result.runs[strategy].cdr_cycles):
                    rows.append(
                        {
                            "scenario": scenario_name,
                            "seed": result.seed,
                            "strategy": strategy,
                            "cycle": index + 1,
                            "cdr": round(cdr, 3),
                        }
                    )
    return rows


def energy_rows(results_by_scenario) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scenario_name, results in results_by_scenario.items():
        for result in results:
            rows.append(
                {
                    "scenario": scenario_name,
                    "seed": result.seed,
                    "prevented_drops": result.prevented_drops,
                    "energy_saved_j": round(result.energy_saved_j, 4),
                    "energy_cpu_j": round(result.energy_cpu_j, 4),
                    "energy_ratio": round(result.energy_ratio, 4),
                }
            )
    return rows


def summary_rows(results_by_scenario) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scenario_name, results in results_by_scenario.items():
        for strategy in scenario.STRATEGIES:
            runs = [result.runs[strategy] for result in results]
            rows.append(
                {
                    "scenario": scenario_name,
                    "strategy": strategy,
                    "cdr_mean": round(mean(run.cdr_mean for run in runs), 3),
                    "cdr_mean_ci95": round(ci95(run.cdr_mean for run in runs), 3),
                    "cdr_block0": round(mean(run.cdr_block0 for run in runs), 3),
                    "cdr_block0_ci95": round(ci95(run.cdr_block0 for run in runs), 3),
                    "cdr_overall": round(mean(run.cdr_overall for run in runs), 3),
                    "cdr_std": round(mean(run.cdr_std for run in runs), 3),
                    "p95_ms": round(mean(run.p95_ms for run in runs), 2),
                    "peak_churn": round(mean(run.peak_churn for run in runs), 4),
                    "tv_churn": round(mean(run.tv_churn for run in runs), 4),
                    "switches": round(mean(run.switches for run in runs), 2),
                    "cpu_4d_ms": round(mean(run.cpu_4d_ms for run in runs), 2),
                }
            )
    return rows


def h15_rows(results_by_scenario) -> list[dict[str, object]]:
    flapping = results_by_scenario["flapping"]
    sustained = results_by_scenario["sustained"]
    rows: list[dict[str, object]] = []

    churn_peak = {
        strategy: mean(result.runs[strategy].peak_churn for result in flapping)
        for strategy in scenario.STRATEGIES
    }
    rows.append(
        {
            "criterion": "Peak reconfiguration (flapping)",
            "crmr": round(churn_peak["crmr"], 4),
            "ddmr": round(churn_peak["ddmr"], 4),
            "value": round(churn_peak["crmr"] / churn_peak["ddmr"], 4),
            "limit": "<= 0.50 of DDMR",
            "verdict": "PASS" if churn_peak["crmr"] <= 0.5 * churn_peak["ddmr"] else "FAIL",
        }
    )

    sustained_gap = mean(
        result.runs["ddmr"].cdr_mean - result.runs["crmr"].cdr_mean
        for result in sustained
    )
    sustained_gain = mean(
        result.runs["crmr"].cdr_mean - result.runs["static"].cdr_mean
        for result in sustained
    )
    rows.append(
        {
            "criterion": "Sustained CDR gap vs DDMR",
            "crmr": round(mean(r.cdr_mean for r in (x.runs["crmr"] for x in sustained)), 3),
            "ddmr": round(mean(r.cdr_mean for r in (x.runs["ddmr"] for x in sustained)), 3),
            "value": round(sustained_gap, 3),
            "limit": "<= 5 points",
            "verdict": "PASS" if sustained_gap <= 5.0 else "FAIL",
        }
    )
    rows.append(
        {
            "criterion": "Sustained CDR gain vs static",
            "crmr": round(
                mean(r.cdr_mean for r in (x.runs["crmr"] for x in sustained)), 3
            ),
            "ddmr": round(
                mean(r.cdr_mean for r in (x.runs["static"] for x in sustained)), 3
            ),
            "value": round(sustained_gain, 3),
            "limit": ">= 15 points",
            "verdict": "PASS" if sustained_gain >= 15.0 else "FAIL",
        }
    )

    flapping_gap = mean(
        result.runs["ddmr"].cdr_mean - result.runs["crmr"].cdr_mean
        for result in flapping
    )
    rows.append(
        {
            "criterion": "Flapping CDR gap vs DDMR (reported)",
            "crmr": round(mean(r.cdr_mean for r in (x.runs["crmr"] for x in flapping)), 3),
            "ddmr": round(mean(r.cdr_mean for r in (x.runs["ddmr"] for x in flapping)), 3),
            "value": round(flapping_gap, 3),
            "limit": "measured boundary",
            "verdict": "REPORTED",
        }
    )

    energy_cpu = mean(result.energy_cpu_j for result in sustained)
    energy_saved = mean(result.energy_saved_j for result in sustained)
    rows.append(
        {
            "criterion": "Energy (sustained)",
            "crmr": round(energy_cpu, 3),
            "ddmr": round(energy_saved, 3),
            "value": round(energy_cpu / energy_saved, 4) if energy_saved else float("inf"),
            "limit": "< 1.0",
            "verdict": "PASS" if energy_cpu < energy_saved else "FAIL",
        }
    )
    return rows


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _figure_style() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 9.5,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": 150,
        }
    )


def figure_phasor(output_dir: Path) -> None:
    _figure_style()
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(3.6, 3.3))
    axis.axhline(0.0, color="0.7", linewidth=0.8)
    axis.axvline(0.0, color="0.7", linewidth=0.8)
    theta = np.linspace(0.0, math.pi / 2.0, 200)
    axis.plot(np.cos(theta), np.sin(theta), color="0.5", linewidth=1.2)
    angle = math.radians(52.0)
    axis.annotate(
        "",
        xy=(math.cos(angle), math.sin(angle)),
        xytext=(0.0, 0.0),
        arrowprops=dict(arrowstyle="->", color="#c0392b", linewidth=2.0),
    )
    axis.annotate(
        "",
        xy=(0.32, 0.0),
        xytext=(0.0, 0.0),
        arrowprops=dict(arrowstyle="->", color="#1f4e9c", linewidth=1.6),
    )
    axis.annotate(
        "",
        xy=(0.62 * math.cos(angle), 0.62 * math.sin(angle)),
        xytext=(0.62, 0.0),
        arrowprops=dict(arrowstyle="->", color="#2e7d32", linewidth=1.2, linestyle="--"),
    )
    axis.text(0.64, 0.04, r"$R\sin\theta$", color="#2e7d32", fontsize=8)
    axis.text(0.14, -0.11, r"$R\cos\theta$", color="#1f4e9c", fontsize=8)
    axis.text(0.66, 0.46, r"$\psi=R e^{i\theta}$", color="#c0392b", fontsize=10)
    arc = np.linspace(0.0, angle, 60)
    axis.plot(0.22 * np.cos(arc), 0.22 * np.sin(arc), color="0.3", linewidth=0.8)
    axis.text(0.24, 0.10, r"$\theta$", fontsize=9)
    axis.text(1.02, 0.06, "prefix (real)", fontsize=8, va="bottom")
    axis.text(0.05, 1.02, "defence (imaginary)", fontsize=8, rotation=90, va="top")
    axis.set_xlim(-0.12, 1.18)
    axis.set_ylim(-0.12, 1.18)
    axis.set_aspect("equal")
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in ("left", "bottom", "top", "right"):
        axis.spines[spine].set_visible(False)
    figure.tight_layout()
    figure.savefig(output_dir / "crmr_phasor.pdf")
    figure.savefig(output_dir / "crmr_phasor.png", dpi=180)
    plt.close(figure)


def figure_trajectory(result: scenario.SeedResult, output_dir: Path) -> None:
    _figure_style()
    import matplotlib.pyplot as plt

    crmr_timeline = result.runs["crmr"].timeline
    ddmr_timeline = result.runs["ddmr"].timeline
    times = [float(entry["time_s"]) for entry in crmr_timeline]
    theta = [float(entry["state"]) for entry in crmr_timeline]
    share = [float(entry["fraction"]) for entry in crmr_timeline]
    ddmr_share = [float(entry["fraction"]) for entry in ddmr_timeline]

    figure, axes = plt.subplots(2, 1, figsize=(6.2, 3.6), sharex=True)
    for axis in axes:
        for start, end in scenario.SCENARIO_WINDOWS["flapping"]:
            axis.axvspan(start, end, color="#c0392b", alpha=0.08, linewidth=0)
    axes[0].plot(times, theta, color="#c0392b", linewidth=1.4)
    axes[0].set_ylabel(r"phase $\theta$ (rad)")
    axes[0].set_ylim(0.0, math.pi / 2.0 + 0.08)
    axes[0].axhline(math.pi / 4.0, color="0.6", linewidth=0.8, linestyle=":")
    axes[0].text(0.6, math.pi / 4.0 + 0.04, "gate", fontsize=7, color="0.4")
    axes[1].step(
        [float(entry["time_s"]) for entry in ddmr_timeline],
        ddmr_share,
        where="post",
        color="#1f4e9c",
        linewidth=1.2,
        label="DDMR share",
    )
    axes[1].plot(times, share, color="#c0392b", linewidth=1.4, label=r"CRMR $\sin^2\theta$")
    axes[1].set_ylabel("legitimate share\nrouted to replica")
    axes[1].set_xlabel("simulation time (s)")
    axes[1].set_ylim(-0.03, 1.05)
    axes[1].legend(loc="lower right", frameon=False)
    axes[1].set_xlim(28.0, 48.0)
    figure.tight_layout()
    figure.savefig(output_dir / "crmr_trajectory.pdf")
    figure.savefig(output_dir / "crmr_trajectory.png", dpi=180)
    plt.close(figure)


def figure_cycles(results, output_dir: Path) -> None:
    _figure_style()
    import matplotlib.pyplot as plt

    cycles = len(results[0].runs["crmr"].cdr_cycles)
    figure, axis = plt.subplots(figsize=(4.6, 2.9))
    width = 0.26
    positions = np.arange(cycles)
    for offset, strategy in enumerate(scenario.STRATEGIES):
        label, colour = STYLE[strategy]
        values = [
            mean(result.runs[strategy].cdr_cycles[index] for result in results)
            for index in range(cycles)
        ]
        errors = [
            ci95(result.runs[strategy].cdr_cycles[index] for result in results)
            for index in range(cycles)
        ]
        axis.bar(
            positions + (offset - 1) * width,
            values,
            width,
            yerr=errors,
            capsize=2,
            color=colour,
            label=label,
            alpha=0.9,
        )
    axis.set_xticks(positions)
    axis.set_xticklabels([f"burst {index + 1}" for index in range(cycles)])
    axis.set_ylabel("legitimate CDR (%)")
    axis.set_ylim(0.0, 105.0)
    axis.legend(loc="lower right", frameon=False, ncol=1)
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(output_dir / "crmr_cycles.pdf")
    figure.savefig(output_dir / "crmr_cycles.png", dpi=180)
    plt.close(figure)


def figure_sweep(sweep_rows, output_dir: Path) -> None:
    _figure_style()
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(4.6, 3.0))
    for strategy in scenario.STRATEGIES:
        label, colour = STYLE[strategy]
        values = []
        errors = []
        for length in SWEEP_LENGTHS:
            points = [
                float(row["cdr_block0"])
                for row in sweep_rows
                if row["strategy"] == strategy and float(row["burst_s"]) == length
            ]
            values.append(mean(points))
            errors.append(ci95(points))
        axis.errorbar(
            SWEEP_LENGTHS,
            values,
            yerr=errors,
            marker="o",
            markersize=3.5,
            linewidth=1.3,
            capsize=2,
            color=colour,
            label=label,
        )
    axis.set_xlabel("DDoS burst duration (s)")
    axis.set_ylabel("attacked-prefix CDR (%)")
    axis.set_ylim(0.0, 105.0)
    axis.set_xscale("log")
    axis.set_xticks(list(SWEEP_LENGTHS))
    axis.set_xticklabels([f"{int(value)}" for value in SWEEP_LENGTHS])
    axis.grid(alpha=0.25)
    axis.legend(loc="lower right", frameon=False)
    figure.tight_layout()
    figure.savefig(output_dir / "crmr_sweep.pdf")
    figure.savefig(output_dir / "crmr_sweep.png", dpi=180)
    plt.close(figure)


def figure_betti(result: scenario.SeedResult, output_dir: Path) -> None:
    _figure_style()
    import matplotlib.pyplot as plt

    timeline = result.runs["crmr"].timeline
    times = [float(entry["time_s"]) for entry in timeline]
    b0 = [int(entry["b0"]) for entry in timeline]
    b1 = [int(entry["b1"]) for entry in timeline]
    figure, axis = plt.subplots(figsize=(4.6, 2.7))
    axis.plot(times, b0, color="#1f4e9c", linewidth=1.1, label=r"$\beta_0$ (components)")
    axis.plot(times, b1, color="#e67e22", linewidth=1.1, label=r"$\beta_1$ (loops)")
    for start, end in scenario.SCENARIO_WINDOWS["sustained"]:
        axis.axvspan(start, end, color="#c0392b", alpha=0.08, linewidth=0)
    axis.set_xlabel("simulation time (s)")
    axis.set_ylabel("Betti number at $\\varepsilon(\\theta)$")
    axis.legend(loc="upper left", frameon=False, ncol=2)
    axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(output_dir / "crmr_betti.pdf")
    figure.savefig(output_dir / "crmr_betti.png", dpi=180)
    plt.close(figure)


def figure_energy(results_by_scenario, output_dir: Path) -> None:
    _figure_style()
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(3.8, 2.8))
    labels = ["flapping", "sustained"]
    positions = np.arange(len(labels))
    width = 0.34
    cpu = [
        mean(result.energy_cpu_j for result in results_by_scenario[name])
        for name in labels
    ]
    saved = [
        mean(result.energy_saved_j for result in results_by_scenario[name])
        for name in labels
    ]
    axis.bar(
        positions - width / 2,
        cpu,
        width,
        color="#1f4e9c",
        label="4-D homology (J)",
    )
    axis.bar(
        positions + width / 2,
        saved,
        width,
        color="#2e7d32",
        label="prevented-loss energy (J)",
    )
    axis.set_xticks(positions)
    axis.set_xticklabels(["flapping", "sustained"])
    axis.set_ylabel("energy (J)")
    axis.legend(frameon=False, fontsize=7.5)
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(output_dir / "crmr_energy.pdf")
    figure.savefig(output_dir / "crmr_energy.png", dpi=180)
    plt.close(figure)


def run_all(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results_by_scenario = {
        "flapping": collect("flapping"),
        "sustained": collect("sustained"),
    }
    sweep = collect_sweep()

    per_seed = per_seed_rows(results_by_scenario)
    cycles = cycle_rows(results_by_scenario)
    energy = energy_rows(results_by_scenario)
    summary = summary_rows(results_by_scenario)
    h15 = h15_rows(results_by_scenario)

    _write_csv(output_dir / "crmr_per_seed.csv", per_seed)
    _write_csv(output_dir / "crmr_cycles.csv", cycles)
    _write_csv(output_dir / "crmr_energy.csv", energy)
    _write_csv(output_dir / "crmr_summary.csv", summary)
    _write_csv(output_dir / "crmr_h15.csv", h15)
    _write_csv(output_dir / "crmr_sweep.csv", sweep)

    flapping = results_by_scenario["flapping"]
    sustained = results_by_scenario["sustained"]
    figure_phasor(output_dir)
    figure_trajectory(flapping[0], output_dir)
    figure_cycles(flapping, output_dir)
    figure_sweep(sweep, output_dir)
    figure_betti(sustained[0], output_dir)
    figure_energy(results_by_scenario, output_dir)

    print("CRMR (H15): continuous phase rotation vs discrete DDMR")
    print(f"  evaluation seeds {BASE_SEED}-{BASE_SEED + SEEDS - 1} (pilot 2026 excluded)")
    print("  scenario            strategy      CDR%   block0%   p95ms  peak churn  switches")
    for row in summary:
        print(
            f"  {row['scenario']:12s} {row['strategy']:10s} "
            f"{row['cdr_mean']:7.2f} {row['cdr_block0']:8.2f} "
            f"{row['p95_ms']:7.1f} {row['peak_churn']:10.3f} {row['switches']:9.2f}"
        )

    print("\nH15 criteria:")
    for row in h15:
        print(
            f"  {row['criterion']:42s} CRM={row['crmr']:>9} DDMR/static={row['ddmr']:>9} "
            f"value={row['value']:>8} limit={row['limit']:>20} -> {row['verdict']}"
        )
    verdicts = [row["verdict"] for row in h15 if row["verdict"] in ("PASS", "FAIL")]
    verdict = "SUPPORTED" if all(value == "PASS" for value in verdicts) else "PARTIALLY REFUTED"
    print(f"\nH15: {verdict}")
    print(f"CSVs and figures: {output_dir}/crmr_*")
    return {
        "results": results_by_scenario,
        "summary": summary,
        "h15": h15,
        "verdict": verdict,
        "sweep": sweep,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args(argv)
    run_all(args.output_dir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
