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


"""Reordering depth and the reference replay filter (frozen section 8).

Pure functions over the sequence numbers read from the ``vN2`` egress capture,
so the reference model can be unit-tested without a kernel.

The reference filter is written exactly as the frozen file states it: accept a
packet iff it is a new maximum, or ``max_seq_seen - seq < window`` and it has
not already been accepted.  It is deliberately *not* tuned to the kernel; a
disagreement is the finding P16a asks for.
"""

from __future__ import annotations

from typing import Iterable, Sequence


def reordering_depth(seqs: Sequence[int]) -> int:
    """Largest distance by which a packet arrived behind the highest seen so far."""
    highest = -1
    depth = 0
    for seq in seqs:
        if seq > highest:
            highest = seq
        else:
            depth = max(depth, highest - seq)
    return depth


def reference_accepted(seqs: Iterable[int], window: int) -> int:
    """Count packets the frozen reference filter accepts (legacy, non-ESN)."""
    accepted = 0
    highest = -1
    seen: set[int] = set()
    for seq in seqs:
        if seq > highest:
            highest = seq
            accepted += 1
            seen.add(seq)
            continue
        if highest - seq < window and seq not in seen:
            accepted += 1
            seen.add(seq)
    return accepted


def delivered_percent(delivered: int, sent: int) -> float:
    return 0.0 if sent <= 0 else 100.0 * delivered / sent


__all__ = ["delivered_percent", "reference_accepted", "reordering_depth"]
