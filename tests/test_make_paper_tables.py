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


"""Tests for tools/make_paper_tables.py.

The first group checks that the generator and its ``--check`` mode pass on the committed
results.  The second group is the one that matters: it tampers with the data in memory and
verifies that the checks go red, so that a passing run means something.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("make_paper_tables", ROOT / "tools" / "make_paper_tables.py")
mpt = importlib.util.module_from_spec(_SPEC)
sys.modules["make_paper_tables"] = mpt  # required by @dataclass on Python 3.12
_SPEC.loader.exec_module(mpt)


def _failed(results) -> set[str]:
    return {name for name, ok, _ in results if not ok}


class CommittedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = mpt.Data.load()
        cls.matrix = mpt.verdict_matrix(cls.data)

    def test_all_checks_pass_on_committed_results(self) -> None:
        self.assertEqual(_failed(mpt.run_checks(self.data, 20)), set())

    def test_check_labels_are_console_safe(self) -> None:
        # The --check driver prints labels to stdout.  A Unicode minus in a
        # label crashed the Windows cp1252 console, so labels must stay ASCII.
        for name, _, _ in mpt.run_checks(self.data, 20):
            name.encode("ascii")

    def test_every_table_has_rows_and_consistent_widths(self) -> None:
        for table in mpt.build_tables(self.data, self.matrix):
            self.assertTrue(table.rows, table.key)
            for row in table.rows:
                self.assertEqual(len(row), len(table.headers), table.key)

    def test_markdown_and_latex_render_every_table(self) -> None:
        for table in mpt.build_tables(self.data, self.matrix):
            self.assertIn("|", mpt.render_md(table))
            latex = mpt.render_latex(table)
            self.assertIn(r"\toprule", latex)
            self.assertIn(f"tab:{table.key}", latex)

    def test_headline_counts_are_internally_consistent(self) -> None:
        counts = mpt.headline_counts(self.matrix)
        total_c = sum(c for k, (c, _) in counts.items() if k != "total")
        total_n = sum(n for k, (_, n) in counts.items() if k != "total")
        self.assertEqual(counts["total"], (total_c, total_n))
        self.assertEqual(counts["P1-P7"][1], 7)

    def test_calibration_parser_and_stats(self) -> None:
        rows = mpt.parse_calibration("| P13a | 0.90 | 1 | 0.0100 |\n| P16d | 0.70 | 0 | 0.4900 |\n| junk |\n")
        self.assertEqual(rows, [("P13a", 0.9, 1), ("P16d", 0.7, 0)])
        stats = mpt.calibration_stats(mpt.Data(*([[]] * 1 + [{}, None, [], None, [], rows])))
        self.assertAlmostEqual(stats["brier"], (0.01 + 0.49) / 2)
        self.assertAlmostEqual(stats["expected_refutations"], 0.1 + 0.3)
        self.assertEqual(stats["observed_refutations"], 1)


class TamperTests(unittest.TestCase):
    """Each test breaks one fact in memory and expects exactly the matching check to fail."""

    def setUp(self) -> None:
        self.data = mpt.Data.load()

    @staticmethod
    def _rebuild(obs, mutate) -> "mpt.Obs":
        rows = copy.deepcopy(obs.rows)
        for row in rows:
            mutate(row)
        return mpt.Obs(rows)

    def test_wrong_p9_wire_size_is_caught(self) -> None:
        def mutate(row):
            if row["scenario"] == "P9" and row["policy"] == "P9_L100" and row["metric"] in ("wire_bytes_min", "wire_bytes_max"):
                row["value"] = str(float(row["value"]) + 1)
        self.data.rs = self._rebuild(self.data.rs, mutate)
        self.assertIn("P9: wire = 60 + 16*ceil(L/16) for every L and run", _failed(mpt.run_checks(self.data, 20)))

    def test_commuting_p10_orderings_are_caught(self) -> None:
        def mutate(row):
            if row["scenario"] == "P10" and row["policy"] == "P10_y_to_w_L65" and row["metric"] == "wire_bytes_min":
                row["value"] = "160"
        self.data.rs = self._rebuild(self.data.rs, mutate)
        self.assertIn("P10: d(L) matches R(L+20) - R(L) - 20 for every L and run", _failed(mpt.run_checks(self.data, 20)))

    def test_two_run_smoke_test_is_caught(self) -> None:
        self.data.r2 = self._rebuild(self.data.r2, lambda row: None)
        self.data.r2 = mpt.Obs([r for r in self.data.r2.rows if int(r["seed"]) < 2])
        self.assertIn("round2: every case has 20 runs", _failed(mpt.run_checks(self.data, 20)))

    def test_unexpected_delivery_is_caught(self) -> None:
        def mutate(row):
            if row["scenario"] == "P8" and row["policy"] == "P8a" and row["metric"] == "delivery_percent" and row["seed"] == "3":
                row["value"] = "2.0"
        self.data.rs = self._rebuild(self.data.rs, mutate)
        self.assertIn("P8/P11/P12: delivery equals the predicted extreme in every run", _failed(mpt.run_checks(self.data, 20)))

    def test_wrong_p15_wire_size_is_caught(self) -> None:
        def mutate(row):
            if row["scenario"] == "P15" and row["policy"] == "P15_FtoE" and row["metric"] == "wire_bytes_per_datagram" and row["seed"] == "0":
                row["value"] = "2181"
        self.data.r2 = self._rebuild(self.data.r2, mutate)
        self.assertIn("P15: wire bytes equal the frozen 2112 / 2180 in every run", _failed(mpt.run_checks(self.data, 20)))

    def test_flipped_calibration_outcome_is_caught(self) -> None:
        self.data.calibration = [(p, c, 0 if p == "P13a" else o) for p, c, o in self.data.calibration]
        self.assertIn("calibration.md outcomes agree with verdicts.csv", _failed(mpt.run_checks(self.data, 20)))

    def test_replay_filter_mismatch_is_caught(self) -> None:
        def mutate(row):
            if row["scenario"] == "P16" and row["policy"] == "P16a" and row["metric"] == "delivery_matches_reference" and row["seed"] == "5":
                row["value"] = "0"
        self.data.r2 = self._rebuild(self.data.r2, mutate)
        self.assertIn("P16: delivery equals the reference replay filter in every run (all four cases)",
                      _failed(mpt.run_checks(self.data, 20)))

    def test_a_refutation_is_reported_not_hidden(self) -> None:
        matrix = mpt.verdict_matrix(self.data)
        refuted = [(r["round"], r["prediction"]) for r in matrix if r["verdict"] == "REFUTED"]
        self.assertIn(("P13-P16", "P16d"), refuted)
        self.assertIn(("P1-P7", "P5"), refuted)


class HelperTests(unittest.TestCase):
    def test_verdict_aggregation_precedence(self) -> None:
        self.assertEqual(mpt.agg_verdict(["CONFIRMED", "CONFIRMED"]), "CONFIRMED")
        self.assertEqual(mpt.agg_verdict(["CONFIRMED", "REFUTED", "INVALID"]), "REFUTED")
        self.assertEqual(mpt.agg_verdict(["CONFIRMED", "INCONCLUSIVE"]), "INCONCLUSIVE")
        self.assertEqual(mpt.agg_verdict(["NOT RUN", "INVALID"]), "INVALID")
        self.assertEqual(mpt.agg_verdict([]), "n/a")

    def test_latex_escaping(self) -> None:
        self.assertEqual(mpt.latex_cell("50 % & a_b"), r"50 \% \& a\_b")
        self.assertIn(r"$\rightarrow$", mpt.latex_cell("E→F"))

    def test_range_formatting(self) -> None:
        self.assertEqual(mpt.frange([673.0, 717.0]), "673–717")
        self.assertEqual(mpt.frange([20.0, 20.0]), "20")
        self.assertEqual(mpt.frange([]), "n/a")


if __name__ == "__main__":
    unittest.main()
