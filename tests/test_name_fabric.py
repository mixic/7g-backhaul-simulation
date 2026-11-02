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

import math
import unittest

from simulation.name_fabric import (
    DNS_POISONING_ACCEPTANCE,
    SERVICE_FORGERY_ACCEPTANCE,
    FabricConfig,
    experiment_flooding,
    experiment_gateway,
    experiment_latency,
    experiment_poisoning,
    experiment_transition,
    gradient_resolution,
    shortest_path,
    sustainable_rate,
)


class TopologyTests(unittest.TestCase):
    def test_shortest_path_uses_the_low_latency_route(self):
        latency, capacity = shortest_path("E2", "E3")
        self.assertAlmostEqual(latency, 5.0)
        self.assertAlmostEqual(capacity, 60.0)

    def test_path_bottleneck_is_the_minimum_link(self):
        latency, capacity = shortest_path("P", "E2")
        self.assertAlmostEqual(latency, 2.0 + 4.0)
        self.assertAlmostEqual(capacity, 150.0)


class GradientTests(unittest.TestCase):
    def test_gradient_latency_covers_path_and_queue(self):
        config = FabricConfig()
        import random

        resolution = gradient_resolution(config, "E2", config.request_rate, random.Random(1))
        self.assertTrue(math.isfinite(resolution.latency_ms))
        self.assertGreater(resolution.latency_ms, 6.0)

    def test_resolution_is_faster_than_a_miss(self):
        config = FabricConfig(request_rate=1000.0)
        transition = experiment_transition(config, ttl_values=(60.0,), clients=50)
        gradient = [
            sample.time_to_first_success_ms
            for sample in transition
            if sample.strategy == "gradient"
        ]
        dns = [
            sample.time_to_first_success_ms
            for sample in transition
            if sample.strategy == "dns"
        ]
        self.assertLess(max(gradient), min(dns))
        self.assertTrue(
            all(sample.failed_requests == 0 for sample in transition if sample.strategy == "gradient")
        )


class PoisoningTests(unittest.TestCase):
    def test_immutable_names_are_never_forged(self):
        rows = experiment_poisoning(trials=2000)
        immutable = [row for row in rows if row.name_class == "immutable"]
        self.assertTrue(immutable)
        self.assertTrue(all(row.acceptance_percent == 0.0 for row in immutable))

    def test_service_acceptance_falls_with_strength(self):
        rows = experiment_poisoning(trials=4000)
        service = {
            int(row.variant.split()[-1]): row.acceptance_percent
            for row in rows
            if row.name_class == "service"
        }
        self.assertEqual(sorted(service), sorted(SERVICE_FORGERY_ACCEPTANCE))
        ordered = [service[strength] for strength in sorted(service)]
        for earlier, later in zip(ordered, ordered[1:]):
            self.assertGreaterEqual(earlier, later)

    def test_dns_poisoning_is_bounded_by_dnssec(self):
        rows = experiment_poisoning(trials=4000)
        external = {row.variant: row.acceptance_percent for row in rows if row.name_class == "external"}
        self.assertGreater(
            external["dns cache, no-dnssec"],
            DNS_POISONING_ACCEPTANCE["dnssec"],
        )
        self.assertAlmostEqual(external["dns cache, dnssec"], 0.0, places=6)


class FloodingTests(unittest.TestCase):
    def test_pending_table_scales_with_rate_times_lifetime(self):
        config = FabricConfig()
        rows = experiment_flooding(config, rates=(1000.0,))
        self.assertAlmostEqual(rows[0].pit_occupancy, 1000.0 * config.pit_lifetime_s)
        self.assertEqual(rows[0].pit_failure_percent, 0.0)

    def test_resolver_saturates_at_its_capacity(self):
        config = FabricConfig(resolver_qps=5000.0)
        rows = experiment_flooding(config, rates=(4000.0, 5000.0))
        self.assertLess(rows[0].dns_failure_percent, 100.0)
        self.assertEqual(rows[1].dns_failure_percent, 100.0)

    def test_sustainable_rate_is_monotone_in_the_sweep(self):
        config = FabricConfig()
        rows = experiment_flooding(config)
        self.assertLessEqual(
            sustainable_rate(rows, "dns_failure_percent"),
            sustainable_rate(rows, "pit_failure_percent"),
        )


class LatencyAndGatewayTests(unittest.TestCase):
    def test_tail_is_worse_than_the_median_for_every_strategy(self):
        rows = experiment_latency(FabricConfig(), trials=1500)
        self.assertTrue(rows)
        for row in rows:
            self.assertLessEqual(row.p50_ms, row.p95_ms)
            self.assertLessEqual(row.p95_ms, row.p99_ms)

    def test_uncached_dns_exceeds_cached_dns(self):
        rows = {row.strategy: row.p50_ms for row in experiment_latency(FabricConfig(), trials=1500)}
        self.assertGreater(rows["dns (uncached)"], rows["dns (cached)"])

    def test_gateway_utilisation_and_external_tail_grow(self):
        rows = experiment_gateway(FabricConfig(), trials=400)
        self.assertLess(rows[0].gateway_utilization, rows[-1].gateway_utilization)
        self.assertGreater(rows[-1].external_p95_ms, rows[-1].internal_p95_ms)

    def test_experiments_are_deterministic(self):
        self.assertEqual(
            experiment_poisoning(trials=500),
            experiment_poisoning(trials=500),
        )


if __name__ == "__main__":
    unittest.main()
