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

"""Tests for the AES-GCM layering model at the medium boundary."""

from __future__ import annotations

import unittest

from simulation.surgical.layering import ORDERINGS, measure_boundary


class LayeringTests(unittest.TestCase):
    def test_all_orderings_run_with_real_aead(self) -> None:
        for ordering in ORDERINGS:
            result = measure_boundary(1000, ordering, drop_probability=0.0, seed=0)
            self.assertGreater(result.fragments, 0)
            self.assertEqual(result.fragment_drop_rate, 0.0)
            self.assertEqual(result.object_loss_rate, 0.0)
            self.assertEqual(result.encrypted, "E" in ordering)

    def test_encrypt_then_fragment_is_cheaper_than_fragment_then_encrypt(self) -> None:
        # EF adds one tag and one nonce; FE adds one per fragment.
        ef = measure_boundary(2000, "EF", drop_probability=0.0, seed=0)
        fe = measure_boundary(2000, "FE", drop_probability=0.0, seed=0)
        self.assertEqual(ef.fragments, fe.fragments)
        self.assertGreater(fe.wire_bytes, ef.wire_bytes)

    def test_fragment_drop_rate_is_a_fraction(self) -> None:
        result = measure_boundary(2000, "CF", drop_probability=0.5, seed=0)
        self.assertGreaterEqual(result.fragment_drop_rate, 0.0)
        self.assertLessEqual(result.fragment_drop_rate, 1.0)

    def test_rejects_invalid_ordering(self) -> None:
        with self.assertRaises(ValueError):
            measure_boundary(100, "EX", seed=0)


if __name__ == "__main__":
    unittest.main()
