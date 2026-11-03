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

"""Unit tests for the Linux relay's wire parsing and rewrite logic.

These do not create namespaces; the namespace data plane itself is exercised
by ``python -m validation.layering.run_linux``.
"""

from __future__ import annotations

import struct
import sys
import unittest

if sys.platform == "win32":
    raise unittest.SkipTest("The Linux TUN relay requires fcntl; run this test on Linux.")

from simulation.layering.scenarios import make_stack, p3_cases, p7_cases, random_bytes
from validation.linux_layering import tun_relay as relay


class RelayParsingTests(unittest.TestCase):
    def test_ipv4_udp_to_app_port_is_accepted(self) -> None:
        packet = bytearray(28)
        packet[0] = 0x45
        packet[9] = 17
        struct.pack_into(">HHHH", packet, 20, 1234, 9999, 8, 0)
        self.assertTrue(relay.is_application_packet(bytes(packet), 9999))
        self.assertFalse(relay.is_application_packet(bytes(packet), 9998))

    def test_ipv6_and_tcp_are_rejected(self) -> None:
        self.assertFalse(relay.is_application_packet(b"\x60" + bytes(40), 9999))
        tcp = bytearray(40)
        tcp[0] = 0x45
        tcp[9] = 6
        self.assertFalse(relay.is_application_packet(bytes(tcp), 9999))

    def test_aad_offsets_follow_outer_headers(self) -> None:
        tags = relay.synth_tags(("E", "T", "S"), (("T", "src_port"),), b"")
        self.assertEqual(tags[0].aad[0].offset, 24 + 8)
        tags = relay.synth_tags(("E", "T", "S"), (("S", "seq"),), b"")
        self.assertEqual(tags[0].aad[0].offset, 0)
        self.assertEqual(tags[0].aad[0].length, 8)


class RelayDecodeTests(unittest.TestCase):
    def test_integrity_scope_cases_match_the_codec(self) -> None:
        for case in p3_cases():
            with self.subTest(case=case.name):
                stack = make_stack(case.kinds, case.aad)
                encoded = stack.encode(case.data())
                frames = {index: bytearray(part) for index, part in enumerate(encoded.parts)}
                reachable, visible, applied = relay.apply_rewrite(
                    case.kinds,
                    case.target,
                    case.rewrite,
                    case.max_depth,
                    frames,
                )
                result = relay.decode_datagram(
                    case.kinds, case.aad, {key: bytes(value) for key, value in frames.items()}, 1
                )
                self.assertEqual(visible, case.name != "inside_ciphertext")
                self.assertEqual(applied, case.name != "inside_ciphertext")
                self.assertEqual(
                    result["auth_ok"], case.name != "aad_covers"
                )
                self.assertEqual(
                    result["delivered"], case.name != "aad_covers"
                )

    def test_structural_rewrite_breaks_delivery(self) -> None:
        for case in p7_cases():
            with self.subTest(case=case.name):
                stack = make_stack(case.kinds, case.aad)
                encoded = stack.encode(random_bytes(4096))
                frames = {
                    index: bytearray(part) for index, part in enumerate(encoded.parts)
                }
                relay.apply_rewrite(
                    case.kinds, case.target, case.rewrite, case.max_depth, frames
                )
                result = relay.decode_datagram(
                    case.kinds,
                    case.aad,
                    {key: bytes(value) for key, value in frames.items()},
                    encoded.fragment_count,
                )
                self.assertTrue(result["auth_ok"])
                self.assertEqual(
                    result["delivered"], case.name == "inert_field"
                )


if __name__ == "__main__":
    unittest.main()
