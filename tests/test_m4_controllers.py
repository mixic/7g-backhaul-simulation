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

"""CI tests for the standalone M4 controller modules.

These import ``simulation.oef_controller`` and ``simulation.mkb_controller``
directly, so the suite fails if either module is missing or its public API
drifts from what ``make_controller`` registers.
"""

from __future__ import annotations

import math
import unittest

from simulation.mkb_controller import MkbController, MkbMonitor
from simulation.oef_controller import OefController, OefSurgicalController
from simulation.surgical.config import MKB, OEF, SimConfig
from simulation.surgical.network import SimRun
from simulation.surgical.sim import run_and_score


class StandaloneModuleTests(unittest.TestCase):
    def test_make_controller_returns_standalone_classes(self) -> None:
        oef_sim = SimRun(SimConfig(name="exp1_ddos", seed=0, controller=OEF))
        self.assertIsInstance(oef_sim.controller, OefController)
        mkb_sim = SimRun(SimConfig(name="exp1_ddos", seed=0, controller=MKB))
        self.assertIsInstance(mkb_sim.controller, MkbController)

    def test_backwards_compatible_alias(self) -> None:
        self.assertIs(OefSurgicalController, OefController)

    def test_oef_engages_and_stays_a_fraction(self) -> None:
        result = run_and_score(SimConfig(name="exp1_ddos", seed=0,
                                         controller=OEF).child(duration=45.0))
        self.assertGreater(result["oef_peak"], 0.0)
        self.assertLessEqual(result["oef_peak"], 1.0)
        self.assertGreater(result["goodput_shock"], 0.5)

    def test_mkb_uses_vector_norm_trigger(self) -> None:
        monitor = MkbMonitor(4, 0.2, tau_s=0.3, tau_v=1.0, k=4.0,
                             floor_a=2.0, floor_v=0.08)
        steady = [monitor.update([0.4 + 0.05 * math.sin(i / 3), 0.1, 0.0, 0.0])
                  for i in range(50)]
        self.assertEqual(sum(steady), 0)
        shock = [monitor.update([1.0, 0.5, 0.1, 0.0]) for _ in range(10)]
        self.assertGreaterEqual(sum(shock), 1)

    def test_mkb_runs_and_records_spikes(self) -> None:
        result = run_and_score(SimConfig(name="exp1_ddos", seed=0,
                                         controller=MKB).child(duration=45.0))
        self.assertGreaterEqual(result["mkb_spike_count"], 0)
        self.assertGreater(result["goodput_shock"], 0.0)


if __name__ == "__main__":
    unittest.main()
