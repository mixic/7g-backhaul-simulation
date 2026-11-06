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

"""Draw the surgical-controller figures from the benchmark CSVs.

Reads ``output/surgical/{summary,timeseries}.csv`` written by
``tools/benchmark_surgical.py`` and writes ``figures/surgical_*.png``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from simulation.surgical.config import LABELS, SAVANT_GAINS  # noqa: E402

ORDER = [
    "k8s",
    "pressure",
    "pressure_tuned",
    "surgical_global",
    "surgical_unlimited",
    "surgical_ab",
    "surgical",
    "static_isolation",
    "vdr",
    "vdr_surgical",
    "savant",
]
COLORS = {
    "k8s": "#8c8c8c",
    "pressure": "#c0392b",
    "pressure_tuned": "#e07b39",
    "surgical": "#1f6feb",
    "surgical_unlimited": "#7fb3f5",
    "surgical_ab": "#5b8def",
    "surgical_global": "#a0a4a8",
    "static_isolation": "#27ae60",
    "vdr": "#8e44ad",
    "vdr_surgical": "#b07cd6",
    "savant": "#e6b800",
}


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _summary(rows: list[dict], experiment: str) -> dict[tuple[str, str], tuple[float, float]]:
    out: dict[tuple[str, str], tuple[float, float]] = {}
    for row in rows:
        if row["experiment"] != experiment:
            continue
        out[(row["arm"], row["metric"])] = (float(row["mean"]), float(row["ci95"]))
    return out


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _bars(ax, arms, stats, metric, scale=1.0, threshold=None, label=""):
    xs = range(len(arms))
    values = [stats.get((arm, metric), (0.0, 0.0))[0] * scale for arm in arms]
    errs = [stats.get((arm, metric), (0.0, 0.0))[1] * scale for arm in arms]
    ax.bar(xs, values, yerr=errs, capsize=3,
           color=[COLORS.get(a, "#333333") for a in arms])
    if threshold is not None:
        ax.axhline(threshold, ls="--", c="k", lw=1, label=label)
        ax.legend(fontsize=8)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([a.replace("_", "\n") for a in arms], fontsize=7)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=REPO / "output" / "surgical")
    parser.add_argument("--figure-dir", type=Path, default=REPO / "figures")
    args = parser.parse_args()
    args.figure_dir.mkdir(parents=True, exist_ok=True)

    summary = _read(args.input_dir / "summary.csv")
    series = _read(args.input_dir / "timeseries.csv")
    if not summary:
        print("no summary.csv; run tools/benchmark_surgical.py first")
        return 1

    e1 = _summary(summary, "exp1_ddos")
    e2 = _summary(summary, "exp2_churn")
    e3 = _summary(summary, "exp3_boundary")
    arms1 = [a for a in ORDER if (a, "ratio_p95") in e1]
    arms2 = [a for a in ORDER if (a, "churn_max") in e2]
    arms3 = [a for a in ORDER if (a, "reasm_peak") in e3]

    # -- H1 ------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    _bars(axes[0], arms1, e1, "ratio_p95", threshold=1.5, label="H1 bound: 1.5x")
    axes[0].set_ylabel("shock-window p95 / baseline p95")
    axes[0].set_title("H1: p95 latency inflation under the shockwave")
    _bars(axes[1], arms1, e1, "goodput_shock", scale=100.0, threshold=95.0,
          label="H1 bound: 95%")
    axes[1].set_ylabel("legitimate goodput (%)")
    axes[1].set_ylim(0, 105)
    axes[1].set_title("H1: legitimate goodput under the shockwave")
    fig.tight_layout()
    fig.savefig(args.figure_dir / "surgical_h1_headline.png", dpi=150)
    plt.close(fig)

    # -- H2 ------------------------------------------------------------
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.4))
    by_arm: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in series:
        if row["experiment"] == "exp2_churn" and row["series"] == "churn_rate":
            by_arm[row["arm"]].append((float(row["t"]), float(row["value"])))
    for arm in ("pressure", "surgical", "surgical_unlimited"):
        points = sorted(by_arm.get(arm, []))
        if not points:
            continue
        ts = [p[0] for p in points]
        vs = [p[1] for p in points]
        axes[0].plot(ts, vs, lw=1.5, color=COLORS[arm], label=LABELS[arm])
    for stamp in (24.0, 38.0, 50.0):
        axes[0].axvline(stamp, color="k", ls=":", lw=0.8)
    axes[0].set_ylabel("state-change rate (units/s)")
    axes[0].set_xlabel("time (s)")
    axes[0].set_title("H2: state-change SPEED over time (seed-averaged)")
    axes[0].legend(fontsize=8)
    _bars(axes[1], arms2, e2, "churn_max")
    axes[1].set_ylabel("peak state-change rate (units/s)")
    axes[1].set_title("H2: per-run PEAK state-change rate")
    fig.tight_layout()
    fig.savefig(args.figure_dir / "surgical_h2_state_change.png", dpi=150)
    plt.close(fig)

    # -- H3 ------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    _bars(axes[0], arms3, e3, "reasm_peak", scale=1.0 / 1024.0)
    axes[0].set_ylabel("peak reassembly occupancy (kB)")
    axes[0].set_title("H3: reorder buffer at the fiber->satellite edge")
    _bars(axes[1], arms3, e3, "reasm_deadlock_frac", scale=100.0)
    axes[1].set_ylabel("time above 80% occupancy (%)")
    axes[1].set_title("H3: head-of-line deadlock fraction")
    fig.tight_layout()
    fig.savefig(args.figure_dir / "surgical_h3_boundary.png", dpi=150)
    plt.close(fig)

    # -- H4 ------------------------------------------------------------
    arms4 = [a for a in ("k8s", "pressure", "surgical", "static_isolation", "savant")
             if (a, "gp_affected") in e1]
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    xs = range(len(arms4))
    aff = [e1.get((a, "gp_affected"), (0.0, 0.0)) for a in arms4]
    oth = [e1.get((a, "gp_other"), (0.0, 0.0)) for a in arms4]
    ax.bar([x - 0.2 for x in xs], [v[0] * 100 for v in aff], 0.4,
           yerr=[v[1] * 100 for v in aff], capsize=3, label="affected name")
    ax.bar([x + 0.2 for x in xs], [v[0] * 100 for v in oth], 0.4,
           yerr=[v[1] * 100 for v in oth], capsize=3, label="all other names")
    ax.set_xticks(list(xs))
    ax.set_xticklabels([a.replace("_", "\n") for a in arms4], fontsize=8)
    ax.set_ylabel("delivery probability, shock window (%)")
    ax.set_title("H4: local hyper-specialisation vs system-wide delivery")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(args.figure_dir / "surgical_h4_savant.png", dpi=150)
    plt.close(fig)

    # -- H4 trade-off curve across the savant gain sweep ----------------
    e4 = _summary(summary, "exp4_savant")
    gains, aff, oth, sysd, spill = [], [], [], [], []
    for arm, gain in sorted(SAVANT_GAINS.items(), key=lambda kv: kv[1]):
        if (arm, "gp_affected") not in e4:
            continue
        gains.append(gain)
        aff.append(e4.get((arm, "gp_affected"), (0.0, 0.0)))
        oth.append(e4.get((arm, "gp_other"), (0.0, 0.0)))
        sysd.append(e4.get((arm, "goodput_shock"), (0.0, 0.0)))
        spill.append(e4.get((arm, "spillover"), (0.0, 0.0)))
    if gains:
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
        axes[0].errorbar(gains, [v[0] * 100 for v in aff],
                         yerr=[v[1] * 100 for v in aff], marker="o",
                         color="#e6b800", label="affected name")
        axes[0].errorbar(gains, [v[0] * 100 for v in oth],
                         yerr=[v[1] * 100 for v in oth], marker="s",
                         color="#1f6feb", label="all other names")
        for arm, tag in (("surgical", "surgical arm"), ("k8s", "Baseline A")):
            ref = e4.get((arm, "gp_affected"))
            if ref:
                axes[0].axhline(ref[0] * 100, ls="--", lw=1,
                                color=COLORS.get(arm, "#333333"),
                                label=f"{tag} (affected)")
        axes[0].set_xlabel("savant role shift (alpha target)")
        axes[0].set_ylabel("delivery probability, shock window (%)")
        axes[0].set_title("H4: local gain versus system-wide cost")
        axes[0].legend(fontsize=7)

        axes[1].errorbar(gains, [v[0] * 100 for v in sysd],
                         yerr=[v[1] * 100 for v in sysd], marker="o",
                         color="#c0392b", label="system-wide goodput")
        ref = e4.get(("surgical", "goodput_shock"))
        if ref:
            axes[1].axhline(ref[0] * 100, ls="--", lw=1, color="#1f6feb",
                            label="surgical arm")
        twin = axes[1].twinx()
        twin.plot(gains, [v[0] * 100 for v in spill], marker="^",
                  color="#555555", ls=":")
        twin.set_ylabel("neighbour throughput change (%)")
        axes[1].set_xlabel("savant role shift (alpha target)")
        axes[1].set_ylabel("system-wide legitimate goodput (%)")
        axes[1].set_title("H4: cascading cost to neighbours (dotted, right axis)")
        axes[1].legend(fontsize=7, loc="lower left")
        fig.tight_layout()
        fig.savefig(args.figure_dir / "surgical_h4_gain_sweep.png", dpi=150)
        plt.close(fig)

    # parked copies of the machine-readable results, per repo convention
    _write_csv(args.figure_dir / "surgical_summary.csv", summary)
    _write_csv(args.figure_dir / "surgical_verdict.csv",
               _read(args.input_dir / "verdict.csv"))
    print(f"figures written to {args.figure_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
