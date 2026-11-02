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

import numpy as np

from tools.benchmark_brain_inspired import (
    POLICIES,
    PATHS,
    SCENARIOS,
    Scenario,
    _demand,
    _path_capacity,
    _simulate,
    load_measured_trace,
    run_benchmark,
    simulate,
)


class BrainInspiredBenchmarkTests(unittest.TestCase):
    def test_cooperative_policy_recovers_cloud_service_faster(self):
        reactive = simulate(POLICIES[0], seed=2026)
        cooperative = simulate(POLICIES[1], seed=2026)

        self.assertGreater(
            cooperative.critical_service_availability_percent,
            reactive.critical_service_availability_percent,
        )
        self.assertLess(
            cooperative.cloud_recovery_seconds,
            reactive.cloud_recovery_seconds,
        )
        self.assertGreaterEqual(reactive.path_recovery_seconds, 0.0)
        self.assertGreaterEqual(cooperative.path_recovery_seconds, 0.0)

    def test_matched_cloud_and_duplication_policy_arms(self):
        reactive = simulate(POLICIES[0], seed=27)
        prepared_cloud = simulate(POLICIES[4], seed=27)
        correlated = SCENARIOS[2]
        reactive_correlated = simulate(POLICIES[0], seed=27, scenario=correlated)
        reactive_with_duplication = simulate(
            POLICIES[2],
            seed=27,
            scenario=correlated,
        )
        predictive_joint = simulate(POLICIES[5], seed=27, scenario=correlated)
        cooperative = simulate(POLICIES[1], seed=27, scenario=correlated)

        self.assertLess(
            prepared_cloud.cloud_recovery_seconds,
            reactive.cloud_recovery_seconds,
        )
        self.assertEqual(predictive_joint.duplicate_payload_percent, 0.0)
        self.assertGreater(cooperative.duplicate_payload_percent, 0.0)
        self.assertGreater(
            reactive_with_duplication.duplicate_payload_percent,
            reactive_correlated.duplicate_payload_percent,
        )

    def test_correlated_outage_changes_real_time_qos(self):
        nominal = simulate(POLICIES[0], seed=41, scenario=SCENARIOS[0])
        correlated = simulate(POLICIES[0], seed=41, scenario=SCENARIOS[2])

        self.assertLess(
            correlated.video_frames_on_time_percent,
            nominal.video_frames_on_time_percent,
        )

    def test_simulation_metrics_are_bounded_and_reproducible(self):
        first = simulate(POLICIES[1], seed=19)
        second = simulate(POLICIES[1], seed=19)

        self.assertEqual(first, second)
        for metric in (
            first.demand_delivery_percent,
            first.critical_service_availability_percent,
            first.video_frames_on_time_percent,
            first.audio_packets_on_time_percent,
            first.duplicate_packet_percent,
            first.duplicate_payload_percent,
            first.media_copy_loss_percent,
        ):
            self.assertGreaterEqual(metric, 0.0)
            self.assertLessEqual(metric, 100.0)

    def test_trace_input_and_sensitivity_parameters_are_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory) / "measured.csv"
            with trace_path.open("w", newline="", encoding="utf-8") as file:
                file.write(
                    "second,critical_mbps,bulk_mbps,path,capacity_mbps,"
                    "delay_ms,loss_probability\n"
                )
                for second in range(240):
                    for path, capacity, delay, loss in PATHS:
                        file.write(
                            f"{second},10,20,{path},{capacity},{delay},{loss}\n"
                        )
            trace = load_measured_trace(trace_path)

        scenario = Scenario("trace", measured_trace=trace, demand_scale=1.5)
        self.assertEqual(
            _demand(0, np.random.default_rng(1), scenario),
            (15.0, 30.0),
        )
        _, trace_values = _simulate(POLICIES[0], seed=2, scenario=scenario)
        self.assertEqual(trace_values["demand_mbps"][0], 45.0)
        self.assertEqual(
            _path_capacity(0, 0, Scenario("scaled", path_capacity_scale=0.5)),
            75.0,
        )

    def test_benchmark_generates_summary_and_figure(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            rows = run_benchmark(output_dir, replicates=2, seed=9)

            self.assertEqual(len(rows), len(POLICIES) * len(SCENARIOS))
            self.assertTrue(
                (output_dir / "brain_inspired_cooperative_benchmark.csv").is_file()
            )
            self.assertTrue(
                (output_dir / "brain_inspired_cooperative_benchmark.png").is_file()
            )
            self.assertTrue(
                (output_dir / "brain_inspired_cooperative_resources.png").is_file()
            )
            self.assertTrue(
                (output_dir / "brain_inspired_cooperative_effects.png").is_file()
            )
            self.assertTrue(
                (output_dir / "brain_inspired_cooperative_timeseries.png").is_file()
            )
            self.assertTrue(
                (output_dir / "brain_inspired_cooperative_replicates.csv").is_file()
            )


if __name__ == "__main__":
    unittest.main()
