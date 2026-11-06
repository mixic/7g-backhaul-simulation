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

"""M3 experiment runner: paired-seed CSVs for the frozen H1-H4 hypotheses.

Writes one CSV per run to ``results/m3/{experiment}_{baseline}_{seed}.csv``,
then ``results/m3_summary.md`` (bare means and 95% confidence intervals, no
interpretation), and ``results/m3_state_change_acceleration.png`` (raw
state-change acceleration, Baseline C versus Surgical).

The runner only measures.  It never tunes thresholds to force a hypothesis to
pass; a refutation is logged and the constants are left alone.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from simulation.surgical.config import (  # noqa: E402
    SAVANT_GAINS,
    SimConfig,
    parse_arm,
    scenario_exp1,
)
from simulation.surgical.layering import ORDERINGS, measure_boundary  # noqa: E402
from simulation.surgical.sim import run_and_score  # noqa: E402

# Experiment 1 arms: Baseline A / B / C and the surgical controller.
EXP1_ARMS = {"A": "k8s", "B": "vdr", "C": "pressure", "D": "surgical"}
# Experiment 2: the symmetric control versus the savant gain sweep.
EXP2_ARMS = ["surgical"] + list(SAVANT_GAINS)
# Experiment 3: the four layer orderings at the medium boundary.
SEEDS = list(range(30))
ATTACK_10X = 3_000_000.0


def _exp1_cfg(seed: int, arm: str) -> SimConfig:
    return scenario_exp1(seed, arm)


def _exp2_cfg(seed: int, arm: str) -> SimConfig:
    controller, kwargs = parse_arm(arm)
    return SimConfig(name="exp4_savant", seed=seed, controller=controller,
                     arm=arm, attack_rate=ATTACK_10X,
                     snapshot_times=(20.0, 30.0, 41.0), **kwargs)


def _mean_ci(values) -> tuple[float, float]:
    array = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if array.size < 2:
        return (float(array.mean()) if array.size else float("nan")), 0.0
    return float(array.mean()), float(1.96 * array.std(ddof=1) / math.sqrt(array.size))


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_experiment_1(out_dir: Path):
    rows = []
    for label, arm in EXP1_ARMS.items():
        for seed in SEEDS:
            r = run_and_score(_exp1_cfg(seed, arm))
            row = {
                "experiment": "exp1",
                "baseline": label,
                "seed": seed,
                "Goodput_Legitimate": round(r["goodput_shock"], 6),
                "p95_Latency": round(r["shock"]["p95"], 6),
                "State_Change_Speed": round(r["churn_mean"], 6),
                "State_Change_Acceleration": round(r["churn_accel_mean"], 6),
                "State_Change_Acceleration_Max": round(r["churn_accel_max"], 6),
            }
            _write(out_dir / f"exp1_{label}_{seed}.csv", [row])
            rows.append(row)
            # keep the raw acceleration series for the PNG (Baseline C and Surgical)
            if label in ("C", "D"):
                row["_accel_series"] = r["churn_accel"]
    return rows


def run_experiment_2(out_dir: Path):
    rows = []
    for arm in EXP2_ARMS:
        for seed in SEEDS:
            r = run_and_score(_exp2_cfg(seed, arm))
            row = {
                "experiment": "exp2",
                "baseline": arm,
                "seed": seed,
                "Affected_Flow_Delivery": round(r["gp_affected"], 6),
                "General_Flow_Delivery": round(r["gp_other"], 6),
                "Cascading_Failure_Rate": round(r["cascading_failure_rate"], 6),
                "Starvation_Other_Drops": int(r["savant_other_drops"]),
                "Starvation_Affected_Drops": int(r["savant_affected_drops"]),
                "p95_Ratio": round(r["ratio_p95"], 6),
                "System_Wide_Goodput": round(r["goodput_shock"], 6),
            }
            _write(out_dir / f"exp2_{arm}_{seed}.csv", [row])
            rows.append(row)
    return rows


def run_experiment_3(out_dir: Path):
    rows = []
    payload = 100_000          # the 100 kB object
    drop_probability = 0.02    # microwave 1% plus satellite loss at the boundary
    for ordering in ORDERINGS:
        for seed in SEEDS:
            result = measure_boundary(payload, ordering,
                                      drop_probability=drop_probability, seed=seed)
            row = {
                "experiment": "exp3",
                "baseline": ordering,
                "seed": seed,
                "Reordering_Buffer_Occupancy": result.reorder_occupancy,
                "Fragment_Drop_Rate": round(result.fragment_drop_rate, 6),
                "Fragments": result.fragments,
                "Wire_Bytes": result.wire_bytes,
                "Object_Loss_Rate": result.object_loss_rate,
            }
            _write(out_dir / f"exp3_{ordering}_{seed}.csv", [row])
            rows.append(row)
    return rows


def _summarise(rows: list[dict], experiments: list[str]) -> str:
    lines = [
        "# M3 summary (means and 95% confidence intervals over 30 paired seeds)",
        "",
        "Bare numbers only.  No interpretation (M4/M5 follow).",
        "",
    ]
    for experiment in experiments:
        lines.append(f"## {experiment}")
        lines.append("")
        subset = [r for r in rows if r["experiment"] == experiment]
        baselines = sorted({r["baseline"] for r in subset})
        metrics = [k for k in subset[0].keys()
                   if k not in ("experiment", "baseline", "seed", "_accel_series")]
        header = "| baseline | " + " | ".join(metrics) + " |"
        lines.append(header)
        lines.append("|---|" + "---|" * len(metrics))
        for baseline in baselines:
            cells = []
            for metric in metrics:
                values = [r[metric] for r in subset if r["baseline"] == baseline
                          and metric in r]
                mean, ci = _mean_ci(values)
                cells.append(f"{mean:.4f} +/- {ci:.4f}")
            lines.append(f"| {baseline} | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def plot_acceleration(rows: list[dict], out_dir: Path):
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for label, color, name in (("C", "#c0392b", "Baseline C (global pressure)"),
                               ("D", "#1f6feb", "Surgical")):
        series = [r["_accel_series"] for r in rows
                  if r["experiment"] == "exp1" and r["baseline"] == label]
        if not series:
            continue
        n = min(len(a) for a in series)
        stacked = np.vstack([np.asarray(a[:n], dtype=float) for a in series])
        mean = stacked.mean(axis=0)
        t = np.arange(n) * 0.1
        ax.plot(t, mean, lw=1.4, color=color, label=name)
    for stamp in (24.0, 38.0, 50.0):
        ax.axvline(stamp, color="k", ls=":", lw=0.8)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("state-change acceleration (units/s^2)")
    ax.set_title("M3 raw data: State_Change_Acceleration, seed-averaged (30 seeds)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "m3_state_change_acceleration.png", dpi=150)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--out-dir", type=Path, default=REPO / "results" / "m3")
    parser.add_argument("--skip-exp3", action="store_true")
    args = parser.parse_args()

    global SEEDS
    SEEDS = list(range(args.seeds))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    print("experiment 1 (H1/H2) ...", flush=True)
    rows += run_experiment_1(args.out_dir)
    print("experiment 2 (H4) ...", flush=True)
    rows += run_experiment_2(args.out_dir)
    experiments = ["exp1", "exp2"]
    if not args.skip_exp3:
        print("experiment 3 (H3) ...", flush=True)
        rows += run_experiment_3(args.out_dir)
        experiments.append("exp3")

    summary = _summarise(rows, experiments)
    (args.out_dir / "m3_summary.md").write_text(summary, encoding="utf-8")
    plot_acceleration(rows, args.out_dir)
    print(f"wrote {len(rows)} per-seed CSVs, summary, and PNG to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
