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

"""Tests for the layering report classifier."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from simulation.layering.experiments import run_model
from tools.validation_io import METRIC_UNITS
from validation.layering._io import FIELDS
from validation.layering.report import (
    EVALUATORS,
    Observations,
    evaluate_p4,
)


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = run_model()

    def _write(self, rows, directory: str) -> Path:
        path = Path(directory) / "observations.csv"
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_frozen_predictions_are_confirmed_by_the_python_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            observations = {
                "model": Observations(self._write(self.rows, directory), "model")
            }
            for evaluator in EVALUATORS.values():
                result = evaluator(observations)
                self.assertEqual(result.verdict, "CONFIRMED", result.prediction)

    def test_a_tampered_wire_size_refutes_p4(self) -> None:
        rows = [dict(row) for row in self.rows]
        target = next(
            row
            for row in rows
            if row["scenario"] == "P4"
            and row["policy"] == "T>E>S"
            and row["metric"] == "wire_bytes"
        )
        target["value"] = float(target["value"]) + 1.0
        with tempfile.TemporaryDirectory() as directory:
            observations = {
                "model": Observations(self._write(rows, directory), "model")
            }
            self.assertEqual(evaluate_p4(observations).verdict, "REFUTED")

    def test_unit_mismatch_is_rejected(self) -> None:
        rows = []
        for row in self.rows:
            rows.append(dict(row))
        target = next(row for row in rows if row["metric"] == "wire_bytes")
        target["unit"] = "percent"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                Observations(self._write(rows, directory), "model")

    def test_layering_metrics_are_registered(self) -> None:
        for metric in (
            "wire_bytes",
            "max_payload_bytes",
            "delivery_percent",
            "auth_accept_percent",
            "mutation_applied",
            "field_visible",
            "fragment_count",
        ):
            with self.subTest(metric=metric):
                self.assertIn(metric, METRIC_UNITS)


if __name__ == "__main__":
    unittest.main()
