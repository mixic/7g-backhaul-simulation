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

"""Tests for the continuous-time Monte Carlo engine (MC-H16 to MC-H20)."""

from __future__ import annotations

import math
import unittest

import numpy as np

from simulation import common_mode as cm
from simulation import common_mode_mc as mc
from tools import mc_stats


class UnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = cm.build_backhaul_scenario()

    def test_unit_counts(self) -> None:
        units = mc.build_units(self.scenario)
        # 3 shared + gateway + controller + 3 control planes + 3 providers
        # + 18 edge links + 3 conduits + 3 provider-cloud links = 35
        self.assertEqual(len(units), 35)
        self.assertEqual(sum(1 for unit in units if unit.kind == "srlg"), 3)

    def test_conduit_takes_three_links(self) -> None:
        units = {unit.name: unit for unit in mc.build_units(self.scenario)}
        conduit = units["srlg-agg-1"]
        self.assertEqual(len(conduit.targets), 3)
        self.assertEqual(set(conduit.targets), {"a1-p1", "a1-p2", "a1-p3"})


class TimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = cm.build_backhaul_scenario()

    def test_intervals_cover_horizon_contiguously(self) -> None:
        for replication in range(5):
            intervals, _, _ = mc.sample_replication(
                self.scenario, replication, "ai_link", mc.H_INCIDENT_S
            )
            self.assertAlmostEqual(intervals[0].start, 0.0)
            self.assertAlmostEqual(intervals[-1].end, mc.H_INCIDENT_S)
            for left, right in zip(intervals, intervals[1:]):
                self.assertAlmostEqual(left.end, right.start)
            for interval in intervals:
                self.assertGreater(interval.duration, 0.0)

    def test_injected_link_is_down_only_inside_the_window(self) -> None:
        intervals, injected, _ = mc.sample_replication(
            self.scenario, 11, "link", mc.H_INCIDENT_S
        )
        self.assertIsNotNone(injected)
        start, end = injected
        for interval in intervals:
            inside = interval.start >= start - 1e-9 and interval.end <= end + 1e-9
            if inside:
                self.assertIn("a1-p1", interval.down_links)
            if "a1-p1" in interval.down_links:
                self.assertGreaterEqual(interval.start, start - 1e-9)
                self.assertLessEqual(interval.end, end + 1e-9)

    def test_none_event_has_no_injection(self) -> None:
        intervals, injected, _ = mc.sample_replication(
            self.scenario, 3, "none", mc.H_INCIDENT_S
        )
        self.assertIsNone(injected)
        # Only background failures can be down.
        self.assertNotIn("a1-p1", {link for interval in intervals for link in interval.down_links})

    def test_episodes_number_dependency_outages(self) -> None:
        intervals, _, _ = mc.sample_replication(
            self.scenario, 42, "ai", mc.H_INCIDENT_S
        )
        previous_down = False
        counter = 0
        for interval in intervals:
            if interval.any_down:
                if not previous_down:
                    counter += 1
                self.assertEqual(interval.episode, counter)
            else:
                self.assertEqual(interval.episode, 0)
            previous_down = interval.any_down


class MechanismTests(unittest.TestCase):
    """The mechanism contrasts of the frozen protocol on a few replications."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = cm.build_backhaul_scenario()
        cls.replications = list(range(12))
        cls.runs = mc.incident_runs(
            list(cm.EVENT_KINDS),
            list(cm.ARMS.values()),
            cls.replications,
            cls.scenario,
        )
        cls.index: dict[tuple[str, str], list[float]] = {}
        for result in cls.runs:
            cls.index.setdefault((result.event, result.arm), []).append(
                result.availability_event
            )

    def value(self, event: str, arm: str) -> float:
        values = self.index[(event, arm)]
        return sum(values) / len(values)

    def test_all_availabilities_are_fractions(self) -> None:
        for result in self.runs:
            self.assertGreaterEqual(result.availability_event, 0.0)
            self.assertLessEqual(result.availability_event, 1.0)
            self.assertGreaterEqual(result.availability_overall, 0.0)
            self.assertLessEqual(result.availability_overall, 1.0)

    def test_single_path_fails_a_link_event(self) -> None:
        self.assertLess(self.value("link", "A1"), 0.01)

    def test_shared_fate_multipath_fails_a_conduit_event(self) -> None:
        self.assertLess(self.value("srlg", "A2"), 0.01)

    def test_disjoint_multipath_survives_a_conduit_event(self) -> None:
        self.assertGreater(self.value("srlg", "A3"), 0.95)

    def test_tenant_isolation_contains_the_gateway(self) -> None:
        self.assertLess(self.value("tenant_gw", "A3"), 0.01)
        self.assertGreater(self.value("tenant_gw", "A4"), 0.95)

    def test_tenant_isolation_does_not_contain_identity(self) -> None:
        self.assertLess(self.value("idp", "A4"), 0.01)

    def test_one_way_boundary_survives_an_ai_failure(self) -> None:
        self.assertLess(self.value("ai", "A5"), 0.01)
        self.assertGreater(self.value("ai", "A6"), 0.80)

    def test_global_controller_is_a_dependency(self) -> None:
        self.assertGreater(self.value("controller_link", "A5"), 0.95)
        self.assertLess(self.value("controller_link", "A8"), 0.01)

    def test_fallback_partially_covers_a_backhaul_cut(self) -> None:
        self.assertGreater(self.value("backhaul_cut", "A6"), 0.40)
        self.assertLess(self.value("backhaul_cut", "A6"), 0.60)
        self.assertGreater(
            self.value("backhaul_cut", "A6"), self.value("backhaul_cut", "A7")
        )

    def test_path_independence_matches_the_reference_model(self) -> None:
        self.assertAlmostEqual(mc._path_independence(self.scenario, cm.ARMS["A2"]), 1.0 / 3.0, places=6)
        self.assertAlmostEqual(mc._path_independence(self.scenario, cm.ARMS["A3"]), 1.0, places=6)


class DeterminismTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = cm.build_backhaul_scenario()

    def test_same_replication_is_identical(self) -> None:
        first = mc.simulate_incident(cm.ARMS["A6"], "ai_link", 7, self.scenario)
        second = mc.simulate_incident(cm.ARMS["A6"], "ai_link", 7, self.scenario)
        self.assertEqual(first, second)

    def test_batch_matches_single(self) -> None:
        batch = mc.incident_runs(
            ["backhaul_cut"], [cm.ARMS["A7"]], [5, 6], self.scenario
        )
        single = mc.simulate_incident(cm.ARMS["A7"], "backhaul_cut", 6, self.scenario)
        self.assertEqual(batch[1], single)

    def test_different_replications_differ(self) -> None:
        first = mc.simulate_incident(cm.ARMS["A6"], "backhaul_cut", 11, self.scenario)
        second = mc.simulate_incident(cm.ARMS["A6"], "backhaul_cut", 12, self.scenario)
        self.assertNotEqual(
            (first.recovery_s, first.fallback_rate),
            (second.recovery_s, second.fallback_rate),
        )


class ParameterMonotonicityTests(unittest.TestCase):
    """The stipulated constants move the output in the expected direction."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = cm.build_backhaul_scenario()
        cls.replications = list(range(30))

    def mean(self, arm: str, event: str, params: mc.MCParams) -> float:
        results = mc.incident_runs(
            [event], [cm.ARMS[arm]], self.replications, self.scenario, params
        )
        return 100.0 * mc_stats.mean([result.availability_event for result in results])

    def test_longer_fallback_delay_lowers_availability(self) -> None:
        fast = self.mean("A6", "backhaul_cut", mc.MCParams(fallback_tested_delay_s=2.0))
        slow = self.mean("A6", "backhaul_cut", mc.MCParams(fallback_tested_delay_s=20.0))
        self.assertGreater(fast, slow)

    def test_smaller_fallback_capacity_lowers_availability(self) -> None:
        large = self.mean(
            "A6", "backhaul_cut", mc.MCParams(fallback_tested_capacity_gbps=0.50)
        )
        small = self.mean(
            "A6", "backhaul_cut", mc.MCParams(fallback_tested_capacity_gbps=0.25)
        )
        self.assertGreater(large, small)

    def test_lower_activation_probability_lowers_availability(self) -> None:
        likely = self.mean(
            "A7", "backhaul_cut", mc.MCParams(fallback_untested_probability=0.60)
        )
        unlikely = self.mean(
            "A7", "backhaul_cut", mc.MCParams(fallback_untested_probability=0.10)
        )
        self.assertGreater(likely, unlikely)

    def test_one_way_efficiency_is_monotone(self) -> None:
        high = self.mean("A6", "ai", mc.MCParams(one_way_efficiency=1.0))
        low = self.mean("A6", "ai", mc.MCParams(one_way_efficiency=0.7))
        self.assertGreater(high, low)
        self.assertAlmostEqual(high, 100.0, delta=1.0)
        self.assertAlmostEqual(low, 70.0, delta=1.0)


class CampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = cm.build_backhaul_scenario()
        cls.results = mc.campaign_runs(
            list(cm.ARMS.values()), list(range(6)), cls.scenario
        )

    def test_decomposition_sums_to_total(self) -> None:
        for result in self.results:
            total = (
                result.availability_ss
                + result.policy_loss
                + result.congestion_loss
                + result.dependency_loss
            )
            self.assertAlmostEqual(total, 1.0, places=5)

    def test_one_way_arms_pay_the_policy_cost(self) -> None:
        # The policy share is booked on healthy intervals only; down intervals
        # already carry it inside the dependency term, so it is at most 0.10.
        for result in self.results:
            if cm.ARMS[result.arm].one_way:
                self.assertGreater(result.policy_loss, 0.08)
                self.assertLessEqual(result.policy_loss, 0.10 + 1e-9)
            else:
                self.assertEqual(result.policy_loss, 0.0)

    def test_shared_attribution_is_zero_for_one_way_arms(self) -> None:
        for result in self.results:
            if cm.ARMS[result.arm].one_way:
                self.assertEqual(result.shared_attrib, 0.0)

    def test_shared_attribution_is_positive_with_shared_control(self) -> None:
        for result in self.results:
            if not cm.ARMS[result.arm].independent_control:
                self.assertGreater(result.shared_attrib, 0.2)

    def test_deterministic_given_a_seed(self) -> None:
        first = mc.simulate_campaign(cm.ARMS["A6"], 9, self.scenario)
        second = mc.simulate_campaign(cm.ARMS["A6"], 9, self.scenario)
        self.assertEqual(first, second)


class StatisticsTests(unittest.TestCase):
    def test_bootstrap_interval_contains_the_mean(self) -> None:
        rng = np.random.default_rng(0)
        values = rng.normal(10.0, 2.0, size=500)
        low, high = mc_stats.bootstrap_interval(values)
        self.assertLess(low, 10.0)
        self.assertGreater(high, 10.0)
        self.assertLess(high - low, 1.0)

    def test_permutation_detects_a_large_shift(self) -> None:
        values = np.full(200, 90.0) + np.random.default_rng(1).normal(0, 1, 200)
        self.assertLess(mc_stats.permutation_p_two_sided(values, 50.0), 0.01)

    def test_permutation_is_not_significant_for_a_small_shift(self) -> None:
        values = np.random.default_rng(2).normal(0.0, 1.0, size=200)
        self.assertGreater(mc_stats.permutation_p_two_sided(values, 0.0), 0.05)

    def test_mean_and_sd(self) -> None:
        self.assertAlmostEqual(mc_stats.mean([1.0, 2.0, 3.0]), 2.0)
        self.assertAlmostEqual(mc_stats.sd([1.0, 2.0, 3.0]), 1.0)
        self.assertEqual(mc_stats.sd([1.0]), 0.0)

    def test_t_interval_is_symmetric(self) -> None:
        centre, low, high = mc_stats.t_interval([1.0, 2.0, 3.0, 4.0])
        self.assertAlmostEqual(centre, 2.5)
        self.assertAlmostEqual(centre - low, high - centre)


class ProtocolTests(unittest.TestCase):
    """The frozen constants of the Monte Carlo protocol are what the engine uses."""

    def test_frozen_parameters(self) -> None:
        params = mc.DEFAULT_PARAMS
        self.assertEqual(params.one_way_efficiency, 0.90)
        self.assertEqual(params.fallback_tested_probability, 0.98)
        self.assertEqual(params.fallback_untested_probability, 0.60)
        self.assertEqual(params.fallback_tested_delay_s, 2.0)
        self.assertEqual(params.fallback_untested_delay_s, 8.0)
        self.assertEqual(params.fallback_tested_capacity_gbps, 0.50)
        self.assertEqual(params.fallback_untested_capacity_gbps, 0.30)

    def test_frozen_replication_counts(self) -> None:
        self.assertEqual(mc.INCIDENT_REPLICATIONS, 2000)
        self.assertEqual(mc.CAMPAIGN_REPLICATIONS, 500)
        self.assertEqual(mc.BASE_SEED, 2026)

    def test_every_event_class_has_a_median(self) -> None:
        for event in cm.EVENT_KINDS:
            self.assertIn(event, mc.INCIDENT_MEDIAN_S)

    def test_horizons(self) -> None:
        self.assertAlmostEqual(mc.H_INCIDENT_S, 24 * 3600.0)
        self.assertAlmostEqual(mc.H_CAMPAIGN_S, 30 * 24 * 3600.0)
        self.assertLess(mc.INCIDENT_START_MIN_S + mc.INCIDENT_START_SPAN_S, mc.H_INCIDENT_S)
        self.assertGreater(math.log(mc.process_specs()["shared"].p95_duration_s), 0.0)


if __name__ == "__main__":
    unittest.main()
