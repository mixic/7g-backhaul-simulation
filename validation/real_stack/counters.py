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


"""Kernel counters used by the cause gates.

Parsers are pure functions over text so they can be unit-tested; the ``read_*``
helpers run the corresponding command inside a namespace.
"""

from __future__ import annotations

import re
from typing import Mapping

from .shell import Shell

_XFRM_IN_ERROR = re.compile(r"^XfrmIn.*Error$")


def parse_xfrm_stat(text: str) -> dict[str, int]:
    """Parse ``/proc/net/xfrm_stat`` (``Name<spaces>value`` per line)."""
    stats: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
            stats[parts[0]] = int(parts[1])
    return stats


def xfrm_in_error_total(stats: Mapping[str, int]) -> int:
    """Sum of every ``XfrmIn*Error`` counter (the frozen cause gate for P8a)."""
    return sum(value for name, value in stats.items() if _XFRM_IN_ERROR.match(name))


def parse_snmp_udp(text: str) -> dict[str, int]:
    """Parse the ``Udp:`` header/value line pair of ``/proc/net/snmp``."""
    header: list[str] | None = None
    for line in text.splitlines():
        if not line.startswith("Udp:"):
            continue
        fields = line.split()[1:]
        if header is None:
            header = fields
            continue
        return {name: int(value) for name, value in zip(header, fields)}
    return {}


def parse_wg_transfer(text: str) -> tuple[int, int]:
    """Total (rx, tx) bytes over all peers from ``wg show <if> transfer``."""
    rx = tx = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            rx += int(parts[1])
            tx += int(parts[2])
    return rx, tx


def parse_wg_endpoints(text: str) -> list[tuple[str, int]]:
    """``wg show <if> endpoints`` -> list of (address, port); IPv4 only."""
    endpoints: list[tuple[str, int]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and ":" in parts[1] and parts[1] != "(none)":
            address, _, port = parts[1].rpartition(":")
            if port.isdigit():
                endpoints.append((address, int(port)))
    return endpoints


def read_xfrm_stat(shell: Shell, namespace: str) -> dict[str, int]:
    return parse_xfrm_stat(shell.ns(namespace, ["cat", "/proc/net/xfrm_stat"], check=False).stdout)


def read_udp_snmp(shell: Shell, namespace: str) -> dict[str, int]:
    return parse_snmp_udp(shell.ns(namespace, ["cat", "/proc/net/snmp"]).stdout)


def read_wg_transfer(shell: Shell, namespace: str, interface: str = "wg0") -> tuple[int, int]:
    return parse_wg_transfer(shell.ns(namespace, ["wg", "show", interface, "transfer"]).stdout)


def read_wg_endpoints(shell: Shell, namespace: str, interface: str = "wg0") -> list[tuple[str, int]]:
    return parse_wg_endpoints(shell.ns(namespace, ["wg", "show", interface, "endpoints"]).stdout)
