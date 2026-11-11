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

"""Run the M10 T-NDN experiment (H13) over paired seeds.

Thresholds are fixed before the run and mirrored in
``docs/tndn-predictions.md``:

1. FIB size: T-NDN at least 20 % smaller than *every* baseline
   (ratio <= 0.80 on the 30-seed mean).
2. Reconvergence: T-NDN at least 20 % faster than *every* baseline
   (ratio <= 0.80 on the 30-seed mean).
3. Content delivery: T-NDN CDR >= 95 % of the NLSR CDR.
4. TDA overhead: the measured persistent-homology cost must be smaller than the
   convergence time it saves against the fastest baseline; otherwise H13 is
   refuted, however good the other numbers look.

The run is paired: each seed produces one network, one request stream, one
failed link, and all four strategies are evaluated on them.
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

from simulation import ndn_scenario as scenario  # noqa: E402
from simulation import nlsr_baseline as nlsr  # noqa: E402
from simulation import topology  # noqa: E402
from simulation.ndn_network import PhysicalNetwork  # noqa: E402

#: Pre-registered H13 thresholds.
FIB_RATIO_LIMIT = 0.80
CONVERGENCE_RATIO_LIMIT = 0.80
CDR_RATIO_LIMIT = 0.95
BASELINES = ("nlsr", "fsr", "fisheye")
STRATEGY_LABELS = {
    "nlsr": "NLSR",
    "fsr": "FSR-NDN",
    "fisheye": "Fisheye-Overlay",
    "tndn": "T-NDN",
}
METRICS = (
    ("fib_mean", "fib_mean"),
    ("convergence_p99_s", "conv_s"),
    ("cdr_percent", "cdr_pct"),
    ("p95_latency_ms", "p95_ms"),
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


def ratio_series(results: Sequence[scenario.SeedResult], metric: str, baseline: str) -> list[float]:
    ratios = []
    for result in results:
        values = getattr(result, metric)
        ratios.append(values["tndn"] / values[baseline])
    return ratios


def paired_summary(results: Sequence[scenario.SeedResult]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for metric, _ in METRICS:
        summary[metric] = {}
        for strategy in scenario.STRATEGIES:
            values = [getattr(result, metric)[strategy] for result in results]
            summary[metric][strategy] = mean(values)
            summary[metric][f"{strategy}_ci95"] = ci95(values)
    return summary


def per_seed_rows(results: Sequence[scenario.SeedResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        row: dict[str, object] = {
            "seed": result.seed,
            "failure_link": result.failure_link,
            "requests": result.requests,
            "affected_fraction": round(result.affected_fraction, 4),
            "tda_ms": round(result.tda_ms, 3),
            "tda_core_ms": round(result.tda_core_ms, 3),
        }
        for metric, prefix in METRICS:
            for strategy in scenario.STRATEGIES:
                row[f"{prefix}_{strategy}"] = round(
                    getattr(result, metric)[strategy], 4
                )
        rows.append(row)
    return rows


def summary_rows(summary: dict[str, dict[str, float]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for strategy in ("nlsr", "fsr", "fisheye", "tndn"):
        rows.append(
            {
                "strategy": STRATEGY_LABELS[strategy],
                "fib_mean": round(summary["fib_mean"][strategy], 1),
                "fib_ci95": round(summary["fib_mean"][f"{strategy}_ci95"], 1),
                "conv_mean_s": round(summary["convergence_p99_s"][strategy], 4),
                "conv_ci95_s": round(
                    summary["convergence_p99_s"][f"{strategy}_ci95"], 4
                ),
                "cdr_mean_pct": round(summary["cdr_percent"][strategy], 4),
                "cdr_ci95_pct": round(summary["cdr_percent"][f"{strategy}_ci95"], 4),
                "p95_mean_ms": round(summary["p95_latency_ms"][strategy], 2),
                "p95_ci95_ms": round(
                    summary["p95_latency_ms"][f"{strategy}_ci95"], 2
                ),
            }
        )
    return rows


def h13_rows(results: Sequence[scenario.SeedResult]) -> list[dict[str, object]]:
    summary = paired_summary(results)
    rows: list[dict[str, object]] = []

    tndn_fib = summary["fib_mean"]["tndn"]
    for baseline in BASELINES:
        baseline_fib = summary["fib_mean"][baseline]
        ratio = tndn_fib / baseline_fib
        rows.append(
            {
                "criterion": f"FIB vs {STRATEGY_LABELS[baseline]}",
                "tndn": round(tndn_fib, 1),
                "baseline": round(baseline_fib, 1),
                "ratio": round(ratio, 4),
                "limit": FIB_RATIO_LIMIT,
                "verdict": "PASS" if ratio <= FIB_RATIO_LIMIT else "FAIL",
            }
        )

    tndn_conv = summary["convergence_p99_s"]["tndn"]
    savings_s: list[float] = []
    for baseline in BASELINES:
        baseline_conv = summary["convergence_p99_s"][baseline]
        ratio = tndn_conv / baseline_conv if baseline_conv else 0.0
        savings_s.append(baseline_conv - tndn_conv)
        rows.append(
            {
                "criterion": f"convergence vs {STRATEGY_LABELS[baseline]}",
                "tndn": round(tndn_conv, 4),
                "baseline": round(baseline_conv, 4),
                "ratio": round(ratio, 4),
                "limit": CONVERGENCE_RATIO_LIMIT,
                "verdict": "PASS" if ratio <= CONVERGENCE_RATIO_LIMIT else "FAIL",
            }
        )

    tndn_cdr = summary["cdr_percent"]["tndn"]
    nlsr_cdr = summary["cdr_percent"]["nlsr"]
    cdr_ratio = tndn_cdr / nlsr_cdr if nlsr_cdr else 0.0
    rows.append(
        {
            "criterion": "CDR vs NLSR",
            "tndn": round(tndn_cdr, 4),
            "baseline": round(nlsr_cdr, 4),
            "ratio": round(cdr_ratio, 4),
            "limit": CDR_RATIO_LIMIT,
            "verdict": "PASS" if cdr_ratio >= CDR_RATIO_LIMIT else "FAIL",
        }
    )

    tda_ms = mean(result.tda_ms for result in results)
    smallest_saving_s = min(savings_s)
    tda_verdict = "PASS" if tda_ms < smallest_saving_s * 1000.0 else "FAIL"
    rows.append(
        {
            "criterion": "TDA cost vs saved convergence",
            "tndn": round(tda_ms, 3),
            "baseline": round(smallest_saving_s * 1000.0, 1),
            "ratio": round(tda_ms / (smallest_saving_s * 1000.0), 5)
            if smallest_saving_s > 0
            else float("inf"),
            "limit": 1.0,
            "verdict": tda_verdict,
        }
    )
    return rows


def seed_pass_fractions(results: Sequence[scenario.SeedResult]) -> dict[str, float]:
    """Fraction of paired seeds in which each criterion holds."""
    fractions: dict[str, float] = {}
    for metric, limit, label in (
        ("fib_mean", FIB_RATIO_LIMIT, "fib"),
        ("convergence_p99_s", CONVERGENCE_RATIO_LIMIT, "conv"),
    ):
        passes = 0
        for result in results:
            values = getattr(result, metric)
            if all(values["tndn"] <= limit * values[baseline] for baseline in BASELINES):
                passes += 1
        fractions[label] = passes / len(results)
    passes = sum(
        1
        for result in results
        if result.cdr_percent["tndn"]
        >= CDR_RATIO_LIMIT * result.cdr_percent["nlsr"]
    )
    fractions["cdr"] = passes / len(results)
    return fractions


def equal_detection_sensitivity(
    results: Sequence[scenario.SeedResult],
    detection_s: float = 0.2,
) -> list[dict[str, object]]:
    """Post-hoc sensitivity: NLSR with T-NDN's heartbeat instead of 1 s.

    This is not part of H13.  It answers the obvious objection that the frozen
    comparison gives NLSR a one-second failure detection.  With equal detection,
    NLSR still pays the flood, so the question is whether T-NDN's local repair
    keeps a 20 % margin on every seed.
    """
    rows: list[dict[str, object]] = []
    for result in results:
        network = PhysicalNetwork(seed=result.seed)
        after = network.without_link(result.failure_link)
        nlsr_conv = (
            detection_s
            + after.diameter_hops() * nlsr.FLOOD_MS_PER_HOP / 1000.0
            + nlsr.SPF_S
        )
        tndn_conv = result.convergence_p99_s["tndn"]
        rows.append(
            {
                "seed": result.seed,
                "nlsr_detection_s": detection_s,
                "nlsr_conv_s": round(nlsr_conv, 4),
                "tndn_conv_s": round(tndn_conv, 4),
                "ratio": round(tndn_conv / nlsr_conv, 4),
                "passes_20pct": "yes" if tndn_conv <= 0.8 * nlsr_conv else "no",
            }
        )
    return rows


def run_all(
    output_dir: Path,
    seeds: int = scenario.SEED_COUNT,
    base_seed: int = scenario.BASE_SEED,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis = topology.analyse()

    results: list[scenario.SeedResult] = []
    for offset in range(seeds):
        results.append(scenario.run_seed(base_seed + offset, analysis))

    per_seed = per_seed_rows(results)
    summary = paired_summary(results)
    summary_table = summary_rows(summary)
    h13 = h13_rows(results)
    fractions = seed_pass_fractions(results)
    sensitivity = equal_detection_sensitivity(results)

    sample = PhysicalNetwork(seed=base_seed)
    sample_placement = scenario.producer_placement(sample)
    aggregated_fib = nlsr.aggregated_fib_mean(
        sample, list(sample_placement.block_to_node)
    )

    _write_csv(output_dir / "tndn_per_seed.csv", per_seed)
    _write_csv(output_dir / "tndn_summary.csv", summary_table)
    _write_csv(output_dir / "tndn_h13.csv", h13)
    _write_csv(output_dir / "tndn_equal_detection.csv", sensitivity)
    _write_csv(
        output_dir / "tndn_tda.csv",
        [
            {
                "landmarks": len(analysis.landmark_indices),
                "clusters": analysis.clusters,
                "holes": analysis.holes,
                "hole_clusters": len(analysis.hole_clusters),
                "tda_total_ms": round(analysis.time_ms, 3),
                "tda_core_ms": round(analysis.persistence_ms, 3),
                "landmark_ms": round(analysis.landmarks_ms, 3),
                "assign_ms": round(analysis.assign_ms, 3),
                "seeds": seeds,
                "nlsr_aggregated_fib_mean": round(aggregated_fib, 2),
            }
        ],
    )

    print("M10: T-NDN versus NLSR, FSR-NDN and Fisheye-Overlay")
    print(
        f"  {scenario.NODE_COUNT} nodes, {topology.NAME_COUNT} names, "
        f"{seeds} paired seeds, link failure at t={scenario.FAILURE_S:.0f} s"
    )
    print(
        f"  name space: {analysis.clusters} persistent H0 clusters, "
        f"{analysis.holes} persistent H1 loop, "
        f"{len(analysis.landmark_indices)} landmarks"
    )
    print(
        f"  TDA cost: {analysis.time_ms:.1f} ms total "
        f"({analysis.persistence_ms:.1f} ms core) per FIB build\n"
    )

    header = f"  {'strategy':16s} {'FIB mean':>10s} {'conv p99 s':>12s} {'CDR %':>8s} {'p95 ms':>9s}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for row in summary_table:
        print(
            f"  {row['strategy']:16s} {row['fib_mean']:10.1f} "
            f"{row['conv_mean_s']:12.3f} {row['cdr_mean_pct']:8.3f} "
            f"{row['p95_mean_ms']:9.1f}"
        )

    print(f"\nH13 criteria ({seeds}-seed means):")
    for row in h13:
        print(
            f"  {row['criterion']:32s} T-NDN={row['tndn']:>10} "
            f"baseline={row['baseline']:>10} ratio={row['ratio']:>8} "
            f"limit={row['limit']:>6} -> {row['verdict']}"
        )
    print(
        "\n  seeds passing all-baseline FIB: "
        f"{100.0 * fractions['fib']:.0f} %; all-baseline convergence: "
        f"{100.0 * fractions['conv']:.0f} %; CDR: {100.0 * fractions['cdr']:.0f} %"
    )
    verdict = "SUPPORTED" if all(row["verdict"] == "PASS" for row in h13) else "REFUTED"
    print(f"\nH13: {verdict}")
    passing = sum(1 for row in sensitivity if row["passes_20pct"] == "yes")
    ratio_mean = sum(float(row["ratio"]) for row in sensitivity) / len(sensitivity)
    print(
        "  sensitivity (not part of H13): with equal 200 ms detection on both "
        f"sides, NLSR reconverges in ~{sum(float(r['nlsr_conv_s']) for r in sensitivity) / len(sensitivity):.2f} s, "
        f"T-NDN/NLSR ratio {ratio_mean:.2f}; 20 % margin holds on "
        f"{passing}/{len(sensitivity)} seeds"
    )
    print(
        "  sensitivity (not part of H13): a prefix-aggregating NLSR would have "
        f"{aggregated_fib:.1f} block entries, versus {summary['fib_mean']['tndn']:.1f} "
        "for T-NDN"
    )
    print(f"CSVs: {output_dir}/tndn_*.csv")
    return {
        "results": results,
        "summary": summary_table,
        "h13": h13,
        "fractions": fractions,
        "verdict": verdict,
        "analysis": analysis,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    parser.add_argument("--seeds", type=int, default=scenario.SEED_COUNT)
    parser.add_argument("--base-seed", type=int, default=scenario.BASE_SEED)
    args = parser.parse_args(argv)
    run_all(args.output_dir, args.seeds, args.base_seed)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
