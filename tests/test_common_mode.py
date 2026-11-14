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

"""Tests for the common-mode resilience testbed (H16-H20)."""

from __future__ import annotations

import unittest

from simulation import common_mode as cm


class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = cm.build_backhaul_scenario()

    def test_shape(self) -> None:
        self.assertEqual(len(self.scenario.nodes), 28)
        self.assertEqual(len(self.scenario.links), 30)
        self.assertEqual(len(self.scenario.tenants), 6)

    def test_links_reference_known_nodes(self) -> None:
        for link in self.scenario.links:
            self.assertIn(link.source, self.scenario.nodes)
            self.assertIn(link.target, self.scenario.nodes)

    def test_aggregation_conduit_has_three_links(self) -> None:
        conduit = [
            link for link in self.scenario.links if link.srlg == "agg-1"
        ]
        self.assertEqual(len(conduit), 3)
        self.assertEqual({link.target for link in conduit}, {"p1", "p2", "p3"})


class PathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = cm.build_backhaul_scenario()

    def test_single_path_is_the_shortest(self) -> None:
        paths = cm.select_paths(self.scenario, cm.ARMS["A1"])["t1"]
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].nodes, ("e1", "a1", "p1", "c1"))

    def test_shortest_three_share_the_fast_conduit(self) -> None:
        paths = cm.select_paths(self.scenario, cm.ARMS["A2"])["t1"]
        self.assertEqual(len(paths), 3)
        self.assertTrue(all("a1" in path.nodes for path in paths))

    def test_disjoint_three_use_three_conduits(self) -> None:
        paths = cm.select_paths(self.scenario, cm.ARMS["A3"])["t1"]
        self.assertEqual(len(paths), 3)
        self.assertEqual(
            {node for path in paths for node in path.nodes if node.startswith("a")},
            {"a1", "a2", "a3"},
        )

    def test_single_path_arms_agree(self) -> None:
        a1 = cm.select_paths(self.scenario, cm.ARMS["A1"])["t1"]
        a9 = cm.select_paths(self.scenario, cm.ARMS["A9"])["t1"]
        self.assertEqual([path.nodes for path in a1], [path.nodes for path in a9])

    def test_path_independence_metric(self) -> None:
        a1 = cm.select_paths(self.scenario, cm.ARMS["A1"])["t1"]
        a2 = cm.select_paths(self.scenario, cm.ARMS["A2"])["t1"]
        a3 = cm.select_paths(self.scenario, cm.ARMS["A3"])["t1"]
        self.assertAlmostEqual(cm.path_independence(a1), 1.0)
        self.assertAlmostEqual(cm.path_independence(a2), 1.0 / 3.0)
        self.assertAlmostEqual(cm.path_independence(a3), 1.0)


class SeedInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = cm.build_backhaul_scenario()

    def test_draws_are_deterministic(self) -> None:
        first = cm.build_seed_inputs(self.scenario, 42, "ai_link")
        second = cm.build_seed_inputs(self.scenario, 42, "ai_link")
        self.assertEqual(first.event, second.event)
        self.assertEqual(first.demand_factors, second.demand_factors)
        self.assertEqual(first.fallback_draws, second.fallback_draws)

    def test_event_targets_exist(self) -> None:
        link_names = {link.name for link in self.scenario.links}
        for kind in cm.EVENT_KINDS:
            inputs = cm.build_seed_inputs(self.scenario, 2026, kind)
            self.assertTrue(inputs.event.failed_links <= link_names)
            self.assertTrue(inputs.event.failed_nodes <= set(self.scenario.nodes))

    def test_event_sizes(self) -> None:
        self.assertEqual(
            len(cm.build_seed_inputs(self.scenario, 1, "srlg").event.failed_links), 3
        )
        self.assertEqual(
            len(
                cm.build_seed_inputs(
                    self.scenario, 1, "backhaul_cut"
                ).event.failed_links
            ),
            9,
        )
        link = cm.build_seed_inputs(self.scenario, 1, "link").event
        self.assertEqual(link.failed_links, frozenset({"a1-p1"}))
        combined = cm.build_seed_inputs(self.scenario, 1, "ai_link").event
        self.assertEqual(combined.failed_nodes, frozenset({"ai"}))
        self.assertEqual(combined.failed_links, frozenset({"a1-p1"}))

    def test_demand_and_fallback_ranges(self) -> None:
        inputs = cm.build_seed_inputs(self.scenario, 7, "none")
        for factor in inputs.demand_factors.values():
            self.assertGreaterEqual(factor, 0.95)
            self.assertLessEqual(factor, 1.05)
        for draw in inputs.fallback_draws.values():
            self.assertGreaterEqual(draw, 0.0)
            self.assertLess(draw, 1.0)


class HypothesisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = cm.build_backhaul_scenario()

    def ratio(self, arm: str, event: str, seed: int = 2026) -> float:
        result = cm.simulate(
            cm.ARMS[arm], scenario=self.scenario, seed=seed, event_kind=event
        )
        return result.availability_event * 100.0

    def test_h16_tenant_isolation_is_the_wrong_cut(self) -> None:
        self.assertAlmostEqual(self.ratio("A3", "tenant_gw"), 0.0)
        self.assertAlmostEqual(self.ratio("A4", "tenant_gw"), 100.0)
        self.assertAlmostEqual(self.ratio("A3", "idp"), 0.0)
        self.assertAlmostEqual(self.ratio("A4", "idp"), 0.0)

    def test_h17_independence_not_count(self) -> None:
        self.assertAlmostEqual(self.ratio("A2", "srlg"), 0.0)
        self.assertAlmostEqual(self.ratio("A3", "srlg"), 100.0)
        self.assertAlmostEqual(self.ratio("A1", "link"), 0.0)
        self.assertAlmostEqual(self.ratio("A2", "link"), 100.0)

    def test_h18_one_way_boundary_with_fallback(self) -> None:
        self.assertAlmostEqual(self.ratio("A5", "ai"), 0.0)
        self.assertAlmostEqual(self.ratio("A6", "ai"), 90.0)
        self.assertAlmostEqual(self.ratio("A5", "none"), 100.0)
        self.assertAlmostEqual(self.ratio("A6", "none"), 90.0)

    def test_h19_interaction(self) -> None:
        interaction = (self.ratio("A6", "ai_link") - self.ratio("A3", "ai_link")) - (
            self.ratio("A9", "ai_link") - self.ratio("A1", "ai_link")
        )
        self.assertGreaterEqual(interaction, 20.0)
        self.assertGreaterEqual(self.ratio("A6", "ai_link"), 80.0)
        self.assertLessEqual(self.ratio("A3", "ai_link"), 20.0)

    def test_h20_global_controller_is_a_dependency(self) -> None:
        self.assertAlmostEqual(self.ratio("A5", "controller_link"), 100.0)
        self.assertAlmostEqual(self.ratio("A8", "controller_link"), 0.0)
        self.assertAlmostEqual(self.ratio("A5", "none"), 100.0)
        self.assertAlmostEqual(self.ratio("A8", "none"), 100.0)

    def test_tested_fallback_beats_untested(self) -> None:
        tested = self.ratio("A6", "backhaul_cut")
        untested = self.ratio("A7", "backhaul_cut")
        self.assertGreater(tested, untested)

    def test_determinism(self) -> None:
        first = cm.simulate(
            cm.ARMS["A6"], scenario=self.scenario, seed=11, event_kind="ai_link"
        )
        second = cm.simulate(
            cm.ARMS["A6"], scenario=self.scenario, seed=11, event_kind="ai_link"
        )
        self.assertEqual(first, second)

    def test_none_event_reports_normal_operation(self) -> None:
        result = cm.simulate(
            cm.ARMS["A2"], scenario=self.scenario, seed=2026, event_kind="none"
        )
        self.assertAlmostEqual(
            result.availability_event, result.availability_overall
        )
        self.assertEqual(result.blast_radius, 0.0)
        self.assertEqual(result.recovery_s, 0.0)

    def test_fallback_rate_is_high_for_tested_and_lower_for_untested(self) -> None:
        tested = cm.simulate(
            cm.ARMS["A6"], scenario=self.scenario, seed=2026, event_kind="backhaul_cut"
        )
        untested = cm.simulate(
            cm.ARMS["A7"], scenario=self.scenario, seed=2026, event_kind="backhaul_cut"
        )
        self.assertGreaterEqual(tested.fallback_rate, untested.fallback_rate)

    def test_cost_ordering(self) -> None:
        a1 = cm.simulate(
            cm.ARMS["A1"], scenario=self.scenario, seed=2026, event_kind="none"
        )
        a9 = cm.simulate(
            cm.ARMS["A9"], scenario=self.scenario, seed=2026, event_kind="none"
        )
        a6 = cm.simulate(
            cm.ARMS["A6"], scenario=self.scenario, seed=2026, event_kind="none"
        )
        self.assertLess(a1.cost_index, a9.cost_index)
        self.assertLess(a9.cost_index, a6.cost_index)


if __name__ == "__main__":
    unittest.main()
