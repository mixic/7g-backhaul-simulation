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

"""Generate the two figures of the restructured layering paper.

Figure 1 is the visibility matrix of the six orderings (data: the P4 table in
``docs/layering-results.md``).  Figure 2 is the verdict matrix built from the
three committed verdict CSVs, so no disposition is transcribed by hand.

Run: ``py tools/make_layering_figures.py --output-dir figures``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ORDERINGS = (
    "T -> E -> S",
    "T -> S -> E",
    "E -> T -> S",
    "E -> S -> T",
    "S -> T -> E",
    "S -> E -> T",
)
#: P4 visibility table, docs/layering-results.md.
VISIBILITY = {
    "T -> E -> S": (False, True),
    "T -> S -> E": (False, False),
    "E -> T -> S": (True, True),
    "E -> S -> T": (True, True),
    "S -> T -> E": (False, False),
    "S -> E -> T": (True, False),
}

GREEN = "#2e7d32"
RED = "#c0392b"
AMBER = "#e69f00"
GREY = "#d9d9d9"


def _load(path: Path, key_columns: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _group_status(rows: list[dict[str, str]], key: str) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(row["verdict"])
    result: dict[str, str] = {}
    for name, verdicts in grouped.items():
        if any(verdict == "REFUTED" for verdict in verdicts):
            result[name] = "PARTIAL" if any(v == "CONFIRMED" for v in verdicts) else "REFUTED"
        elif all(verdict == "CONFIRMED" for verdict in verdicts):
            result[name] = "CONFIRMED"
        else:
            result[name] = "OTHER"
    return result


def verdict_matrix(repo: Path) -> tuple[list[str], list[str], list[list[str]]]:
    rows = [f"P{index}" for index in range(1, 17)]
    columns = ["Model", "SimPy", "Linux\nP1-P7", "Linux\nP8-P12", "Linux\nP13-P16"]

    layering = _load(repo / "validation/layering/results/verdicts.csv", ("prediction", "fidelity"))
    layering_status = {
        (row["prediction"], row["fidelity"]): row["verdict"] for row in layering
    }
    real = _group_status(
        _load(repo / "validation/real_stack/results/verdicts.csv", ("prediction", "case")),
        "prediction",
    )
    round2 = _group_status(
        _load(repo / "validation/round2/results/verdicts.csv", ("prediction", "case")),
        "prediction",
    )

    matrix: list[list[str]] = []
    for prediction in rows:
        row = ["n/a"] * len(columns)
        if prediction in ("P1", "P2", "P3", "P4", "P5", "P6", "P7"):
            row[0] = layering_status.get((prediction, "model"), "n/a")
            row[1] = layering_status.get((prediction, "simpy"), "n/a")
            row[2] = layering_status.get((prediction, "linux"), "n/a")
        elif prediction in real:
            row[3] = real[prediction]
        elif prediction in round2:
            row[4] = round2[prediction]
        matrix.append(row)
    return rows, columns, matrix


def draw_visibility(output_dir: Path) -> None:
    figure, axis = plt.subplots(figsize=(5.4, 3.1))
    fields = ("T.src_port", "S.seq")
    axis.set_xlim(0, 2.0)
    axis.set_ylim(0, len(ORDERINGS))
    for row, ordering in enumerate(ORDERINGS):
        y = len(ORDERINGS) - row - 1
        visible = VISIBILITY[ordering]
        for column, flag in enumerate(visible):
            colour = GREEN if flag else RED
            axis.add_patch(
                Rectangle((column, y + 0.08), 0.94, 0.84, facecolor=colour, alpha=0.18, edgecolor=colour)
            )
            axis.text(
                column + 0.47,
                y + 0.5,
                "visible" if flag else "inside E",
                ha="center",
                va="center",
                fontsize=8,
                color="#1b1b1b",
            )
        axis.text(-0.06, y + 0.5, ordering, ha="right", va="center", fontsize=9, family="monospace")
    axis.set_xticks([0.47, 1.47])
    axis.set_xticklabels(fields, fontsize=9)
    axis.set_yticks([])
    axis.set_title("Visibility of two header fields in six orderings of T, E, S", fontsize=9)
    for spine in ("left", "bottom", "top", "right"):
        axis.spines[spine].set_visible(False)
    figure.tight_layout()
    figure.savefig(output_dir / "layering_visibility.png", dpi=200)
    figure.savefig(output_dir / "layering_visibility.pdf")
    plt.close(figure)


def draw_verdicts(output_dir: Path) -> None:
    rows, columns, matrix = verdict_matrix(REPO)
    figure, axis = plt.subplots(figsize=(5.6, 6.4))
    colour_for = {
        "CONFIRMED": GREEN,
        "REFUTED": RED,
        "PARTIAL": AMBER,
        "OTHER": AMBER,
        "n/a": GREY,
    }
    for row_index, row in enumerate(matrix):
        for column_index, value in enumerate(row):
            colour = colour_for.get(value, GREY)
            axis.add_patch(
                Rectangle(
                    (column_index, len(rows) - row_index - 1),
                    1,
                    1,
                    facecolor=colour,
                    alpha=0.22 if value != "n/a" else 0.35,
                    edgecolor="white",
                )
            )
            label = {
                "CONFIRMED": "C",
                "REFUTED": "R",
                "PARTIAL": "1 R",
                "n/a": "-",
            }.get(value, value)
            axis.text(
                column_index + 0.5,
                len(rows) - row_index - 0.5,
                label,
                ha="center",
                va="center",
                fontsize=8,
                color="#1b1b1b",
            )
    axis.set_xlim(0, len(columns))
    axis.set_ylim(0, len(rows))
    axis.set_xticks([index + 0.5 for index in range(len(columns))])
    axis.set_xticklabels(columns, fontsize=8)
    axis.set_yticks([len(rows) - index - 0.5 for index in range(len(rows))])
    axis.set_yticklabels(rows, fontsize=8)
    axis.xaxis.tick_top()
    axis.tick_params(length=0)
    for spine in ("left", "bottom", "top", "right"):
        axis.spines[spine].set_visible(False)
    axis.set_title("Dispositions by prediction and fidelity", fontsize=9, pad=18)
    figure.tight_layout()
    figure.savefig(output_dir / "layering_verdicts.png", dpi=200)
    figure.savefig(output_dir / "layering_verdicts.pdf")
    plt.close(figure)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    draw_visibility(args.output_dir)
    draw_verdicts(args.output_dir)
    print(f"wrote {args.output_dir}/layering_visibility.* and layering_verdicts.*")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
