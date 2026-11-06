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

"""Starvation accounting for the savant mode.

The anti-cheat rule requires the testbed to *exactly* measure how many packets
of other flows a node discards while it is hyper-specialised.  A drop is recorded
against the node whose savant mode was active when it happened, classified by
whether the dropped request carried the affected (attacked) name or any other
name.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StarvationLogger:
    """Per-node count of requests dropped while savant mode is active."""

    affected: dict = field(default_factory=dict)   # node -> affected-name drops
    other: dict = field(default_factory=dict)      # node -> other-flow drops
    active: set = field(default_factory=set)       # nodes currently in savant mode

    def activate(self, node: int) -> None:
        self.active.add(node)
        self.affected.setdefault(node, 0)
        self.other.setdefault(node, 0)

    def deactivate(self, node: int) -> None:
        self.active.discard(node)

    def record(self, node: int, is_affected: bool) -> None:
        if node not in self.active:
            return
        if is_affected:
            self.affected[node] += 1
        else:
            self.other[node] += 1

    def total_other(self) -> int:
        return sum(self.other.values())

    def total_affected(self) -> int:
        return sum(self.affected.values())

    def per_node(self) -> dict:
        nodes = sorted(set(self.affected) | set(self.other))
        return {
            n: {"affected": self.affected.get(n, 0), "other": self.other.get(n, 0)}
            for n in nodes
        }
