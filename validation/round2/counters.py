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


"""Kernel counters and qdisc configuration used by the round-2 gates."""

from __future__ import annotations

from .net import NS_B, NS_N
from validation.real_stack.shell import Shell

INTERFACE_STATS = ("rx_packets", "rx_errors", "rx_dropped", "rx_frame_errors", "rx_length_errors", "rx_bytes")


def read_interface_stats(shell: Shell, namespace: str, device: str) -> dict[str, int]:
    """``/sys/class/net/<dev>/statistics/*`` for one device (zeros when absent)."""
    stats: dict[str, int] = {}
    for name in INTERFACE_STATS:
        result = shell.ns(namespace, ["cat", f"/sys/class/net/{device}/statistics/{name}"], check=False)
        text = (result.stdout or "").strip()
        stats[name] = int(text) if text.isdigit() else 0
    return stats


def read_xfrm_stat(shell: Shell, namespace: str) -> dict[str, int]:
    from validation.real_stack.counters import parse_xfrm_stat

    return parse_xfrm_stat(shell.ns(namespace, ["cat", "/proc/net/xfrm_stat"], check=False).stdout)


def read_conntrack_stat(shell: Shell, namespace: str) -> dict[str, int]:
    """First data line of ``/proc/net/stat/nf_conntrack`` keyed by its header."""
    text = shell.ns(namespace, ["cat", "/proc/net/stat/nf_conntrack"], check=False).stdout
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return {}
    header = lines[0].split()
    values = lines[1].split()
    result: dict[str, int] = {}
    for name, value in zip(header, values):
        try:
            result[name] = int(value, 16)
        except ValueError:
            continue
    return result


def read_conntrack_count(shell: Shell, namespace: str) -> int:
    text = shell.ns(namespace, ["cat", "/proc/sys/net/netfilter/nf_conntrack_count"], check=False).stdout
    return int(text.strip()) if text.strip().isdigit() else 0


def read_conntrack_dump(shell: Shell, namespace: str) -> list[str]:
    """Lines of ``/proc/net/nf_conntrack`` (empty when the file or module is absent)."""
    text = shell.ns(namespace, ["cat", "/proc/net/nf_conntrack"], check=False).stdout
    return [line for line in text.splitlines() if line.strip()]


def count_esp_entries(lines: list[str]) -> int:
    """Conntrack entries for ESP (protocol 50, printed as ``unknown`` by the generic tracker).

    The dump line for an ESP flow is e.g.
    ``ipv4 2 unknown 50 599 src=10.200.1.2 dst=10.200.2.2 [UNREPLIED] ...``.
    """
    total = 0
    for line in lines:
        head = line.split()[:6]
        if "esp" in head or ("unknown" in head and "50" in head):
            total += 1
    return total


def install_netem(shell: Shell, *, delay_ms: float, reorder_percent: float = 25.0, loss_percent: float = 0.0,
                  limit: int = 100_000) -> None:
    """One root qdisc on ``vN2`` egress (router namespace).

    ``limit`` is raised well above netem's 1000-packet default: with a 100 ms
    delay and a burst of 2000 datagrams the default tail-drop would lose packets
    before the replay window ever sees them.
    """
    parts = ["tc", "qdisc", "add", "dev", "vN2", "root", "netem"]
    if delay_ms:
        parts += ["delay", f"{delay_ms}ms"]
        if reorder_percent:
            parts += ["reorder", f"{reorder_percent}%"]
    if loss_percent:
        parts += ["loss", f"{loss_percent}%"]
    parts += ["limit", str(limit)]
    shell.ns(NS_N, parts)
