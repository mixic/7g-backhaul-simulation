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

from simulation.link_queue import DEFAULT_QUEUE_LIMIT_PACKETS, DropTailQueue
from validation.scenario_s1 import POLICIES, simulate


class DropTailQueueTests(unittest.TestCase):
    def test_empty_queue_adds_no_delay(self):
        queue = DropTailQueue()
        outcome = queue.arrive(0.0, 0.001)
        self.assertFalse(outcome.dropped)
        self.assertEqual(outcome.queue_delay_seconds, 0.0)
        self.assertAlmostEqual(outcome.total_seconds, 0.001)
        self.assertEqual(queue.occupancy, 1)

    def test_packets_are_served_first_in_first_out(self):
        queue = DropTailQueue()
        first = queue.arrive(0.0, 0.01)
        second = queue.arrive(0.0, 0.01)
        self.assertEqual(first.queue_delay_seconds, 0.0)
        self.assertAlmostEqual(second.queue_delay_seconds, 0.01)

    def test_occupancy_expires_after_departure(self):
        queue = DropTailQueue()
        queue.arrive(0.0, 0.01)
        self.assertEqual(queue.occupancy, 1)
        queue.arrive(0.02, 0.01)
        self.assertEqual(queue.occupancy, 1)

    def test_overflow_drops_and_consumes_no_service(self):
        queue = DropTailQueue(limit_packets=2)
        queue.arrive(0.0, 0.01)
        queue.arrive(0.0, 0.01)
        overflow = queue.arrive(0.0, 0.01)
        self.assertTrue(overflow.dropped)
        self.assertEqual(overflow.total_seconds, 0.0)
        self.assertEqual(queue.occupancy, 2)

    def test_default_limit_is_one_hundred_packets(self):
        self.assertEqual(DEFAULT_QUEUE_LIMIT_PACKETS, 100)
        queue = DropTailQueue()
        for _ in range(DEFAULT_QUEUE_LIMIT_PACKETS):
            self.assertFalse(queue.arrive(0.0, 0.001).dropped)
        self.assertTrue(queue.arrive(0.0, 0.001).dropped)

    def test_invalid_arguments_are_rejected(self):
        with self.assertRaises(ValueError):
            DropTailQueue(limit_packets=0)
        with self.assertRaises(TypeError):
            DropTailQueue(limit_packets=1.5)
        with self.assertRaises(ValueError):
            DropTailQueue().arrive(0.0, 0.0)


class ScenarioS1Tests(unittest.TestCase):
    def test_queue_free_model_hides_handover_overload(self):
        no_queue = simulate("s1_handover", POLICIES[0], 1)
        fifo = simulate("s1_handover", POLICIES[1], 1)
        self.assertGreater(no_queue["packet_delivery_percent"], 99.0)
        self.assertLess(fifo["packet_delivery_percent"], 96.0)
        self.assertGreater(fifo["one_way_delay_p95_ms"], 100.0)
        self.assertLess(no_queue["one_way_delay_p95_ms"], 30.0)

    def test_nominal_scenario_has_no_queueing(self):
        no_queue = simulate("s0_nominal", POLICIES[0], 1)
        fifo = simulate("s0_nominal", POLICIES[1], 1)
        self.assertAlmostEqual(
            no_queue["one_way_delay_p95_ms"],
            fifo["one_way_delay_p95_ms"],
            places=6,
        )
        self.assertEqual(
            no_queue["primary_share_percent"],
            fifo["primary_share_percent"],
        )


if __name__ == "__main__":
    unittest.main()
