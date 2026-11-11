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


"""Closed-form content of the frozen round-2 file, transcribed once.

Nothing here is tuned after a run: the numbers, windows and credences are copied
from ``docs/layering-real-stack-predictions-round2.md`` and the kernel-free
tests in ``tests/test_round2.py`` pin them.
"""

from __future__ import annotations

from typing import NamedTuple

ECN_NOT_ECT = 0x00
ECN_ECT0 = 0x02
ECN_CE = 0x03


class P13Case(NamedTuple):
    stack: str
    inner_tos: int | None  # None -> the control sends half Not-ECT, half ECT(0)
    outer_tos: int | None  # None -> no mangler
    delivery: int  # 0 or 100
    inner_at_receiver: int | None  # expected delivered inner ToS (None: unchanged)
    credence: float


#: Table of frozen section 5 (row h becomes one control case per stack).
P13_CASES: dict[str, P13Case] = {
    "P13a": P13Case("ipip", ECN_NOT_ECT, ECN_CE, 0, None, 0.90),
    "P13b": P13Case("ipip", ECN_NOT_ECT, ECN_ECT0, 100, ECN_NOT_ECT, 0.90),
    "P13c": P13Case("ipip", ECN_ECT0, ECN_CE, 100, ECN_CE, 0.90),
    "P13d": P13Case("wireguard", ECN_NOT_ECT, ECN_CE, 100, ECN_NOT_ECT, 0.70),
    "P13e": P13Case("wireguard", ECN_ECT0, ECN_CE, 100, ECN_CE, 0.70),
    "P13f": P13Case("esp_tunnel", ECN_NOT_ECT, ECN_CE, 100, ECN_NOT_ECT, 0.60),
    "P13g": P13Case("esp_tunnel", ECN_ECT0, ECN_CE, 100, ECN_CE, 0.60),
    "P13h_ipip": P13Case("ipip", None, None, 100, None, 0.95),
    "P13h_wg": P13Case("wireguard", None, None, 100, None, 0.95),
    "P13h_esp": P13Case("esp_tunnel", None, None, 100, None, 0.95),
}

#: Frozen section 7: the two predicted wire-byte totals, in capture order.
P15_PACKETS = {"E->F": (1500, 612), "F->E": (1480, 700)}
P15_TOTALS = {"E->F": 2112, "F->E": 2180}
P15_TOTAL_DIFFERENCE = 68
P15_LOSS = 0.05
P15_EXPECTED_DELIVERY = (1 - P15_LOSS) ** 2
P15_TOLERANCE_POINTS = 1.5
P15_BYTES_CREDENCE = 0.80
P15_DELIVERY_CREDENCE = 0.75

#: Frozen section 8.
class P16Case(NamedTuple):
    stack: str
    window: int | None
    delay_ms: float
    min_depth: int
    max_depth: int | None
    credence: float


P16_CASES: dict[str, P16Case] = {
    "P16a": P16Case("esp_tunnel", 32, 100.0, 64, None, 0.85),
    "P16b": P16Case("esp_tunnel", 32, 4.0, 0, 16, 0.90),
    "P16c": P16Case("wireguard", None, 100.0, 64, None, 0.90),
    "P16d": P16Case("esp_tunnel", 256, 100.0, 64, None, 0.70),
}

P14_CASES = {
    # case -> (predicted client 1 delivery, predicted client 2 delivery, nat, first, credence)
    "P14a": (100, 0, True, 1, 0.60),
    "P14b": (100, 0, True, 2, 0.60),
    "P14c": (100, 100, True, 1, 0.90),
    "P14d": (100, 100, False, 1, 0.95),
}

#: Frozen section 9, as credence per scored prediction.
CREDENCE: dict[str, float] = {
    "P13a": 0.90,
    "P13b": 0.90,
    "P13c": 0.90,
    "P13d": 0.70,
    "P13e": 0.70,
    "P13f": 0.60,
    "P13g": 0.60,
    "P13h": 0.95,
    "P14a": 0.60,
    "P14b": 0.60,
    "P14c": 0.90,
    "P14d": 0.95,
    "P15_bytes": 0.80,
    "P15_delivery": 0.75,
    "P16a": 0.85,
    "P16b": 0.90,
    "P16c": 0.90,
    "P16d": 0.70,
}

__all__ = [
    "CREDENCE",
    "ECN_CE",
    "ECN_ECT0",
    "ECN_NOT_ECT",
    "P13_CASES",
    "P14_CASES",
    "P15_EXPECTED_DELIVERY",
    "P15_PACKETS",
    "P15_TOTALS",
    "P16_CASES",
]
