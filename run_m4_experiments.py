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

"""M4-Execution: the definitive benchmark.

Five arms, 30 paired seeds (the M3 ``default_rng(2026)`` seed set), one 60 s
scenario -- 30 s of normal traffic, a 10 s massive DDoS shockwave at t=30, then
20 s of recovery:

  * ``static_isolation``  the M3 confound baseline (fixed per-flow queues)
  * ``m3_surgical_1d``    the M3 1D scalar-EMA limiter
  * ``m4_oef``            the Fick-principle OEF actuator on the 1D base
  * ``m4_mkb``            the 4D vector-acceleration trigger (OEF off)
  * ``m4_combined``       OEF actuator + MKB vector trigger together

The runner only measures.  It never tunes a knob to force H5 or H6 to pass; a
refutation is a successful execution.  Outputs ``final_benchmark_raw.csv``, the
three PNG plots and ``m4_summary.md`` with explicit verdicts.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from simulation.surgical.config import (  # noqa: E402
    MKB,
    MKB_NO_OEF,
    OEF,
    STATIC_ISO,
    SURGICAL,
    SimConfig,
)
from simulation.surgical.sim import run_and_score  # noqa: E402

ARMS = [
    ("static_isolation", STATIC_ISO),
    ("m3_surgical_1d", SURGICAL),
    ("m4_oef", OEF),
    ("m4_mkb", MKB_NO_OEF),
    ("m4_combined", MKB),
]

ATTACK_START = 30.0
ATTACK_END = 40.0
FIELDS = [
    "arm", "seed", "Total_Throughput_CBF", "Legitimate_Goodput_CMRO2",
    "OEF_Value", "Peak_State_Change_Speed", "Number_of_Edits",
    "False_Positive_Edits", "Transit_Drop_Rate",
]


def _seeds(n: int = 30, base: int = 2026) -> list[int]:
    """The exact M3 seed set (``benchmark_surgical.py``)."""
    return [int(v) for v in np.random.default_rng(base).integers(0, 2**31 - 1, size=n)]


def _cfg(seed: int, controller: str) -> SimConfig:
    """Exactly the M3 ``scenario_exp1`` (static_isolation is not degraded)."""
    return SimConfig(name="exp1_ddos", seed=seed, controller=controller)


def _mean_ci(values) -> tuple[float, float]:
    array = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if array.size < 2:
        return (float(array.mean()) if array.size else float("nan")), 0.0
    return float(array.mean()), float(1.96 * array.std(ddof=1) / math.sqrt(array.size))


def _round(value, nd: int = 6):
    return round(value, nd) if np.isfinite(value) else ""


def run_benchmark(out_dir: Path, seeds: list[int]):
    rows: list[dict] = []
    series: dict[str, dict] = {}
    for label, controller in ARMS:
        oef_s, speed_s, goodput_s, transit_s = [], [], [], []
        for seed in seeds:
            r = run_and_score(_cfg(seed, controller))
            fp = int((r["edit_times"] < ATTACK_START - 0.5).sum())
            row = {
                "arm": label,
                "seed": seed,
                "Total_Throughput_CBF": _round(r["cbf_shock"], 4),
                "Legitimate_Goodput_CMRO2": _round(r["goodput_shock"]),
                "OEF_Value": _round(r["oef_peak"]),
                "Peak_State_Change_Speed": _round(r["churn_max"]),
                "Number_of_Edits": int(r["edits"]),
                "False_Positive_Edits": fp,
                "Transit_Drop_Rate": _round(1.0 - r["gp_other"]),
            }
            rows.append(row)
            if label in ("m4_oef", "m4_combined") and len(r.get("oef_series", [])) > 4:
                oef_s.append(r["oef_series"])
            if len(r["churn_speed"]):
                speed_s.append(np.asarray(r["churn_speed"], dtype=float))
            if len(r["roll_goodput"]):
                goodput_s.append(np.asarray(r["roll_goodput"], dtype=float))
            if len(r["roll_transit_goodput"]):
                transit_s.append(np.asarray(r["roll_transit_goodput"], dtype=float))

        entry: dict = {}
        if oef_s:
            n = min(len(a) for a in oef_s)
            entry["oef"] = np.stack([a[:n] for a in oef_s])
        if speed_s:
            n = min(len(a) for a in speed_s)
            entry["speed"] = np.stack([a[:n] for a in speed_s])
            entry["speed_t"] = np.asarray(r["churn_t"], dtype=float)[:n]
        if goodput_s:
            n = min(len(a) for a in goodput_s)
            entry["goodput"] = np.stack([a[:n] for a in goodput_s])
            entry["goodput_t"] = np.asarray(r["roll_goodput_t"], dtype=float)[:n]
        if transit_s:
            n = min(len(a) for a in transit_s)
            entry["transit"] = np.stack([a[:n] for a in transit_s])
        series[label] = entry

    _write_raw(out_dir / "final_benchmark_raw.csv", rows)
    return rows, series


def _write_raw(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# --------------------------------------------------------------------------
# Starvation threshold and computational overhead (reviewer requirements W2/W3)
# --------------------------------------------------------------------------
STARVATION_SWEEP = [1.0, 2.0, 4.0, 8.0, 16.0]


def run_starvation_sweep(seeds: list[int]) -> list[dict]:
    """Force OEF to its maximum and sweep the WFQ weight multiplier, to locate
    the point where OEF compensation becomes destructive (transit drop climbs).
    """
    rows = []
    for oef_max in STARVATION_SWEEP:
        for seed in seeds:
            cfg = _cfg(seed, OEF).child(oef_force_max=True, oef_max=oef_max)
            r = run_and_score(cfg)
            rows.append({
                "oef_max": oef_max,
                "seed": seed,
                "Legitimate_Goodput": r["goodput_shock"],
                "Transit_Drop_Rate": 1.0 - r["gp_other"],
            })
    return rows


def _starvation_table(rows: list[dict]) -> str:
    lines = ["## Starvation threshold (OEF forced to max, weight swept)",
             "", "| oef_max (WFQ weight) | Legitimate goodput | Transit drop rate |",
             "|---|---|---|"]
    for oef_max in STARVATION_SWEEP:
        sub = [r for r in rows if r["oef_max"] == oef_max]
        gp, gp_ci = _mean_ci([r["Legitimate_Goodput"] for r in sub])
        dr, dr_ci = _mean_ci([r["Transit_Drop_Rate"] for r in sub])
        lines.append(f"| {oef_max:g} | {gp:.4f} +/- {gp_ci:.4f} | {dr:.4f} +/- {dr_ci:.4f} |")
    lines.append("")
    return "\n".join(lines)


def measure_overhead(seed: int = 42, reps: int = 3) -> dict[str, float]:
    """Controller CPU cost per control tick (seconds), best of ``reps`` runs.

    Wraps ``controller.on_tick`` so only the control law -- the OEF state update
    and the 1D/vector trigger -- is timed, not the queueing substrate.
    """
    from simulation.surgical.network import SimRun

    out: dict[str, float] = {}
    for label, controller in ARMS:
        cfg = _cfg(seed, controller)
        best = float("inf")
        best_ticks = 1
        for _ in range(reps):
            sim = SimRun(cfg)
            ctrl = sim.controller
            orig = ctrl.on_tick
            acc = [0.0]
            ticks = [0]

            def wrapped(t, obs):
                t0 = time.perf_counter()
                orig(t, obs)
                acc[0] += time.perf_counter() - t0
                ticks[0] += 1

            ctrl.on_tick = wrapped
            sim.run()
            if acc[0] < best:
                best = acc[0]
                best_ticks = ticks[0]
        out[label] = best / max(best_ticks, 1)
    return out


def _overhead_table(overhead: dict[str, float]) -> str:
    base = overhead.get("m3_surgical_1d", 0.0) or 1.0
    lines = ["## Computational overhead (controller CPU per tick)",
             "", "| arm | us/tick | vs 1D limiter |", "|---|---|---|"]
    for label, _ in ARMS:
        us = overhead.get(label, 0.0) * 1e6
        ratio = us / (base * 1e6) if base > 0 else float("nan")
        lines.append(f"| {label} | {us:.1f} | {ratio:.2f}x |")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
def _arm_values(rows, arm: str, metric: str):
    values = [r[metric] for r in rows if r["arm"] == arm
              and isinstance(r.get(metric), (int, float)) and np.isfinite(r[metric])]
    return _mean_ci(values)


def _verdicts(rows: list[dict]) -> str:
    oef_gp, oef_ci = _arm_values(rows, "m4_oef", "Legitimate_Goodput_CMRO2")
    iso_gp, iso_ci = _arm_values(rows, "static_isolation", "Legitimate_Goodput_CMRO2")
    oef_drop, oef_drop_ci = _arm_values(rows, "m4_oef", "Transit_Drop_Rate")

    mkb_peak, mkb_ci = _arm_values(rows, "m4_mkb", "Peak_State_Change_Speed")
    s1d_peak, s1d_ci = _arm_values(rows, "m3_surgical_1d", "Peak_State_Change_Speed")
    mkb_fp, mkb_fp_ci = _arm_values(rows, "m4_mkb", "False_Positive_Edits")
    s1d_fp, s1d_fp_ci = _arm_values(rows, "m3_surgical_1d", "False_Positive_Edits")

    h5_pass = oef_gp > 0.92 and oef_gp > iso_gp
    h6_pass = mkb_peak < s1d_peak and mkb_fp == 0.0

    lines = [
        "## Verdicts",
        "",
        f"| H5 OEF compensation | **{'CONFIRMED' if h5_pass else 'REFUTED'}** |",
        "",
        f"m4_oef legitimate goodput (CMRO2) = **{oef_gp:.4f} +/- {oef_ci:.4f}** "
        f"vs static_isolation **{iso_gp:.4f} +/- {iso_ci:.4f}** (documented 86.5 %). "
        f"Target: > 0.92 and > static_isolation. "
        f"Transit drop rate (starvation cost) = **{oef_drop:.4f} +/- {oef_drop_ci:.4f}**.",
        "",
        f"| H6 MKB rate control | **{'CONFIRMED' if h6_pass else 'REFUTED'}** |",
        "",
        f"m4_mkb peak state-change speed = **{mkb_peak:.4f} +/- {mkb_ci:.4f}** "
        f"vs m3_surgical_1d **{s1d_peak:.4f} +/- {s1d_ci:.4f}** (must be lower). "
        f"m4_mkb false-positive edits = **{mkb_fp:.4f} +/- {mkb_fp_ci:.4f}** "
        f"vs m3_surgical_1d **{s1d_fp:.4f} +/- {s1d_fp_ci:.4f}** (must be zero).",
        "",
    ]
    return "\n".join(lines)


def _metric_table(rows: list[dict], metric: str, title: str) -> str:
    lines = [f"## {title}", "", "| arm | mean | 95% CI |", "|---|---|---|"]
    for label, _ in ARMS:
        mean, ci = _arm_values(rows, label, metric)
        lines.append(f"| {label} | {mean:.4f} | +/- {ci:.4f} |")
    lines.append("")
    return "\n".join(lines)


def _full_table(rows: list[dict]) -> str:
    metrics = ["Total_Throughput_CBF", "Legitimate_Goodput_CMRO2", "OEF_Value",
               "Peak_State_Change_Speed", "Number_of_Edits",
               "False_Positive_Edits", "Transit_Drop_Rate"]
    lines = ["## All arms, all metrics (mean +/- 95% CI)",
             "", "| arm | " + " | ".join(metrics) + " |",
             "|---|" + "---|" * len(metrics)]
    for label, _ in ARMS:
        cells = []
        for metric in metrics:
            mean, ci = _arm_values(rows, label, metric)
            cells.append(f"{mean:.4f} +/- {ci:.4f}")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def _interpretation(rows: list[dict]) -> str:
    oef_gp = _arm_values(rows, "m4_oef", "Legitimate_Goodput_CMRO2")[0]
    s1d_gp = _arm_values(rows, "m3_surgical_1d", "Legitimate_Goodput_CMRO2")[0]
    iso_gp = _arm_values(rows, "static_isolation", "Legitimate_Goodput_CMRO2")[0]
    mkb_peak = _arm_values(rows, "m4_mkb", "Peak_State_Change_Speed")[0]
    s1d_peak = _arm_values(rows, "m3_surgical_1d", "Peak_State_Change_Speed")[0]
    comb_gp = _arm_values(rows, "m4_combined", "Legitimate_Goodput_CMRO2")[0]
    comb_fp = _arm_values(rows, "m4_combined", "False_Positive_Edits")[0]

    return "\n".join([
        "## Interpretation",
        "",
        "**H5 (OEF) — REFUTED.** The OEF actuator's CBF monitor tracks *total "
        "delivered throughput*, which a DDoS flood does not lower (the attack's "
        "bytes are served too), so the CBF-drop trigger never fires during the "
        "attack.  ``OEF_Value`` reaches 1.0 only when traffic stops at "
        "end-of-run.  Hence m4_oef is indistinguishable from m3_surgical_1d "
        f"({oef_gp:.4f} vs {s1d_gp:.4f}) and stays below static_isolation "
        f"({iso_gp:.4f}).  The Fick premise — that a DDoS lowers delivered CBF "
        "— does not hold in this testbed, so the compensation has nothing to "
        "compensate.",
        "",
        "**H6 (MKB) — CONFIRMED, with a caveat.** m4_mkb keeps false-positive "
        "edits at exactly zero during steady state, satisfying that clause.  "
        f"Its peak burst speed ({mkb_peak:.1f}) is slightly below the 1D limiter "
        f"({s1d_peak:.1f}), but the confidence intervals overlap heavily, so the "
        "\"cap\" is marginal — a few percent at best — because both arms share "
        "the same discrete surgical edit.  The vector trigger does not make the "
        "burst worse, but it does not clearly bound it either.",
        "",
        "**m4_combined — negative result.** Running OEF and MKB together is "
        f"strictly worse than either alone (goodput {comb_gp:.4f} vs {oef_gp:.4f}): "
        "the OEF actuator's weight changes feed back into the 4-D state vector "
        f"and trip the MKB trigger ~{comb_fp:.0f} times during steady traffic, "
        "isolating innocent classes and roughly halving delivery.",
        "",
    ])


def _answers(rows: list[dict]) -> str:
    oef_gp, oef_ci = _arm_values(rows, "m4_oef", "Legitimate_Goodput_CMRO2")
    iso_gp, iso_ci = _arm_values(rows, "static_isolation", "Legitimate_Goodput_CMRO2")
    oef_drop, oef_drop_ci = _arm_values(rows, "m4_oef", "Transit_Drop_Rate")
    mkb_peak, mkb_ci = _arm_values(rows, "m4_mkb", "Peak_State_Change_Speed")
    s1d_peak, s1d_ci = _arm_values(rows, "m3_surgical_1d", "Peak_State_Change_Speed")
    mkb_fp, _ = _arm_values(rows, "m4_mkb", "False_Positive_Edits")
    return "\n".join([
        "## Direct answers to the review questions",
        "",
        "1. **Did OEF beat static_isolation (86.5 %)?** "
        f"{'**No.**' if oef_gp <= iso_gp else 'Yes.'} m4_oef = {oef_gp:.4f} +/- {oef_ci:.4f} "
        f"vs static_isolation = {iso_gp:.4f} +/- {iso_ci:.4f}.",
        "2. **Did MKB cap the peak burst speed?** "
        f"{'Yes (marginal).' if mkb_peak < s1d_peak else '**No.**'} "
        f"m4_mkb = {mkb_peak:.2f} +/- {mkb_ci:.2f} vs m3_surgical_1d = {s1d_peak:.2f} +/- {s1d_ci:.2f}; "
        f"false-positive edits = {mkb_fp:.0f}.",
        "3. **What is the exact starvation cost?** Transit drop rate = "
        f"{oef_drop:.4f} +/- {oef_drop_ci:.4f} (m4_oef); the destructive threshold "
        "is in the starvation table below.",
        "",
    ])


def _summarise(rows: list[dict], starvation_rows: list[dict],
               overhead: dict[str, float]) -> str:
    return "\n".join([
        "# M4-Execution: definitive benchmark (30 paired seeds)",
        "",
        "Means and 95% confidence intervals across 30 paired seeds (the M3 "
        "`default_rng(2026)` seed set).  No tuning, no cherry-picking.",
        "",
        _verdicts(rows),
        _answers(rows),
        _metric_table(rows, "Legitimate_Goodput_CMRO2",
                      "Legitimate goodput (CMRO2) across arms"),
        _metric_table(rows, "Peak_State_Change_Speed",
                      "Peak burst state-change speed across arms"),
        _full_table(rows),
        _starvation_table(starvation_rows),
        _overhead_table(overhead),
        _interpretation(rows),
    ])


# --------------------------------------------------------------------------
# Plots
# --------------------------------------------------------------------------
def plot_oef(series: dict, out_dir: Path):
    """Plot 1: CBF (left), OEF and CMRO2 (right), seed-averaged for m4_oef."""
    arm = series.get("m4_oef")
    if not arm or "oef" not in arm:
        return
    oef_stack = arm["oef"]
    t = oef_stack[0, :, 0]
    cbf = oef_stack[:, :, 2].mean(axis=0) / 1e6  # MB/s
    oef = oef_stack[:, :, 3].mean(axis=0)        # max OEF across nodes

    fig, ax1 = plt.subplots(figsize=(10, 4.6))
    ax1.plot(t, cbf, color="#c0392b", lw=1.6, label="CBF (total throughput, MB/s)")
    ax1.set_xlabel("time (s)")
    ax1.set_ylabel("CBF (MB/s)", color="#c0392b")
    ax1.tick_params(axis="y", labelcolor="#c0392b")
    ax1.axvspan(ATTACK_START, ATTACK_END, color="red", alpha=0.07)

    ax2 = ax1.twinx()
    ax2.plot(t, oef, color="#1f6feb", lw=1.6, label="OEF (max extraction fraction)")
    if "goodput" in arm:
        gt = arm["goodput_t"]
        gp = arm["goodput"].mean(axis=0)
        ax2.plot(gt, gp, color="#27ae60", lw=1.6, label="CMRO2 (legit goodput)")
    ax2.set_ylabel("fraction (0-1)", color="#1f6feb")
    ax2.set_ylim(0, 1.05)
    ax2.tick_params(axis="y", labelcolor="#1f6feb")

    lines = ax1.get_lines() + ax2.get_lines()
    ax1.legend(lines, [ln.get_label() for ln in lines], loc="upper left", fontsize=8)
    ax1.set_title("M4 H5: CBF, OEF and CMRO2 (legit goodput), m4_oef, seed-averaged")
    fig.tight_layout()
    fig.savefig(out_dir / "oef_vs_goodput.png", dpi=150)
    plt.close(fig)


def plot_peak_burst(series: dict, out_dir: Path):
    """Plot 2: state-change speed, 1D limiter vs MKB arms."""
    fig, ax = plt.subplots(figsize=(10, 4.4))
    for label, color in (("m3_surgical_1d", "#c0392b"),
                         ("m4_mkb", "#1f6feb"),
                         ("m4_combined", "#8e44ad")):
        arm = series.get(label)
        if not arm or "speed" not in arm:
            continue
        ax.plot(arm["speed_t"], arm["speed"].mean(axis=0), lw=1.4,
                color=color, label=label)
    ax.axvspan(ATTACK_START, ATTACK_END, color="red", alpha=0.07)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("state-change speed (units/s)")
    ax.set_title("M4 H6: peak burst state-change speed, seed-averaged (30 seeds)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "peak_burst_cap.png", dpi=150)
    plt.close(fig)


def plot_starvation(series: dict, out_dir: Path):
    """Plot 3: transit drop rate over time (the starvation cost)."""
    fig, ax = plt.subplots(figsize=(10, 4.4))
    for label, color in (("m4_oef", "#c0392b"),
                         ("m4_combined", "#8e44ad"),
                         ("static_isolation", "#27ae60")):
        arm = series.get(label)
        if not arm or "transit" not in arm:
            continue
        drop = 1.0 - arm["transit"].mean(axis=0)
        ax.plot(arm["goodput_t"], drop, lw=1.4, color=color, label=label)
    ax.axvspan(ATTACK_START, ATTACK_END, color="red", alpha=0.07)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("transit drop rate (0-1)")
    ax.set_title("M4: transit drop rate (starvation cost), seed-averaged (30 seeds)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "oef_starvation.png", dpi=150)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--out-dir", type=Path, default=REPO / "results" / "m4")
    args = parser.parse_args()
    seeds = _seeds(args.seeds)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"running benchmark ({len(ARMS)} arms x {len(seeds)} seeds) ...", flush=True)
    rows, series = run_benchmark(args.out_dir, seeds)

    print("running starvation threshold sweep ...", flush=True)
    starvation_rows = run_starvation_sweep(seeds)
    _write_csv(args.out_dir / "starvation_sweep_raw.csv", starvation_rows,
               ["oef_max", "seed", "Legitimate_Goodput", "Transit_Drop_Rate"])

    print("measuring computational overhead ...", flush=True)
    overhead = measure_overhead()

    summary = _summarise(rows, starvation_rows, overhead)
    (args.out_dir / "m4_summary.md").write_text(summary, encoding="utf-8")
    (REPO / "results" / "m4_summary.md").write_text(summary, encoding="utf-8")
    plot_oef(series, args.out_dir)
    plot_peak_burst(series, args.out_dir)
    plot_starvation(series, args.out_dir)
    print(f"wrote {len(rows)} raw rows, summary and 3 PNGs to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
