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

"""Tests for the SimPy data plane."""

from __future__ import annotations

import unittest

from simulation.layering.scenarios import p2_cases, p3_cases, p5_cases
from simulation.layering.simpy_dataplane import simulate_case
from simulation.layering.stack import MiddleboxSpec


class SimPyDataPlaneTests(unittest.TestCase):
    def test_wire_bytes_match_the_codec(self) -> None:
        for case in p2_cases() + p5_cases():
            with self.subTest(case=case.name):
                outcome = simulate_case(case, 1)
                self.assertEqual(
                    outcome.wire_bytes, case.stack().encode(case.data()).wire_bytes
                )
                self.assertGreater(outcome.fragment_count, 0)

    def test_paired_seed_removes_the_delivery_difference(self) -> None:
        left, right = p2_cases()
        for seed in (1, 2, 3, 4, 5):
            with self.subTest(seed=seed):
                self.assertEqual(
                    simulate_case(left, seed).decode.delivered,
                    simulate_case(right, seed).decode.delivered,
                )

    def test_integrity_scope_outcome(self) -> None:
        covers, excludes, inside = p3_cases()
        covered = simulate_case(
            covers,
            1,
            middlebox=MiddleboxSpec(
                covers.target[0], covers.target[1], covers.rewrite
            ),
        )
        self.assertFalse(covered.decode.auth_ok)
        excluded = simulate_case(
            excludes,
            1,
            middlebox=MiddleboxSpec(
                excludes.target[0], excludes.target[1], excludes.rewrite
            ),
        )
        self.assertTrue(excluded.decode.auth_ok)
        invisible = simulate_case(
            inside,
            1,
            middlebox=MiddleboxSpec(
                inside.target[0], inside.target[1], inside.rewrite
            ),
        )
        self.assertFalse(invisible.decode.mutation_applied)


if __name__ == "__main__":
    unittest.main()
