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

"""Tests for the three M3 baselines and the raw-arrival accelerometer."""

from __future__ import annotations

import unittest

from simulation.surgical.config import K8S, PRESSURE, VDR, scenario_exp1
from simulation.surgical.kinematics import ArrivalAccelerometer
from simulation.surgical.sim import run_and_score


class ArrivalAccelerometerTests(unittest.TestCase):
    def test_constant_rate_has_flat_acceleration(self) -> None:
        acc = ArrivalAccelerometer(window=1.0)
        t = 0.0
        while t < 20.0:
            acc.note(t)
            t += 0.1
        a = acc.sample(20.0, 0.5)
        self.assertLess(abs(a), 40.0)

    def test_rate_step_produces_positive_acceleration(self) -> None:
        acc = ArrivalAccelerometer(window=1.0)
        t = 0.0
        while t < 10.0:
            acc.note(t)
            t += 0.1
        while t < 12.0:
            acc.note(t)
            t += 0.02
        a = acc.sample(10.4, 0.25)
        self.assertGreater(a, 0.0)


class BaselineTests(unittest.TestCase):
    def test_baseline_a_is_static(self) -> None:
        result = run_and_score(scenario_exp1(0, K8S).child(duration=40.0))
        self.assertEqual(result["edits"], 0)

    def test_baseline_b_runs_and_never_moves_alpha(self) -> None:
        result = run_and_score(scenario_exp1(0, VDR).child(duration=40.0))
        self.assertEqual(result["alpha_edited_nodes"], 0)

    def test_baseline_c_churns_more_than_surgical(self) -> None:
        baseline = run_and_score(scenario_exp1(3, PRESSURE))
        surgical = run_and_score(scenario_exp1(3, "surgical"))
        self.assertGreater(baseline["churn_mean"], surgical["churn_mean"])


if __name__ == "__main__":
    unittest.main()
