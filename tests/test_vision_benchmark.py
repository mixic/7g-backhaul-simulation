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

import tempfile
import unittest
from pathlib import Path

from tools.benchmark_vision import (
    Link,
    POLICIES,
    Scenario,
    build_scenarios,
    _forecast_demand,
    _forecast_safety_load,
    run_benchmark,
    run_public_safety_benchmark,
    SAFETY_POLICIES,
    simulate_public_safety,
    simulate,
)


class VisionBenchmarkTests(unittest.TestCase):
    def test_scenario_runs_are_reproducible(self):
        scenario = build_scenarios()[0]

        first, _ = simulate(scenario, POLICIES[2], seed=81)
        second, _ = simulate(scenario, POLICIES[2], seed=81)

        self.assertEqual(first, second)

    def test_demand_forecast_preserves_ratios_above_one(self):
        self.assertAlmostEqual(_forecast_demand([1.2, 1.3, 1.4], 3.0), 1.7)

    def test_safety_forecast_does_not_amplify_one_sample_noise(self):
        noisy_load_samples = [26.8, 28.4, 25.2, 30.2]

        self.assertLess(_forecast_safety_load(noisy_load_samples, 6.0), 64.0)

    def test_predictive_policy_warms_cache_for_sustained_demand(self):
        scenario = Scenario(
            key="sustained_demand",
            title="Sustained demand",
            description="Demand remains above baseline.",
            base_demand_mbps=100.0,
            links=(Link("fiber", 500.0, 8.0, 0.02, 0.0),),
            demand=lambda _tick, _rng: 250.0,
            initial_cache_hit=0.10,
        )

        baseline, _ = simulate(scenario, POLICIES[0], seed=2)
        _, trace = simulate(scenario, POLICIES[2], seed=2, retain_trace=True)

        self.assertAlmostEqual(baseline.cache_hit_percent, 10.0)
        self.assertIsNotNone(trace)
        self.assertGreater(trace.cache_hit_percent[-1], 10.0)

    def test_acceleration_trigger_opens_standby_before_reactive_threshold(self):
        reactive, _ = simulate_public_safety(SAFETY_POLICIES[1], seed=2026)
        predictive, _ = simulate_public_safety(SAFETY_POLICIES[2], seed=2026)

        self.assertLess(
            predictive.secondary_activation_seconds,
            reactive.secondary_activation_seconds,
        )
        self.assertGreater(
            predictive.critical_service_availability_percent,
            reactive.critical_service_availability_percent,
        )

    def test_safety_policies_share_the_same_offered_demand_trace(self):
        _, reactive_trace = simulate_public_safety(
            SAFETY_POLICIES[1],
            seed=2026,
            retain_trace=True,
        )
        _, predictive_trace = simulate_public_safety(
            SAFETY_POLICIES[2],
            seed=2026,
            retain_trace=True,
        )

        self.assertIsNotNone(reactive_trace)
        self.assertIsNotNone(predictive_trace)
        self.assertListEqual(
            reactive_trace.demand_mbps.tolist(),
            predictive_trace.demand_mbps.tolist(),
        )

    def test_concurrent_paths_reduce_modeled_handover_outage(self):
        single_path, _ = simulate_public_safety(SAFETY_POLICIES[0], seed=2026)
        reactive, _ = simulate_public_safety(SAFETY_POLICIES[1], seed=2026)
        predictive, _ = simulate_public_safety(SAFETY_POLICIES[2], seed=2026)

        self.assertGreater(
            single_path.longest_critical_outage_seconds,
            predictive.longest_critical_outage_seconds,
        )
        self.assertGreater(predictive.concurrent_media_percent, 0.0)
        self.assertGreater(
            predictive.video_frames_on_time_percent,
            single_path.video_frames_on_time_percent,
        )
        self.assertLess(
            predictive.video_stall_seconds,
            single_path.video_stall_seconds,
        )
        self.assertEqual(single_path.handover_interruption_seconds, 4.0)
        self.assertEqual(single_path.handover_missed_video_frames, 120.0)
        self.assertEqual(reactive.handover_interruption_seconds, 1.0)
        self.assertEqual(predictive.handover_interruption_seconds, 0.0)

    def test_media_assist_improves_deadline_delivery_with_measured_overhead(self):
        predictive, _ = simulate_public_safety(SAFETY_POLICIES[2], seed=2026)
        assisted, _ = simulate_public_safety(SAFETY_POLICIES[3], seed=2026)

        self.assertGreater(
            assisted.video_frames_on_time_percent,
            predictive.video_frames_on_time_percent,
        )
        self.assertGreater(
            assisted.audio_packets_on_time_percent,
            predictive.audio_packets_on_time_percent,
        )
        self.assertGreater(assisted.media_assist_overhead_percent, 0.0)
        self.assertGreater(assisted.media_assist_duplicate_mbps, 0.0)
        self.assertLessEqual(assisted.media_assist_duplicate_mbps, 4.128)
        self.assertEqual(predictive.media_assist_duplicate_mbps, 0.0)
        self.assertEqual(assisted.handover_interruption_seconds, 0.0)

    def test_all_policies_report_bounded_metrics(self):
        for scenario in build_scenarios():
            for policy in POLICIES:
                metrics, _ = simulate(scenario, policy, seed=4)
                self.assertGreaterEqual(metrics.delivered_goodput_mbps, 0.0)
                self.assertGreaterEqual(metrics.p95_latency_ms, 0.0)
                self.assertGreaterEqual(metrics.continuity_percent, 0.0)
                self.assertLessEqual(metrics.continuity_percent, 100.0)
                self.assertGreaterEqual(metrics.cache_hit_percent, 0.0)
                self.assertLessEqual(metrics.cache_hit_percent, 50.0)
                self.assertGreaterEqual(metrics.cost_usd_per_delivered_gb, 0.0)

    def test_benchmark_writes_summary_and_comparison_figures(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            rows = run_benchmark(output_dir, replicates=2, seed=9)

            self.assertEqual(len(rows), len(build_scenarios()) * len(POLICIES))
            self.assertTrue((output_dir / "vision_benchmark_summary.csv").is_file())
            self.assertTrue((output_dir / "vision_benchmark_goodput.png").is_file())
            self.assertTrue((output_dir / "vision_benchmark_latency.png").is_file())
            self.assertTrue((output_dir / "vision_benchmark_continuity.png").is_file())
            self.assertTrue((output_dir / "vision_benchmark_cache.png").is_file())
            self.assertTrue((output_dir / "vision_benchmark_cost.png").is_file())
            self.assertTrue(
                (output_dir / "vision_benchmark_urban_timeseries.png").is_file()
            )
            safety_rows = run_public_safety_benchmark(
                output_dir,
                replicates=2,
                seed=9,
            )
            self.assertEqual(len(safety_rows), len(SAFETY_POLICIES))
            self.assertTrue(
                (output_dir / "public_safety_benchmark_summary.csv").is_file()
            )
            self.assertTrue(
                (output_dir / "public_safety_multimedia_qos.png").is_file()
            )
            self.assertTrue(
                (output_dir / "public_safety_overflow_timeseries.png").is_file()
            )


if __name__ == "__main__":
    unittest.main()
