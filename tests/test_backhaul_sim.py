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

import unittest

from backhaul_sim.engine import (
    AIContentDistributionPolicy,
    RoutingEngine,
    build_reference_flows,
    build_reference_scenario,
    build_tomahawk_cdn_flows,
    build_tomahawk_cdn_scenario,
)


class BackhaulSimulationTests(unittest.TestCase):
    def test_reference_scenario_has_expected_nodes(self):
        scenario = build_reference_scenario()
        self.assertIn("campus-a", scenario.nodes)
        self.assertIn("cloud-aws", scenario.nodes)
        self.assertIn("satellite-leo", scenario.nodes)

    def test_routing_selects_best_path(self):
        scenario = build_reference_scenario()
        engine = RoutingEngine(scenario)
        flow = build_reference_flows()[0]
        route = engine.best_route_for_flow(flow)
        self.assertTrue(route[0] == "campus-a")
        self.assertTrue(route[-1] == "cloud-aws")

    def test_route_evaluation_is_positive(self):
        scenario = build_reference_scenario()
        engine = RoutingEngine(scenario)
        flow = build_reference_flows()[0]
        route = engine.best_route_for_flow(flow)
        result = engine.evaluate_route(flow, route)
        self.assertGreater(result.latency_ms, 0.0)
        self.assertGreaterEqual(result.reliability, 0.0)
        self.assertGreaterEqual(result.estimated_throughput_gbps, 0.0)

    def test_tomahawk_cdn_scenario_includes_ai_routers(self):
        scenario = build_tomahawk_cdn_scenario()
        self.assertIn("tomahawk-npu-1", scenario.nodes)
        self.assertIn("tomahawk-npu-2", scenario.nodes)
        self.assertIn("cdn-cache-1", scenario.nodes)
        policy = AIContentDistributionPolicy(router_intelligence=1.5)
        engine = RoutingEngine(scenario)
        flow = build_tomahawk_cdn_flows()[0]
        route = engine.reinforcement_route(flow, policy)
        self.assertTrue(route[0] == "regional-edge")
        self.assertTrue(route[-1] == "video-edge")


if __name__ == "__main__":
    unittest.main()
