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

"""Compare the continuous dual-role controller with the separated baseline.

The frozen claim is in ``docs/dual-role.md``.  This benchmark produces:

* ``dual_role_summary.csv`` — per scenario and mode, mean and 95 % interval;
* ``dual_role_per_seed.csv`` — paired-seed run-level metrics;
* ``dual_role_sweep.csv`` — delivered load sweep for throughput-vs-load;
* ``dual_role_verdict.csv`` — the frozen acceptance tests at ``L*``;
* ``dual_role_alpha_trace.csv`` — alpha per node and tick (flash crowd);
* ``dual_role_stability.csv`` — mean |delta alpha| per tick;
* ``dual_role_latency_cdf.csv`` — volume-weighted latency quantiles;
* ``dual_role_ddos.csv`` — delivery to attacked and unattacked targets.

Everything is conditional on the stipulated topology, demand and controller
parameters; none of the parameters are fitted to the results.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulation.dual_role import (  # noqa: E402
    NOMINAL_DEMAND_MBPS,
    SCENARIOS,
    simulate_run,
)

MODES = ("fluid", "separated")
SCENARIO_KEYS = ("steady", "flash_crowd", "ddos")
METRICS = (
    "delivered_goodput_mbps",
    "delivered_percent",
    "p95_latency_ms",
    "mean_alpha_abs_delta",
)
SWEEP = tuple(round(0.2 + 0.1 * index, 1) for index in range(19))
TARGETS = ("E1", "E2", "E3")
#: The DDoS scenario floods E2; E1 and E3 are the unattacked targets.
ATTACKED = "E2"
UNATTACKED = ("E1", "E3")


def _mean_ci(values: Sequence[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if array.size < 2:
        return float(array.mean()), 0.0
    return float(array.mean()), float(
        1.96 * array.std(ddof=1) / math.sqrt(array.size)
    )


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _run_rows(
    scenario: str,
    mode: str,
    seed: int,
    load_multiplier: float = 1.0,
) -> dict[str, object]:
    metrics = simulate_run(scenario, mode, seed, load_multiplier=load_multiplier)
    row: dict[str, object] = {
        "scenario": scenario,
        "mode": mode,
        "seed": seed,
        "load_multiplier": load_multiplier,
        "delivered_goodput_mbps": metrics.delivered_goodput_mbps,
        "delivered_percent": metrics.delivered_percent,
        "p95_latency_ms": metrics.p95_latency_ms,
        "mean_alpha_abs_delta": metrics.mean_alpha_abs_delta,
        "offered_mbps": sum(NOMINAL_DEMAND_MBPS.values()) * load_multiplier,
    }
    for target in TARGETS:
        row[f"target_{target}_delivered_percent"] = metrics.target_delivered_percent.get(
            target, 0.0
        )
    return row


def run_benchmark(
    output_dir: Path,
    replicates: int = 12,
    seed: int = 2026,
) -> dict[str, object]:
    if replicates < 2:
        raise ValueError("At least two replicates are required for an interval.")
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    seeds = [int(value) for value in rng.integers(0, 2**31 - 1, size=replicates)]

    per_seed: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []
    for scenario in SCENARIO_KEYS:
        for mode in MODES:
            runs = [_run_rows(scenario, mode, run_seed) for run_seed in seeds]
            per_seed.extend(runs)
            for metric in METRICS:
                mean, interval = _mean_ci([float(row[metric]) for row in runs])
                summary.append(
                    {
                        "scenario": scenario,
                        "mode": mode,
                        "metric": metric,
                        "replicates": replicates,
                        "mean": mean,
                        "ci95": interval,
                    }
                )
            for target in TARGETS:
                key = f"target_{target}_delivered_percent"
                mean, interval = _mean_ci([float(row[key]) for row in runs])
                summary.append(
                    {
                        "scenario": scenario,
                        "mode": mode,
                        "metric": key,
                        "replicates": replicates,
                        "mean": mean,
                        "ci95": interval,
                    }
                )

    sweep_rows: list[dict[str, object]] = []
    for multiplier in SWEEP:
        for mode in MODES:
            runs = [
                _run_rows("steady", mode, run_seed, load_multiplier=multiplier)
                for run_seed in seeds
            ]
            delivered = [float(row["delivered_percent"]) for row in runs]
            goodput = [float(row["delivered_goodput_mbps"]) for row in runs]
            p95 = [float(row["p95_latency_ms"]) for row in runs]
            sweep_rows.append(
                {
                    "load_multiplier": multiplier,
                    "mode": mode,
                    "replicates": replicates,
                    "delivered_percent_mean": float(np.mean(delivered)),
                    "delivered_percent_ci95": _mean_ci(delivered)[1],
                    "delivered_goodput_mean": float(np.mean(goodput)),
                    "delivered_goodput_ci95": _mean_ci(goodput)[1],
                    "p95_latency_mean": float(np.mean(p95)),
                    "p95_latency_ci95": _mean_ci(p95)[1],
                }
            )

    verdict_rows = _verdict(sweep_rows, seeds)

    alpha_rows, stability_rows, latency_rows = _plot_data(seeds, seed)
    ddos_rows = [row for row in summary if row["scenario"] == "ddos"]

    _write_csv(output_dir / "dual_role_per_seed.csv", per_seed)
    _write_csv(output_dir / "dual_role_summary.csv", summary)
    _write_csv(output_dir / "dual_role_sweep.csv", sweep_rows)
    _write_csv(output_dir / "dual_role_verdict.csv", verdict_rows)
    _write_csv(output_dir / "dual_role_alpha_trace.csv", alpha_rows)
    _write_csv(output_dir / "dual_role_stability.csv", stability_rows)
    _write_csv(output_dir / "dual_role_latency_cdf.csv", latency_rows)
    _write_csv(output_dir / "dual_role_ddos.csv", ddos_rows)

    _print_summary(summary, sweep_rows, verdict_rows)
    return {"summary": summary, "sweep": sweep_rows, "verdict": verdict_rows}


def _verdict(
    sweep_rows: Sequence[dict[str, object]], seeds: Sequence[int]
) -> list[dict[str, object]]:
    """Evaluate the frozen acceptance tests at the separated arm's L*."""
    by_key = {
        (float(row["load_multiplier"]), str(row["mode"])): row for row in sweep_rows
    }
    separated = [
        row
        for row in sweep_rows
        if row["mode"] == "separated"
        and float(row["delivered_percent_mean"]) < 95.0
    ]
    rows: list[dict[str, object]] = []
    if not separated:
        rows.append(
            {
                "test": "L_star",
                "value": "",
                "threshold": "",
                "passed": False,
                "detail": "separated arm never dropped below 95 % in the sweep",
            }
        )
        return rows
    load_star = min(float(row["load_multiplier"]) for row in separated)
    fluid = by_key[(load_star, "fluid")]
    sep = by_key[(load_star, "separated")]
    goodput_ratio = float(fluid["delivered_goodput_mean"]) / max(
        1e-9, float(sep["delivered_goodput_mean"])
    )
    p95_ratio = float(fluid["p95_latency_mean"]) / max(
        1e-9, float(sep["p95_latency_mean"])
    )
    rows.append(
        {
            "test": "L_star",
            "value": load_star,
            "threshold": 95.0,
            "passed": True,
            "detail": "lowest sweep load where separated delivery < 95 %",
        }
    )
    rows.append(
        {
            "test": "goodput_margin",
            "value": goodput_ratio,
            "threshold": 1.05,
            "passed": goodput_ratio >= 1.05,
            "detail": "fluid goodput / separated goodput at L*",
        }
    )
    rows.append(
        {
            "test": "latency_bound",
            "value": p95_ratio,
            "threshold": 1.5,
            "passed": p95_ratio <= 1.5,
            "detail": "fluid p95 / separated p95 at L*",
        }
    )
    return rows


def _plot_data(
    seeds: Sequence[int], rng_seed: int
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    representative_seed = seeds[0]
    alpha_rows: list[dict[str, object]] = []
    stability_rows: list[dict[str, object]] = []
    latency_rows: list[dict[str, object]] = []
    for mode in MODES:
        metrics = simulate_run("flash_crowd", mode, representative_seed)
        for node, trace in metrics.alpha_trace.items():
            if node == "O":
                continue
            for tick, alpha in enumerate(trace):
                alpha_rows.append(
                    {
                        "scenario": "flash_crowd",
                        "mode": mode,
                        "node": node,
                        "tick": tick,
                        "alpha": alpha,
                    }
                )
        for tick in range(len(metrics.alpha_trace["E1"])):
            rows = [
                abs(trace[tick] - trace[tick - 1])
                for node, trace in metrics.alpha_trace.items()
                if node != "O" and tick > 0
            ]
            stability_rows.append(
                {
                    "scenario": "flash_crowd",
                    "mode": mode,
                    "tick": tick,
                    "mean_abs_delta": float(np.mean(rows)) if rows else 0.0,
                }
            )
        pooled: list[tuple[float, float]] = []
        for run_seed in seeds:
            pooled.extend(
                simulate_run("flash_crowd", mode, run_seed).latency_weighted
            )
        values = np.asarray([value for value, _ in pooled], dtype=float)
        weights = np.asarray([weight for _, weight in pooled], dtype=float)
        order = np.argsort(values)
        values = values[order]
        weights = weights[order]
        cumulative = np.cumsum(weights)
        cumulative /= cumulative[-1]
        for quantile in np.linspace(0.01, 1.0, 100):
            index = int(np.searchsorted(cumulative, quantile))
            latency_rows.append(
                {
                    "scenario": "flash_crowd",
                    "mode": mode,
                    "quantile": float(quantile),
                    "latency_ms": float(values[min(index, len(values) - 1)]),
                }
            )
    return alpha_rows, stability_rows, latency_rows


def _print_summary(
    summary: Sequence[dict[str, object]],
    sweep: Sequence[dict[str, object]],
    verdict: Sequence[dict[str, object]],
) -> None:
    print("Dual-role comparison (mean over paired seeds):")
    for row in summary:
        if row["scenario"] == "ddos" and row["metric"].startswith("target_"):
            continue
        print(
            f"  {row['scenario']:12s} | {row['mode']:9s} | {row['metric']:26s} "
            f"{float(row['mean']):9.3f} +/- {float(row['ci95']):7.3f}"
        )
    print("\nDDoS delivery by target:")
    for row in summary:
        if row["scenario"] == "ddos" and row["metric"].startswith("target_"):
            print(
                f"  {row['mode']:9s} | {row['metric']:34s} "
                f"{float(row['mean']):6.2f} % +/- {float(row['ci95']):.2f}"
            )
    print("\nAcceptance tests at L*:")
    for row in verdict:
        print(
            f"  {row['test']:16s} value={row['value']} threshold={row['threshold']} "
            f"{'PASS' if row['passed'] else 'FAIL'}"
        )
    print("\nLoad sweep (delivered % / goodput / p95):")
    for row in sweep:
        print(
            f"  load={float(row['load_multiplier']):3.1f} | {row['mode']:9s} | "
            f"{float(row['delivered_percent_mean']):6.2f} % | "
            f"{float(row['delivered_goodput_mean']):7.2f} Mbps | "
            f"{float(row['p95_latency_mean']):6.2f} ms"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    parser.add_argument("--replicates", type=int, default=12)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    run_benchmark(args.output_dir, args.replicates, args.seed)
    print(f"\nCSVs: {args.output_dir}/dual_role_*.csv")


if __name__ == "__main__":
    main()
