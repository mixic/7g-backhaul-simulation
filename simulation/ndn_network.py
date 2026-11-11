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

"""Physical network shared by every M10 strategy (T-NDN versus three baselines).

The topology is a random geometric graph on the unit square: 100 nodes,
``RADIUS``-radius edges, latency ``BASE_MS + SPAN_MS * distance``.  The same
graph, the same producer placement, the same request stream and the same failed
link are handed to all four strategies, so the comparison is paired by
construction.

Only :class:`PhysicalNetwork` knows the whole graph.  NLSR is allowed to use it
(it is a link-state protocol); FSR, the fisheye overlay and T-NDN are given the
same graph object only because the simulator has to give every strategy the
same physical reality.  The strategies themselves are written so that their
forwarding state is built from local information: adjacency, neighbour
advertisements, RTT probes and name advertisements.  The one exception is the
FSR/T-NDN distance-vector solve, which in deployment is iterative and local; in
this simulator it is solved centrally for exactness and the strategy code never
reads a global shortest-path table.
"""

from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass

NODE_COUNT = 100
RADIUS = 0.175
BASE_MS = 10.0
SPAN_MS = 40.0
FAILURE_S = 30.0


@dataclass(frozen=True)
class Link:
    index: int
    a: int
    b: int
    latency_ms: float

    @property
    def endpoints(self) -> tuple[int, int]:
        return (self.a, self.b)

    def other(self, node: int) -> int:
        return self.b if node == self.a else self.a


class PhysicalNetwork:
    """Random geometric graph with exact all-pairs shortest paths."""

    def __init__(
        self,
        node_count: int = NODE_COUNT,
        seed: int = 2026,
        radius: float = RADIUS,
    ) -> None:
        rng = random.Random(seed)
        self.node_count = node_count
        self.positions = [(rng.random(), rng.random()) for _ in range(node_count)]
        self.links: list[Link] = []
        self._adjacency: list[list[tuple[int, int]]] = [[] for _ in range(node_count)]

        for left in range(node_count):
            for right in range(left + 1, node_count):
                delta = self._euclidean(left, right)
                if delta <= radius:
                    self._add_link(left, right, BASE_MS + SPAN_MS * delta)
        self._connect_components()
        self._all_pairs()

    # -- construction ------------------------------------------------------
    @classmethod
    def from_parts(
        cls,
        positions: list[tuple[float, float]],
        links: list[tuple[int, int, float]],
    ) -> "PhysicalNetwork":
        network = cls.__new__(cls)
        network.node_count = len(positions)
        network.positions = list(positions)
        network.links = []
        network._adjacency = [[] for _ in positions]
        for a, b, latency in links:
            network._add_link(a, b, latency)
        network._all_pairs()
        return network

    def _euclidean(self, left: int, right: int) -> float:
        ax, ay = self.positions[left]
        bx, by = self.positions[right]
        return math.hypot(ax - bx, ay - by)

    def _add_link(self, a: int, b: int, latency_ms: float) -> None:
        link = Link(len(self.links), a, b, latency_ms)
        self.links.append(link)
        self._adjacency[a].append((b, link.index))
        self._adjacency[b].append((a, link.index))

    def _connect_components(self) -> None:
        while True:
            components = self._components()
            if len(components) == 1:
                return
            best: tuple[float, int, int] | None = None
            for left_index, left in enumerate(components):
                for right in components[left_index + 1 :]:
                    for a in left:
                        for b in right:
                            candidate = self._euclidean(a, b)
                            if best is None or candidate < best[0]:
                                best = (candidate, a, b)
            assert best is not None
            _, a, b = best
            self._add_link(a, b, BASE_MS + SPAN_MS * self._euclidean(a, b))

    def _components(self) -> list[list[int]]:
        seen: set[int] = set()
        components: list[list[int]] = []
        for start in range(self.node_count):
            if start in seen:
                continue
            stack = [start]
            seen.add(start)
            members = []
            while stack:
                node = stack.pop()
                members.append(node)
                for neighbour, _ in self._adjacency[node]:
                    if neighbour not in seen:
                        seen.add(neighbour)
                        stack.append(neighbour)
            components.append(members)
        return components

    # -- shortest paths ----------------------------------------------------
    def _all_pairs(self) -> None:
        self.distance_ms: list[list[float]] = []
        self.hops: list[list[int]] = []
        self.next_hop: list[list[int]] = []
        for source in range(self.node_count):
            distance, hops, first = self._dijkstra(source)
            self.distance_ms.append(distance)
            self.hops.append(hops)
            self.next_hop.append(first)

    def _dijkstra(self, source: int) -> tuple[list[float], list[int], list[int]]:
        infinity = math.inf
        distance = [infinity] * self.node_count
        hops = [0] * self.node_count
        first = [-1] * self.node_count
        distance[source] = 0.0
        first[source] = source
        queue: list[tuple[float, int, int]] = [(0.0, 0, source)]
        while queue:
            latency, hop_count, node = heapq.heappop(queue)
            if latency > distance[node] + 1e-12:
                continue
            for neighbour, link_index in self._adjacency[node]:
                candidate = latency + self.links[link_index].latency_ms
                candidate_hops = hop_count + 1
                better = candidate < distance[neighbour] - 1e-12
                equal_but_fewer = (
                    abs(candidate - distance[neighbour]) <= 1e-12
                    and candidate_hops < hops[neighbour]
                )
                if better or equal_but_fewer:
                    distance[neighbour] = candidate
                    hops[neighbour] = candidate_hops
                    first[neighbour] = neighbour if node == source else first[node]
                    heapq.heappush(queue, (candidate, candidate_hops, neighbour))
        return distance, hops, first

    def path_links(self, source: int, target: int) -> list[int]:
        """Link indices along the shortest path (empty when unreachable)."""
        if source == target:
            return []
        if not math.isfinite(self.distance_ms[source][target]):
            return []
        links: list[int] = []
        node = source
        seen = 0
        while node != target and seen <= self.node_count:
            step = self.next_hop[node][target]
            link = self.link_between(node, step)
            if link is None:
                return []
            links.append(link)
            node = step
            seen += 1
        return links

    def link_between(self, a: int, b: int) -> int | None:
        for neighbour, link_index in self._adjacency[a]:
            if neighbour == b:
                return link_index
        return None

    def neighbours(self, node: int) -> list[tuple[int, int, float]]:
        """``(neighbour, link index, latency)`` triples."""
        return [
            (neighbour, link_index, self.links[link_index].latency_ms)
            for neighbour, link_index in self._adjacency[node]
        ]

    def neighbour_count(self, node: int) -> int:
        return len(self._adjacency[node])

    def diameter_hops(self) -> int:
        return max(max(row) for row in self.hops)

    def link_usage(self) -> list[int]:
        """How many ordered pairs use each link on their shortest path."""
        usage = [0] * len(self.links)
        for source in range(self.node_count):
            for target in range(self.node_count):
                if source == target:
                    continue
                if not math.isfinite(self.distance_ms[source][target]):
                    continue
                for link in self.path_links(source, target):
                    usage[link] += 1
        return usage

    def choose_failure_link(self) -> int:
        """Highest-usage link whose endpoints both have at least 3 links."""
        usage = self.link_usage()
        candidates = [
            link.index
            for link in self.links
            if self.neighbour_count(link.a) >= 3
            and self.neighbour_count(link.b) >= 3
            and self._remains_connected(link.index)
        ]
        if not candidates:
            raise RuntimeError("no non-bridge link with high-degree endpoints")
        return max(candidates, key=lambda index: (usage[index], -index))

    def _remains_connected(self, link_index: int) -> bool:
        blocked = self.links[link_index]
        seen = {0}
        stack = [0]
        while stack:
            node = stack.pop()
            for neighbour, index in self._adjacency[node]:
                if index == link_index:
                    continue
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        return len(seen) == self.node_count

    def without_link(self, link_index: int) -> "PhysicalNetwork":
        links = [
            (link.a, link.b, link.latency_ms)
            for link in self.links
            if link.index != link_index
        ]
        return PhysicalNetwork.from_parts(self.positions, links)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"PhysicalNetwork(nodes={self.node_count}, links={len(self.links)}, "
            f"diameter={self.diameter_hops()})"
        )
