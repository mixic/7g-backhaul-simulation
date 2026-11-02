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

import math
import unittest
from dataclasses import replace

from simulation.role_fluid import (
    DEFAULT_WEIGHTS,
    POLICIES,
    SCENARIOS,
    FlowWeights,
    RoleFluidSimulation,
    build_links,
    build_nodes,
    build_paths,
    simulate_run,
)


class PathModelTests(unittest.TestCase):
    def test_every_target_has_several_candidate_paths(self):
        paths = build_paths(build_nodes(), build_links())
        for target, candidates in paths.items():
            self.assertGreaterEqual(len(candidates), 2, target)
            for path in candidates:
                self.assertEqual(path.nodes[0], "O")
                self.assertEqual(path.nodes[-1], target)

    def test_small_mtu_paths_pay_a_fragmentation_penalty(self):
        paths = build_paths(build_nodes(), build_links())
        factors = set()
        for candidates in paths.values():
            for path in candidates:
                smallest = min(link.mtu_bytes for link in path.links)
                expected = max(1.0, 1500.0 / smallest)
                self.assertAlmostEqual(path.fragment_factor, expected)
                factors.add(round(path.fragment_factor, 6))
        # Every path ends over a 1200- or 1500-byte medium; both coefficients occur.
        self.assertEqual(factors, {1.0, 1.25})

    def test_path_capacity_is_bounded_by_its_bottleneck(self):
        paths = build_paths(build_nodes(), build_links())
        for candidates in paths.values():
            for path in candidates:
                bottleneck = min(link.capacity_mbps for link in path.links)
                self.assertLessEqual(path.capacity_mbps, bottleneck + 1e-9)


class SimulationTests(unittest.TestCase):
    def test_unknown_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            RoleFluidSimulation(SCENARIOS["steady"], "not_a_policy", 1)

    def test_static_design_never_switches_roles(self):
        metrics = simulate_run("steady", "static_design", 3)
        self.assertEqual(metrics.role_switches, 0)

    def test_delivery_is_bounded_and_cost_positive(self):
        for policy in POLICIES:
            metrics = simulate_run("flash_crowd", policy, 5)
            self.assertGreater(metrics.delivered_percent, 0.0)
            self.assertLessEqual(metrics.delivered_percent, 100.0001)
            self.assertGreater(metrics.total_cost_usd, 0.0)

    def test_same_seed_is_reproducible(self):
        first = simulate_run("steady", "local_fluid", 7)
        second = simulate_run("steady", "local_fluid", 7)
        self.assertEqual(first, second)

    def test_damping_reduces_share_oscillation(self):
        damped = simulate_run("flash_crowd", "local_fluid", 9)
        undamped = simulate_run("flash_crowd", "local_reactive", 9)
        self.assertLess(damped.oscillation_index, undamped.oscillation_index)

    def test_large_hysteresis_stops_role_churn(self):
        weights = replace(DEFAULT_WEIGHTS, hysteresis_usd=10.0)
        simulation = RoleFluidSimulation(
            SCENARIOS["flash_crowd"], "local_fluid", 4, weights
        )
        metrics = simulation.run()
        self.assertEqual(metrics.role_switches, 0)

    def test_unmet_signal_improves_delivery_under_a_flash_crowd(self):
        fluid = simulate_run("flash_crowd", "local_fluid", 6)
        congestion_only = simulate_run("flash_crowd", "local_congestion", 6)
        self.assertGreaterEqual(
            fluid.delivered_percent,
            congestion_only.delivered_percent - 1e-9,
        )

    def test_serving_relieves_congested_paths(self):
        """A serve role at the demand node must reduce transit load."""
        scenario = SCENARIOS["steady"]
        serving = RoleFluidSimulation(scenario, "static_design", 2)
        forwarding = RoleFluidSimulation(scenario, "centralized_greedy", 2)
        serving_metrics = serving.run()
        forwarding_metrics = forwarding.run()
        self.assertGreater(serving_metrics.local_serve_percent, 0.0)
        self.assertLessEqual(
            forwarding_metrics.local_serve_percent,
            serving_metrics.local_serve_percent,
        )

    def test_link_loads_never_exceed_capacity(self):
        simulation = RoleFluidSimulation(SCENARIOS["steady"], "local_fluid", 8)
        weights = DEFAULT_WEIGHTS
        demand = {"E1": 40.0, "E2": 50.0, "E3": 30.0}
        capacities = {link.name: link.capacity_mbps for link in simulation.links}
        allocation = simulation._allocate(simulation.roles, demand, capacities)
        for name, load in allocation.link_load.items():
            self.assertLessEqual(load, capacities[name] + 1e-9, name)
        for target, value in allocation.delivered_mbps.items():
            self.assertLessEqual(value, demand[target] + 1e-9, target)

    def test_weights_are_dimensionless_and_positive(self):
        self.assertGreater(FlowWeights().temperature, 0.0)
        self.assertGreater(FlowWeights().damping, 0.0)
        self.assertLessEqual(FlowWeights().damping, 1.0)
        self.assertTrue(math.isfinite(FlowWeights().w_balance_bonus))


if __name__ == "__main__":
    unittest.main()
