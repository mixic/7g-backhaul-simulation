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

"""Run the M11 DDMR experiment (H14) over paired seeds.

Thresholds are frozen in ``docs/ddmr-predictions.md``:

1. Legitimate CDR during the DDoS window must be at least 15 *percentage
   points* above static T-NDN (the stricter reading of "15 % higher").
2. DDMR's CDR in that window must be at least 95 %.
3. The 4-D persistent-homology cost must be below the energy saved by the
   prevented legitimate losses (the anti-cheat energy clause).
4. No early collapse: the dimension must not return to 1 before the attack
   ends at t = 45 s.

The energy clause uses stipulated constants: 15 W per active CPU core and
0.02 J per prevented lost request.  The break-even joules per prevented loss is
reported, so the verdict can be read without adopting the stipulation.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Iterable, Sequence

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulation import ddmr_scenario as scenario  # noqa: E402

#: Pre-registered thresholds.
CDR_GAIN_LIMIT_POINTS = 15.0
CDR_TARGET_PERCENT = 95.0
BASELINES = ("nlsr", "fsr")
METRIC_KEYS = (
    ("cdr_window", "cdr_window_pct"),
    ("cdr_block0_window", "cdr_block0_window_pct"),
    ("cdr_overall", "cdr_overall_pct"),
    ("p95_window_ms", "p95_window_ms"),
)


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


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


def per_seed_rows(results: Sequence[scenario.SeedResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        run = result.runs["ddmr"]
        shock = [entry for entry in run.timeline if entry["dimension"] == 4]
        shock_b0 = [int(entry["b0"]) for entry in shock]
        shock_b1 = [int(entry["b1"]) for entry in shock]
        row: dict[str, object] = {
            "seed": result.seed,
            "attack_start_s": result.attack_window_s[0],
            "attack_end_s": result.attack_window_s[1],
            "prevented_drops": result.prevented_drops,
            "energy_saved_j": round(result.energy_saved_j, 3),
            "energy_cpu_j": round(result.energy_cpu_j, 4),
            "energy_ratio": round(result.energy_ratio, 4),
            "cdr_gain_points": round(result.cdr_gain_points, 3),
            "h14_supported": result.h14_supported,
            "early_collapse": run.early_collapse,
            "expansions": run.expansions,
            "collapses": run.collapses,
            "first_expansion_s": run.first_expansion_s,
            "last_shock_s": run.last_shock_s,
            "shock_epochs": len(shock),
            "shock_epochs_with_h1": sum(1 for value in shock_b1 if value > 0),
            "max_b1_shock": max(shock_b1) if shock_b1 else 0,
            "mean_b0_shock": round(sum(shock_b0) / len(shock_b0), 2)
            if shock_b0
            else 0.0,
            "tda_4d_ms": round(run.tda_4d_ms, 3),
            "tda_4d_calls": run.tda_4d_calls,
            "manifold_calls": run.manifold_calls,
        }
        for strategy in scenario.STRATEGIES:
            run = result.runs[strategy]
            for attribute, prefix in METRIC_KEYS:
                row[f"{prefix}_{strategy}"] = round(
                    getattr(run, attribute), 4
                )
        rows.append(row)
    return rows


def summary_rows(results: Sequence[scenario.SeedResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    labels = {
        "nlsr": "NLSR",
        "fsr": "FSR-NDN",
        "static": "Static T-NDN",
        "ddmr": "DDMR",
    }
    for strategy in scenario.STRATEGIES:
        cdr = [result.runs[strategy].cdr_window for result in results]
        block0 = [result.runs[strategy].cdr_block0_window for result in results]
        overall = [result.runs[strategy].cdr_overall for result in results]
        p95 = [result.runs[strategy].p95_window_ms for result in results]
        rows.append(
            {
                "strategy": labels[strategy],
                "cdr_window_mean_pct": round(mean(cdr), 3),
                "cdr_window_ci95_pct": round(ci95(cdr), 3),
                "cdr_block0_mean_pct": round(mean(block0), 3),
                "cdr_block0_ci95_pct": round(ci95(block0), 3),
                "cdr_overall_mean_pct": round(mean(overall), 3),
                "p95_window_mean_ms": round(mean(p95), 1),
                "p95_window_ci95_ms": round(ci95(p95), 1),
            }
        )
    return rows


def h14_rows(results: Sequence[scenario.SeedResult]) -> list[dict[str, object]]:
    ddmr = [result.runs["ddmr"] for result in results]
    static = [result.runs["static"] for result in results]
    gain = [result.cdr_gain_points for result in results]
    cdr = [run.cdr_window for run in ddmr]
    energy_cpu = [result.energy_cpu_j for result in results]
    energy_saved = [result.energy_saved_j for result in results]
    early = sum(1 for run in ddmr if run.early_collapse)

    rows: list[dict[str, object]] = [
        {
            "criterion": "CDR gain vs static T-NDN",
            "ddmr": round(mean(cdr), 3),
            "baseline": round(mean(run.cdr_window for run in static), 3),
            "delta": round(mean(gain), 3),
            "limit": f">= {CDR_GAIN_LIMIT_POINTS:.0f} points",
            "verdict": "PASS" if mean(gain) >= CDR_GAIN_LIMIT_POINTS else "FAIL",
        },
        {
            "criterion": "DDMR CDR during shock",
            "ddmr": round(mean(cdr), 3),
            "baseline": "—",
            "delta": "—",
            "limit": f">= {CDR_TARGET_PERCENT:.0f} %",
            "verdict": "PASS" if mean(cdr) >= CDR_TARGET_PERCENT else "FAIL",
        },
        {
            "criterion": "Energy: 4D TDA vs saved",
            "ddmr": round(mean(energy_cpu), 3),
            "baseline": round(mean(energy_saved), 3),
            "delta": round(mean(energy_cpu) / mean(energy_saved), 4)
            if mean(energy_saved) > 0
            else float("inf"),
            "limit": "< 1.0 (J CPU / J saved)",
            "verdict": "PASS" if mean(energy_cpu) < mean(energy_saved) else "FAIL",
        },
        {
            "criterion": "Early collapse before t=45 s",
            "ddmr": early,
            "baseline": "—",
            "delta": "—",
            "limit": "0 seeds",
            "verdict": "PASS" if early == 0 else "FAIL",
        },
    ]
    return rows


def write_dimension_timeline(
    result: scenario.SeedResult, output_dir: Path
) -> list[dict[str, object]]:
    rows = []
    for entry in result.runs["ddmr"].timeline:
        rows.append(
            {
                "time_s": entry["time_s"],
                "dimension": entry["dimension"],
                "anomaly": entry["anomaly"],
                "b0": entry["b0"],
                "b1": entry["b1"],
                "cpu_ms": entry["cpu_ms"],
            }
        )
    _write_csv(output_dir / "ddmr_dimension.csv", rows)
    return rows


def plot_dimension(rows: Sequence[dict[str, object]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    times = [float(row["time_s"]) for row in rows if int(row["dimension"]) > 0]
    dimensions = [int(row["dimension"]) for row in rows if int(row["dimension"]) > 0]
    b0 = [int(row["b0"]) for row in rows if int(row["dimension"]) > 0]
    b1 = [int(row["b1"]) for row in rows if int(row["dimension"]) > 0]
    if not times:
        return

    figure, axis = plt.subplots(figsize=(8.0, 4.2))
    axis.step(times, dimensions, where="post", color="#1f4e79", linewidth=2.0)
    axis.set_xlabel("simulation time (s)")
    axis.set_ylabel("filtration dimension", color="#1f4e79")
    axis.set_yticks([1, 4])
    axis.set_ylim(0.5, 4.5)
    axis.axvspan(30.0, 45.0, color="#c00000", alpha=0.12, label="DDoS shockwave")
    axis.grid(alpha=0.3)

    homology = axis.twinx()
    homology.plot(times, b0, color="#2e7d32", linewidth=1.2, label="b0 (components)")
    homology.plot(times, b1, color="#ed7d31", linewidth=1.2, label="b1 (loops)")
    homology.set_ylabel("Betti numbers at eps=0.25")

    lines = axis.get_legend_handles_labels()[0] + homology.get_legend_handles_labels()[0]
    labels = axis.get_legend_handles_labels()[1] + homology.get_legend_handles_labels()[1]
    axis.legend(lines, labels, loc="upper left", fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def run_all(
    output_dir: Path,
    seeds: int = scenario.SEEDS,
    base_seed: int = scenario.BASE_SEED,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = [scenario.run_seed(base_seed + offset) for offset in range(seeds)]

    per_seed = per_seed_rows(results)
    summary = summary_rows(results)
    h14 = h14_rows(results)
    timeline = write_dimension_timeline(results[0], output_dir)
    plot_dimension(timeline, output_dir / "ddmr_dimension.png")

    _write_csv(output_dir / "ddmr_per_seed.csv", per_seed)
    _write_csv(output_dir / "ddmr_summary.csv", summary)
    _write_csv(output_dir / "ddmr_h14.csv", h14)

    print("M11: DDMR versus static T-NDN, FSR-NDN and NLSR")
    print(
        f"  {scenario.NODE_COUNT} nodes, {scenario.BLOCKS} prefix blocks, "
        f"{seeds} paired seeds, literal DDoS {scenario.ATTACK_START_S:.0f}-"
        f"{scenario.ATTACK_END_S:.0f} s at {scenario.ATTACK_RPS:.0f} rps on block 0"
    )
    print(
        f"  legitimate CDR measured in the attack window; capacity "
        f"{scenario.CAPACITY_RPS:.0f} rps/instance\n"
    )

    header = f"  {'strategy':14s} {'CDR win %':>10s} {'block0 %':>10s} {'overall %':>10s} {'p95 ms':>9s}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for row in summary:
        print(
            f"  {row['strategy']:14s} {row['cdr_window_mean_pct']:10.2f} "
            f"{row['cdr_block0_mean_pct']:10.2f} {row['cdr_overall_mean_pct']:10.2f} "
            f"{row['p95_window_mean_ms']:9.1f}"
        )

    first = results[0]
    ddmr_run = first.runs["ddmr"]
    shock_epochs = [
        entry
        for entry in ddmr_run.timeline
        if entry["dimension"] == 4
    ]
    with_loops = sum(1 for entry in shock_epochs if int(entry["b1"]) > 0)
    print(
        "\n  seed 2026: first expansion "
        f"{ddmr_run.first_expansion_s:.2f} s, last shock "
        f"{ddmr_run.last_shock_s:.2f} s, expansions/collapses "
        f"{ddmr_run.expansions}/{ddmr_run.collapses}, "
        f"shock epochs with H1 loop {with_loops}/{len(shock_epochs)}"
    )
    print(
        f"  energy: 4D TDA {mean(r.energy_cpu_j for r in results):.2f} J, "
        f"saved {mean(r.energy_saved_j for r in results):.2f} J, "
        f"break-even {1000.0 * mean(r.energy_cpu_j for r in results) / max(1.0, mean(r.prevented_drops for r in results)):.2f} mJ per prevented loss"
    )

    print("\nH14 criteria:")
    for row in h14:
        print(
            f"  {row['criterion']:30s} DDMR={row['ddmr']:>10} "
            f"baseline={row['baseline']:>8} delta={row['delta']:>8} "
            f"limit={row['limit']:>24} -> {row['verdict']}"
        )
    verdict = "SUPPORTED" if all(row["verdict"] == "PASS" for row in h14) else "REFUTED"
    print(f"\nH14: {verdict}")
    print(f"CSVs: {output_dir}/ddmr_*.csv, plot: {output_dir}/ddmr_dimension.png")
    return {
        "results": results,
        "summary": summary,
        "h14": h14,
        "verdict": verdict,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    parser.add_argument("--seeds", type=int, default=scenario.SEEDS)
    parser.add_argument("--base-seed", type=int, default=scenario.BASE_SEED)
    args = parser.parse_args(argv)
    run_all(args.output_dir, args.seeds, args.base_seed)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
