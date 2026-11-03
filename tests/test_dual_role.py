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

"""Tests for the continuous dual-role model and its acceptance tests."""

from __future__ import annotations

import unittest
from dataclasses import replace

import numpy as np

from simulation.dual_role import (
    DEFAULT_CONTROLLER,
    NOMINAL_DEMAND_MBPS,
    SEPARATED_ALPHA,
    Classifier,
    DualRoleSimulation,
    simulate_run,
)
from tools.benchmark_dual_role import _verdict


class DualRoleModelTests(unittest.TestCase):
    def test_unknown_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DualRoleSimulation("steady", "not_a_mode", 1)

    def test_same_seed_is_reproducible(self) -> None:
        first = simulate_run("flash_crowd", "fluid", 17)
        second = simulate_run("flash_crowd", "fluid", 17)
        self.assertEqual(first.delivered_percent, second.delivered_percent)
        self.assertEqual(first.alpha_trace, second.alpha_trace)

    def test_alpha_is_bounded_and_traced_for_every_tick(self) -> None:
        metrics = simulate_run("flash_crowd", "fluid", 5)
        for node, trace in metrics.alpha_trace.items():
            self.assertEqual(len(trace), 120, node)
            if node != "O":
                self.assertTrue(all(0.0 <= value <= 1.0 for value in trace), node)
        self.assertGreater(metrics.mean_alpha_abs_delta, 0.0)

    def test_separated_baseline_has_fixed_roles(self) -> None:
        metrics = simulate_run("ddos", "separated", 5)
        for node, trace in metrics.alpha_trace.items():
            expected = SEPARATED_ALPHA.get(node, 0.0)
            self.assertTrue(all(abs(value - expected) < 1e-12 for value in trace), node)
        self.assertEqual(metrics.mean_alpha_abs_delta, 0.0)

    def test_delivery_is_bounded_and_non_negative(self) -> None:
        for scenario in ("steady", "flash_crowd", "ddos"):
            for mode in ("fluid", "separated"):
                metrics = simulate_run(scenario, mode, 3)
                self.assertGreaterEqual(metrics.delivered_goodput_mbps, 0.0)
                self.assertGreaterEqual(metrics.delivered_percent, 0.0)
                self.assertLessEqual(metrics.delivered_percent, 100.0 + 1e-9)

    def test_link_loads_never_exceed_capacity(self) -> None:
        simulation = DualRoleSimulation("steady", "fluid", 2)
        allocation = simulation._allocate(dict(NOMINAL_DEMAND_MBPS))
        capacities = {link.name: link.capacity_mbps for link in simulation.links}
        for name, load in allocation.link_load.items():
            self.assertLessEqual(load, capacities[name] + 1e-6, name)

    def test_serving_and_forwarding_share_the_resource(self) -> None:
        simulation = DualRoleSimulation("steady", "fluid", 2)
        simulation.alpha["E2"] = 1.0
        self.assertAlmostEqual(simulation.forward_capacity("E2"), 0.0)
        simulation.alpha["E2"] = 0.0
        self.assertAlmostEqual(simulation.forward_capacity("E2"), 140.0)
        self.assertAlmostEqual(simulation.serve_capacity("E2"), 0.0)

    def test_cache_warms_when_capacity_is_committed_to_serving(self) -> None:
        simulation = DualRoleSimulation("steady", "separated", 2)
        simulation.run()
        self.assertGreater(simulation.cache_fill["E2"], 0.0)
        # M1 is a pure forwarder in the separated baseline and stays cold.
        self.assertEqual(simulation.cache_fill["M1"], 0.0)

    def test_ddos_floods_the_attacked_target(self) -> None:
        metrics = simulate_run("ddos", "fluid", 3)
        self.assertLess(
            metrics.target_delivered_percent["E2"],
            metrics.target_delivered_percent["E1"],
        )
        self.assertLess(
            metrics.target_delivered_percent["E2"],
            metrics.target_delivered_percent["E3"],
        )


class AttackAdmissionTests(unittest.TestCase):
    def test_invalid_classifier_rates_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Classifier(false_positive=1.2)
        with self.assertRaises(ValueError):
            Classifier(false_negative=-0.1)

    def test_unknown_admission_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DualRoleSimulation("ddos", "fluid", 1, admission="unknown")

    def test_perfect_admission_recovers_the_attacked_target(self) -> None:
        open_loop = simulate_run("ddos", "fluid", 5)
        admitted = simulate_run(
            "ddos",
            "fluid",
            5,
            admission="authenticated",
            classifier=Classifier(0.0, 0.0),
        )
        self.assertGreater(
            admitted.target_legit_delivered_percent["E2"],
            open_loop.target_legit_delivered_percent["E2"] + 10.0,
        )

    def test_perfect_admission_reduces_collateral_damage(self) -> None:
        open_loop = simulate_run("ddos", "fluid", 5)
        admitted = simulate_run(
            "ddos",
            "fluid",
            5,
            admission="authenticated",
            classifier=Classifier(0.0, 0.0),
        )
        self.assertGreater(
            admitted.target_legit_delivered_percent["E3"],
            open_loop.target_legit_delivered_percent["E3"],
        )

    def test_false_positives_cost_legitimate_delivery(self) -> None:
        admitted = simulate_run(
            "ddos",
            "fluid",
            5,
            admission="authenticated",
            classifier=Classifier(0.2, 0.0),
        )
        self.assertLessEqual(admitted.target_legit_delivered_percent["E1"], 82.0)

    def test_open_admission_with_all_attack_admitted_matches_the_open_loop(self) -> None:
        open_loop = simulate_run("ddos", "fluid", 5)
        admitted = simulate_run(
            "ddos",
            "fluid",
            5,
            admission="authenticated",
            classifier=Classifier(0.0, 1.0),
        )
        self.assertAlmostEqual(
            admitted.delivered_percent, open_loop.delivered_percent, places=6
        )


class AcceptanceTestLogicTests(unittest.TestCase):
    @staticmethod
    def _sweep(separated_percent: float, goodput_ratio: float, p95_ratio: float):
        return [
            {
                "load_multiplier": 1.4,
                "mode": "separated",
                "delivered_percent_mean": separated_percent,
                "delivered_goodput_mean": 100.0,
                "p95_latency_mean": 10.0,
            },
            {
                "load_multiplier": 1.4,
                "mode": "fluid",
                "delivered_percent_mean": 97.0,
                "delivered_goodput_mean": 100.0 * goodput_ratio,
                "p95_latency_mean": 10.0 * p95_ratio,
            },
        ]

    def test_both_bounds_failing_refutes_the_claim(self) -> None:
        rows = _verdict(self._sweep(94.0, 1.02, 2.0), [1, 2])
        by_test = {row["test"]: row for row in rows}
        self.assertEqual(by_test["L_star"]["value"], 1.4)
        self.assertFalse(by_test["goodput_margin"]["passed"])
        self.assertFalse(by_test["latency_bound"]["passed"])

    def test_both_bounds_passing_confirms_the_claim(self) -> None:
        rows = _verdict(self._sweep(94.0, 1.10, 1.2), [1, 2])
        by_test = {row["test"]: row for row in rows}
        self.assertTrue(by_test["goodput_margin"]["passed"])
        self.assertTrue(by_test["latency_bound"]["passed"])

    def test_no_crossing_is_inconclusive(self) -> None:
        rows = _verdict(self._sweep(99.0, 1.10, 1.2), [1, 2])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["test"], "L_star")
        self.assertFalse(rows[0]["passed"])


class SignedTrendTests(unittest.TestCase):
    def test_flood_wave_ramps_up_plateaus_and_decays(self) -> None:
        from simulation.dual_role import SCENARIOS

        attack = SCENARIOS["flood_wave"].attack
        self.assertAlmostEqual(attack(47)["E2"], 250.0 * 7 / 15)
        self.assertEqual(attack(70)["E2"], 250.0)
        self.assertAlmostEqual(attack(92)["E2"], 250.0 * 8 / 15)
        self.assertEqual(attack(100)["E2"], 0.0)

    def test_signed_trends_change_the_alpha_trajectory(self) -> None:
        positive = simulate_run("flood_wave", "fluid", 3)
        signed = simulate_run(
            "flood_wave",
            "fluid",
            3,
            controller=replace(DEFAULT_CONTROLLER, signed_trends=True),
        )
        self.assertNotEqual(
            positive.alpha_trace["E2"], signed.alpha_trace["E2"]
        )

    def test_signed_trends_oscillate_more(self) -> None:
        positive = np.asarray(
            simulate_run("flood_wave", "fluid", 3).alpha_trace["E2"]
        )
        signed = np.asarray(
            simulate_run(
                "flood_wave",
                "fluid",
                3,
                controller=replace(DEFAULT_CONTROLLER, signed_trends=True),
            ).alpha_trace["E2"]
        )
        positive_delta = np.mean(np.abs(np.diff(positive)))
        signed_delta = np.mean(np.abs(np.diff(signed)))
        self.assertGreater(signed_delta, positive_delta)

    def test_legit_traces_have_one_value_per_tick(self) -> None:
        metrics = simulate_run("flood_wave", "fluid", 3)
        for target in ("E1", "E2", "E3"):
            self.assertEqual(len(metrics.legit_delivered_trace[target]), 120)
            self.assertEqual(len(metrics.legit_offered_trace[target]), 120)


if __name__ == "__main__":
    unittest.main()
