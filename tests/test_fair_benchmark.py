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
import math
import tempfile
import unittest
from pathlib import Path

from tools.benchmark_fair import (
    ARMS,
    ProportionalAllocator,
    build_allocators,
    run_benchmark,
    sign_test_p_value,
)


class SignTestTests(unittest.TestCase):
    def test_all_positive_signs(self):
        self.assertAlmostEqual(sign_test_p_value([1.0, 2.0, 3.0, 4.0]), 0.125)

    def test_symmetric_differences_give_one(self):
        self.assertAlmostEqual(sign_test_p_value([1.0, -1.0, 2.0, -2.0]), 1.0)

    def test_no_differences_gives_one(self):
        self.assertEqual(sign_test_p_value([0.0, 0.0]), 1.0)


class AllocatorTests(unittest.TestCase):
    def test_every_arm_gets_its_own_allocator_except_the_legacy_pair(self):
        allocators = build_allocators(ARMS)
        independent = [ARMS[index].name for index in range(4)]
        self.assertEqual(
            len({id(allocators[name]) for name in independent}),
            len(independent),
        )
        legacy = [arm.name for arm in ARMS if arm.shared_allocator == "legacy"]
        self.assertEqual(len(legacy), 2)
        self.assertIs(allocators[legacy[0]], allocators[legacy[1]])

    def test_allocation_never_exceeds_capacity(self):
        from tools.benchmark_vision import Link

        allocator = ProportionalAllocator()
        links = (Link("a", 10.0, 5.0, 0.02, 0.001), Link("b", 5.0, 20.0, 0.03, 0.002))
        allocation = allocator.allocate(
            40.0,
            links,
            [1.0, 1.0],
        )
        self.assertAlmostEqual(float(sum(allocation)), 15.0)
        for index, link in enumerate(links):
            self.assertLessEqual(allocation[index], link.capacity_mbps + 1e-9)

    def test_smoothing_requires_valid_range(self):
        with self.assertRaises(ValueError):
            ProportionalAllocator(smoothing=1.0)


class FairBenchmarkTests(unittest.TestCase):
    def test_benchmark_writes_finite_paired_results(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            summary, paired = run_benchmark(output, replicates=2, seed=7)
            for name in (
                "vision_fair_summary.csv",
                "vision_fair_paired.csv",
                "vision_fair_per_seed.csv",
            ):
                self.assertTrue((output / name).is_file(), name)
            with (output / "vision_fair_paired.csv").open(
                newline="",
                encoding="utf-8",
            ) as file:
                rows = list(csv.DictReader(file))
        self.assertTrue(rows)
        self.assertEqual(len(summary), 4 * len(ARMS))
        for row in rows:
            self.assertTrue(math.isfinite(float(row["paired_difference"])))
            self.assertTrue(math.isfinite(float(row["paired_ci95"])))
            self.assertIn(row["ci_excludes_zero"], {"True", "False"})
        self.assertTrue(any(row["comparison"].startswith("legacy") for row in rows))


if __name__ == "__main__":
    unittest.main()
