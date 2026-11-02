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
import tempfile
import unittest
from pathlib import Path

from simulation.analytics import CSVNetworkLogger
from simulation.carrier_bonding import BondedCarrierScheduler
from simulation.channels import build_default_channels
from simulation.congestion import AIMDCongestionController
from simulation.continuity import SeamlessTransportSession
from simulation.learning import TabularQRoutingAgent
from simulation.mobility import MobileIpAnchor, RadioCell, RadioHandoverController
from simulation.security import AuthenticationError, SessionAuthenticator


class ProtocolModelTests(unittest.TestCase):
    def setUp(self):
        self.channels = build_default_channels()
        for channel in self.channels:
            channel.packet_loss_base = 0.0
            channel.current_load = 0.0

    def test_radio_handover_preserves_ip_and_applies_hysteresis_ttt(self):
        anchor = MobileIpAnchor()
        controller = RadioHandoverController(anchor, hysteresis_db=3, time_to_trigger_samples=2)
        first = RadioCell("cell-a", "Mobile", -80)
        better = RadioCell("cell-b", "Mobile", -76)

        attached = controller.update("session-1", [first])
        below_threshold = controller.update("session-1", [RadioCell("cell-a", "Mobile", -80), RadioCell("cell-b", "Mobile", -78)])
        preparing = controller.update("session-1", [first, better])
        handed_over = controller.update("session-1", [first, better])

        self.assertEqual(attached.status, "attached")
        self.assertEqual(below_threshold.status, "stable")
        self.assertEqual(preparing.status, "preparing")
        self.assertEqual(handed_over.status, "handed_over")
        self.assertEqual(attached.stable_ip, handed_over.stable_ip)
        self.assertEqual(handed_over.generation, 2)

    def test_bonded_scheduler_allocates_all_bytes_and_masks_failed_links(self):
        self.channels[-1].available = False
        scheduler = BondedCarrierScheduler()

        allocation = scheduler.allocate(12345, self.channels)

        self.assertEqual(sum(allocation.values()), 12345)
        self.assertNotIn("Drones", allocation)
        self.assertGreater(allocation["Microwave"], 0)

    def test_congestion_controller_uses_aimd_feedback(self):
        channel = self.channels[0]
        controller = AIMDCongestionController(channel)
        initial = controller.congestion_window_bytes

        controller.on_loss()
        reduced = controller.congestion_window_bytes
        controller.on_ack(1200, 5)

        self.assertLess(reduced, initial)
        self.assertGreater(controller.congestion_window_bytes, reduced)
        self.assertLessEqual(controller.pacing_rate_mbps, channel.base_bandwidth)

    def test_q_learning_uses_safe_mask_and_updates_selected_action(self):
        self.channels[0].available = False
        agent = TabularQRoutingAgent(exploration_rate=0, rng=random.Random(4))
        state = agent.state(self.channels)
        selected = agent.choose_action(self.channels, {"HF": 100, "WiFi": 1}, explore=False)
        self.assertNotEqual(selected, "Microwave")

        updated = agent.update(state, selected, 0.8, state, terminal=True)
        learned_choice = agent.choose_action(self.channels, explore=False)

        self.assertGreater(updated, 0)
        self.assertEqual(learned_choice, selected)

    def test_authenticated_transport_rejects_missing_expired_and_wrong_session_tokens(self):
        authenticator = SessionAuthenticator(b"simulator-test-secret-key-32bytes")
        session = SeamlessTransportSession(self.channels, authenticator=authenticator, rng=random.Random(3))
        credential = authenticator.issue("mobile-user", "session-a", now=100, lifetime_seconds=10)

        with self.assertRaises(AuthenticationError):
            session.transmit(b"data", "session-a", now=101)
        with self.assertRaises(AuthenticationError):
            session.transmit(b"data", "session-b", credential=credential, now=101)
        with self.assertRaises(AuthenticationError):
            session.transmit(b"data", "session-a", credential=credential, now=110)

        result = session.transmit(b"data", "session-a", credential=credential, now=101)
        self.assertEqual(result.principal, "mobile-user")

    def test_csv_logger_records_link_and_transfer_kpis(self):
        session = SeamlessTransportSession(self.channels, rng=random.Random(5))
        result = session.transmit(b"csv payload", session_id="csv-session")
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "history.csv"
            logger = CSVNetworkLogger(path)
            logger.log_network_snapshot(1.0, self.channels, {"HF": 0.25})
            logger.log_transfer(1.1, result, cache_hit=False, cache_hit_ratio=0.0)
            content = path.read_text(encoding="utf-8")

        self.assertIn("continuity_preserved", content)
        self.assertIn("csv-session", content)
        self.assertIn("goodput_mbps", content)
        self.assertIn("Microwave", content)


if __name__ == "__main__":
    unittest.main()
