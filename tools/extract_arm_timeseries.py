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

"""Persist the per-tick legitimate-goodput traces that M4 computes in memory.

Why this script exists
----------------------
``run_m4_experiments.py`` computes a rolling legitimate-goodput trace per run
(``simulation/surgical/sim.py::rolling_goodput``, 2 s trailing window, 0.5 s
step, t in [2, 60)) and uses it only for a PNG.  It never writes the trace to
CSV, so the committed artifact cannot back a time-series figure.  Rather than
invent a curve, this script *re-runs the frozen harness* with the same arm
definitions and the same seed set, and refuses to write the trace unless every
recomputed aggregate row reproduces ``results/m4/final_benchmark_raw.csv``
exactly.  The trace is therefore a verified reproduction, not new evidence.

Outputs
-------
* ``results/m4/arm_timeseries.csv``      arm, seed, time_s, goodput_percent
* ``results/m4/timeseries_reproduction.md``  what was checked, and the result

Run from the repository root::

    py tools/extract_arm_timeseries.py
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulation.surgical.config import (  # noqa: E402
    MKB,
    MKB_NO_OEF,
    OEF,
    STATIC_ISO,
    SURGICAL,
    SimConfig,
)
from simulation.surgical.sim import run_and_score  # noqa: E402

ARMS = (
    ("static_isolation", STATIC_ISO),
    ("m3_surgical_1d", SURGICAL),
    ("m4_oef", OEF),
    ("m4_mkb", MKB_NO_OEF),
    ("m4_combined", MKB),
)
COMMITTED = REPO / "results" / "m4" / "final_benchmark_raw.csv"
TRACE = REPO / "results" / "m4" / "arm_timeseries.csv"
REPORT = REPO / "results" / "m4" / "timeseries_reproduction.md"
TRACE_FIELDS = ("arm", "seed", "time_s", "goodput_percent")
#: Decimal places used by ``run_m4_experiments._round`` when it wrote the CSV.
PRECISION = {"Total_Throughput_CBF": 4}
DEFAULT_PRECISION = 6
COMPARED = (
    "Total_Throughput_CBF",
    "Legitimate_Goodput_CMRO2",
    "OEF_Value",
    "Peak_State_Change_Speed",
    "Number_of_Edits",
    "False_Positive_Edits",
    "Transit_Drop_Rate",
    "Compensatory_Distance",
    "Mean_Util",
    "Mean_OEF",
)


def _load_committed(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _tolerance(field: str) -> float:
    digits = PRECISION.get(field, DEFAULT_PRECISION)
    # Half a unit in the last stored place, plus a guard for binary
    # representation noise: a value that sits exactly on a rounding boundary
    # (e.g. 0.4296875 at 6 dp) must not fail on the 17th significant digit.
    return 0.5 * 10.0 ** -digits + 1e-12


def _reproduce(arms, seeds) -> tuple[list[dict], list[dict]]:
    aggregates: list[dict] = []
    trace_rows: list[dict] = []
    for label, controller in ARMS:
        if label not in arms:
            continue
        for seed in seeds:
            result = run_and_score(SimConfig(name="exp1_ddos", seed=seed, controller=controller))
            aggregates.append(
                {
                    "arm": label,
                    "seed": seed,
                    "Total_Throughput_CBF": result["cbf_shock"],
                    "Legitimate_Goodput_CMRO2": result["goodput_shock"],
                    "OEF_Value": result["oef_peak"],
                    "Peak_State_Change_Speed": result["churn_max"],
                    "Number_of_Edits": int(result["edits"]),
                    "False_Positive_Edits": int((result["edit_times"] < 29.5).sum()),
                    "Transit_Drop_Rate": 1.0 - result["gp_other"],
                    "Compensatory_Distance": result["compensatory_distance"],
                    "Mean_Util": result["mean_util"],
                    "Mean_OEF": result["mean_oef"],
                }
            )
            times = result["roll_goodput_t"]
            values = result["roll_goodput"]
            for time_s, goodput in zip(times, values, strict=True):
                if not math.isfinite(float(goodput)):
                    continue
                trace_rows.append(
                    {
                        "arm": label,
                        "seed": seed,
                        "time_s": round(float(time_s), 3),
                        "goodput_percent": round(100.0 * float(goodput), 6),
                    }
                )
    return aggregates, trace_rows


def _verify(committed: list[dict[str, str]], observed: list[dict]) -> tuple[list[str], int]:
    reference = {(row["arm"], int(row["seed"])): row for row in committed}
    problems: list[str] = []
    checked = 0
    for row in observed:
        key = (row["arm"], row["seed"])
        if key not in reference:
            problems.append(f"{key[0]}/{key[1]}: not present in the committed CSV")
            continue
        expected = reference[key]
        checked += 1
        for field in COMPARED:
            cell = expected[field]
            got = float(row[field])
            if cell == "":
                # ``run_m4_experiments._round`` writes an empty cell for non-finite
                # values (e.g. Compensatory_Distance for arms that never navigate
                # the 4-D state).  The reproduction must be non-finite too.
                if math.isfinite(got):
                    problems.append(
                        f"{key[0]}/{key[1]}/{field}: committed an empty cell, reproduced {got!r}"
                    )
                continue
            want = float(cell)
            if not math.isfinite(got) or abs(want - got) > _tolerance(field):
                problems.append(
                    f"{key[0]}/{key[1]}/{field}: committed {want!r} != reproduced {got!r} "
                    f"(tolerance {_tolerance(field):g})"
                )
    return problems, checked


def _write_trace(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRACE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _write_report(
    path: Path,
    *,
    arms: list[str],
    seeds: list[int],
    rows: list[dict],
    checked: int,
    problems: list[str],
) -> None:
    status = "PASS" if not problems else "FAIL"
    lines = [
        "# Arm time series: reproduction record",
        "",
        f"**Status: {status}.** Generated by `tools/extract_arm_timeseries.py`; do not edit by hand.",
        "",
        "## Why",
        "",
        "`run_m4_experiments.py` computes a rolling legitimate-goodput trace per run and",
        "uses it only for a PNG; it never writes the trace to CSV. The committed CSVs",
        "therefore contain no per-tick goodput for the controller arms, which is why",
        "paper B's time-series figure cannot be built from them alone. This record",
        "documents the regeneration that produced `results/m4/arm_timeseries.csv`.",
        "",
        "## What was reproduced",
        "",
        f"- Arms: {', '.join(f'`{arm}`' for arm in arms)}.",
        f"- Seeds: the {len(seeds)} M3/M4 paired seed set, taken from"
        " `results/m4/final_benchmark_raw.csv` (identical to"
        " `run_m4_experiments._seeds(30)`; the script asserts this).",
        "- Configuration: `SimConfig(name=\"exp1_ddos\", seed=..., controller=...)` — exactly",
        "  the `_cfg` of `run_m4_experiments.py`: 60 s run, 30 s baseline, 10 s DDoS",
        "  shockwave at t = 30 s, 20 s recovery.",
        "- Trace: `simulation/surgical/sim.py::rolling_goodput(res, 2.0, 60.0)` —",
        "  delivered/offered over a 2 s trailing window, sampled every 0.5 s.",
        "",
        "## Verification",
        "",
        f"Every recomputed aggregate row was compared against"
        f" `results/m4/final_benchmark_raw.csv` on all {len(COMPARED)} reported metrics,",
        "at the precision the committed file itself stores"
        " (4 dp for `Total_Throughput_CBF`, 6 dp otherwise).",
        "",
        f"- Rows compared: **{checked}** of {len(rows)} reproduced rows.",
        f"- Mismatches: **{len(problems)}**.",
    ]
    if problems:
        lines += ["", "```text", *problems[:40], "```"]
    lines += [
        "",
        "## Consequence for the paper",
        "",
        "The trace is a *reproduction*, not new evidence: it adds no runs, no seeds and",
        "no configuration. Any row that failed to match the committed CSV would have",
        "aborted the write, so the figure drawn from this trace is drawn from the same",
        "model state that produced the committed verdicts.",
        "",
        "Regenerate with:",
        "",
        "```powershell",
        "py tools\\extract_arm_timeseries.py",
        "```",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--committed", type=Path, default=COMMITTED)
    parser.add_argument("--trace", type=Path, default=TRACE)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument(
        "--arms",
        nargs="+",
        default=[label for label, _ in ARMS],
        choices=[label for label, _ in ARMS],
    )
    parser.add_argument("--allow-mismatch", action="store_true", help="write the trace even if verification fails")
    args = parser.parse_args(argv)

    committed = _load_committed(args.committed)
    seeds: list[int] = []
    for row in committed:
        if row["arm"] == "static_isolation":
            seeds.append(int(row["seed"]))
    if not seeds:
        raise SystemExit(f"no static_isolation rows in {args.committed}")

    from run_m4_experiments import _seeds  # noqa: PLC0415  (import after REPO is on sys.path)

    expected_seeds = _seeds(len(seeds))
    if expected_seeds != seeds:
        raise SystemExit(
            "seed set drifted from run_m4_experiments._seeds(); refusing to reproduce "
            f"({seeds[:3]}... != {expected_seeds[:3]}...)"
        )

    observed, trace_rows = _reproduce(set(args.arms), seeds)
    problems, checked = _verify(committed, observed)
    _write_report(
        args.report,
        arms=sorted(set(args.arms)),
        seeds=seeds,
        rows=observed,
        checked=checked,
        problems=problems,
    )
    if problems and not args.allow_mismatch:
        print(f"verification FAILED with {len(problems)} mismatch(es); trace not written")
        for problem in problems[:10]:
            print(f"  {problem}")
        print(f"see {args.report}")
        return 1
    _write_trace(args.trace, trace_rows)
    print(
        f"verified {checked} aggregate rows against {args.committed.name}; "
        f"wrote {len(trace_rows)} trace rows to {args.trace}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


