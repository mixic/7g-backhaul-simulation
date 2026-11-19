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

"""Status analysis for the M8 postmortem study after two blind LLM coding passes.

The frozen protocol wants **C1 = the author** and **C2 = an independent blind
coder**, with a kappa gate between them and C3 adjudication of disagreements.
This run has neither an author-coded C1 nor a C3.  What it does have is two
independent blind passes by the same model configuration (``C2`` and the
replicate ``C2b``), each coded in its own session from the packet only.

So this tool reports three separate things and never merges them:

1. **Coder reliability, measured**: Cohen's kappa between C2 and C2b per
   variable.  This is a reliability estimate for the model configuration.  It is
   *not* the protocol's C1-C2 kappa, and the report says so on every line.
2. **Unclear counts and subset sizes**: the size gate and the unclear
   denominator the protocol asks for.
3. **Verdicts under two labelled scenarios**, computed with the frozen rules:
   ``replicate-kappa`` (the measured kappa is applied, so a variable below 0.60
   makes its predictions INVALID exactly as the protocol says) and
   ``no-reliability`` (kappa unavailable, so every prediction is INVALID).  The
   codes scored are always C2's, because no C3 adjudicated anything.

Nothing here is a protocol verdict: the report states that E1-E8 remain
unadjudicated until the author codes C1 and a C3 adjudicates.

Usage::

    py tools/analyze_m8_status.py --frame study/frame.csv \\
        --c2 study/coded_c2.csv --c2b study/coded_c2b.csv \\
        --reports-dir study/reports --output-dir study/analysis
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]

_SPEC = importlib.util.spec_from_file_location(
    "analyze_postmortems", ROOT / "tools" / "analyze_postmortems.py"
)
ap = importlib.util.module_from_spec(_SPEC)
sys.modules["analyze_postmortems"] = ap
_SPEC.loader.exec_module(ap)


def _agreement(first: str, second: str) -> float:
    return 1.0 if first.strip() == second.strip() else 0.0


def reliability_rows(
    c2: dict[str, ap.CodeRow], c2b: dict[str, ap.CodeRow]
) -> list[dict[str, object]]:
    """Per-variable kappa between the two blind passes, plus raw agreement."""
    kappas, rows = ap.kappa_table(c2b, c2)
    shared = sorted(set(c2) & set(c2b))
    for row in rows:
        variable = str(row["variable"])
        agree = sum(
            1
            for incident in shared
            if _agreement(
                c2[incident].values.get(variable, ""),
                c2b[incident].values.get(variable, ""),
            )
        )
        row["agree"] = agree
        row["agreement"] = round(agree / len(shared), 6) if shared else ""
        row["gate"] = "PASS" if row["reliable"] else "BELOW 0.60"
    return kappas, rows


def disagreements(
    c2: dict[str, ap.CodeRow], c2b: dict[str, ap.CodeRow]
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for incident in sorted(set(c2) & set(c2b)):
        for variable in ap.VARIABLES:
            first = c2[incident].values.get(variable, "")
            second = c2b[incident].values.get(variable, "")
            if first != second:
                out.append(
                    {
                        "incident_id": incident,
                        "variable": variable,
                        "c2": first,
                        "c2b": second,
                    }
                )
    return out


def render(
    frame: Sequence[ap.FrameRow],
    c2: dict[str, ap.CodeRow],
    rows: list[dict[str, object]],
    verdict_scenarios: dict[str, list[ap.Verdict]],
    unclear: list[dict[str, object]],
    disagreement_rows: list[dict[str, str]],
) -> str:
    n_frame = len(frame)
    eligible = [row for row in frame if row.eligible == "yes" and not row.duplicate_of]
    lines: list[str] = []
    lines.append("# Postmortem study (M8): status after two blind LLM coding passes")
    lines.append("")
    lines.append(
        "**This is not the protocol's verdict.** The frozen protocol requires an "
        "author-coded C1, a kappa gate between C1 and C2, and C3 adjudication. "
        "This run has two independent blind passes by the same model "
        "configuration (`C2` and the replicate `C2b`) and no C1 and no C3, so "
        "E1-E8 stay unadjudicated. Every kappa below is C2-vs-C2b, not C1-vs-C2."
    )
    lines.append("")
    lines.append("## Frame")
    lines.append("")
    lines.append(f"- incidents in the frozen frame: **{n_frame}**")
    lines.append(f"- eligible and not a duplicate: **{len(eligible)}**")
    ids = {row.incident_id for row in eligible}
    lines.append(f"- coded by C2: **{len(ids & set(c2))}**")
    lines.append("")
    lines.append("## Coder reliability, C2 vs C2b (unweighted Cohen's kappa)")
    lines.append("")
    lines.append("| Variable | n | kappa | raw agreement | gate >= 0.60 |")
    lines.append("|---|---:|---:|---:|---|")
    for row in rows:
        kappa = row["kappa"] if row["kappa"] != "" else "n/a"
        lines.append(
            f"| {row['variable']} | {row['n']} | {kappa} | {row['agreement']} | {row['gate']} |"
        )
    lines.append("")
    lines.append(
        f"Disagreeing cells across all variables: **{len(disagreement_rows)}** "
        f"over {(rows[0]['n'] if rows else 0)} incidents."
    )
    lines.append("")
    lines.append("## Unclear counts (C2 codes)")
    lines.append("")
    lines.append("| Variable | n | unclear |")
    lines.append("|---|---:|---:|")
    for row in unclear:
        lines.append(f"| {row['variable']} | {row['n']} | {row['unclear']} |")
    lines.append("")
    for name, verdicts in verdict_scenarios.items():
        lines.append(f"## Verdicts, scenario `{name}` (scored on C2 codes)")
        lines.append("")
        lines.append("| ID | n | estimate | 95% interval | verdict | reason |")
        lines.append("|---|---:|---:|---|---|---|")
        for verdict in verdicts:
            value = "" if verdict.value is None else f"{verdict.value:.3f}"
            interval = (
                ""
                if verdict.low is None or verdict.high is None
                else f"[{verdict.low:.3f}, {verdict.high:.3f}]"
            )
            lines.append(
                f"| {verdict.id} | {verdict.n} | {value} | {interval} | "
                f"**{verdict.verdict}** | {verdict.reason} |"
            )
        lines.append("")
    lines.append("## How to read the scenarios")
    lines.append("")
    lines.append(
        "- `replicate-kappa` applies the measured C2-vs-C2b kappa to the frozen "
        "gate: a variable below 0.60 turns its predictions into INVALID, which is "
        "the protocol's own treatment of an unreliable variable."
    )
    lines.append(
        "- `no-reliability` is the strict protocol position when no independent "
        "human coder exists: kappa unavailable, so every prediction is INVALID."
    )
    lines.append(
        "- Neither scenario is a finding about providers. The author's C1 and a "
        "C3 remain the missing inputs."
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, default=ROOT / "study" / "frame.csv")
    parser.add_argument("--c2", type=Path, default=ROOT / "study" / "coded_c2.csv")
    parser.add_argument("--c2b", type=Path, default=ROOT / "study" / "coded_c2b.csv")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "study" / "reports")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "study" / "analysis")
    args = parser.parse_args(list(argv) if argv is not None else None)

    frame = ap.load_frame(args.frame)
    problems = ap.verify_frame_hashes(frame, args.reports_dir)
    if problems:
        for problem in problems[:10]:
            print(f"frame hash problem: {problem}")
        return 2

    c2 = ap.load_codes(args.c2)
    c2b = ap.load_codes(args.c2b)
    kappas, rows = reliability_rows(c2, c2b)
    disagreement_rows = disagreements(c2, c2b)
    unclear = ap.unclear_counts([c2[row.incident_id] for row in frame if row.incident_id in c2])

    ids = [row.incident_id for row in frame if row.eligible == "yes" and not row.duplicate_of]
    coded = [c2[incident] for incident in ids if incident in c2]
    scenarios = {
        "replicate-kappa": ap.analyse_set(coded, kappas),
        "no-reliability": ap.analyse_set(
            coded, {variable: None for variable in ap.VARIABLES}
        ),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "m8-reliability.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    with (args.output_dir / "m8-disagreements.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["incident_id", "variable", "c2", "c2b"]
        )
        writer.writeheader()
        writer.writerows(disagreement_rows)
    with (args.output_dir / "m8-verdicts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["scenario", "id", "n", "value", "low", "high", "verdict", "reason"])
        for name, verdicts in scenarios.items():
            for verdict in verdicts:
                writer.writerow(
                    [
                        name,
                        verdict.id,
                        verdict.n,
                        "" if verdict.value is None else round(verdict.value, 6),
                        "" if verdict.low is None else round(verdict.low, 6),
                        "" if verdict.high is None else round(verdict.high, 6),
                        verdict.verdict,
                        verdict.reason,
                    ]
                )
    (args.output_dir / "m8-status.md").write_text(
        render(frame, c2, rows, scenarios, unclear, disagreement_rows), encoding="utf-8"
    )
    print(f"wrote {args.output_dir / 'm8-status.md'}")
    print(f"coded incidents: {len(coded)} of {len(ids)} eligible")
    print("reliability (C2 vs C2b):")
    for row in rows:
        print(f"  {row['variable']:44s} kappa={row['kappa']} agreement={row['agreement']} {row['gate']}")
    for name, verdicts in scenarios.items():
        counts: dict[str, int] = {}
        for verdict in verdicts:
            counts[verdict.verdict] = counts.get(verdict.verdict, 0) + 1
        print(f"scenario {name}: {json.dumps(counts, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
