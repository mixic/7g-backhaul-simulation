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

"""Tests for the common-mode sensitivity / break-even mode."""

from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from simulation import common_mode as cm

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_common_mode_sensitivity", ROOT / "tools" / "benchmark_common_mode.py"
)
bench = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = bench
_SPEC.loader.exec_module(bench)


class ParameterTests(unittest.TestCase):
    def test_default_params_reproduce_the_frozen_result(self) -> None:
        for arm, event in (("A6", "ai"), ("A6", "backhaul_cut"), ("A9", "link")):
            with self.subTest(arm=arm, event=event):
                frozen = cm.simulate(cm.ARMS[arm], seed=2026, event_kind=event)
                explicit = cm.simulate(
                    cm.ARMS[arm],
                    seed=2026,
                    event_kind=event,
                    params=cm.ScenarioParams(),
                )
                self.assertEqual(frozen, explicit)

    def test_efficiency_is_applied_to_one_way_arms(self) -> None:
        params = cm.ScenarioParams(one_way_efficiency=0.5)
        result = cm.simulate(
            cm.ARMS["A6"], seed=2026, event_kind="ai", params=params
        )
        self.assertAlmostEqual(result.availability_event, 0.5)

    def test_fallback_probability_is_applied(self) -> None:
        params = cm.ScenarioParams(fallback_tested_probability=0.0)
        backhaul = cm.simulate(
            cm.ARMS["A6"], seed=2026, event_kind="backhaul_cut", params=params
        )
        link = cm.simulate(cm.ARMS["A9"], seed=2026, event_kind="link", params=params)
        self.assertEqual(backhaul.availability_event, 0.0)
        self.assertEqual(link.availability_event, 0.0)

    def test_parameterisation_does_not_mutate_module_constants(self) -> None:
        before = (
            cm.ONE_WAY_EFFICIENCY,
            cm.FALLBACK_TESTED_PROBABILITY,
            cm.FALLBACK_TESTED_DELAY_S,
            cm.FALLBACK_TESTED_CAPACITY_GBPS,
        )
        cm.simulate(
            cm.ARMS["A6"],
            seed=2026,
            event_kind="backhaul_cut",
            params=cm.ScenarioParams(
                one_way_efficiency=0.2,
                fallback_tested_probability=0.1,
                fallback_tested_delay_s=10.0,
                fallback_tested_capacity_gbps=0.1,
            ),
        )
        self.assertEqual(
            before,
            (
                cm.ONE_WAY_EFFICIENCY,
                cm.FALLBACK_TESTED_PROBABILITY,
                cm.FALLBACK_TESTED_DELAY_S,
                cm.FALLBACK_TESTED_CAPACITY_GBPS,
            ),
        )


class BreakEvenTests(unittest.TestCase):
    def _point(self, value: float, normal_cost: float) -> bench.SensitivityPoint:
        # Only the fields used by the H18 normal-cost criterion need to be
        # meaningful; the rest are fixed at the current-run values.
        return bench.SensitivityPoint(
            value=value,
            a5_ai=0.0,
            a6_ai=90.0,
            a5_none=100.0,
            a6_none=100.0 - normal_cost,
            a6_ai_link=90.0,
            a3_ai_link=0.0,
            a9_ai_link=45.6,
            a1_ai_link=0.0,
            a6_backhaul=45.6,
            a7_backhaul=11.1,
            a9_link=45.6,
            interaction=44.4,
        )

    def test_linear_interpolation_locates_the_boundary(self) -> None:
        sweep = bench.Sweep(
            "efficiency", "efficiency", "one_way_efficiency", 0.5, 1.0, 0.9, "fraction"
        )
        criterion = next(
            item for item in bench.CRITERIA if item.key == "H18_normal_cost"
        )
        points = [self._point(0.8, 20.0), self._point(0.9, 10.0)]
        row = bench.break_even_for(sweep, points, criterion)
        self.assertTrue(row["current_pass"])
        self.assertAlmostEqual(float(row["break_even_value"]), 0.85, places=6)

    def test_no_break_even_is_reported_honestly(self) -> None:
        sweep = bench.Sweep(
            "efficiency", "efficiency", "one_way_efficiency", 0.5, 1.0, 0.9, "fraction"
        )
        criterion = next(
            item for item in bench.CRITERIA if item.key == "H18_normal_cost"
        )
        points = [self._point(0.8, 10.0), self._point(0.9, 10.0)]
        row = bench.break_even_for(sweep, points, criterion)
        self.assertEqual(row["break_even_value"], "")
        self.assertIn("none", str(row["direction"]))


class SensitivityRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = cm.build_backhaul_scenario()
        cls.grid, cls.breaks = bench.run_sensitivity([2026], cls.scenario, points=5)

    def test_every_constant_is_swept(self) -> None:
        self.assertEqual({row["parameter"] for row in self.grid}, {s.key for s in bench.SWEEPS})
        self.assertEqual(len(self.breaks), len(bench.SWEEPS) * len(bench.CRITERIA))

    def test_the_primary_criterion_passes_at_the_stipulated_value(self) -> None:
        for row in self.breaks:
            with self.subTest(parameter=row["parameter"], criterion=row["criterion"]):
                self.assertTrue(row["current_pass"], row)

    def test_efficiency_break_even_is_near_085(self) -> None:
        row = next(
            item
            for item in self.breaks
            if item["parameter"] == "one_way_efficiency"
            and item["criterion"] == "H18_normal_cost"
        )
        self.assertNotEqual(row["break_even_value"], "")
        self.assertAlmostEqual(float(row["break_even_value"]), 0.85, places=2)

    def test_markdown_reports_the_primary_break_even(self) -> None:
        text = bench.sensitivity_markdown(self.breaks, points=5, seeds=1)
        self.assertIn("Break-even values", text)
        self.assertIn("one-way local-policy efficiency", text)
        self.assertIn("0.85", text)


class CliTests(unittest.TestCase):
    def test_sensitivity_cli_writes_the_three_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code = bench.main(
                [
                    "--sensitivity",
                    "--seeds",
                    "1",
                    "--sensitivity-points",
                    "5",
                    "--sensitivity-out",
                    directory,
                ]
            )
            self.assertEqual(code, 0)
            for name in (
                "common-mode-sensitivity.csv",
                "common-mode-break-even.csv",
                "common-mode-break-even.md",
            ):
                self.assertTrue((Path(directory) / name).exists(), name)
            with (Path(directory) / "common-mode-sensitivity.csv").open(
                encoding="utf-8"
            ) as handle:
                rows = list(csv.DictReader(handle))
            counts = {sweep.key: 0 for sweep in bench.SWEEPS}
            for row in rows:
                counts[row["parameter"]] += 1
            # The stipulated value is appended when the regular grid does not
            # contain it, so each sweep has at least `points` rows.
            self.assertTrue(all(count >= 5 for count in counts.values()), counts)


if __name__ == "__main__":
    unittest.main()
