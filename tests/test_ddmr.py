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

"""Tests for DDMR (M11): real TDA, anomaly trigger, dimension hysteresis."""

from __future__ import annotations

import inspect
import unittest

import numpy as np

from simulation import ddmr
from simulation import ddmr_scenario as scenario


class RealTdaTests(unittest.TestCase):
    def test_ripser_is_installed(self):
        self.assertTrue(
            ddmr.ripser_available(),
            "DDMR requires the real ripser library (pip install ripser)",
        )

    def test_two_clusters_give_two_components(self):
        rng = np.random.default_rng(7)
        left = np.tile(np.array([0.0, 0.0, 0.0, 0.0]), (40, 1))
        left += rng.normal(0.0, 0.01, left.shape)
        right = np.tile(np.array([0.05, 0.8, 0.6, 1.0]), (40, 1))
        right += rng.normal(0.0, 0.01, right.shape)
        manifold = ddmr.compute_manifold(np.vstack([left, right]), ddmr.DIMENSION_SHOCK)
        self.assertEqual(manifold.b0, 2)
        self.assertGreaterEqual(manifold.b1, 0)
        self.assertEqual(manifold.centroids.shape[1], 4)
        self.assertTrue(any(manifold.attack))
        self.assertTrue(manifold.attacked_blocks)

    def test_one_cluster_in_calm_dimension(self):
        rng = np.random.default_rng(11)
        cloud = np.tile(np.array([0.0, 0.0, 0.0, 0.0]), (30, 1))
        cloud += rng.normal(0.0, 0.01, cloud.shape)
        manifold = ddmr.compute_manifold(cloud, ddmr.DIMENSION_CALM)
        self.assertEqual(manifold.b0, 1)
        self.assertFalse(any(manifold.attack))


class AnomalyTests(unittest.TestCase):
    def test_block_monitor_fires_on_a_rate_jump_only_after_warmup(self):
        monitor = ddmr.BlockMonitor()
        # 10 s of 80 rps on block 0.
        time_s = 0.0
        while time_s < 10.0:
            time_s += 1.0 / 80.0
            monitor.observe(0, time_s)
        self.assertEqual(monitor.anomaly(0, 10.1), 0.0)
        # 500 rps attack.
        for _ in range(2500):
            time_s += 1.0 / 500.0
            monitor.observe(0, time_s)
        self.assertGreater(monitor.anomaly(0, time_s), ddmr.ANOMALY_HIGH)

    def test_block_monitor_does_not_fire_on_poisson_noise(self):
        monitor = ddmr.BlockMonitor()
        rng = np.random.default_rng(3)
        time_s = 0.0
        while time_s < 10.0:
            time_s += 1.0 / 6.0
            monitor.observe(1, time_s)
        worst = 0.0
        # 45 s after warm-up, the same duration as the experiment.
        deadline = time_s + 45.0
        while time_s < deadline:
            time_s += rng.exponential(1.0 / 6.0)
            monitor.observe(1, time_s)
            worst = max(worst, monitor.anomaly(1, time_s))
        self.assertLess(worst, ddmr.ANOMALY_HIGH)

    def test_flow_anomaly_separates_a_bot_from_a_legit_flow(self):
        legit = ddmr.FlowState(consumer=1, block=0, baseline_latency_ms=50.0)
        bot = ddmr.FlowState(consumer=2, block=0, baseline_latency_ms=50.0)
        for index in range(20):
            time_s = float(index)
            legit.observe(time_s, 2.0)
            for burst in range(25):
                bot.observe(time_s + burst * 0.04, 30.0)
        self.assertEqual(legit.anomaly, 0.0)
        self.assertEqual(bot.anomaly, 1.0)


class DimensionTests(unittest.TestCase):
    def test_hysteresis_expands_and_contracts(self):
        controller = ddmr.DimensionController()
        self.assertEqual(controller.update(0.1, 0.0)[0], ddmr.DIMENSION_CALM)
        self.assertEqual(controller.update(0.9, 0.5)[0], ddmr.DIMENSION_CALM)
        dimension, switched = controller.update(0.9, 1.0)
        self.assertEqual(dimension, ddmr.DIMENSION_SHOCK)
        self.assertTrue(switched)
        # A single dip below the low threshold must not collapse.
        for tick in range(ddmr.DOWN_TICKS - 1):
            self.assertEqual(
                controller.update(0.1, 1.5 + tick)[0], ddmr.DIMENSION_SHOCK
            )
        self.assertEqual(controller.update(0.1, 5.0)[0], ddmr.DIMENSION_CALM)

    def test_dimension_does_not_depend_on_the_clock(self):
        early = ddmr.DimensionController()
        late = ddmr.DimensionController()
        for tick in range(2):
            early.update(0.9, 1.0 + tick)
            late.update(0.9, 1000.0 + tick)
        self.assertEqual(early.dimension, ddmr.DIMENSION_SHOCK)
        self.assertEqual(late.dimension, ddmr.DIMENSION_SHOCK)

    def test_no_attack_time_is_hardcoded_in_the_router(self):
        source = inspect.getsource(ddmr)
        self.assertNotIn("ATTACK_START", source)
        self.assertNotIn("ATTACK_END", source)


class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = scenario.run_seed(scenario.BASE_SEED)

    def test_ddmr_beats_static_tndn_by_fifteen_points(self):
        self.assertGreaterEqual(self.result.cdr_gain_points, 15.0)

    def test_ddmr_keeps_cdr_above_ninety_five_percent(self):
        self.assertGreaterEqual(self.result.runs["ddmr"].cdr_window, 95.0)

    def test_static_tndn_never_changes_dimension(self):
        dimensions = {
            entry["dimension"] for entry in self.result.runs["static"].timeline
        }
        self.assertEqual(dimensions, {ddmr.DIMENSION_CALM})

    def test_static_and_ddmr_share_the_detector(self):
        static = self.result.runs["static"].timeline
        ddmr_timeline = self.result.runs["ddmr"].timeline
        self.assertEqual(
            [entry["anomaly"] for entry in static],
            [entry["anomaly"] for entry in ddmr_timeline],
        )

    def test_expansion_happens_at_the_attack_not_before(self):
        run = self.result.runs["ddmr"]
        self.assertIsNotNone(run.first_expansion_s)
        self.assertGreaterEqual(run.first_expansion_s, scenario.ATTACK_START_S - 1.0)
        self.assertLessEqual(run.first_expansion_s, scenario.ATTACK_START_S + 2.0)

    def test_no_early_collapse(self):
        self.assertFalse(self.result.runs["ddmr"].early_collapse)

    def test_energy_clause_passes(self):
        self.assertLess(self.result.energy_cpu_j, self.result.energy_saved_j)

    def test_dimension_returns_to_calm_after_the_attack(self):
        run = self.result.runs["ddmr"]
        self.assertIsNotNone(run.last_shock_s)
        self.assertGreaterEqual(run.last_shock_s, scenario.ATTACK_END_S)

    def test_attack_alone_loads_the_primary(self):
        # Without rerouting the attacked block must lose at least half of its
        # legitimate requests; that is what the static baseline shows.
        self.assertLess(self.result.runs["static"].cdr_block0_window, 50.0)
        self.assertGreater(self.result.runs["ddmr"].cdr_block0_window, 90.0)

    def test_run_is_deterministic(self):
        again = scenario.run_seed(scenario.BASE_SEED)
        self.assertEqual(again.cdr_gain_points, self.result.cdr_gain_points)
        self.assertEqual(
            again.runs["ddmr"].delivered_window,
            self.result.runs["ddmr"].delivered_window,
        )


if __name__ == "__main__":
    unittest.main()
