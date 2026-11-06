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

"""Tests for OEF compensation and multidimensional kinematic baselining."""

from __future__ import annotations

import unittest

import numpy as np

from simulation.surgical.config import MKB, OEF, SURGICAL, SimConfig
from simulation.surgical.homeostasis import MkbMonitor
from simulation.surgical.sim import run_and_score


class MkbMonitorTests(unittest.TestCase):
    def test_steady_state_is_quiet_and_step_triggers(self) -> None:
        monitor = MkbMonitor(4, 0.2, tau_s=0.3, tau_v=1.0, k=4.0,
                             floor_a=2.0, floor_v=0.08)
        steady = [monitor.update([0.4 + 0.05 * np.sin(i / 3), 0.1, 0.0, 0.0])
                  for i in range(50)]
        self.assertEqual(sum(steady), 0)
        shock = [monitor.update([1.0, 0.5, 0.1, 0.0]) for _ in range(10)]
        self.assertGreaterEqual(sum(shock), 1)

    def test_vector_velocity_is_not_zero_after_aliasing_fix(self) -> None:
        # regression: prev_ema must be a copy, or in-place += zeroes the velocity
        monitor = MkbMonitor(2, 0.2, tau_s=0.3)
        monitor.update([0.0, 0.0])
        monitor.update([1.0, 0.0])
        self.assertGreater(float(np.linalg.norm(monitor.v_prev)), 0.0)


class OefControllerTests(unittest.TestCase):
    def test_oef_engages_and_stays_a_fraction(self) -> None:
        result = run_and_score(SimConfig(name="exp1_ddos", seed=0,
                                         controller=OEF).child(duration=45.0))
        self.assertGreater(result["oef_peak"], 0.0)
        self.assertLessEqual(result["oef_peak"], 1.0)
        self.assertGreater(result["goodput_shock"], 0.5)

    def test_oef_is_not_hardcoded(self) -> None:
        """OEF must react to the CBF drop, not be pinned to 1 without cause.

        The whole-run peak is 1.0 only because traffic stops at the end of the
        run and the controller sees a genuine collapse; the steady window must
        be quiet.
        """
        idle = run_and_score(SimConfig(name="exp1_ddos", seed=1,
                                       controller=OEF,
                                       attack_rate=0.0).child(duration=40.0))
        series = idle["oef_series"]
        steady = series[series[:, 0] < 29.0, 1].mean() if len(series) else 0.0
        self.assertLess(steady, 0.2)

    def test_mkb_runs_and_never_crashes(self) -> None:
        result = run_and_score(SimConfig(name="exp1_ddos", seed=0,
                                         controller=MKB).child(duration=45.0))
        self.assertGreaterEqual(result["mkb_spike_count"], 0)
        self.assertGreater(result["goodput_shock"], 0.0)


if __name__ == "__main__":
    unittest.main()
