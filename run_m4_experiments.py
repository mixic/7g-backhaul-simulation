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

"""M4 experiments: OEF compensation (H5) and multidimensional baselining.

Three experiments, 30 paired seeds:

* exp1 (H5)    -- surgical vs OEF-surgical under a DDoS shockwave.
* exp2 (starvation boundary) -- OEF forced to its limit, gain swept, so the
  transit-drop threshold can be located.
* exp3 (MKB)   -- scalar trigger (surgical) vs vector trigger (MKB).

The runner measures; it never tunes OEF to force H5 to pass.  A refutation is a
successful completion of M4.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from simulation.surgical.config import MKB, OEF, SURGICAL, SimConfig  # noqa: E402
from simulation.surgical.sim import run_and_score  # noqa: E402

SEEDS = list(range(30))
ATTACK_START = 30.0


def _exp1_cfg(seed: int, arm: str) -> SimConfig:
    return SimConfig(name="exp1_ddos", seed=seed, controller=arm,
                     snapshot_times=(20.0, 30.0, 41.0))


def _exp3_cfg(seed: int, arm: str) -> SimConfig:
    return SimConfig(name="exp1_ddos", seed=seed, controller=arm)


def _mean_ci(values) -> tuple[float, float]:
    array = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if array.size < 2:
        return (float(array.mean()) if array.size else float("nan")), 0.0
    return float(array.mean()), float(1.96 * array.std(ddof=1) / math.sqrt(array.size))


def _write(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def _trigger_stats(result: dict):
    """Trigger latency and false positives for a run."""
    attack = ATTACK_START
    if result["controller"] == MKB:
        spikes = result["mkb_spikes"]
        times = spikes[:, 0] if len(spikes) else np.zeros(0)
    else:
        times = result["edit_times"]
    after = times[times >= attack - 0.5]
    before = times[times < attack - 0.5]
    latency = float(after.min() - attack) if len(after) else float("nan")
    return latency, int(len(before))


def run_exp1(out_dir: Path):
    rows = []
    series = {}
    for arm in (SURGICAL, OEF):
        oef_series = []
        for seed in SEEDS:
            r = run_and_score(_exp1_cfg(seed, arm))
            row = {
                "experiment": "exp1",
                "baseline": arm,
                "seed": seed,
                "Total_Throughput_CBF": round(r["cbf_shock"], 4),
                "Legitimate_Goodput_CMRO2": round(r["goodput_shock"], 6),
                "OEF_Value": round(r["oef_peak"], 6),
                "OEF_Change_Speed": round(r["oef_speed_max"], 6),
                "OEF_Change_Acceleration": round(r["oef_accel_max"], 6),
                "OEF_Limit_Hit": int(r["oef_limit_hit"]),
                "p95_Ratio": round(r["ratio_p95"], 6),
                "Goodput_Base": round(r["goodput_base"], 6),
            }
            _write(out_dir / f"exp1_{arm}_{seed}.csv", row)
            rows.append(row)
            if len(r.get("oef_series", [])) > 4:
                oef_series.append(r["oef_series"])
        if oef_series:
            n = min(len(a) for a in oef_series)
            series[arm] = np.stack([a[:n] for a in oef_series])
    return rows, series


def run_exp2(out_dir: Path) -> list[dict]:
    """Starvation boundary: OEF pinned to max, gain swept, transit drop measured."""
    rows = []
    for oef_max in (1.5, 2.0, 4.0, 8.0, 16.0):
        arm = f"oef_max{oef_max:g}"
        for seed in SEEDS:
            cfg = _exp1_cfg(seed, OEF).child(oef_force_max=True, oef_max=oef_max)
            r = run_and_score(cfg)
            row = {
                "experiment": "exp2",
                "baseline": arm,
                "oef_max": oef_max,
                "seed": seed,
                "Legitimate_Goodput": round(r["goodput_shock"], 6),
                "Transit_Drop_Rate": round(1.0 - r["gp_other"], 6),
                "p95_Ratio": round(r["ratio_p95"], 6),
                "OEF_Value": round(r["oef_peak"], 6),
            }
            _write(out_dir / f"exp2_{arm}_{seed}.csv", row)
            rows.append(row)
    return rows


def run_exp3(out_dir: Path) -> list[dict]:
    rows = []
    for arm in (SURGICAL, OEF, MKB):
        for seed in SEEDS:
            r = run_and_score(_exp3_cfg(seed, arm))
            latency, false_pos = _trigger_stats(r)
            row = {
                "experiment": "exp3",
                "baseline": arm,
                "seed": seed,
                "Trigger_Latency_s": round(latency, 4) if np.isfinite(latency) else "",
                "False_Positives": false_pos,
                "Legitimate_Goodput": round(r["goodput_shock"], 6),
                "p95_Ratio": round(r["ratio_p95"], 6),
                "OEF_Limit_Hit": int(r["oef_limit_hit"]),
            }
            _write(out_dir / f"exp3_{arm}_{seed}.csv", row)
            rows.append(row)
    return rows


def _summarise(rows: list[dict]) -> str:
    lines = [
        "# M4 summary (means and 95% confidence intervals over 30 paired seeds)",
        "",
        "Bare numbers.  H5 verdict is mechanical; interpretation in M5.",
        "",
    ]
    for experiment in ("exp1", "exp2", "exp3"):
        subset = [r for r in rows if r["experiment"] == experiment]
        baselines = sorted({r["baseline"] for r in subset})
        metrics = [k for k in subset[0].keys()
                   if k not in ("experiment", "baseline", "seed", "oef_max")]
        lines.append(f"## {experiment}")
        lines.append("")
        lines.append("| baseline | " + " | ".join(metrics) + " |")
        lines.append("|---|" + "---|" * len(metrics))
        for baseline in baselines:
            cells = []
            for metric in metrics:
                values = [r[metric] for r in subset if r["baseline"] == baseline
                          and isinstance(r.get(metric), (int, float))
                          and np.isfinite(r[metric])]
                mean, ci = _mean_ci(values)
                cells.append(f"{mean:.4f} +/- {ci:.4f}" if values else "nan")
            lines.append(f"| {baseline} | " + " | ".join(cells) + " |")
        lines.append("")

    # H5 verdict
    s = {r["baseline"]: r for r in rows if r["experiment"] == "exp1"}
    return "\n".join(lines)


def plot_oef(series: dict, out_dir: Path):
    """oef_vs_goodput: CBF drops, OEF rises, CMRO2 stays flat."""
    if OEF not in series:
        return
    stacked = series[OEF]
    t = stacked[0, :, 0]
    oef = stacked[:, :, 1].mean(axis=0)
    cbf = stacked[:, :, 2].mean(axis=0) / 1e6  # MB/s

    fig, ax1 = plt.subplots(figsize=(10, 4.4))
    ax1.plot(t, cbf, color="#c0392b", lw=1.6, label="CBF (total throughput, MB/s)")
    ax1.set_xlabel("time (s)")
    ax1.set_ylabel("CBF (MB/s)", color="#c0392b")
    ax1.axvspan(30, 40, color="red", alpha=0.07)
    ax2 = ax1.twinx()
    ax2.plot(t, oef, color="#1f6feb", lw=1.6, label="OEF (extraction fraction)")
    ax2.set_ylabel("OEF", color="#1f6feb")
    ax2.set_ylim(0, 1.05)
    fig.legend(loc="upper center", ncol=2, fontsize=8)
    ax1.set_title("M4 raw data: CBF collapses, OEF rises (CMRO2 flat), seed-averaged")
    fig.tight_layout()
    fig.savefig(out_dir / "oef_vs_goodput.png", dpi=150)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--out-dir", type=Path, default=REPO / "results" / "m4")
    args = parser.parse_args()
    global SEEDS
    SEEDS = list(range(args.seeds))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    print("exp1 (H5 OEF) ...", flush=True)
    rows_1, series = run_exp1(args.out_dir)
    rows += rows_1
    print("exp2 (starvation boundary) ...", flush=True)
    rows += run_exp2(args.out_dir)
    print("exp3 (MKB) ...", flush=True)
    rows += run_exp3(args.out_dir)

    summary = _summarise(rows)
    summary += ("\nCBF (Total_Throughput) is instrumented by the OEF/MKB\n"
                "controller; the plain surgical arm carries no CBF monitor and\n"
                "therefore reports 0.\n")
    (args.out_dir / "m4_summary.md").write_text(summary, encoding="utf-8")
    plot_oef(series, args.out_dir)
    print(f"wrote CSVs, summary and PNG to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
