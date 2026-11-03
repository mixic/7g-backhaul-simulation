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

"""Property-based tests for decap(encap(x)) == x and size accounting."""

from __future__ import annotations

import unittest

from hypothesis import given, settings, strategies as st

from simulation.layering.layers import (
    CompressLayer,
    EncryptLayer,
    FragmentLayer,
    SequenceLayer,
    TunnelLayer,
)
from simulation.layering.stack import MiddleboxSpec, Stack

STACKS = [
    ("C",),
    ("E",),
    ("T",),
    ("S",),
    ("F",),
    ("C", "E"),
    ("E", "C"),
    ("T", "E", "S"),
    ("E", "F"),
    ("F", "E"),
    ("C", "F"),
    ("F", "C"),
    ("T", "F"),
    ("F", "T"),
]


def build(kinds, aad=()):
    layers = {
        "C": CompressLayer,
        "E": lambda: EncryptLayer(aad=aad),
        "T": TunnelLayer,
        "F": lambda: FragmentLayer(mtu=1500, datagram_id=11),
        "S": SequenceLayer,
    }
    return Stack([layers[kind]() for kind in kinds])


class LayeringProperties(unittest.TestCase):
    @settings(max_examples=25, deadline=None)
    @given(payload=st.binary(max_size=6000))
    def test_round_trip_is_exact(self, payload: bytes) -> None:
        for kinds in STACKS:
            composed = build(kinds)
            result = composed.decode(composed.encode(payload))
            self.assertTrue(result.delivered, kinds)
            self.assertEqual(result.payload, payload, kinds)

    @settings(max_examples=25, deadline=None)
    @given(payload=st.binary(min_size=1, max_size=5000))
    def test_fixed_overhead_is_exact(self, payload: bytes) -> None:
        for order in (
            ("T", "E", "S"),
            ("T", "S", "E"),
            ("E", "T", "S"),
            ("E", "S", "T"),
            ("S", "T", "E"),
            ("S", "E", "T"),
        ):
            composed = build(order)
            self.assertEqual(
                composed.wire_bytes(payload),
                len(payload) + 28 + 28 + 24,
            )

    @settings(max_examples=20, deadline=None)
    @given(payload=st.binary(min_size=1, max_size=4000))
    def test_rewrite_preserves_delivery_outside_integrity_scope(
        self, payload: bytes
    ) -> None:
        composed = build(("E", "T"))
        encoded = composed.encode(payload)
        result = composed.decode(
            encoded,
            middlebox=MiddleboxSpec("T", "src_port", b"\x9c\x40"),
        )
        self.assertTrue(result.auth_ok)
        self.assertTrue(result.delivered)

    @settings(max_examples=20, deadline=None)
    @given(payload=st.binary(min_size=1, max_size=4000))
    def test_rewrite_breaks_authentication_inside_integrity_scope(
        self, payload: bytes
    ) -> None:
        composed = build(("E", "T"), aad=(("T", "src_port"),))
        encoded = composed.encode(payload)
        result = composed.decode(
            encoded,
            middlebox=MiddleboxSpec("T", "src_port", b"\x9c\x40"),
        )
        self.assertFalse(result.auth_ok)
        self.assertFalse(result.delivered)


if __name__ == "__main__":
    unittest.main()
