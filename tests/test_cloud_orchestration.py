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

from simulation.orchestration import (
    AIDataCenter,
    AIWorkload,
    CloudPlacementError,
    KEDAInspiredScaler,
    KubernetesEdgeCluster,
    MultiCloudAIScheduler,
)


class CloudOrchestrationTests(unittest.TestCase):
    def test_scaler_uses_demand_forecast_and_reports_capacity_limit(self):
        cluster = KubernetesEdgeCluster(
            name="bern-edge",
            region="bern",
            target_requests_per_second_per_pod=10,
            min_replicas=1,
            max_replicas=5,
        )

        decision = KEDAInspiredScaler().reconcile(
            cluster,
            observed_requests_per_second=22,
            forecast_requests_per_second=80,
        )

        self.assertEqual(decision.desired_replicas, 5)
        self.assertEqual(decision.modeled_capacity_requests_per_second, 50)
        self.assertTrue(decision.capacity_saturated)
        self.assertEqual(cluster.current_replicas, 5)

    def test_scaler_does_not_scale_below_minimum(self):
        cluster = KubernetesEdgeCluster(
            name="small-edge",
            region="bern",
            target_requests_per_second_per_pod=10,
            min_replicas=2,
            max_replicas=6,
            current_replicas=2,
        )

        decision = KEDAInspiredScaler().reconcile(cluster, 0, -3)

        self.assertEqual(decision.forecast_requests_per_second, 0)
        self.assertEqual(decision.desired_replicas, 2)
        self.assertFalse(decision.capacity_saturated)

    def test_scheduler_uses_latency_weight_for_inference_placement(self):
        datacenters = [
            AIDataCenter("near", "private-cloud", "bern", 8, 0.08, 4, 0.5),
            AIDataCenter("far", "public-cloud-b", "eu-west", 40, 0.02, 16, 0.1),
        ]
        scheduler = MultiCloudAIScheduler(
            datacenters,
            latency_weight=1,
            egress_weight=0,
            accelerator_load_weight=0,
        )

        decision = scheduler.schedule(
            AIWorkload("inference-1", "inference", 10_000_000, latency_slo_ms=50)
        )

        self.assertEqual(decision.datacenter, "near")
        self.assertEqual(decision.estimated_latency_ms, 8)
        self.assertAlmostEqual(decision.estimated_egress_cost, 0.0008)

    def test_scheduler_respects_latency_capacity_and_availability(self):
        datacenters = [
            AIDataCenter("offline", "cloud-a", "eu", 10, 0.01, 8, available=False),
            AIDataCenter("undersized", "cloud-b", "eu", 12, 0.01, 1),
            AIDataCenter("too-far", "cloud-c", "us", 100, 0.01, 8),
            AIDataCenter("eligible", "cloud-d", "ch", 20, 0.03, 2),
        ]
        scheduler = MultiCloudAIScheduler(datacenters)
        workload = AIWorkload(
            "training-1",
            "training",
            1_000_000_000,
            required_accelerators=2,
            latency_slo_ms=30,
        )

        decision = scheduler.schedule(workload)

        self.assertEqual(decision.datacenter, "eligible")
        self.assertAlmostEqual(decision.estimated_egress_cost, 0.03)

    def test_scheduler_reports_when_no_site_can_serve_workload(self):
        scheduler = MultiCloudAIScheduler(
            [AIDataCenter("edge-only", "private", "bern", 5, 0.0, 0)]
        )

        with self.assertRaises(CloudPlacementError):
            scheduler.schedule(AIWorkload("model-1", "model_distribution", 0))

    def test_egress_weight_prefers_lower_configured_cost(self):
        datacenters = [
            AIDataCenter("expensive", "cloud-a", "eu", 10, 0.1, 4),
            AIDataCenter("economical", "cloud-b", "eu", 20, 0.01, 4),
        ]
        scheduler = MultiCloudAIScheduler(
            datacenters,
            latency_weight=0,
            egress_weight=1,
            accelerator_load_weight=0,
        )

        decision = scheduler.schedule(
            AIWorkload("model-copy", "model_distribution", 1_000_000_000)
        )

        self.assertEqual(decision.datacenter, "economical")
        self.assertAlmostEqual(decision.estimated_egress_cost, 0.01)


if __name__ == "__main__":
    unittest.main()
