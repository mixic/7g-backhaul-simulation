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


"""M14: verify every number in the Paper A and Paper B abstracts.

Read-only.  Every check reads a committed CSV (or, where a quantity has no
CSV, the committed data file that records it) and prints the value the
abstract must match.  Run from the repository root::

    py -3 tools/verify_m14.py
"""

from __future__ import annotations

import ast
import csv
import importlib.util
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from scipy import stats

ROOT = Path(__file__).resolve().parents[1]

VERDICT_FILES = (
    ("validation/layering/results/verdicts.csv", "P1-P7"),
    ("validation/real_stack/results/verdicts.csv", "P8-P12"),
    ("validation/round2/results/verdicts.csv", "P13-P16"),
    ("validation/round3/results/verdicts.csv", "P17"),
)


def load(path: str) -> list[dict[str, str]]:
    with open(ROOT / path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def obs(path: str) -> list[dict[str, str]]:
    return load(path)


def values(rows, scenario, policy, metric) -> list[float]:
    return [
        float(r["value"])
        for r in rows
        if r["scenario"] == scenario and r["policy"] == policy and r["metric"] == metric
    ]


def mean(xs: list[float]) -> float:
    return statistics.fmean(xs)


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def verdict_counts() -> None:
    section("1. VERDICT FILES: rows, categories and outcomes")
    total_rows = 0
    all_predictions: set[str] = set()
    goal_scope: set[str] = set()
    for path, label in VERDICT_FILES:
        rows = load(path)
        total_rows += len(rows)
        preds = {r["prediction"] for r in rows}
        all_predictions |= preds
        if label != "P17":
            goal_scope |= preds
        cases = {r["case"] for r in rows if r.get("case")}
        print(f"{label:7s} rows={len(rows):2d}  distinct prediction values={len(preds):2d}  "
              f"distinct cases={len(cases):2d}  verdicts={dict(Counter(r['verdict'] for r in rows))}")
        if label == "P1-P7":
            per_pred = defaultdict(list)
            for r in rows:
                per_pred[r["prediction"]].append(r["verdict"])
            print(f"        per-prediction (any fidelity refuted -> REFUTED): "
                  f"{ {k: ('REFUTED' if 'REFUTED' in v else 'CONFIRMED') for k, v in sorted(per_pred.items())} }")

    print()
    print(f"total verdict rows: {total_rows}")
    print(f"distinct prediction values, all four files: {len(all_predictions)} -> {sorted(all_predictions)}")
    print(f"distinct main categories, first three files only (the goal script): {len(goal_scope)} -> {sorted(goal_scope)}")
    categories = {re.match(r"P\d+", p).group(0) for p in all_predictions}
    print(f"normalised categories (P17a-f -> P17): {len(categories)} -> {sorted(categories, key=lambda x: int(x[1:]))}")


def scored_counts() -> None:
    section("2. SCORED PREDICTIONS (the unit Table 8 and the Brier denominators use)")
    spec = importlib.util.spec_from_file_location("mpt_m14", ROOT / "tools" / "make_paper_tables.py")
    mpt = importlib.util.module_from_spec(spec)
    sys.modules["mpt_m14"] = mpt
    spec.loader.exec_module(mpt)
    data = mpt.Data.load()
    matrix = mpt.verdict_matrix(data)
    counts = mpt.headline_counts(matrix)
    print(f"verdict-matrix rows: {len(matrix)} "
          f"(P1-P7 contribute 21 fidelity rows that collapse to 7 predictions)")
    for key, (confirmed, total) in counts.items():
        print(f"  {key:12s} {confirmed} of {total}")
    print(f"total scored predictions: {counts['total'][1]}, confirmed {counts['total'][0]}")


def paper_a_numbers() -> None:
    section("3. PAPER A: abstract numbers")
    linux = obs("validation/layering/results/linux_observations.csv")
    model = obs("validation/layering/results/model_observations.csv")
    real = obs("validation/real_stack/results/observations.csv")

    # P4: six orderings, one wire size.
    p4 = {
        policy: mean(values(linux, "P4", policy, "wire_bytes"))
        for policy in sorted({r["policy"] for r in linux if r["scenario"] == "P4"})
    }
    p4_model = {
        policy: mean(values(model, "P4", policy, "wire_bytes"))
        for policy in sorted({r["policy"] for r in model if r["scenario"] == "P4"})
    }
    print(f"P4 wire bytes by ordering (linux): {p4}")
    print(f"P4 wire bytes by ordering (model): {p4_model}")
    print(f"  -> all six orderings equal 1104 B: {set(p4.values()) == {1104.0}}")

    # P2: two orderings, 224 B apart.
    e_to_f = mean(values(linux, "P2", "E_to_F", "wire_bytes"))
    f_to_e = mean(values(linux, "P2", "F_to_E", "wire_bytes"))
    print(f"P2 wire bytes E->F {e_to_f:.0f}, F->E {f_to_e:.0f}, difference {f_to_e - e_to_f:.0f}")

    # P10: quantised ordering difference.  The real-stack CSV records
    # wire_bytes_min / wire_bytes_max per run; the two orderings are exact.
    pairs = defaultdict(dict)
    for policy in {r["policy"] for r in real if r["scenario"] == "P10"}:
        match = re.search(r"L(\d+)$", policy)
        if match:
            side = policy[: -len(match.group(0))].rstrip("_")
            pairs[int(match.group(1))][side] = mean(values(real, "P10", policy, "wire_bytes_min"))
    diffs = {}
    for length, sides in sorted(pairs.items()):
        if len(sides) == 2:
            diffs[length] = sides["P10_y_to_w"] - sides["P10_w_to_y"]
    print(f"P10 d(L) = wire(IPIP then WG) - wire(WG then IPIP): {diffs}")
    print(f"  -> non-empty and d(L) in {{-4, +12}}: {bool(diffs) and set(diffs.values()) <= {-4.0, 12.0}}")

    # P5: Linux delivery difference.
    c_to_f = mean(values(linux, "P5", "C_to_F", "delivery_percent"))
    f_to_c = mean(values(linux, "P5", "F_to_C", "delivery_percent"))
    print(f"P5 Linux delivery C->F {c_to_f:.2f} %, F->C {f_to_c:.2f} %, difference {c_to_f - f_to_c:+.2f} pp")
    print(f"  frozen expectation 0.9^3 - 0.9^6 = {(0.9 ** 3 - 0.9 ** 6) * 100:.2f} pp")

    # P8a: AH through NAT.
    p8a = mean(values(obs("validation/real_stack/results/observations.csv"), "P8", "P8a", "delivery_percent"))
    print(f"P8a AH through NAT delivery: {p8a:.1f} %")

    # P13: the same outer CE mark under three decapsulators.
    r2 = obs("validation/round2/results/observations.csv")
    p13 = {pol: mean(values(r2, "P13", pol, "delivery_percent")) for pol in ("P13a", "P13d", "P13f")}
    print(f"P13 delivery with outer CE: IPIP P13a {p13['P13a']:.1f} %, "
          f"WireGuard P13d {p13['P13d']:.1f} %, ESP P13f {p13['P13f']:.1f} %")

    # P16d: delivered range.
    r2 = obs("validation/round2/results/observations.csv")
    p16d = values(r2, "P16", "P16d", "delivered_datagrams")
    sent = values(r2, "P16", "P16d", "sent_datagrams")
    print(f"P16d delivered: min {min(p16d):.0f}, max {max(p16d):.0f}, n={len(p16d)} runs, "
          f"sent/run {min(sent):.0f}")

    # Brier scores.
    def brier(path: str) -> tuple[float, int]:
        rows = []
        for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 4 and re.fullmatch(r"P\d+[a-z_]*", cells[0]):
                rows.append((float(cells[1]), int(cells[2])))
        return statistics.fmean((c - o) ** 2 for c, o in rows), len(rows)

    b2, n2 = brier("validation/round2/results/calibration.md")
    b3, n3 = brier("validation/round3/results/calibration.md")
    print(f"round-2 Brier over {n2} scored predictions: {b2:.4f}")
    print(f"round-3 Brier over {n3} scored predictions: {b3:.4f}")

    # Tamper tests.
    print(f"tamper tests: {tamper_count()}")


def tamper_count() -> int:
    def methods(path: str, cls: str, exclude: set[str]) -> int:
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == cls:
                return sum(1 for n in node.body if isinstance(n, ast.FunctionDef)
                           and n.name.startswith("test_") and n.name not in exclude)
        return 0

    a = methods("tests/test_make_paper_tables.py", "TamperTests", {"test_a_refutation_is_reported_not_hidden"})
    b = methods("tests/test_lint_claims.py", "LintTests",
                {"test_committed_papers_pass", "test_facts_are_the_committed_values"})
    return a + b


def paper_b_numbers() -> None:
    section("4. PAPER B: abstract numbers")
    m4 = load("results/m4/final_benchmark_raw.csv")
    by_arm: dict[str, dict[int, dict[str, str]]] = defaultdict(dict)
    for row in m4:
        by_arm[row["arm"]][int(row["seed"])] = row
    print(f"m4 arms: {sorted(by_arm)}; seeds per arm: {sorted({len(v) for v in by_arm.values()})}")

    def paired_p(a: str, b: str, column: str):
        common = sorted(set(by_arm[a]) & set(by_arm[b]))
        xs = [float(by_arm[a][s][column]) for s in common]
        ys = [float(by_arm[b][s][column]) for s in common]
        t, p = stats.ttest_rel(xs, ys)
        return mean(xs), mean(ys), mean(xs) - mean(ys), p, len(common)

    oef_x, st_x, diff, p, n = paired_p("m4_oef", "static_isolation", "Legitimate_Goodput_CMRO2")
    print(f"OEF vs static goodput: {oef_x:.4f} vs {st_x:.4f}, diff {diff:+.4f}, paired p={p:.4f}, n={n}")
    mkb_x, lim_x, diff, p, n = paired_p("m4_mkb", "m3_surgical_1d", "Peak_State_Change_Speed")
    print(f"MKB vs 1-D limiter peak speed: {mkb_x:.2f} vs {lim_x:.2f}, diff {diff:+.2f}, paired p={p:.4f}, n={n}")
    print(f"combined OEF+MKB goodput: {mean([float(r['Legitimate_Goodput_CMRO2']) for r in by_arm['m4_combined'].values()]):.4f}")

    exp1 = load("results/m6/m6_exp1_raw.csv")
    edits = defaultdict(float)
    tx = defaultdict(list)
    for row in exp1:
        edits[row["arm"]] += float(row["Churn_Edits"])
        tx[row["arm"]].append(float(row["E_tx_J"]))
    ewma_ratio = edits["m5_ewma_mkb"] / edits["m4_raw_mkb"]
    print(f"churn edits over 30 seeds: raw MKB {edits['m4_raw_mkb']:.0f}, EWMA {edits['m5_ewma_mkb']:.0f}, "
          f"ratio {ewma_ratio:.4f} (+{(ewma_ratio - 1) * 100:.1f} %)")
    break_even_churn = (mean(tx["static_isolation"]) - mean(tx["m4_raw_mkb"])) / (edits["m4_raw_mkb"] / 30)
    print(f"static-vs-MKB churn break-even: {break_even_churn:.3f} J/edit "
          f"(= (E_tx_static - E_tx_mkb) / edits_per_seed); 5 J stipulation is {5 / break_even_churn:.1f}x")

    exp2 = load("results/m6/m6_exp2_raw.csv")
    saved = [float(r["E_tx_saved_J"]) for r in exp2 if r["arm"] == "llm_compiler"]
    llm = [float(r["E_llm_J"]) for r in exp2 if r["arm"] == "llm_compiler"]
    wire_static = mean([float(r["Wire_Bytes_Total"]) for r in exp2 if r["arm"] == "static_iso"])
    wire_llm = mean([float(r["Wire_Bytes_Total"]) for r in exp2 if r["arm"] == "llm_compiler"])
    eroi = mean(saved) / mean(llm)
    print(f"wire bytes static {wire_static:.1f} -> LLM {wire_llm:.1f} ({(1 - wire_llm / wire_static) * 100:.1f} % reduction)")
    print(f"E_tx_saved {mean(saved):.6e} J, E_llm {mean(llm):.1f} J, EROI {eroi:.3e}")
    print(f"break-even inference energy: {mean(saved) * 1000:.3f} mJ per 3-call transition, "
          f"{mean(saved) * 1000 / 3:.3f} mJ/call")

    # Arms and seed design.
    arms = {r["arm"] for r in m4} | {r["arm"] for r in exp1} | {r["arm"] for r in exp2}
    five = {"static_isolation", "m4_oef", "m4_mkb", "m5_ewma_mkb", "llm_compiler"}
    print(f"arms present in the M4/M6 CSVs: {sorted(arms)}")
    print(f"  -> the five controller arms of the Paper B table are all present: {five <= arms}")
    print(f"paired seeds: M4 {len(by_arm['m4_oef'])}, M6 exp1 {len({int(r['seed']) for r in exp1})}, "
          f"M6 exp2 {len({int(r['seed']) for r in exp2})}")

    # The 135x CPU claim has no CSV backing.
    cpu = any("813.4" in f.read_text(encoding="utf-8", errors="ignore")
              for f in (ROOT / "results").rglob("*.csv"))
    print(f"'813.4 us/tick' (the ~135x per-tick CPU claim) present in any results CSV: {cpu}")

    # 100-node fabric (scenario constant, not a CSV row).
    topo = (ROOT / "simulation" / "surgical" / "topology.py").read_text(encoding="utf-8")
    print(f"fabric size: topology.py says 100 nodes -> {'100 nodes' in topo}")


def main() -> int:
    print("M14 verification: committed data -> abstract numbers")
    print(f"repository: {ROOT}")
    verdict_counts()
    scored_counts()
    paper_a_numbers()
    paper_b_numbers()
    print()
    print("No files were modified by this script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
