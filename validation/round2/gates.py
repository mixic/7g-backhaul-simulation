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


"""Round-2 gates (frozen section 3): ECN mutation, SPI, fragment, depth, warm-up.

Gates are pure functions over capture records and counters so they can be tested
without a kernel.  A failed gate makes a case INVALID, never REFUTED.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from .predictions import P15_PACKETS

Record = Mapping[str, object]


# --- ECN mutation gate (P13) -----------------------------------------------------------


def ecn_gate(before: Sequence[Record], after: Sequence[Record], *, target_tos: int,
             expected: int) -> tuple[bool, str]:
    """Every test packet after the mangler carries the target codepoint; none is CE before it."""
    if len(after) < expected:
        return False, f"only {len(after)} of {expected} test packets seen at vN2 egress"
    if len(before) < expected:
        return False, f"only {len(before)} of {expected} test packets seen at vA1 egress"
    wrong = [record for record in after if int(record["tos"]) != target_tos]
    dscp = [record for record in after if int(record["tos"]) & 0xFC]
    ce_before = [record for record in before if int(record["tos"]) & 0x03 == 0x03]
    if wrong or dscp or ce_before:
        return False, (f"{len(wrong)} packets without ToS {target_tos:#04x}, "
                       f"{len(dscp)} with a non-zero DSCP, {len(ce_before)} already CE before the mangler")
    return True, f"all {len(after)} packets carry outer ToS {target_tos:#04x} and DSCP 0"


# --- SPI gate (P14) --------------------------------------------------------------------


def spi_counts(records: Iterable[Record]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for record in records:
        spi = record.get("esp_spi")
        if isinstance(spi, int):
            counts[spi] = counts.get(spi, 0) + 1
    return counts


def spi_gate(records: Sequence[Record], *, spis: Sequence[int], drops: Sequence[bool]) -> tuple[bool, str]:
    """A client called ``dropped`` needs its SPI to be *absent* at ``vN2`` egress."""
    counts = spi_counts(records)
    problems = [f"client {index + 1} delivered nothing but its SPI {spi:#010x} appears {counts.get(spi, 0)} times"
                for index, (spi, dropped) in enumerate(zip(spis, drops)) if dropped and counts.get(spi, 0)]
    detail = ", ".join(f"{spi:#010x}:{counts.get(spi, 0)}" for spi in spis)
    if problems:
        return False, "; ".join(problems)
    return True, f"SPI occurrences at vN2 egress: {detail}"


# --- Fragment gate (P15) ---------------------------------------------------------------


def fragment_groups(records: Sequence[Record], per_datagram: int) -> list[list[Record]]:
    return [list(records[index:index + per_datagram]) for index in range(0, len(records), per_datagram)]


def fragment_gate(records: Sequence[Record], *, ordering: str, expected_datagrams: int) -> tuple[bool, str]:
    """Each datagram must yield exactly the two predicted outer packets."""
    expected = P15_PACKETS[ordering]
    if len(records) != 2 * expected_datagrams:
        return False, f"captured {len(records)} outer packets for {expected_datagrams} datagrams, expected {2 * expected_datagrams}"
    groups = fragment_groups(records, 2)
    bad_lengths = [index for index, group in enumerate(groups)
                   if tuple(int(record["ip_len"]) for record in group) != expected]
    if bad_lengths:
        first = groups[bad_lengths[0]]
        return False, (f"{len(bad_lengths)} datagrams with lengths "
                       f"{tuple(int(record['ip_len']) for record in first)}, predicted {expected}")
    if ordering == "E->F":
        bad_flags = [index for index, group in enumerate(groups) if sum(int(record["mf"]) for record in group) != 1]
        if bad_flags:
            return False, f"{len(bad_flags)} datagrams did not carry exactly one more-fragments flag"
        return True, f"every datagram is two fragments {expected} with one MF flag"
    if any(int(record["mf"]) or int(record["frag_off"]) for group in groups for record in group):
        return False, "an outer packet carried a fragment flag or offset in the F->E ordering"
    return True, f"every datagram is two unfragmented packets {expected}"


# --- Depth gate (P16) ------------------------------------------------------------------


def depth_gate(depth: int, *, min_depth: int, max_depth: int | None) -> tuple[bool, str]:
    if depth < min_depth:
        return False, f"reordering depth {depth} below the required {min_depth}"
    if max_depth is not None and depth > max_depth:
        return False, f"reordering depth {depth} above the allowed {max_depth}"
    return True, f"reordering depth {depth} inside [{min_depth}, {max_depth if max_depth is not None else 'inf'}]"


# --- Warm-up gate (all) ----------------------------------------------------------------


def warmup_gate(warmed: bool) -> tuple[bool, str]:
    return (True, "tunnel carried traffic before any impairment") if warmed else (False, "tunnel never carried warm-up traffic")


__all__ = [
    "depth_gate",
    "ecn_gate",
    "fragment_gate",
    "spi_counts",
    "spi_gate",
    "warmup_gate",
]
