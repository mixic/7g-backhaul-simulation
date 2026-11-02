# 7g-backhaul-simulation
# Copyright (C) 2026 MILAN NIKOLIC
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import hashlib
import unittest

from simulation.cooperative import CooperativeBackhaulCoordinator
from simulation.mesh import MeshLink, MeshPeer, PeerMesh
from simulation.quantum import QuantumResourceLink, QuantumResourceUnavailable


class QuantumCooperativeBackhaulTests(unittest.TestCase):
    def setUp(self):
        self.payload = b"quantum-assisted classical content" * 30
        self.peers = [
            MeshPeer("edge-a", 4096),
            MeshPeer("edge-b", 4096),
            MeshPeer("core", 4096),
        ]
        self.mesh = PeerMesh(
            self.peers,
            [
                MeshLink(
                    "edge-a",
                    "core",
                    1000,
                    3,
                    classical_mtu_bytes=1500,
                    encapsulation_overhead_bytes=100,
                ),
                MeshLink(
                    "edge-a",
                    "edge-b",
                    1000,
                    8,
                    classical_mtu_bytes=900,
                    encapsulation_overhead_bytes=40,
                ),
                MeshLink(
                    "edge-b",
                    "core",
                    1000,
                    8,
                    classical_mtu_bytes=700,
                    encapsulation_overhead_bytes=50,
                ),
            ],
            trusted_publishers={"registry"},
        )
        self.mesh.register_manifest(
            "content",
            "registry",
            hashlib.sha256(self.payload).hexdigest(),
        )
        self.mesh.publish("core", "content", self.payload, "registry")
        self.quantum_link = QuantumResourceLink(
            "edge-a",
            "core",
            max_qubits_per_frame=128,
            qubit_rate_per_second=2000,
            fidelity=0.99,
        )
        self.coordinator = CooperativeBackhaulCoordinator(
            self.mesh,
            [self.quantum_link],
            replica_demand_threshold=3,
        )

    def test_quantum_frame_capacity_is_separate_from_classical_path_mtu(self):
        generation = self.quantum_link.generate_key_material(1.0)
        telemetry = self.mesh.record_link_telemetry(
            "edge-a", "core", utilization=0.95, queue_delay_ms=50, loss_rate=0.02
        )
        for _ in range(2):
            telemetry = self.mesh.record_link_telemetry(
                "edge-a", "core", utilization=0.95, queue_delay_ms=50, loss_rate=0.02
            )
        decision = self.coordinator.request("edge-a", "content")

        self.assertEqual(generation.source_qubits, 2000)
        self.assertEqual(generation.quantum_frames, 16)
        self.assertEqual(generation.generated_key_bits, 1980)
        self.assertTrue(telemetry.congestion_active)
        self.assertEqual(decision.delivery.path, ("edge-a", "edge-b", "core"))
        self.assertEqual(decision.classical_path_payload_mtu_bytes, 650)
        self.assertEqual(
            decision.classical_fragment_count,
            (len(self.payload) + 649) // 650,
        )
        self.assertNotEqual(
            decision.classical_path_payload_mtu_bytes,
            self.quantum_link.max_qubits_per_frame,
        )

    def test_cooperative_policy_uses_key_resource_and_forecast_cache_replication(self):
        self.quantum_link.generate_key_material(1.0)

        first = self.coordinator.request(
            "edge-a",
            "content",
            requires_quantum_key=True,
            quantum_key_bits=256,
        )
        second = self.coordinator.request(
            "edge-a",
            "content",
            requires_quantum_key=True,
            quantum_key_bits=256,
        )
        third = self.coordinator.request(
            "edge-a",
            "content",
            requires_quantum_key=True,
            quantum_key_bits=256,
        )
        fourth = self.coordinator.request(
            "edge-a",
            "content",
            requires_quantum_key=True,
            quantum_key_bits=256,
        )
        fifth = self.coordinator.request(
            "edge-a",
            "content",
            requires_quantum_key=True,
            quantum_key_bits=256,
        )

        self.assertEqual(first.reserved_key_bits, 256)
        self.assertEqual(first.quantum_link, "edge-a<->core")
        self.assertEqual(first.delivery.serving_peer, "core")
        self.assertEqual(fourth.delivery.cache_trigger, "predicted_demand")
        self.assertEqual(fourth.delivery.cache_action, "replicated_for_predicted_demand")
        self.assertTrue(fifth.delivery.cache_hit)
        self.assertEqual(fifth.reserved_key_bits, 0)
        self.assertEqual(self.quantum_link.buffered_key_bits, 1980 - 4 * 256)

    def test_required_quantum_key_fails_explicitly_without_resource(self):
        with self.assertRaises(QuantumResourceUnavailable):
            self.coordinator.request(
                "edge-a",
                "content",
                requires_quantum_key=True,
                quantum_key_bits=256,
            )

    def test_quantum_link_rejects_invalid_frame_mtu(self):
        with self.assertRaises(ValueError):
            QuantumResourceLink("edge-a", "core", 0, 100)


if __name__ == "__main__":
    unittest.main()
