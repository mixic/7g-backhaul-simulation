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

"""T-NDN: the topological NDN forwarding plan.

The plan is built from three local inputs only:

* the node's own links and their latencies (neighbour telemetry),
* name advertisements carrying ``name -> origin`` (the same advertisements every
  baseline receives),
* the persistent homology of the name space (``simulation/topology.py``),
  computed from pairwise name distances.

Nothing in this module reads a global shortest-path table, a link-state database
or the identity of the failed link.  The next hops come from a distance-vector
solve over neighbour advertisements, and the backup next hop is the standard
loop-free-alternate test (the neighbour's advertised distance is strictly
smaller than the node's own).

The FIB has one entry per persistent ``H0`` cluster, not one per name, and a
second entry for each cluster that lies on an ``H1`` loop.  The second entry is
what lets the node next to a failure switch locally: the failure is a lost
neighbour advertisement, the cluster is one the node already routes, and the
alternate was installed before the failure happened.  No void is hardcoded: the
void is the neighbour that stops advertising a finite distance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from simulation.ndn_network import PhysicalNetwork
from simulation.topology import PRODUCER_COUNT, Analysis

#: Stipulated control-plane constants.
HEARTBEAT_S = 0.2
DV_ROUND_S = 0.2

_INFINITY = math.inf


@dataclass(frozen=True)
class TndnPlan:
    cluster_of_name: tuple[int, ...]
    cluster_producer: tuple[int, ...]
    primary: tuple[tuple[int, ...], ...]  # node x cluster -> next hop, -1 local
    backup: tuple[tuple[int, ...], ...]
    fib_entries: tuple[int, ...]

    def fib_mean(self) -> float:
        return sum(self.fib_entries) / len(self.fib_entries)

    def has_backup(self, node: int, producer: int) -> bool:
        for cluster, owner in enumerate(self.cluster_producer):
            if owner == producer:
                return self.backup[node][cluster] >= 0
        return False

    def recovery_s(self, node: int, producer: int) -> float:
        """Local switch when an alternate exists, one DV round otherwise."""
        return HEARTBEAT_S if self.has_backup(node, producer) else HEARTBEAT_S + DV_ROUND_S


def _distance_vector(
    network: PhysicalNetwork, producer_node: list[int]
) -> tuple[list[list[float]], list[list[int]]]:
    """Bellman--Ford over neighbour advertisements (local by construction)."""
    count = network.node_count
    distance = [[_INFINITY] * PRODUCER_COUNT for _ in range(count)]
    for producer, origin in enumerate(producer_node):
        distance[origin][producer] = 0.0

    changed = True
    rounds = 0
    while changed and rounds <= count:
        changed = False
        rounds += 1
        for node in range(count):
            for producer in range(PRODUCER_COUNT):
                best = distance[node][producer]
                for neighbour, _, latency in network.neighbours(node):
                    candidate = latency + distance[neighbour][producer]
                    if candidate < best - 1e-12:
                        best = candidate
                if best < distance[node][producer] - 1e-12:
                    distance[node][producer] = best
                    changed = True

    first_hop = [[-1] * PRODUCER_COUNT for _ in range(count)]
    for node in range(count):
        for producer in range(PRODUCER_COUNT):
            best = _INFINITY
            choice = -1
            for neighbour, _, latency in network.neighbours(node):
                candidate = latency + distance[neighbour][producer]
                if candidate < best - 1e-12 or (
                    abs(candidate - best) <= 1e-12
                    and (choice < 0 or neighbour < choice)
                ):
                    best = candidate
                    choice = neighbour
            if math.isfinite(best) and abs(best - distance[node][producer]) <= 1e-9:
                first_hop[node][producer] = choice
    return distance, first_hop


def _fib(
    network: PhysicalNetwork,
    analysis: Analysis,
    distance: list[list[float]],
    first_hop: list[list[int]],
) -> tuple[
    tuple[tuple[int, ...], ...],
    tuple[tuple[int, ...], ...],
    tuple[int, ...],
]:
    cluster_producer = tuple(
        owners[0] if owners else 0 for owners in analysis.cluster_producers
    )
    primary: list[tuple[int, ...]] = []
    backup: list[tuple[int, ...]] = []
    entries: list[int] = []

    for node in range(network.node_count):
        node_primary: list[int] = []
        node_backup: list[int] = []
        count = 0
        for cluster, producer in enumerate(cluster_producer):
            hop = first_hop[node][producer]
            if hop < 0:
                node_primary.append(-1)
                node_backup.append(-1)
                continue
            if distance[node][producer] <= 1e-9:
                # The node is the producer for this cluster: local delivery.
                node_primary.append(-1)
                node_backup.append(-1)
                continue
            node_primary.append(hop)
            count += 1

            alternate = -1
            if cluster in analysis.hole_clusters:
                best = _INFINITY
                own = distance[node][producer]
                for neighbour, _, latency in network.neighbours(node):
                    if neighbour == hop:
                        continue
                    # Loop-free alternate: the neighbour is strictly closer to
                    # the producer than this node, so it cannot route back.
                    advertised = distance[neighbour][producer]
                    if advertised >= own - 1e-12:
                        continue
                    candidate = latency + advertised
                    if candidate < best - 1e-12:
                        best = candidate
                        alternate = neighbour
                if alternate >= 0:
                    count += 1
            node_backup.append(alternate)
        primary.append(tuple(node_primary))
        backup.append(tuple(node_backup))
        entries.append(count)

    return tuple(primary), tuple(backup), tuple(entries)


def build(
    network: PhysicalNetwork, analysis: Analysis, producer_node: list[int]
) -> TndnPlan:
    distance, first_hop = _distance_vector(network, producer_node)
    primary, backup, entries = _fib(network, analysis, distance, first_hop)
    return TndnPlan(
        cluster_of_name=analysis.cluster_of_name,
        cluster_producer=tuple(
            owners[0] if owners else 0 for owners in analysis.cluster_producers
        ),
        primary=primary,
        backup=backup,
        fib_entries=entries,
    )
