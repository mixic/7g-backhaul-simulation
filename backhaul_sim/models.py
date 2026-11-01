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

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Link:
    source: str
    target: str
    medium: str
    capacity_gbps: float
    latency_ms: float
    packet_loss_pct: float = 0.0
    reliability: float = 0.99
    cost_index: float = 1.0

    @property
    def effective_capacity(self) -> float:
        throughput_factor = max(0.05, 1.0 - (self.packet_loss_pct / 100.0))
        return self.capacity_gbps * throughput_factor * self.reliability

    @property
    def path_score(self) -> float:
        return (self.effective_capacity / max(1.0, self.latency_ms)) / max(0.1, self.cost_index)

    def reversed(self) -> "Link":
        return Link(
            source=self.target,
            target=self.source,
            medium=self.medium,
            capacity_gbps=self.capacity_gbps,
            latency_ms=self.latency_ms,
            packet_loss_pct=self.packet_loss_pct,
            reliability=self.reliability,
            cost_index=self.cost_index,
        )


@dataclass
class Node:
    name: str
    kind: str
    region: str
    capacity_gbps: float = 0.0
    notes: str = ""


@dataclass(frozen=True)
class TrafficFlow:
    name: str
    source: str
    destination: str
    demand_gbps: float
    priority: int = 1


@dataclass
class RouteResult:
    flow_name: str
    route: List[str]
    latency_ms: float
    estimated_throughput_gbps: float
    reliability: float
    utilization: float


class NetworkScenario:
    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self.nodes: Dict[str, Node] = {}
        self.links: List[Link] = []

    def add_node(self, node: Node) -> None:
        self.nodes[node.name] = node

    def add_link(
        self,
        source: str,
        target: str,
        medium: str,
        capacity_gbps: float,
        latency_ms: float,
        packet_loss_pct: float = 0.0,
        reliability: float = 0.99,
        cost_index: float = 1.0,
    ) -> None:
        self.links.append(
            Link(
                source=source,
                target=target,
                medium=medium,
                capacity_gbps=capacity_gbps,
                latency_ms=latency_ms,
                packet_loss_pct=packet_loss_pct,
                reliability=reliability,
                cost_index=cost_index,
            )
        )

    @property
    def adjacency(self) -> Dict[str, List[Link]]:
        graph: Dict[str, List[Link]] = {node_name: [] for node_name in self.nodes}
        for link in self.links:
            graph.setdefault(link.source, []).append(link)
            graph.setdefault(link.target, []).append(link.reversed())
        return graph

    def node_count(self) -> int:
        return len(self.nodes)

    def link_count(self) -> int:
        return len(self.links)
