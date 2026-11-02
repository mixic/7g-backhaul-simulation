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

import hashlib
import unittest

from simulation.mesh import (
    MeshContentNotFound,
    MeshContentRejected,
    MeshLink,
    MeshPeer,
    PeerMesh,
)


class PeerMeshTests(unittest.TestCase):
    def setUp(self):
        self.payload = b"trusted model artifact"
        self.peers = [
            MeshPeer("edge-a", 4096),
            MeshPeer("edge-b", 4096),
            MeshPeer("ai-core", 4096),
        ]
        self.mesh = PeerMesh(
            self.peers,
            [
                MeshLink("edge-a", "ai-core", 1000, 3),
                MeshLink("edge-a", "edge-b", 1000, 8),
                MeshLink("edge-b", "ai-core", 1000, 8),
            ],
            trusted_publishers={"model-registry"},
        )
        self.mesh.register_manifest(
            "model-v1",
            "model-registry",
            hashlib.sha256(self.payload).hexdigest(),
        )
        self.mesh.publish("ai-core", "model-v1", self.payload, "model-registry")

    def congest_direct_link(self):
        for _ in range(3):
            telemetry = self.mesh.record_link_telemetry(
                "edge-a",
                "ai-core",
                utilization=0.95,
                queue_delay_ms=50,
                loss_rate=0.02,
            )
        return telemetry

    def test_predictive_congestion_reroutes_and_replicates_after_reuse(self):
        telemetry = self.congest_direct_link()

        self.assertTrue(telemetry.congestion_active)
        self.assertGreaterEqual(telemetry.predicted_pressure, 0.7)
        first = self.mesh.request("edge-a", "model-v1")
        second = self.mesh.request("edge-a", "model-v1")
        third = self.mesh.request("edge-a", "model-v1")
        local_hit = self.mesh.request("edge-a", "model-v1")

        self.assertEqual(first.path, ("edge-a", "edge-b", "ai-core"))
        self.assertTrue(first.route_avoided_congestion)
        self.assertEqual(first.cache_action, "rejected_cache_pollution")
        self.assertEqual(first.cache_trigger, "congestion")
        self.assertEqual(second.cache_action, "rejected_cache_pollution")
        self.assertEqual(third.cache_action, "replicated_for_congestion")
        self.assertIsNotNone(third.cache_admission_score)
        self.assertLessEqual(third.cache_admission_score, 0.3)
        self.assertTrue(local_hit.cache_hit)
        self.assertEqual(local_hit.path, ("edge-a",))
        self.assertEqual(local_hit.payload, self.payload)

    def test_unique_content_is_not_replica_cached_during_congestion(self):
        self.congest_direct_link()
        for sequence in range(5):
            content_id = f"unique-{sequence}"
            payload = f"content-{sequence}".encode()
            self.mesh.register_manifest(
                content_id,
                "model-registry",
                hashlib.sha256(payload).hexdigest(),
            )
            self.mesh.publish("ai-core", content_id, payload, "model-registry")
            result = self.mesh.request("edge-a", content_id)

            self.assertEqual(result.cache_action, "rejected_cache_pollution")
            self.assertNotIn(content_id, self.peers[0].cache.contents)

    def test_poisoned_cached_payload_is_evicted_and_rejected(self):
        self.peers[2].cache.contents["model-v1"] = b"poisoned payload"

        with self.assertRaises(MeshContentRejected):
            self.mesh.request("edge-a", "model-v1")

        self.assertNotIn("model-v1", self.peers[2].cache.contents)

    def test_untrusted_or_mismatched_publish_is_rejected(self):
        with self.assertRaises(MeshContentRejected):
            self.mesh.publish("edge-a", "model-v1", self.payload, "unknown")
        with self.assertRaises(MeshContentRejected):
            self.mesh.publish("edge-a", "model-v1", b"tampered", "model-registry")
        self.assertNotIn("model-v1", self.peers[0].cache.contents)

    def test_peer_cache_is_local_and_unknown_content_is_explicit(self):
        self.assertIsNone(self.peers[0].cache.get("model-v1"))
        with self.assertRaises(MeshContentNotFound):
            self.mesh.request("edge-a", "not-published")

    def test_congestion_hysteresis_prevents_immediate_clear(self):
        self.congest_direct_link()
        telemetry = self.mesh.record_link_telemetry(
            "edge-a",
            "ai-core",
            utilization=0.4,
            queue_delay_ms=5,
            loss_rate=0,
        )
        self.assertTrue(telemetry.congestion_active)

        telemetry = self.mesh.record_link_telemetry(
            "edge-a",
            "ai-core",
            utilization=0.1,
            queue_delay_ms=0,
            loss_rate=0,
        )
        self.assertFalse(telemetry.congestion_active)

    def test_active_active_path_shares_shift_with_pressure_speed_and_acceleration(self):
        baseline = self.mesh.plan_active_active_paths(
            "edge-a",
            "ai-core",
            total_bytes=100_000,
        )
        direct_baseline = next(
            allocation for allocation in baseline
            if allocation.path == ("edge-a", "ai-core")
        )
        self.assertEqual(len(baseline), 2)
        self.assertEqual(sum(item.allocated_bytes for item in baseline), 100_000)
        self.assertTrue(all(item.allocated_bytes > 0 for item in baseline))

        for utilization in (0.1, 0.3, 0.7):
            telemetry = self.mesh.record_link_telemetry(
                "edge-a",
                "ai-core",
                utilization=utilization,
                queue_delay_ms=0,
                loss_rate=0,
            )
        updated = self.mesh.plan_active_active_paths(
            "edge-a",
            "ai-core",
            total_bytes=100_000,
        )
        direct_updated = next(
            allocation for allocation in updated
            if allocation.path == ("edge-a", "ai-core")
        )

        self.assertGreater(telemetry.pressure_velocity, 0)
        self.assertGreater(telemetry.pressure_acceleration, 0)
        self.assertGreater(direct_updated.pressure_velocity, 0)
        self.assertGreater(direct_updated.pressure_acceleration, 0)
        self.assertGreater(direct_updated.predicted_pressure, 0)
        self.assertLess(direct_updated.traffic_share, direct_baseline.traffic_share)
        self.assertEqual(sum(item.allocated_bytes for item in updated), 100_000)

    def test_active_active_path_policy_accounts_for_configured_cost(self):
        peers = [MeshPeer("a", 0), MeshPeer("b", 0), MeshPeer("c", 0)]
        mesh = PeerMesh(
            peers,
            [
                MeshLink("a", "c", 1000, 3, cost_per_gb=20),
                MeshLink("a", "b", 1000, 8, cost_per_gb=0.1),
                MeshLink("b", "c", 1000, 8, cost_per_gb=0.1),
            ],
            cost_weight=20,
        )

        allocations = mesh.plan_active_active_paths("a", "c", 10_000)
        direct_share = next(
            item.traffic_share for item in allocations
            if item.path == ("a", "c")
        )
        indirect_share = next(
            item.traffic_share for item in allocations
            if item.path == ("a", "b", "c")
        )

        self.assertGreater(indirect_share, direct_share)
        self.assertAlmostEqual(sum(item.traffic_share for item in allocations), 1.0)

    def test_mesh_request_reports_concurrent_path_allocations(self):
        self.congest_direct_link()

        result = self.mesh.request("edge-a", "model-v1")

        self.assertEqual(len(result.active_active_paths), 2)
        self.assertEqual(
            sum(item.allocated_bytes for item in result.active_active_paths),
            len(self.payload),
        )
        self.assertGreater(
            sum(item.traffic_share for item in result.active_active_paths),
            0.99,
        )
        self.assertTrue(result.route_avoided_congestion)

    def test_unavailable_link_is_removed_and_mesh_self_heals_to_remaining_route(self):
        self.mesh.links[("ai-core", "edge-a")].available = False

        result = self.mesh.request("edge-a", "model-v1")

        self.assertEqual(result.path, ("edge-a", "edge-b", "ai-core"))
        self.assertEqual(
            [allocation.path for allocation in result.active_active_paths],
            [("edge-a", "edge-b", "ai-core")],
        )
        self.assertEqual(
            sum(allocation.allocated_bytes for allocation in result.active_active_paths),
            len(self.payload),
        )


if __name__ == "__main__":
    unittest.main()
