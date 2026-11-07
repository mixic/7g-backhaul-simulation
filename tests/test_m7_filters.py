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

"""CI tests for the M7 dual-band filter and its controller."""

from __future__ import annotations

import math
import unittest

from simulation.dual_band_controller import DualBandController, LpfOnlyController
from simulation.filters import DualBandFilter, LpfEwma, LpfOnlyFilter
from simulation.surgical.config import DUAL_BAND, LPF_ONLY, SimConfig
from simulation.surgical.network import SimRun
from simulation.surgical.sim import run_and_score


class LpfEwmaTests(unittest.TestCase):
    def test_first_sample_initialises(self):
        f = LpfEwma(tau=2.0, dt=0.2)
        self.assertEqual(f.update(0.5), 0.5)

    def test_converges_to_constant(self):
        f = LpfEwma(tau=0.5, dt=0.1)
        for _ in range(100):
            f.update(1.0)
        self.assertAlmostEqual(f.value, 1.0, places=3)

    def test_alpha_matches_exponential_form(self):
        tau, dt = 2.0, 0.2
        f = LpfEwma(tau=tau, dt=dt)
        self.assertAlmostEqual(f.alpha, 1.0 - math.exp(-dt / tau))


class DualBandFilterTests(unittest.TestCase):
    def _run(self, f, values, t0=0.0, dt=0.2):
        t = t0
        results = []
        for v in values:
            results.append(f.update(t, v))
            t += dt
        return results

    def test_hpf_is_residual(self):
        f = DualBandFilter(tau_lpf=2.0, dt=0.2, k=3.0, window=6.0)
        r = f.update(0.0, 0.5)
        self.assertAlmostEqual(r.hpf, r.raw - r.lpf)

    def test_constant_signal_does_not_trigger(self):
        f = DualBandFilter(tau_lpf=2.0, dt=0.2, k=3.0, window=6.0)
        results = self._run(f, [0.5] * 100)
        self.assertFalse(any(r.triggered for r in results))

    def test_step_detected(self):
        # A sharp step (the DDoS) must cross the high-pass threshold.
        f = DualBandFilter(tau_lpf=2.0, dt=0.2, k=3.0, window=6.0, floor_abs=0.02)
        results = self._run(f, [0.5] * 60 + [1.0] * 20)
        self.assertTrue(any(r.triggered for r in results))
        # the trigger happens only after the step, not during the baseline
        baseline = results[:60]
        self.assertFalse(any(r.triggered for r in baseline))

    def test_threshold_is_floor_plus_k_sigma(self):
        f = DualBandFilter(tau_lpf=2.0, dt=0.2, k=3.0, window=6.0, floor_abs=0.02)
        self._run(f, [0.5] * 20)
        self.assertGreaterEqual(f.last.threshold, 0.02)


class LpfOnlyFilterTests(unittest.TestCase):
    def test_fixed_threshold_triggers_on_spike(self):
        f = LpfOnlyFilter(tau_lpf=2.0, dt=0.2, fixed_threshold=0.10)
        for _ in range(50):
            f.update(0.0, 0.5)
        self.assertFalse(f.update(0.0, 0.5).triggered)
        # a 0.3 jump above the baseline exceeds the fixed 0.10 threshold
        self.assertTrue(f.update(0.0, 0.85).triggered)


class DualBandControllerTests(unittest.TestCase):
    def test_dual_band_controller_is_registered(self):
        sim = SimRun(SimConfig(name="exp1_ddos", seed=0, controller=DUAL_BAND))
        self.assertIsInstance(sim.controller, DualBandController)

    def test_lpf_only_controller_is_registered(self):
        sim = SimRun(SimConfig(name="exp1_ddos", seed=0, controller=LPF_ONLY))
        self.assertIsInstance(sim.controller, LpfOnlyController)

    def test_dual_band_runs_and_reports(self):
        r = run_and_score(SimConfig(name="exp1_ddos", seed=0,
                                    controller=DUAL_BAND,
                                    load_wave_amp=0.0).child(duration=45.0))
        self.assertGreaterEqual(r["edits"], 0)
        self.assertGreaterEqual(r["detection_count"], 1)
        self.assertGreater(r["goodput_shock"], 0.0)
        self.assertGreater(len(r["filter_series"]), 0)


if __name__ == "__main__":
    unittest.main()
