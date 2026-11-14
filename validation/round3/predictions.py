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

"""Closed-form content of the frozen round-3 file, transcribed once.

Nothing here is tuned after a run: the numbers, windows, offsets and credences
are copied from ``docs/layering-real-stack-predictions-round3.md`` and the
kernel-free tests in ``tests/test_round3.py`` pin them.
"""

from __future__ import annotations

from typing import NamedTuple


class Round3Case(NamedTuple):
    id: str
    kind: str  # rate | reinject | mode
    window: int | None
    mode: str  # legacy | esn
    offset: int | None  # displacement for reinjection
    expected_delivered: int | None
    expected_reference: int | None
    min_depth: int | None
    max_depth: int | None
    datagrams: int
    interval: float
    credence: float


CASES: dict[str, Round3Case] = {
    "P17a": Round3Case(
        "P17a", "rate", 256, "esn", None, None, None, 64, 200, 600, 0.001, 0.75
    ),
    "P17b": Round3Case(
        "P17b", "reinject", 32, "legacy", 32, 1, 1, None, None, 120, 0.0, 0.80
    ),
    "P17c": Round3Case(
        "P17c", "reinject", 32, "legacy", 31, 2, 2, None, None, 120, 0.0, 0.80
    ),
    "P17d": Round3Case(
        "P17d", "reinject", 256, "esn", 256, 1, 1, None, None, 320, 0.0, 0.70
    ),
    "P17e": Round3Case(
        "P17e", "reinject", 256, "esn", 255, 2, 2, None, None, 320, 0.0, 0.70
    ),
}

MODE_CREDENCE = 0.95
CREDENCE = {key: value.credence for key, value in CASES.items()}
CREDENCE["P17f"] = MODE_CREDENCE

__all__ = ["CASES", "CREDENCE", "MODE_CREDENCE", "Round3Case"]
