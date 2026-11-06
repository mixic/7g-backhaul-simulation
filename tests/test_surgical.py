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

"""Tests for the surgical, rate-controlled state-update testbed."""

from __future__ import annotations

import unittest

import numpy as np

from simulation.surgical.config import (
    FIBER,
    MICRO,
    K8S,
    PRESSURE,
    SAT,
    SAVANT,
    SURGICAL,
    parse_arm,
    scenario_exp1,
    scenario_exp4,
)
from simulation.surgical.controllers import Governor
from simulation.surgical.link import class_id
from simulation.surgical.sim import run_and_score
from simulation.surgical.state import NodeState, QueuePolicy, StateLedger
from simulation.surgical.topology import HOST_UPLINK, build_topology


class TopologyTests(unittest.TestCase):
    def test_three_media_and_full_connectivity(self) -> None:
        topo = build_topology()
        self.assertEqual(topo.n_nodes, 100)
        kinds = {link.kind for link in topo.links.values()}
        self.assertEqual(kinds, {"fiber", "microwave", "satellite"})
        seen, stack = {0}, [0]
        while stack:
            node = stack.pop()
            for peer in topo.adj[node]:
                if peer not in seen:
                    seen.add(peer)
                    stack.append(peer)
        self.assertEqual(len(seen), 100)

    def test_origins_are_single_uplink_leaves(self) -> None:
        """Without leaf origins a name-targeted flood has no shared bottleneck."""
        topo = build_topology()
        for host, uplink in HOST_UPLINK.items():
            self.assertEqual(topo.adj[host], [uplink])
            self.assertIn(host, set(topo.hosts.values()))

    def test_channel_specs_match_the_brief(self) -> None:
        self.assertAlmostEqual(FIBER.capacity_bps, 1e9)
        self.assertAlmostEqual(FIBER.prop_s, 0.002)
        self.assertAlmostEqual(MICRO.capacity_bps, 100e6)
        self.assertEqual(MICRO.loss, 0.01)
        self.assertAlmostEqual(SAT.prop_s, 0.5)
        self.assertEqual(SAT.mtu, 576)


class LedgerTests(unittest.TestCase):
    def test_alpha_edit_is_measured(self) -> None:
        state = NodeState(0, 0.0, QueuePolicy())
        ledger = StateLedger()
        ledger.set_alpha(1.0, state, 0.2)
        ledger.set_alpha(2.0, state, 0.4)
        self.assertEqual(len(ledger.edits), 2)
        self.assertAlmostEqual(ledger.edits[0].magnitude, 0.2, places=9)
        _, speed, _, magnitude = ledger.churn_series(4.0, 0.1)
        self.assertGreater(magnitude.sum(), 0.0)
        self.assertGreater(speed.max(), 0.0)

    def test_zero_magnitude_edit_is_not_recorded(self) -> None:
        state = NodeState(0, 0.5, QueuePolicy())
        ledger = StateLedger()
        ledger.set_alpha(1.0, state, 0.5)
        self.assertEqual(ledger.edits, [])


class GovernorTests(unittest.TestCase):
    def test_speed_and_acceleration_caps_hold(self) -> None:
        gov = Governor(0.0, vmax=0.35, amax=0.60)
        gov.target = 1.0
        speeds = []
        previous = gov.value
        for _ in range(400):
            gov.step(0.2)
            speeds.append(abs(gov.value - previous) / 0.2)
            previous = gov.value
        self.assertLessEqual(max(speeds), 0.35 + 1e-6)
        self.assertAlmostEqual(gov.value, 1.0, places=3)
        deltas = np.abs(np.diff(speeds))
        self.assertLessEqual(float(deltas.max()), 0.60 * 0.2 + 1e-6)


class ClassIdentityTests(unittest.TestCase):
    def test_name_and_region_are_distinct_classes(self) -> None:
        self.assertNotEqual(class_id(0, 0), class_id(0, 1))
        self.assertNotEqual(class_id(0, 0), class_id(1, 0))
        self.assertEqual(class_id(3, 2), 1 + 3 * 8 + 2)


class EndToEndTests(unittest.TestCase):
    def test_steady_state_is_quiet(self) -> None:
        """Phase 1: no shockwave -> no state edits at all."""
        result = run_and_score(
            scenario_exp1(0, SURGICAL).child(attack_rate=0.0, duration=40.0)
        )
        self.assertEqual(result["edits"], 0)
        self.assertGreater(result["goodput_base"], 0.8)

    def test_shockwave_triggers_a_surgical_edit(self) -> None:
        result = run_and_score(scenario_exp1(1, SURGICAL))
        self.assertGreater(result["edits"], 0)
        self.assertGreaterEqual(result["ns_classes_peak"], 1)

    def test_goodput_is_a_probability(self) -> None:
        result = run_and_score(scenario_exp1(2, K8S))
        self.assertGreaterEqual(result["goodput_shock"], 0.0)
        self.assertLessEqual(result["goodput_shock"], 1.0)
        self.assertGreaterEqual(result["goodput_base"], 0.0)
        self.assertLessEqual(result["goodput_base"], 1.0)

    def test_paired_seed_is_deterministic(self) -> None:
        first = run_and_score(scenario_exp1(5, K8S).child(duration=25.0))
        second = run_and_score(scenario_exp1(5, K8S).child(duration=25.0))
        self.assertEqual(first["goodput_base"], second["goodput_base"])
        self.assertEqual(first["edits"], second["edits"])

    def test_pressure_controller_churns_more_than_surgical(self) -> None:
        baseline = run_and_score(scenario_exp1(3, PRESSURE))
        surgical = run_and_score(scenario_exp1(3, SURGICAL))
        self.assertGreater(baseline["churn_mean"], surgical["churn_mean"])


class SavantSweepTests(unittest.TestCase):
    def test_arm_label_maps_to_a_parameterised_controller(self) -> None:
        controller, kwargs = parse_arm("savant_a85")
        self.assertEqual(controller, SAVANT)
        self.assertAlmostEqual(kwargs["savant_alpha"], 0.85)
        plain, empty = parse_arm(SURGICAL)
        self.assertEqual((plain, empty), (SURGICAL, {}))

    def test_sweep_arm_records_the_parameterised_label(self) -> None:
        result = run_and_score(scenario_exp4(0, "savant_a85").child(duration=22.0))
        self.assertEqual(result["controller"], "savant_a85")

    def test_savant_shifts_alpha_and_reports_spillover(self) -> None:
        armed = run_and_score(scenario_exp4(0, "savant_a85"))
        control = run_and_score(scenario_exp4(0, SURGICAL))
        self.assertGreater(armed["alpha_edited_nodes"], 0)
        self.assertTrue(np.isfinite(armed["spillover"]))
        # the savant sacrifices transit, so the control keeps alpha untouched
        self.assertEqual(int(control["alpha_edited_nodes"]), 0)

    def test_both_arms_report_a_finite_affected_delivery(self) -> None:
        for arm in ("savant_a85", SURGICAL, K8S):
            result = run_and_score(scenario_exp4(1, arm).child(duration=45.0))
            self.assertTrue(np.isfinite(result["gp_affected"]))
            self.assertGreaterEqual(result["gp_affected"], 0.0)
            self.assertLessEqual(result["gp_affected"], 1.0)


if __name__ == "__main__":
    unittest.main()
