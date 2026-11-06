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

"""Evaluate surgical, rate-controlled state updates on the 100-node fabric.

Implements the pre-registered tests in ``docs/surgical-rate-controlled.md``:
H1 (surgical advantage under a DDoS shockwave), H2 (rate control versus churn),
H3 (fiber->satellite MTU boundary) and H4 (savant hyper-specialisation).

Arms include two baselines, four ablations and one confound control:

* ``k8s``               Baseline A - static roles, slow central scaling
* ``pressure``          Baseline B - the previous iteration's global alpha law
* ``surgical``          the thesis arm
* ``surgical_unlimited``/``surgical_ab``/``surgical_global``  ablations
* ``static_isolation``  confound control - per-flow isolation, no trigger at all
* ``sav ant``           H4

Run::

    py tools/benchmark_surgical.py --replicates 30
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulation.surgical.config import (  # noqa: E402
    ALL_CONTROLLERS,
    K8S,
    PRESSURE,
    SAVANT,
    SURGICAL,
    SURGICAL_UNLIM,
    VDR_SURGICAL,
    scenario_exp1,
    scenario_exp2,
    scenario_exp3,
)
from simulation.surgical.sim import run_and_score  # noqa: E402

SCENARIOS = {
    "exp1_ddos": scenario_exp1,
    "exp2_churn": scenario_exp2,
    "exp3_boundary": scenario_exp3,
}
EXP3_ARMS = [K8S, PRESSURE, SURGICAL, SURGICAL_UNLIM, VDR_SURGICAL, SAVANT]
ARMS = {
    "exp1_ddos": list(ALL_CONTROLLERS),
    "exp2_churn": list(ALL_CONTROLLERS),
    "exp3_boundary": EXP3_ARMS,
}
DEFAULT_REPLICATES = 30
DEFAULT_SEED = 2026

SCALARS = (
    "ratio_p95",
    "ratio_p95_eff",
    "goodput_base",
    "goodput_shock",
    "goodput_loss",
    "gp_affected",
    "gp_other",
    "churn_max",
    "churn_mean",
    "churn_total",
    "churn_accel_max",
    "edits",
    "ns_classes_peak",
    "reasm_peak",
    "reasm_deadlock_frac",
    "loop_drops",
    "buffer_drops",
    "loss_drops",
    "p95_base",
    "p95_shock",
    "reasm_deadlock_k8s",
)


def _mean_ci(values: Sequence[float]) -> tuple[float, float]:
    array = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if array.size < 2:
        return (float(array.mean()) if array.size else float("nan")), 0.0
    return float(array.mean()), float(
        1.96 * array.std(ddof=1) / math.sqrt(array.size)
    )


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _job(args: tuple[str, int, str]):
    experiment, seed, controller = args
    cfg = SCENARIOS[experiment](seed, controller)
    try:
        return (experiment, controller, seed, run_and_score(cfg), None)
    except Exception:  # noqa: BLE001 - the report must record failures
        import traceback

        return (experiment, controller, seed, None, traceback.format_exc())


def _row(experiment: str, controller: str, seed: int, result: dict) -> dict:
    row = {
        "experiment": experiment,
        "arm": controller,
        "seed": seed,
        "p95_base": result["base"]["p95"],
        "p95_shock": result["shock"]["p95"],
    }
    for name in SCALARS:
        if name in ("p95_base", "p95_shock"):
            continue
        row[name] = result.get(name, float("nan"))
    return row


def _series(experiment: str, controller: str, results: list[dict]) -> list[dict]:
    """Seed-averaged time series for the figures."""
    out: list[dict] = []
    rolls = [r["roll_p95"] for r in results if len(r.get("roll_p95", [])) > 4]
    roll_t = [r["roll_t"] for r in results if len(r.get("roll_t", [])) > 4]
    if rolls:
        n = min(len(a) for a in rolls)
        mean = np.vstack([np.asarray(a[:n], float) for a in rolls]).mean(axis=0)
        t = np.asarray(roll_t[0][:n], float)
        for i in range(n):
            out.append(
                {
                    "experiment": experiment,
                    "arm": controller,
                    "series": "roll_p95",
                    "t": round(float(t[i]), 3),
                    "value": float(mean[i]),
                }
            )
    churns = [r["churn_rate"] for r in results if len(r.get("churn_rate", [])) > 4]
    if churns:
        n = min(len(a) for a in churns)
        mean = np.vstack([np.asarray(a[:n], float) for a in churns]).mean(axis=0)
        for i in range(n):
            out.append(
                {
                    "experiment": experiment,
                    "arm": controller,
                    "series": "churn_rate",
                    "t": round(i * 0.1, 3),
                    "value": float(mean[i]),
                }
            )
    return out


def _verdicts(by_arm: dict[str, dict[str, float]], arms: dict) -> list[dict]:
    def g(exp: str, arm: str, field: str) -> float:
        return by_arm.get(exp, {}).get(f"{arm}:{field}", float("nan"))

    rows: list[dict] = []
    s_ratio = g("exp1_ddos", SURGICAL, "ratio_p95")
    s_gp = g("exp1_ddos", SURGICAL, "goodput_shock")
    b_ratio = g("exp1_ddos", PRESSURE, "ratio_p95")
    b_gp = g("exp1_ddos", PRESSURE, "goodput_shock")
    s_peak = g("exp2_churn", SURGICAL, "churn_max")
    s_sust = g("exp2_churn", SURGICAL, "churn_mean")
    b_peak = g("exp2_churn", PRESSURE, "churn_max")
    b_sust = g("exp2_churn", PRESSURE, "churn_mean")
    unrestr = g("exp2_churn", SURGICAL_UNLIM, "goodput_shock")
    reasm = g("exp3_boundary", SURGICAL, "reasm_peak")
    dead = g("exp3_boundary", SURGICAL, "reasm_deadlock_frac")
    sav_aff = g("exp1_ddos", SAVANT, "gp_affected")
    surg_aff = g("exp1_ddos", SURGICAL, "gp_affected")
    sav_oth = g("exp1_ddos", SAVANT, "gp_other")
    surg_oth = g("exp1_ddos", SURGICAL, "gp_other")

    def add(h, cond, value, passed, note=""):
        rows.append(
            {
                "hypothesis": h,
                "condition": cond,
                "value": round(float(value), 4) if np.isfinite(value) else "",
                "verdict": "pass" if passed else "fail",
                "note": note,
            }
        )

    add("H1", "surgical p95 ratio <= 1.5", s_ratio, s_ratio <= 1.5)
    add("H1", "surgical goodput > 95%", s_gp * 100, s_gp > 0.95)
    add("H1", "Baseline B p95 ratio > 2.2", b_ratio, b_ratio > 2.2)
    add("H1", "Baseline B goodput loss > 10%", (1.0 - b_gp) * 100, (1.0 - b_gp) > 0.10)
    add(
        "H2",
        "surgical sustained state-change rate < 50% of Baseline B",
        s_sust / b_sust if b_sust else float("nan"),
        s_sust < 0.5 * b_sust,
    )
    add(
        "H2",
        "surgical PEAK state-change rate also < 50% of Baseline B",
        s_peak / b_peak if b_peak else float("nan"),
        s_peak < 0.5 * b_peak,
        "per-node token bucket bounds edit frequency, not fleet-wide burst",
    )
    add(
        "H2",
        "rate cap beats no rate cap on goodput",
        unrestr,
        np.isfinite(unrestr) and s_gp > unrestr,
    )
    k8s_dead = g("exp3_boundary", K8S, "reasm_deadlock_frac")
    add(
        "H3",
        "reassembly buffer engaged at all (> 0 kB)",
        reasm / 1024.0,
        reasm > 0.0,
        "0 means the MTU-mismatch mechanism never fired: UNTESTED, not a pass",
    )
    add(
        "H3",
        "surgical reduces reassembly deadlock below Baseline A",
        dead,
        dead < k8s_dead,
        f"Baseline A deadlock fraction {k8s_dead:.3f}",
    )
    add(
        "H4",
        "savant affected-name delivery beats the surgical arm",
        sav_aff,
        sav_aff > surg_aff,
    )
    add("H4", "savant costs unrelated traffic", sav_oth, sav_oth < surg_oth)
    return rows


def run_benchmark(
    output_dir: Path,
    replicates: int = DEFAULT_REPLICATES,
    seed: int = DEFAULT_SEED,
    workers: int = 0,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    seeds = [int(v) for v in rng.integers(0, 2**31 - 1, size=replicates)]

    tasks = [
        (experiment, s, arm)
        for experiment, arms in ARMS.items()
        for arm in arms
        for s in seeds
    ]
    nworkers = workers or min(16, os.cpu_count() or 1)
    results: dict[tuple[str, str], list[dict]] = {}
    failures: list[str] = []
    if nworkers > 1:
        with Pool(processes=nworkers) as pool:
            for experiment, arm, s, result, err in pool.imap_unordered(
                _job, tasks, chunksize=2
            ):
                if err is not None:
                    failures.append(f"{experiment}/{arm}/{s}: {err.splitlines()[-1]}")
                    continue
                results.setdefault((experiment, arm), []).append(result)
    else:
        for task in tasks:
            experiment, arm, s, result, err = _job(task)
            if err is not None:
                failures.append(f"{experiment}/{arm}/{s}: {err.splitlines()[-1]}")
                continue
            results.setdefault((experiment, arm), []).append(result)

    per_seed: list[dict] = []
    summary: list[dict] = []
    series: list[dict] = []
    by_arm: dict[str, dict[str, float]] = {}
    for (experiment, arm), rows in sorted(results.items()):
        for result in sorted(rows, key=lambda r: r["seed"]):
            per_seed.append(_row(experiment, arm, result["seed"], result))
            for name in SCALARS:
                value = per_seed[-1].get(name, float("nan"))
                by_arm.setdefault(experiment, {})[f"{arm}:{name}"] = float("nan")
        for name in SCALARS:
            values = [row.get(name, float("nan")) for row in per_seed
                      if row["experiment"] == experiment and row["arm"] == arm]
            mean, interval = _mean_ci(values)
            by_arm[experiment][f"{arm}:{name}"] = mean
            summary.append(
                {
                    "experiment": experiment,
                    "arm": arm,
                    "metric": name,
                    "replicates": len(values),
                    "mean": mean,
                    "ci95": interval,
                }
            )
        series.extend(_series(experiment, arm, rows))

    verdicts = _verdicts(by_arm, ARMS)
    _write_csv(output_dir / "per_seed.csv", per_seed)
    _write_csv(output_dir / "summary.csv", summary)
    _write_csv(output_dir / "timeseries.csv", series)
    _write_csv(output_dir / "verdict.csv", verdicts)
    _write_csv(output_dir / "failures.csv", [{"failure": f} for f in failures])
    return {
        "seeds": len(seeds),
        "runs": len(per_seed),
        "failures": failures,
        "verdicts": verdicts,
        "by_arm": by_arm,
        "series": series,
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicates", type=int, default=DEFAULT_REPLICATES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO / "output" / "surgical",
    )
    args = parser.parse_args()
    report = run_benchmark(args.output_dir, args.replicates, args.seed, args.workers)
    print(f"runs: {report['runs']}  seeds: {report['seeds']}  "
          f"failures: {len(report['failures'])}")
    for row in report["verdicts"]:
        print(f"  {row['hypothesis']:3s} {row['verdict']:4s} "
              f"{row['condition']}: {row['value']}")
    if report["failures"]:
        for failure in report["failures"][:5]:
            print("  FAIL", failure)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
