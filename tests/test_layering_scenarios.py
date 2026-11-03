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

"""Tests for the frozen cases and the formal survival predictor."""

from __future__ import annotations

import unittest

from simulation.layering.predictions import predict
from simulation.layering.scenarios import (
    p3_cases,
    p4_cases,
    p6_cases,
    p7_cases,
    payload_bytes,
    loss_unit,
    text_bytes,
)
from simulation.layering.stack import MiddleboxSpec


class FrozenCaseTests(unittest.TestCase):
    def test_case_counts(self) -> None:
        self.assertEqual(len(p3_cases()), 3)
        self.assertEqual(len(p4_cases()), 6)
        self.assertEqual(len(p6_cases()), 54)
        self.assertEqual(len(p7_cases()), 3)

    def test_corpora_are_deterministic_and_sized(self) -> None:
        self.assertEqual(len(text_bytes(8192)), 8192)
        self.assertEqual(payload_bytes("text:1000"), text_bytes(1000))
        self.assertEqual(payload_bytes("random:12000"), payload_bytes("random:12000"))
        self.assertNotEqual(payload_bytes("random:12000"), b"\x00" * 12000)

    def test_loss_draws_are_in_range_and_seeded(self) -> None:
        self.assertEqual(loss_unit(1, 0, 0), loss_unit(1, 0, 0))
        self.assertNotEqual(loss_unit(1, 0, 0), loss_unit(2, 0, 0))
        for seed in range(1, 50):
            for fragment in range(9):
                self.assertGreaterEqual(loss_unit(seed, 0, fragment), 0.0)
                self.assertLess(loss_unit(seed, 0, fragment), 1.0)


class PredictorMatchesCodecTests(unittest.TestCase):
    def _check(self, case) -> None:
        stack = case.stack()
        encoded = stack.encode(case.data())
        middlebox = MiddleboxSpec(
            case.target[0], case.target[1], case.rewrite, case.max_depth
        )
        result = stack.decode(encoded, middlebox=middlebox)
        expected = predict(case)
        self.assertEqual(result.field_visible, expected.visible, case.name)
        self.assertEqual(result.mutation_applied, expected.mutation, case.name)
        self.assertEqual(result.auth_ok, expected.auth_ok, case.name)
        self.assertEqual(result.delivered, expected.delivered, case.name)

    def test_p6_sweep(self) -> None:
        for case in p6_cases():
            with self.subTest(case=case.name):
                self._check(case)

    def test_p7_structural_clause(self) -> None:
        for case in p7_cases():
            with self.subTest(case=case.name):
                self._check(case)


if __name__ == "__main__":
    unittest.main()
