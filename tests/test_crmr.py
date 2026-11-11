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

"""Tests for CRMR (H15): phase dynamics, phase-weighted TDA and the scenario."""

from __future__ import annotations

import inspect
import math
import unittest

import numpy as np

from simulation import crmr
from simulation import crmr_scenario as scenario


class PhaseTests(unittest.TestCase):
    def test_target_is_monotone_in_the_anomaly(self):
        values = [crmr.phase_target(a) for a in (0.0, 0.2, 0.5, 0.8, 1.0)]
        self.assertEqual(values[0], 0.0)
        self.assertAlmostEqual(values[-1], math.pi / 2.0)
        self.assertEqual(values, sorted(values))

    def test_damped_rotation_rises_and_returns(self):
        controller = crmr.PhaseController()
        for _ in range(60):
            controller.update(1.0, 0.1)
        self.assertGreater(controller.theta, 1.2)
        for _ in range(80):
            controller.update(0.0, 0.1)
        self.assertLess(controller.theta, 0.1)

    def test_fraction_is_sin_squared(self):
        controller = crmr.PhaseController(theta=math.pi / 4.0)
        self.assertAlmostEqual(controller.fraction(), 0.5)

    def test_no_attack_time_in_the_router(self):
        source = inspect.getsource(crmr)
        self.assertNotIn("ATTACK_START", source)
        self.assertNotIn("ATTACK_END", source)
        self.assertNotIn("if time", source)


class PhaseManifoldTests(unittest.TestCase):
    def test_high_phase_separates_two_clusters(self):
        rng = np.random.default_rng(3)
        legit = np.tile(np.array([0.0, 0.2, 0.02, 0.0]), (40, 1))
        legit += rng.normal(0.0, 0.01, legit.shape)
        attack = np.tile(np.array([0.0, 0.6, 0.3, 1.0]), (20, 1))
        attack += rng.normal(0.0, 0.01, attack.shape)
        manifold = crmr.compute_phase_manifold(
            np.vstack([legit, attack]), math.pi / 2.0, 2.0
        )
        self.assertGreaterEqual(manifold.b0, 2)
        self.assertTrue(any(manifold.attack))

    def test_calm_phase_is_one_component(self):
        rng = np.random.default_rng(4)
        points = np.tile(np.array([0.0, 0.0, 0.0, 0.0]), (30, 1))
        points[:, 0] = rng.uniform(0.0, 0.1, 30)
        points += rng.normal(0.0, 0.004, points.shape)
        points[:, 0] = np.clip(points[:, 0], 0.0, 0.1)
        manifold = crmr.compute_phase_manifold(points, 0.0, 1.0)
        self.assertEqual(manifold.b0, 1)

    def test_transform_is_not_a_rigid_rotation(self):
        point = np.array([0.1, 0.3, 0.2, 0.5])
        manifold = crmr.compute_phase_manifold(
            np.tile(point, (10, 1)), math.pi / 4.0, 2.0
        )
        transformed = manifold.transform(point)
        sine = 2.0 * math.sin(math.pi / 4.0)
        expected = math.sqrt(
            (math.cos(math.pi / 4.0) * 0.1) ** 2
            + sine**2 * (0.3**2 + 0.2**2 + 0.5**2)
        )
        self.assertAlmostEqual(float(np.linalg.norm(transformed)), expected, places=6)
        self.assertNotAlmostEqual(
            float(np.linalg.norm(transformed)),
            float(np.linalg.norm(point)),
            places=2,
        )


class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = scenario.run_seed(2030, "sustained")

    def test_crmr_keeps_isolation(self):
        static = self.result.runs["static"].cdr_mean
        crmr_cdr = self.result.runs["crmr"].cdr_mean
        ddmr = self.result.runs["ddmr"].cdr_mean
        self.assertGreaterEqual(crmr_cdr, static + 15.0)
        self.assertLessEqual(ddmr - crmr_cdr, 5.0)
        self.assertGreater(crmr_cdr, 90.0)

    def test_peak_reconfiguration_is_smoothed(self):
        ddmr_peak = self.result.runs["ddmr"].peak_churn
        crmr_peak = self.result.runs["crmr"].peak_churn
        self.assertLessEqual(crmr_peak, 0.5 * ddmr_peak)

    def test_energy_clause_passes(self):
        self.assertLess(self.result.energy_cpu_j, self.result.energy_saved_j)

    def test_run_is_deterministic(self):
        again = scenario.run_seed(2030, "sustained")
        self.assertEqual(
            again.runs["crmr"].delivered_window,
            self.result.runs["crmr"].delivered_window,
        )
        self.assertEqual(again.h15, self.result.h15)


if __name__ == "__main__":
    unittest.main()
