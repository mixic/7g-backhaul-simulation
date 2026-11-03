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

"""Tests for the SDN control-plane prototype."""

from __future__ import annotations

import unittest

from simulation.dual_role import DualRoleSimulation, simulate_run
from simulation.sdn_plane import (
    FloodAwareController,
    SouthboundMessage,
    simulate_sdn,
)


class ControllerTests(unittest.TestCase):
    def test_no_alert_emits_no_instructions(self) -> None:
        simulation = DualRoleSimulation("steady", "fluid", 1)
        simulation.tick = 40
        self.assertEqual(FloodAwareController().reconcile(simulation), [])

    def test_flood_policy_pins_attacked_and_unattacked_roles(self) -> None:
        simulation = DualRoleSimulation("ddos", "fluid", 1)
        simulation.tick = 40
        messages = FloodAwareController().reconcile(simulation)
        by_node = {message.node: message for message in messages}
        self.assertNotIn("O", by_node)
        self.assertEqual(by_node["E2"].value, 0.0)
        self.assertEqual(by_node["E1"].value, 1.0)
        self.assertEqual(by_node["E3"].value, 1.0)
        self.assertEqual(by_node["M1"].value, 0.0)
        self.assertEqual(by_node["M2"].value, 0.0)
        for message in messages:
            self.assertIsInstance(message, SouthboundMessage)
            self.assertEqual(message.action, "set_alpha")
            self.assertGreaterEqual(message.value, 0.0)
            self.assertLessEqual(message.value, 1.0)

    def test_alert_schedule_is_read_from_the_scenario(self) -> None:
        simulation = DualRoleSimulation("ddos", "fluid", 1)
        simulation.tick = 39
        self.assertEqual(FloodAwareController().reconcile(simulation), [])
        simulation.tick = 40
        self.assertTrue(FloodAwareController().reconcile(simulation))


class SdnDataPlaneTests(unittest.TestCase):
    def test_steady_state_matches_local_control(self) -> None:
        local = simulate_run("steady", "fluid", 5)
        sdn = simulate_sdn("steady", 5)
        self.assertAlmostEqual(
            sdn.delivered_percent, local.delivered_percent, places=9
        )
        self.assertEqual(sdn.alpha_trace, local.alpha_trace)

    def test_flood_policy_protects_the_unattacked_target(self) -> None:
        local = simulate_run("ddos", "fluid", 5)
        sdn = simulate_sdn("ddos", 5)
        self.assertGreater(
            sdn.target_legit_delivered_percent["E3"],
            local.target_legit_delivered_percent["E3"] + 5.0,
        )
        self.assertGreaterEqual(sdn.target_legit_delivered_percent["E3"], 95.0)

    def test_same_seed_is_reproducible(self) -> None:
        first = simulate_sdn("ddos", 7)
        second = simulate_sdn("ddos", 7)
        self.assertEqual(first.delivered_percent, second.delivered_percent)
        self.assertEqual(first.alpha_trace, second.alpha_trace)


if __name__ == "__main__":
    unittest.main()
