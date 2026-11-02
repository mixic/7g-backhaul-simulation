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

from simulation.rfmp import (
    HANDOFF_HEADSTART,
    HANDOFF_TAIL,
    JITTER_SECONDS,
    PACKET_COUNT,
    SERVE_END,
    SERVE_START,
    AckClock,
    RfmpSimulation,
    active_sources,
    hash_unit,
    jitter,
    simulate,
)


class RoleEpochTests(unittest.TestCase):
    def test_overlap_windows_have_two_sources(self):
        for boundary in (SERVE_START, SERVE_END):
            self.assertEqual(active_sources(boundary), ("O", "X"))
            self.assertEqual(
                active_sources(boundary - HANDOFF_HEADSTART / 2),
                ("O", "X"),
            )
            self.assertEqual(
                active_sources(boundary + HANDOFF_TAIL / 2),
                ("O", "X"),
            )

    def test_single_source_outside_overlaps(self):
        self.assertEqual(active_sources(1.0), ("O",))
        self.assertEqual(active_sources(8.0), ("X",))
        self.assertEqual(active_sources(15.0), ("O",))
        self.assertEqual(active_sources(SERVE_START - HANDOFF_HEADSTART - 1e-9), ("O",))
        self.assertEqual(active_sources(SERVE_START + HANDOFF_TAIL + 1e-9), ("X",))

    def test_jitter_is_deterministic_and_bounded(self):
        for index in (0, 1, 17, 24999):
            self.assertEqual(jitter(3, index), jitter(3, index))
            self.assertLessEqual(abs(jitter(3, index)), JITTER_SECONDS + 1e-12)
        self.assertNotEqual(jitter(3, 17), jitter(4, 17))


class ReorderingTests(unittest.TestCase):
    @staticmethod
    def _arrival(time_value: float, sequence: int) -> tuple:
        return (time_value, sequence, "X", "XD", time_value, sequence * 0.0008)

    def test_in_order_arrivals_release_immediately(self):
        simulation = RfmpSimulation(1)
        metrics = simulation._receive(
            [self._arrival(0.010, 0), self._arrival(0.011, 1)], 0
        )
        self.assertEqual(metrics.released_packets, 2)
        self.assertEqual(metrics.duplicate_percent, 0.0)

    def test_hole_is_filled_and_buffered_packets_release(self):
        simulation = RfmpSimulation(1)
        metrics = simulation._receive(
            [
                self._arrival(0.000, 0),
                self._arrival(0.010, 2),
                self._arrival(0.020, 1),
            ],
            0,
        )
        self.assertEqual(metrics.released_packets, 3)
        self.assertGreater(metrics.reorder_stall_max_ms, 9.0)

    def test_duplicate_is_suppressed(self):
        simulation = RfmpSimulation(1)
        metrics = simulation._receive(
            [self._arrival(0.000, 0), self._arrival(0.001, 0), self._arrival(0.002, 1)],
            0,
        )
        self.assertEqual(metrics.released_packets, 2)
        self.assertAlmostEqual(metrics.duplicate_percent, 100.0 / 3.0, places=6)

    def test_deadline_skips_a_missing_sequence(self):
        simulation = RfmpSimulation(1)
        metrics = simulation._receive(
            [
                self._arrival(0.000, 0),
                self._arrival(0.050, 2),
                self._arrival(0.300, 3),
            ],
            0,
        )
        # seq 1 is declared lost after the 200 ms deadline, so 2 and 3 release.
        self.assertGreaterEqual(metrics.released_packets, 3)
        self.assertGreater(metrics.late_drop_percent, 0.0)

    def test_duplicates_inside_handoff_window_are_counted(self):
        simulation = RfmpSimulation(1)
        boundary = SERVE_START
        metrics = simulation._receive(
            [
                self._arrival(boundary + 0.001, 7500),
                self._arrival(boundary + 0.002, 7500),
            ],
            0,
        )
        self.assertGreater(metrics.handoff_duplicate_percent, 0.0)


class AckClockTests(unittest.TestCase):
    def test_rtt_tracks_samples_and_rto_has_floor(self):
        clock = AckClock(ack_interval=0.01)
        self.assertTrue(clock.on_release(0.050, 0.000))
        self.assertAlmostEqual(clock.srtt_ms, 50.0, places=6)
        self.assertGreaterEqual(clock.rto_ms, 50.0)

    def test_ack_is_rate_limited(self):
        clock = AckClock(ack_interval=0.01)
        self.assertTrue(clock.on_release(0.010, 0.000))
        self.assertFalse(clock.on_release(0.011, 0.000))
        self.assertTrue(clock.on_release(0.020, 0.000))

    def test_invalid_interval_is_rejected(self):
        with self.assertRaises(ValueError):
            AckClock(ack_interval=0.0)


class ScenarioTests(unittest.TestCase):
    def test_replicate_is_reproducible(self):
        self.assertEqual(simulate(2), simulate(2))

    def test_scenario_metrics(self):
        metrics = simulate(1)
        self.assertAlmostEqual(metrics.in_order_delivery_percent, 100.0, places=6)
        self.assertAlmostEqual(metrics.duplicate_percent, 0.990099, places=4)
        self.assertGreater(metrics.reorder_stall_p95_ms, 15.0)
        self.assertLess(metrics.reorder_stall_p95_ms, 17.0)
        self.assertLess(metrics.transition_gap_6s_ms, 2.0)
        self.assertLess(metrics.transition_gap_12s_ms, 2.0)
        self.assertEqual(metrics.late_drop_percent, 0.0)

    def test_rt2_cache_warms_and_sources_only_hits(self):
        metrics = simulate(1, mode="rt2")
        self.assertAlmostEqual(metrics.in_order_delivery_percent, 100.0, places=6)
        self.assertEqual(metrics.duplicate_percent, 0.0)
        # Linear warm-up over 8 s inside a 6 s serve epoch averages 3/8.
        self.assertAlmostEqual(metrics.served_fraction_percent, 37.5, places=1)

    def test_rt2_with_a_warm_cache_serves_everything(self):
        metrics = simulate(1, mode="rt2", warm_seconds=0.0)
        self.assertAlmostEqual(metrics.served_fraction_percent, 100.0, places=6)
        self.assertEqual(metrics.duplicate_percent, 0.0)

    def test_rt2_is_deterministic(self):
        self.assertEqual(simulate(4, mode="rt2"), simulate(4, mode="rt2"))

    def test_hit_fraction_is_zero_outside_the_serve_epoch(self):
        simulation = RfmpSimulation(1, mode="rt2")
        self.assertEqual(simulation.hit_fraction(0.0), 0.0)
        self.assertEqual(simulation.hit_fraction(5.999), 0.0)
        self.assertEqual(simulation.hit_fraction(12.0), 0.0)
        self.assertAlmostEqual(simulation.hit_fraction(10.0), 0.5)

    def test_hash_unit_is_a_probability(self):
        for index in (0, 1, 4999, 24999):
            value = hash_unit(2, index)
            self.assertGreaterEqual(value, 0.0)
            self.assertLess(value, 1.0)

    def test_arrival_count_includes_the_handoff_duplicates(self):
        simulation = RfmpSimulation(1)
        metrics = simulation.run()
        self.assertEqual(metrics.released_packets, PACKET_COUNT)
        # Two 100 ms overlaps at 12 Mbit/s produce about 250 duplicate arrivals.
        self.assertGreaterEqual(metrics.arrivals, PACKET_COUNT + 240)
        self.assertLessEqual(metrics.arrivals, PACKET_COUNT + 260)


if __name__ == "__main__":
    unittest.main()
