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

import random
import unittest

from simulation.cdn import SelfScalingContentNetwork
from simulation.channels import build_default_channels
from simulation.continuity import (
    AdaptiveMTULearner,
    FragmentReassembler,
    PacketFragment,
    SeamlessTransportSession,
)
from simulation.trends import SecondOrderTrendEstimator


class SeamlessTransportTests(unittest.TestCase):
    def setUp(self):
        self.channels = build_default_channels()
        for channel in self.channels:
            channel.packet_loss_base = 0.0
            channel.current_load = 0.0

    def test_payload_is_reconstructed_after_multimedium_fragmentation(self):
        session = SeamlessTransportSession(self.channels, rng=random.Random(7))
        payload = bytes(range(256)) * 100

        result = session.transmit(payload, session_id="test-mobile-session")

        self.assertEqual(result.payload, payload)
        self.assertGreater(len(result.fragments), 1)
        self.assertGreater(len(set(result.media_used)), 1)
        for fragment in result.fragments:
            channel = next(item for item in self.channels if item.name == fragment.medium)
            self.assertLessEqual(
                len(fragment.payload) + channel.encapsulation_overhead_bytes,
                fragment.mtu_bytes,
            )

    def test_route_allocation_accounts_for_bandwidth_and_latency(self):
        session = SeamlessTransportSession(self.channels, rng=random.Random(2))

        distribution = session.router.calculate_routing_distribution()

        self.assertAlmostEqual(sum(distribution.values()), 1.0)
        self.assertGreater(distribution["WiFi"], distribution["HF"])
        self.assertGreater(distribution["HF"], 0.0)

    def test_reassembler_handles_out_of_order_fragments(self):
        reassembler = FragmentReassembler()
        second = PacketFragment("s", 1, 3, 6, "WiFi", 1500, b"def")
        first = PacketFragment("s", 0, 0, 6, "HF", 512, b"abc")

        self.assertIsNone(reassembler.add(second))
        self.assertEqual(reassembler.add(first), b"abcdef")

    def test_failed_fragment_retries_over_another_medium(self):
        class RetryRng(random.Random):
            def choices(self, population, weights=None, *, cum_weights=None, k=1):
                return [population[0]]

            def __init__(self):
                super().__init__(0)
                self.failed_once = False

            def random(self):
                value = 0.0 if not self.failed_once else 0.9
                self.failed_once = True
                return value

        self.channels[0].packet_loss_base = 1.0
        session = SeamlessTransportSession(self.channels, rng=RetryRng())

        result = session.transmit(b"retry me", session_id="retry-session")

        self.assertGreater(result.retries, 0)
        self.assertNotIn(self.channels[0].name, result.media_used)
        self.assertEqual(result.payload, b"retry me")

    def test_second_order_forecast_uses_acceleration(self):
        estimate = SecondOrderTrendEstimator.estimate(
            current=5.0,
            previous=3.0,
            older=2.0,
            sample_interval=2.0,
            horizon=3.0,
        )

        self.assertEqual(estimate.velocity, 1.0)
        self.assertEqual(estimate.acceleration, 0.25)
        self.assertEqual(estimate.forecast, 9.125)

    def test_solar_flare_degrades_hf_only_and_recovers(self):
        for channel in self.channels:
            channel.update_dynamic_conditions("Solar_Flare")
        hf = next(channel for channel in self.channels if channel.name == "HF")
        wifi = next(channel for channel in self.channels if channel.name == "WiFi")
        self.assertEqual(hf.packet_loss_base, 0.85)
        self.assertEqual(hf.active_disaster, "Solar_Flare")
        self.assertEqual(wifi.packet_loss_base, wifi.base_packet_loss)
        self.assertEqual(wifi.active_disaster, "None")

        hf.update_dynamic_conditions()
        self.assertEqual(hf.packet_loss_base, hf.base_packet_loss)
        self.assertEqual(hf.active_disaster, "None")

    def test_request_acceleration_scales_and_warms_regional_cache(self):
        transport = SeamlessTransportSession(self.channels, rng=random.Random(1))
        cdn = SelfScalingContentNetwork(
            transport,
            cache_capacity_bytes=4096,
            requests_to_scale=3,
            forecast_horizon_seconds=5,
        )
        payload = b"popular content"

        first = cdn.request("bern-edge", "content-a", payload, timestamp=0.0)
        second = cdn.request("bern-edge", "content-a", payload, timestamp=1.0)

        self.assertFalse(first.cache_hit)
        self.assertGreater(cdn.demand_trends["bern-edge"].acceleration, 0.0)
        self.assertGreaterEqual(cdn.cache_node_count, 1)
        self.assertTrue(second.cache_hit)
        self.assertEqual(second.transfer.payload, payload)


if __name__ == "__main__":
    unittest.main()
