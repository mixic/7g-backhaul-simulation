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

import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.benchmark_brain_inspired import Metrics
from tools.benchmark_sensitivity import run_sensitivity
from tools.validation_io import (
    METRIC_UNITS,
    compare_normalized_results,
    export_simulation_replicates,
    normalize_external_results,
)


class ValidationWorkflowTests(unittest.TestCase):
    def test_sensitivity_sweep_reports_paired_differences(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "sensitivity.csv"
            rows = run_sensitivity(
                output_path,
                parameters=("path_capacity_scale",),
                policies=("Reactive baseline",),
                replicates=2,
                seed=17,
            )
            self.assertTrue(output_path.is_file())

        # The sensitivity sweep reports its own metric set, not METRIC_UNITS.
        self.assertEqual(len(rows), 3 * len(Metrics.__dataclass_fields__))
        default = next(
            row
            for row in rows
            if row["metric"] == "video_frames_on_time_percent"
            and row["value"] == 1.0
        )
        self.assertEqual(default["paired_delta_vs_default"], 0.0)

    def test_external_results_normalize_and_compare_by_paired_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replicate_csv = root / "replicates.csv"
            columns = ["scenario", "policy", "seed", *METRIC_UNITS]
            with replicate_csv.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=columns)
                writer.writeheader()
                for seed, on_time in ((101, 80.0), (102, 82.0)):
                    record = {
                        "scenario": "nominal",
                        "policy": "Reactive baseline",
                        "seed": seed,
                    }
                    record.update({metric: 0.0 for metric in METRIC_UNITS})
                    record["video_frames_on_time_percent"] = on_time
                    writer.writerow(record)

            external_csv = root / "external.csv"
            with external_csv.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=["scenario", "algorithm", "run", "video_success"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "scenario": "nominal",
                        "algorithm": "Reactive baseline",
                        "run": 101,
                        "video_success": 90.0,
                    }
                )
                writer.writerow(
                    {
                        "scenario": "nominal",
                        "algorithm": "Reactive baseline",
                        "run": 102,
                        "video_success": 91.0,
                    }
                )
            mapping = root / "mapping.json"
            mapping.write_text(
                json.dumps(
                    {
                        "scenario": "scenario",
                        "policy": "algorithm",
                        "seed": "run",
                        "metrics": {
                            "video_frames_on_time_percent": {
                                "column": "video_success",
                                "unit": "percent",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            python_normalized = root / "python.csv"
            external_normalized = root / "external_normalized.csv"
            report = root / "comparison.csv"

            count = export_simulation_replicates(
                replicate_csv,
                python_normalized,
            )
            self.assertEqual(count, 2 * len(METRIC_UNITS))
            self.assertEqual(
                normalize_external_results(
                    external_csv,
                    external_normalized,
                    mapping,
                    "ns3",
                ),
                2,
            )
            comparison = compare_normalized_results(
                python_normalized,
                external_normalized,
                report,
            )

        video = next(
            row
            for row in comparison
            if row["metric"] == "video_frames_on_time_percent"
        )
        self.assertEqual(video["paired_seeds"], 2)
        self.assertEqual(video["left_mean"], 81.0)
        self.assertEqual(video["right_mean"], 90.5)
        self.assertEqual(video["left_minus_right_mean"], -9.5)

    def test_external_multipath_policies_can_be_compared_by_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lia_path = root / "lia.csv"
            olia_path = root / "olia.csv"
            headers = [
                "source",
                "scenario",
                "policy",
                "seed",
                "metric",
                "value",
                "unit",
            ]
            for path, policy, values in (
                (lia_path, "LIA", (90.0, 92.0)),
                (olia_path, "OLIA", (91.0, 93.0)),
            ):
                with path.open("w", newline="", encoding="utf-8") as file:
                    writer = csv.DictWriter(file, fieldnames=headers)
                    writer.writeheader()
                    for seed, value in zip((201, 202), values):
                        writer.writerow(
                            {
                                "source": "mptcp_testbed",
                                "scenario": "heterogeneous_paths",
                                "policy": policy,
                                "seed": seed,
                                "metric": "video_frames_on_time_percent",
                                "value": value,
                                "unit": "percent",
                            }
                        )
            comparison = compare_normalized_results(
                lia_path,
                olia_path,
                root / "lia_vs_olia.csv",
                left_policy="LIA",
                right_policy="OLIA",
            )

        self.assertEqual(comparison[0]["left_policy"], "LIA")
        self.assertEqual(comparison[0]["right_policy"], "OLIA")
        self.assertEqual(comparison[0]["left_minus_right_mean"], -1.0)

    def test_comparison_requires_two_matched_seed_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            headers = [
                "source",
                "scenario",
                "policy",
                "seed",
                "metric",
                "value",
                "unit",
            ]
            paths = [root / "left.csv", root / "right.csv"]
            for path, source in zip(paths, ("simulator", "testbed")):
                with path.open("w", newline="", encoding="utf-8") as file:
                    writer = csv.DictWriter(file, fieldnames=headers)
                    writer.writeheader()
                    writer.writerow(
                        {
                            "source": source,
                            "scenario": "nominal",
                            "policy": "baseline",
                            "seed": 1,
                            "metric": "video_frames_on_time_percent",
                            "value": 90.0,
                            "unit": "percent",
                        }
                    )

            with self.assertRaisesRegex(ValueError, "At least two matched"):
                compare_normalized_results(
                    paths[0],
                    paths[1],
                    root / "comparison.csv",
                )


if __name__ == "__main__":
    unittest.main()
