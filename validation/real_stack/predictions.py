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


"""Closed-form predictions of ``docs/layering-real-stack-predictions.md``.

Only the deterministic, arithmetic predictions (P9 and P10) are encoded here.
The frozen tables are repeated verbatim so that a test can check the formulas
against the numbers that were committed before any harness code existed.

Nothing in this module touches the network or the kernel.
"""

from __future__ import annotations

WG_BASE = 60  # 20 IPv4 + 8 UDP + 16 WireGuard header + 16 tag
IPIP = 20  # fixed IPv4-in-IPv4 overhead
WG_MTU = 1420
STIPULATED_COMPOSITE = 56  # E (28) + T (28), the repo's stipulated composite

P9_LENGTHS = (29, 44, 60, 61, 76, 100, 1000, 1024, 1400)
P10_LENGTHS = (64, 65, 76, 77, 79, 100, 1000, 1008)

# Frozen tables (docs/layering-real-stack-predictions.md, commit 46c7b40).
P9_FROZEN_WIRE = {
    29: 92,
    44: 108,
    60: 124,
    61: 124,
    76: 140,
    100: 172,
    1000: 1068,
    1024: 1084,
    1400: 1468,
}
P9_FROZEN_DEVIATION = {29: 7, 44: 8, 60: 8, 61: 7, 76: 8, 100: 16, 1000: 12, 1024: 4, 1400: 12}
P10_FROZEN_Y_TO_W = {64: 156, 65: 156, 76: 156, 77: 172, 79: 172, 100: 188, 1000: 1084, 1008: 1100}
P10_FROZEN_W_TO_Y = {64: 144, 65: 160, 76: 160, 77: 160, 79: 160, 100: 192, 1000: 1088, 1008: 1088}
P10_FROZEN_D = {64: 12, 65: -4, 76: -4, 77: 12, 79: 12, 100: -4, 1000: -4, 1008: 12}


def r16(x: int) -> int:
    """Round ``x`` up to the next multiple of 16 (WireGuard plaintext padding)."""
    if x < 0:
        raise ValueError("length must be non-negative")
    return 16 * ((x + 15) // 16)


def wg_wire(inner_length: int) -> int:
    """Outer IPv4 total length of one WireGuard data packet (IPv4 underlay)."""
    padded = r16(inner_length)
    if padded > WG_MTU:
        raise ValueError("padded length exceeds the WireGuard MTU; formula does not apply")
    return WG_BASE + padded


def p9_deviation(inner_length: int) -> int:
    """Measured wire size minus the stipulated ``L + 56`` composite."""
    return wg_wire(inner_length) - inner_length - STIPULATED_COMPOSITE


def p10_wire_y_to_w(inner_length: int) -> int:
    """IPIP applied first, WireGuard outermost."""
    return WG_BASE + r16(inner_length + IPIP)


def p10_wire_w_to_y(inner_length: int) -> int:
    """WireGuard applied first, IPIP outermost."""
    return WG_BASE + IPIP + r16(inner_length)


def p10_d(inner_length: int) -> int:
    """``wire(Y->W) - wire(W->Y)``; predicted -4 or +12 depending on ``L mod 16``."""
    return p10_wire_y_to_w(inner_length) - p10_wire_w_to_y(inner_length)
