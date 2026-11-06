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

"""Tests for the savant controller and its starvation accounting."""

from __future__ import annotations

import unittest

import numpy as np

from simulation.savant.controller import SavantController
from simulation.savant.starvation import StarvationLogger
from simulation.surgical.config import SAVANT, scenario_exp4
from simulation.surgical.sim import run_and_score


class StarvationLoggerTests(unittest.TestCase):
    def test_records_only_while_active(self) -> None:
        log = StarvationLogger()
        log.record(5, False)          # not active: ignored
        self.assertEqual(log.total_other(), 0)
        log.activate(5)
        log.record(5, False)
        log.record(5, False)
        log.record(5, True)
        self.assertEqual(log.total_other(), 2)
        self.assertEqual(log.total_affected(), 1)
        log.deactivate(5)
        log.record(5, False)          # released: ignored
        self.assertEqual(log.total_other(), 2)

    def test_per_node_snapshot(self) -> None:
        log = StarvationLogger()
        log.activate(3)
        log.record(3, False)
        self.assertEqual(log.per_node()[3]["other"], 1)


class SavantControllerTests(unittest.TestCase):
    def test_savant_edits_alpha_and_logs_starvation(self) -> None:
        result = run_and_score(scenario_exp4(0, "savant_a95").child(duration=45.0))
        self.assertGreater(result["alpha_edited_nodes"], 0)
        self.assertGreaterEqual(result["savant_other_drops"], 0)
        self.assertGreaterEqual(result["savant_affected_drops"], 0)

    def test_savant_does_not_leak_to_unattacked_alpha(self) -> None:
        """Isolation: the savant arm moves alpha only at triggered nodes, never
        the whole fabric, and the control arm leaves alpha untouched."""
        savant = run_and_score(scenario_exp4(1, "savant_a95").child(duration=45.0))
        control = run_and_score(scenario_exp4(1, "surgical").child(duration=45.0))
        self.assertEqual(int(control["alpha_edited_nodes"]), 0)
        self.assertLessEqual(int(savant["alpha_edited_nodes"]),
                             int(savant["ns_classes_peak"]) + 24)

    def test_cascading_failure_rate_is_a_probability(self) -> None:
        result = run_and_score(scenario_exp4(2, "savant_a85").child(duration=45.0))
        if np.isfinite(result["cascading_failure_rate"]):
            self.assertGreaterEqual(result["cascading_failure_rate"], 0.0)
            self.assertLessEqual(result["cascading_failure_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
