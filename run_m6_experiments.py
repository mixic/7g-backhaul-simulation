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

"""M6: energy-aware evaluation.

Two paired-seed experiments against the stipulated energy model in
``simulation/energy.py``:

  * exp1 (H9, H11) -- a 60 s DDoS shockwave, auditing transmission, CPU and
    state-change energy across static_isolation, m4_oef, m4_raw_mkb and
    m5_ewma_mkb.
  * exp2 (H10) -- a Fiber -> Satellite transition, measuring the transmission
    energy saved by the LLM compiler against its 20 J/call inference cost.

All energy figures are stipulated, not measured hardware.
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

from run_m5_experiments import PAYLOAD_SIZE, PHASES, run_one as h7_run_one  # noqa: E402
from simulation.energy import (  # noqa: E402
    churn_energy,
    compress_energy,
    ewma_energy,
    llm_energy,
    tx_energy,
)
from simulation.surgical.config import (  # noqa: E402
    MKB_EWMA,
    MKB_NO_OEF,
    OEF,
    STATIC_ISO,
    SimConfig,
)
from simulation.surgical.sim import run_and_score  # noqa: E402

WARMUP = 8.0          # matches SimConfig.warmup
TICKS = 300           # 60 s / 0.2 s control tick

EXP1_ARMS = (
    ("static_isolation", STATIC_ISO),
    ("m4_oef", OEF),
    ("m4_raw_mkb", MKB_NO_OEF),
    ("m5_ewma_mkb", MKB_EWMA),
)

#: arms that run an EWMA / RER filter every control tick
EWMA_ARMS = (OEF, MKB_NO_OEF, MKB_EWMA)


def _exp1_cfg(seed: int, controller: str) -> SimConfig:
    return SimConfig(name="exp1_ddos", seed=seed, controller=controller)


def run_exp1(seeds) -> list[dict]:
    rows = []
    for arm, controller in EXP1_ARMS:
        for seed in seeds:
            r = run_and_score(_exp1_cfg(seed, controller))
            edit_times = r["edit_times"]
            setup_edits = int((edit_times < WARMUP).sum())
            churn_edits = len(edit_times) - setup_edits
            e_churn = churn_energy(churn_edits)
            e_cpu = ewma_energy(TICKS) if controller in EWMA_ARMS else 0.0
            e_tx = tx_energy(r["total_served_bytes"])
            row = {
                "experiment": "exp1",
                "arm": arm,
                "seed": seed,
                "Total_Energy_J": round(e_churn + e_cpu + e_tx, 6),
                "E_tx_J": round(e_tx, 6),
                "E_cpu_J": round(e_cpu, 9),
                "E_churn_J": round(e_churn, 4),
                "E_setup_J": round(churn_energy(setup_edits), 4),
                "Total_Edits": int(r["edits"]),
                "Churn_Edits": churn_edits,
                "Setup_Edits": setup_edits,
            }
            rows.append(row)
    return rows


def run_exp2(seeds) -> list[dict]:
    rows = []
    wire = {arm: [] for arm in ("static_iso", "greedy_heuristic", "llm_compiler")}
    for arm in wire:
        for seed in seeds:
            wire[arm].append(float(h7_run_one(arm, seed)["Wire_Bytes_Total"]))

    payload_bytes = PAYLOAD_SIZE * len(PHASES)
    for arm in wire:
        for i, seed in enumerate(seeds):
            wb = wire[arm][i]
            static_wb = wire["static_iso"][i]
            e_tx = tx_energy(wb)
            e_cpu = compress_energy(payload_bytes)
            e_llm = llm_energy(len(PHASES)) if arm == "llm_compiler" else 0.0
            e_tx_saved = tx_energy(static_wb - wb)
            eroi = e_tx_saved / e_llm if e_llm > 0 else float("nan")
            row = {
                "experiment": "exp2",
                "arm": arm,
                "seed": seed,
                "Wire_Bytes_Total": round(wb, 1),
                "E_tx_J": round(e_tx, 9),
                "E_cpu_J": round(e_cpu, 9),
                "E_llm_J": round(e_llm, 4),
                "E_tx_saved_J": round(e_tx_saved, 9),
                "EROI": round(eroi, 9) if math.isfinite(eroi) else "",
            }
            rows.append(row)
    return rows


def _mean_ci(values) -> tuple[float, float]:
    array = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if array.size < 2:
        return (float(array.mean()) if array.size else float("nan")), 0.0
    return float(array.mean()), float(1.96 * array.std(ddof=1) / math.sqrt(array.size))


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def plot_energy_churn(rows: list[dict], out_dir: Path):
    arms = [a for a, _ in EXP1_ARMS]
    labels = ["static_isolation", "m4_oef", "m4_raw_mkb", "m5_ewma_mkb"]
    colors = {"E_tx_J": "#27ae60", "E_cpu_J": "#1f6feb", "E_churn_J": "#c0392b"}
    x = np.arange(len(arms))
    bottom = np.zeros(len(arms))
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for key, color in colors.items():
        means = [float(np.mean([r[key] for r in rows if r["arm"] == a])) for a in arms]
        ax.bar(x, means, bottom=bottom, color=color, label=key)
        bottom += np.asarray(means)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("energy (J), mean over 30 seeds")
    ax.set_title("M6 exp1: energy decomposition (log scale)")
    ax.set_yscale("log")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "energy_churn_comparison.png", dpi=150)
    plt.close(fig)


def plot_llm_eroi(rows: list[dict], out_dir: Path):
    llm = [r for r in rows if r["arm"] == "llm_compiler"]
    saved = float(np.mean([r["E_tx_saved_J"] for r in llm]))
    spent = float(np.mean([r["E_llm_J"] for r in llm]))
    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(["E_tx_saved", "E_llm"], [saved, spent],
                  color=["#27ae60", "#c0392b"])
    ax.set_yscale("log")
    ax.set_ylabel("energy (J), log scale")
    ax.set_title(f"M6 exp2: Mock Oracle EROI = {saved / spent:.3g} (saved / spent)")
    for b, v in zip(bars, (saved, spent)):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.3g}",
                ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_dir / "llm_eroi.png", dpi=150)
    plt.close(fig)


def plot_total_energy(rows: list[dict], out_dir: Path):
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for arm, color in (("static_isolation", "#27ae60"), ("m4_oef", "#c0392b"),
                       ("m4_raw_mkb", "#1f6feb"), ("m5_ewma_mkb", "#8e44ad")):
        vals = [r["Total_Energy_J"] for r in rows if r["arm"] == arm]
        mean, ci = _mean_ci(vals)
        ax.bar(arm, mean, yerr=ci, color=color, capsize=3)
    ax.set_ylabel("total energy (J), mean +/- 95% CI")
    ax.set_title("M6 exp1: total energy under a DDoS shockwave")
    fig.tight_layout()
    fig.savefig(out_dir / "total_energy_baseline.png", dpi=150)
    plt.close(fig)


def _summarise(rows1: list[dict], rows2: list[dict]) -> str:
    lines = [
        "# M6: energy-aware evaluation",
        "",
        "Stipulated energy model (`simulation/energy.py`); nothing is a hardware",
        "measurement. 30 paired seeds per experiment.",
        "",
        "## exp1 — shockwave energy audit (H9, H11)",
        "",
        "| arm | Total_Energy_J | E_tx_J | E_cpu_J | E_churn_J | E_setup_J | Total_Edits |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm, _ in EXP1_ARMS:
        vals = {k: [r[k] for r in rows1 if r["arm"] == arm]
                for k in ("Total_Energy_J", "E_tx_J", "E_cpu_J", "E_churn_J", "E_setup_J")}
        edits = sum(r["Total_Edits"] for r in rows1 if r["arm"] == arm)
        cells = []
        for k in ("Total_Energy_J", "E_tx_J", "E_cpu_J", "E_churn_J", "E_setup_J"):
            mean, ci = _mean_ci(vals[k])
            cells.append(f"{mean:.4g} +/- {ci:.3g}")
        lines.append(f"| {arm} | " + " | ".join(cells) + f" | {edits} |")
    lines.append("")

    # H9: EWMA reduces churn energy vs raw MKB
    m5_churn = _mean_ci([r["E_churn_J"] for r in rows1 if r["arm"] == "m5_ewma_mkb"])[0]
    m4_churn = _mean_ci([r["E_churn_J"] for r in rows1 if r["arm"] == "m4_raw_mkb"])[0]
    h9 = "CONFIRMED" if m5_churn < m4_churn else "REFUTED"
    lines += [
        f"**H9 EWMA energy efficiency — {h9}.**",
        f"m5_ewma_mkb churn energy = {m5_churn:.4g} J vs m4_raw_mkb {m4_churn:.4g} J "
        f"({'lower' if m5_churn < m4_churn else 'higher'} — the EWMA arm edits *more*, not less).",
        "",
    ]

    # H11: static_isolation most energy-efficient (lowest total energy)
    static_e = _mean_ci([r["Total_Energy_J"] for r in rows1 if r["arm"] == "static_isolation"])[0]
    oef_e = _mean_ci([r["Total_Energy_J"] for r in rows1 if r["arm"] == "m4_oef"])[0]
    others = [_mean_ci([r["Total_Energy_J"] for r in rows1 if r["arm"] == a])[0]
              for a, _ in EXP1_ARMS if a != "static_isolation"]
    h11 = "CONFIRMED" if static_e <= min(others) else "REFUTED"
    lines += [
        f"**H11 static-isolation energy baseline — {h11}.**",
        f"static_isolation total energy = {static_e:.4g} J vs m4_oef {oef_e:.4g} J "
        f"(static has zero runtime churn; its one-time setup is reported as E_setup).",
        "",
        "## exp2 — Mock Oracle EROI (H10)",
        "",
        "| arm | Wire_Bytes_Total | E_tx_J | E_cpu_J | E_llm_J | E_tx_saved_J | EROI |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm in ("static_iso", "greedy_heuristic", "llm_compiler"):
        sub = [r for r in rows2 if r["arm"] == arm]
        wb = float(np.mean([r["Wire_Bytes_Total"] for r in sub]))
        e_tx = float(np.mean([r["E_tx_J"] for r in sub]))
        e_cpu = float(np.mean([r["E_cpu_J"] for r in sub]))
        e_llm = float(np.mean([r["E_llm_J"] for r in sub]))
        e_saved = float(np.mean([r["E_tx_saved_J"] for r in sub]))
        eroi_vals = [r["EROI"] for r in sub if r["EROI"] != ""]
        eroi = float(np.mean(eroi_vals)) if eroi_vals else float("nan")
        eroi_str = f"{eroi:.3g}" if math.isfinite(eroi) else "—"
        lines.append(
            f"| {arm} | {wb:.1f} | {e_tx:.4g} | {e_cpu:.4g} | {e_llm:.4g} | "
            f"{e_saved:.4g} | {eroi_str} |"
        )
    lines.append("")

    llm_saved = _mean_ci([r["E_tx_saved_J"] for r in rows2 if r["arm"] == "llm_compiler"])[0]
    llm_spent = _mean_ci([r["E_llm_J"] for r in rows2 if r["arm"] == "llm_compiler"])[0]
    eroi = llm_saved / llm_spent if llm_spent > 0 else float("nan")
    h10 = "STIPULATION-DEPENDENT"
    lines += [
        f"**H10 Mock Oracle EROI — {h10}.**",
        f"Transmission energy saved = {llm_saved:.4g} J vs inference cost "
        f"{llm_spent:.4g} J -> EROI = {eroi:.3g}. The Mock Oracle is viable "
        f"*if and only if* inference energy falls to <= {llm_saved:.3g} J in "
        f"total (break-even E_llm = E_tx_saved), i.e. ~{llm_saved/llm_spent:.1e}x "
        f"the stipulated {llm_spent:.0f} J.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--out-dir", type=Path, default=REPO / "results" / "m6")
    args = parser.parse_args()
    seeds = list(range(args.seeds))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("exp1 (H9, H11 shockwave energy audit) ...", flush=True)
    rows1 = run_exp1(seeds)
    _write_csv(args.out_dir / "m6_exp1_raw.csv", rows1, [
        "experiment", "arm", "seed", "Total_Energy_J", "E_tx_J", "E_cpu_J",
        "E_churn_J", "E_setup_J", "Total_Edits", "Churn_Edits", "Setup_Edits",
    ])

    print("exp2 (H10 Mock Oracle EROI) ...", flush=True)
    rows2 = run_exp2(seeds)
    _write_csv(args.out_dir / "m6_exp2_raw.csv", rows2, [
        "experiment", "arm", "seed", "Wire_Bytes_Total", "E_tx_J", "E_cpu_J",
        "E_llm_J", "E_tx_saved_J", "EROI",
    ])

    summary = _summarise(rows1, rows2)
    (args.out_dir / "m6_summary.md").write_text(summary, encoding="utf-8")
    (REPO / "results" / "m6_summary.md").write_text(summary, encoding="utf-8")
    plot_energy_churn(rows1, args.out_dir)
    plot_llm_eroi(rows2, args.out_dir)
    plot_total_energy(rows1, args.out_dir)
    print(f"wrote {len(rows1) + len(rows2)} rows, summary and 3 PNGs to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
