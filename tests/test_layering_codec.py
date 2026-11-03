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

"""Unit tests for the typed layer codec."""

from __future__ import annotations

import itertools
import unittest

from simulation.layering.layers import (
    AEAD_OVERHEAD_BYTES,
    FRAGMENT_HEADER_BYTES,
    CompressLayer,
    EncryptLayer,
    FragmentLayer,
    SequenceLayer,
    TunnelLayer,
)
from simulation.layering.stack import MiddleboxSpec, Stack


def stack(*kinds: str, aad=(), mtu: int = 1500) -> Stack:
    layers = {
        "C": CompressLayer,
        "E": lambda: EncryptLayer(aad=aad),
        "T": TunnelLayer,
        "F": lambda: FragmentLayer(mtu=mtu, datagram_id=7),
        "S": SequenceLayer,
    }
    return Stack([layers[kind]() for kind in kinds])


def corpus(size: int) -> bytes:
    text = b"the quick brown fox jumps over the lazy dog. "
    return (text * (size // len(text) + 1))[:size]


class RoundTripTests(unittest.TestCase):
    def test_every_subset_round_trips(self) -> None:
        payload = bytes(range(256)) * 8
        kinds = ("C", "E", "T", "F", "S")
        for size in range(1, 5):
            for subset in itertools.combinations(kinds, size):
                for order in itertools.permutations(subset):
                    with self.subTest(order=order):
                        composed = stack(*order)
                        encoded = composed.encode(payload)
                        result = composed.decode(encoded)
                        self.assertTrue(result.delivered)
                        self.assertEqual(result.payload, payload)

    def test_compression_then_encryption_round_trips(self) -> None:
        payload = corpus(4096)
        composed = stack("C", "E")
        result = composed.decode(composed.encode(payload))
        self.assertEqual(result.payload, payload)

    def test_fragment_reassembly_requires_every_fragment(self) -> None:
        payload = bytes(range(256)) * 20
        composed = stack("F")
        encoded = composed.encode(payload)
        self.assertGreater(encoded.fragment_count, 1)
        for missing in range(encoded.fragment_count):
            with self.subTest(missing=missing):
                received = set(range(encoded.fragment_count)) - {missing}
                result = composed.decode(encoded, received=received)
                self.assertFalse(result.delivered)

    def test_duplicate_kinds_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Stack([TunnelLayer(), TunnelLayer()])

    def test_two_encryption_layers_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Stack([EncryptLayer(), EncryptLayer()])


class ByteAccountingTests(unittest.TestCase):
    def test_fixed_overheads_commute_on_size(self) -> None:
        payload = bytes(range(256)) * 4
        sizes = set()
        maximums = set()
        for order in itertools.permutations(("T", "E", "S")):
            composed = stack(*order)
            sizes.add(composed.wire_bytes(payload))
            maximums.add(composed.max_payload(1500, corpus))
        self.assertEqual(sizes, {1024 + 28 + 28 + 24})
        self.assertEqual(maximums, {1500 - 80})

    def test_fragmented_encryption_overhead_is_exact(self) -> None:
        payload = bytes(range(256)) * 47
        before = stack("E", "F").encode(payload)
        after = stack("F", "E").encode(payload)
        self.assertEqual(
            after.wire_bytes - before.wire_bytes,
            AEAD_OVERHEAD_BYTES * (before.fragment_count - 1),
        )

    def test_fragment_header_accounting(self) -> None:
        payload = bytes(range(256)) * 16
        encoded = stack("F").encode(payload)
        self.assertEqual(
            encoded.wire_bytes,
            len(payload) + FRAGMENT_HEADER_BYTES * encoded.fragment_count,
        )

    def test_max_payload_fits_and_next_byte_does_not(self) -> None:
        for kinds, maker in (
            (("C", "E"), corpus),
            (("E", "C"), corpus),
            (("T", "E", "S"), corpus),
            (("C", "F"), corpus),
        ):
            with self.subTest(kinds=kinds):
                composed = stack(*kinds)
                best = composed.max_payload(1500, maker)
                self.assertLessEqual(composed.wire_bytes(maker(best)), 1500)
                self.assertGreaterEqual(best, 1)
                if best < 60000:
                    self.assertGreater(composed.wire_bytes(maker(best + 1)), 1500)

    def test_visibility_tracks_encryption_and_compression(self) -> None:
        payload = bytes(range(256)) * 2
        inside = stack("S", "E").encode(payload)
        outside = stack("E", "S").encode(payload)
        compressed = stack("S", "C").encode(payload)
        self.assertFalse(inside.fields[0].visible)
        self.assertTrue(outside.fields[0].visible)
        self.assertFalse(compressed.fields[0].visible)


class MiddleboxTests(unittest.TestCase):
    def test_integrity_scope_extremes(self) -> None:
        payload = b"payload" * 100
        covered_stack = stack("E", "T", aad=(("T", "src_port"),))
        covered = covered_stack.decode(
            covered_stack.encode(payload),
            middlebox=MiddleboxSpec("T", "src_port", b"\x9c\x40"),
        )
        self.assertFalse(covered.auth_ok)
        self.assertFalse(covered.delivered)
        self.assertTrue(covered.mutation_applied)

        excluded_stack = stack("E", "T")
        excluded = excluded_stack.decode(
            excluded_stack.encode(payload),
            middlebox=MiddleboxSpec("T", "src_port", b"\x9c\x40"),
        )
        self.assertTrue(excluded.auth_ok)
        self.assertTrue(excluded.delivered)
        self.assertTrue(excluded.mutation_applied)

        invisible_stack = stack("T", "E")
        invisible = invisible_stack.decode(
            invisible_stack.encode(payload),
            middlebox=MiddleboxSpec("T", "src_port", b"\x9c\x40"),
        )
        self.assertTrue(invisible.auth_ok)
        self.assertTrue(invisible.delivered)
        self.assertFalse(invisible.mutation_applied)
        self.assertFalse(invisible.field_visible)

    def test_structural_length_field_breaks_delivery(self) -> None:
        composed = stack("T", "F")
        encoded = composed.encode(bytes(range(256)) * 16)
        broken = composed.decode(
            encoded,
            middlebox=MiddleboxSpec("F", "length", b"\x00\x09"),
        )
        self.assertTrue(broken.auth_ok)
        self.assertFalse(broken.delivered)
        self.assertTrue(broken.mutation_applied)

    def test_inert_field_preserves_delivery(self) -> None:
        composed = stack("T", "F")
        encoded = composed.encode(bytes(range(256)) * 16)
        result = composed.decode(
            encoded,
            middlebox=MiddleboxSpec("T", "src_port", b"\x9c\x40"),
        )
        self.assertTrue(result.auth_ok)
        self.assertTrue(result.delivered)

    def test_aad_over_invisible_field_is_rejected(self) -> None:
        composed = stack("T", "E", aad=(("T", "src_port"),))
        with self.assertRaises(ValueError):
            composed.encode(b"payload")

    def test_length_changing_rewrite_is_rejected(self) -> None:
        composed = stack("T", "E")
        encoded = composed.encode(b"payload")
        with self.assertRaises(ValueError):
            composed.decode(
                encoded,
                middlebox=MiddleboxSpec("T", "src_port", b"\x01"),
            )

    def test_unreachable_field_is_not_rewritten(self) -> None:
        composed = stack("E", "T")
        encoded = composed.encode(b"payload")
        result = composed.decode(
            encoded,
            middlebox=MiddleboxSpec("T", "src_port", b"\x9c\x40", max_depth=0),
        )
        self.assertFalse(result.mutation_applied)
        self.assertTrue(result.delivered)

    def test_rewrite_changes_only_the_visible_copy(self) -> None:
        composed = stack("E", "T")
        encoded = composed.encode(b"payload")
        rewritten, report = _apply(
            encoded, MiddleboxSpec("T", "src_port", b"\x9c\x40")
        )
        self.assertTrue(report.applied)
        self.assertNotEqual(
            encoded.field_values("T", "src_port"),
            rewritten.field_values("T", "src_port"),
        )


def _apply(encoded, spec):
    from simulation.layering.stack import apply_middlebox

    return apply_middlebox(encoded, spec)


if __name__ == "__main__":
    unittest.main()
