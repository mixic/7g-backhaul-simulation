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

"""Tests for the M10 T-NDN experiment and its three baselines."""

from __future__ import annotations

import unittest

from simulation import fisheye_overlay_baseline as fisheye
from simulation import fsr_baseline as fsr
from simulation import ndn_scenario as scenario
from simulation import nlsr_baseline as nlsr
from simulation import tndn_router as tndn
from simulation import topology
from simulation.ndn_network import PhysicalNetwork


class NameSpaceTests(unittest.TestCase):
    def test_name_space_size_and_encoding(self):
        self.assertEqual(len(topology.NAMES), 10_000)
        for index in (0, 1, 1234, 9999):
            name = topology.decode(index)
            self.assertEqual(
                topology.name_id(name.service, name.region, name.type, name.obj),
                index,
            )

    def test_distance_is_a_metric(self):
        for left, right in ((0, 1), (0, 2500), (17, 8123), (9000, 123)):
            self.assertAlmostEqual(
                topology.distance(left, right),
                topology.distance(right, left),
            )
            self.assertGreaterEqual(topology.distance(left, right), 0.0)
        self.assertEqual(topology.distance(42, 42), 0.0)

    def test_within_block_names_are_close(self):
        # Same (service, region), different type/object: <= 0.10.
        for left, right in ((0, 1), (0, 99), (0, 250), (0, 499)):
            self.assertLessEqual(topology.distance(left, right), 0.1001)

    def test_adjacent_blocks_are_farther_than_the_cluster_radius(self):
        # Block 0 vs block 1 are adjacent on the semantic circle.
        block_zero = topology.name_id(0, 0, 0, 0)
        block_one = topology.name_id(0, 1, 0, 0)
        self.assertGreater(
            topology.distance(block_zero, block_one), topology.EPS_CLUSTER
        )
        self.assertLess(topology.distance(block_zero, block_one), topology.EPS_HOLE)

    def test_landmarks_are_bounded_and_distinct(self):
        chosen = topology.landmarks(32)
        self.assertEqual(len(chosen), 32)
        self.assertEqual(len(set(chosen)), 32)


class PersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analysis = topology.analyse()

    def test_twenty_persistent_clusters(self):
        self.assertEqual(self.analysis.clusters, topology.PRODUCER_COUNT)
        self.assertEqual(self.analysis.persistence.b0, 20)

    def test_one_persistent_loop(self):
        self.assertEqual(self.analysis.holes, 1)

    def test_loop_spans_every_cluster(self):
        self.assertEqual(len(self.analysis.hole_clusters), 20)

    def test_each_cluster_belongs_to_exactly_one_producer(self):
        owners = [owners for owners in self.analysis.cluster_producers]
        self.assertEqual(len(owners), 20)
        self.assertTrue(all(len(item) == 1 for item in owners))

    def test_tda_cost_is_measured_and_positive(self):
        self.assertGreater(self.analysis.persistence_ms, 0.0)
        self.assertGreater(self.analysis.time_ms, 0.0)
        self.assertGreaterEqual(self.analysis.time_ms, self.analysis.persistence_ms)


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analysis = topology.analyse()
        cls.network = PhysicalNetwork(seed=scenario.BASE_SEED)
        cls.placement = scenario.producer_placement(cls.network)
        cls.producers = list(cls.placement.block_to_node)
        cls.nlsr = nlsr.build(cls.network, cls.producers)
        cls.fsr = fsr.build(cls.network, cls.producers)
        cls.fisheye = fisheye.build(cls.network, seed=scenario.BASE_SEED)
        cls.tndn = tndn.build(cls.network, cls.analysis, cls.producers)

    def test_nlsr_is_per_name(self):
        self.assertAlmostEqual(nlsr.fib_mean(self.nlsr), 9900.0, places=6)

    def test_prefix_aggregating_nlsr_is_far_smaller(self):
        # The sensitivity reported in the docs: if NLSR aggregated the block
        # prefixes it would fit in ~20 entries, fewer than T-NDN's ~38.
        aggregated = nlsr.aggregated_fib_mean(self.network, self.producers)
        self.assertAlmostEqual(aggregated, 19.8, places=6)
        self.assertLess(aggregated, self.tndn.fib_mean())

    def test_fsr_aggregates_but_stays_above_the_overlay(self):
        fsr_mean = fsr.fib_mean(self.fsr)
        self.assertLess(fsr_mean, 2000.0)
        self.assertGreater(fsr_mean, fisheye.fib_mean(self.fisheye))

    def test_fisheye_overlay_has_peer_and_bucket_entries(self):
        self.assertAlmostEqual(
            fisheye.fib_mean(self.fisheye),
            float(fisheye.PEERS + fisheye.BUCKETS),
            places=6,
        )

    def test_tndn_beats_the_overlay_by_twenty_percent(self):
        tndn_mean = self.tndn.fib_mean()
        self.assertLessEqual(tndn_mean, 0.8 * fisheye.fib_mean(self.fisheye))

    def test_tndn_installs_backups_for_the_loop(self):
        backups = sum(
            1 for row in self.tndn.backup for entry in row if entry >= 0
        )
        self.assertGreater(backups, 0)

    def test_tndn_plan_does_not_know_the_failure(self):
        # The plan carries no failure/void field: voids are detected from
        # neighbour advertisements at run time, never hardcoded at build time.
        self.assertFalse(hasattr(self.tndn, "failure_link"))
        self.assertFalse(hasattr(self.tndn, "voids"))

    def test_tndn_build_is_deterministic(self):
        again = tndn.build(self.network, self.analysis, self.producers)
        self.assertEqual(again.fib_entries, self.tndn.fib_entries)
        self.assertEqual(again.backup, self.tndn.backup)


class PairingAndVerdictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analysis = topology.analyse()
        cls.result = scenario.run_seed(scenario.BASE_SEED, cls.analysis)

    def test_fib_ordering_matches_the_hypothesis(self):
        values = self.result.fib_mean
        self.assertLess(values["tndn"], values["fisheye"])
        self.assertLess(values["fisheye"], values["fsr"])
        self.assertLess(values["fsr"], values["nlsr"])

    def test_convergence_ordering(self):
        values = self.result.convergence_p99_s
        self.assertLess(values["tndn"], values["nlsr"])
        self.assertLess(values["nlsr"], values["fisheye"])
        self.assertLess(values["fisheye"], values["fsr"])

    def test_tndn_cdr_is_within_the_constraint(self):
        self.assertGreaterEqual(
            self.result.cdr_percent["tndn"],
            0.95 * self.result.cdr_percent["nlsr"],
        )

    def test_tda_cost_is_below_the_saved_convergence(self):
        saved_ms = 1000.0 * (
            self.result.convergence_p99_s["nlsr"]
            - self.result.convergence_p99_s["tndn"]
        )
        self.assertLess(self.result.tda_ms, saved_ms)

    def test_a_seed_is_deterministic(self):
        again = scenario.run_seed(scenario.BASE_SEED, self.analysis)
        self.assertEqual(again.fib_mean, self.result.fib_mean)
        self.assertEqual(
            again.convergence_p99_s, self.result.convergence_p99_s
        )
        self.assertEqual(again.cdr_percent, self.result.cdr_percent)

    def test_all_strategies_share_the_scenario(self):
        self.assertEqual(self.result.requests, len(
            scenario.generate_requests(scenario.BASE_SEED)
        ))
        self.assertGreater(self.result.affected_fraction, 0.0)


if __name__ == "__main__":
    unittest.main()
