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

"""FSR-NDN baseline: fisheye scopes over hop distance.

Fisheye State Routing (Pei, Gerla and Chen, ICC 2000) refreshes routing state at
a frequency that decays with distance: neighbours often, distant destinations
rarely.  Adapted to NDN, the same idea gives a *scope-aggregated FIB*: names
whose producer is one hop away are kept as full names, two-hop names are
aggregated by type, and everything further is aggregated to the
``/service/region`` block.  That is deliberately generous to FSR — it is the
strongest aggregation a scoped protocol can plausibly install — so any FIB
advantage T-NDN shows is measured against a competitive baseline.

The price is the one the fisheye design accepts: when a distant name's path
breaks, its entry waits for the next refresh of its scope.  A far-scope request
also has a chance of a transient loop before the refresh lands.  Both effects
are modelled here with stipulated constants, not measured ones.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from simulation.ndn_network import PhysicalNetwork
from simulation.topology import NAME_COUNT, TYPE_COUNT

#: Stipulated refresh intervals by hop distance (1, 2, 3, 4+).
SCOPE_REFRESH_S = (0.0, 1.0, 4.0, 8.0, 15.0)
#: A stale far-scope entry can loop once before the refresh lands.
LOOP_PROBABILITY = 0.30
LOOP_PENALTY_S = 0.5
NAMES_PER_PRODUCER = NAME_COUNT // 20


def scope_level(hops: int) -> int:
    return min(max(hops, 1), len(SCOPE_REFRESH_S) - 1)


@dataclass(frozen=True)
class FsrPlan:
    fib_entries: tuple[int, ...]
    producer_node: tuple[int, ...]

    def fib_mean(self) -> float:
        return sum(self.fib_entries) / len(self.fib_entries)

    def recovery_s(
        self,
        network: PhysicalNetwork,
        consumer: int,
        producer: int,
        rng: random.Random,
    ) -> float:
        hops = network.hops[consumer][self.producer_node[producer]]
        refresh = SCOPE_REFRESH_S[scope_level(hops)]
        penalty = 0.0
        if hops >= 2 and rng.random() < LOOP_PROBABILITY:
            penalty = LOOP_PENALTY_S
        return refresh + penalty


def fib_entries(
    network: PhysicalNetwork, producer_node: list[int]
) -> tuple[int, ...]:
    """Per-node entry count of the scope-aggregated FIB."""
    entries: list[int] = []
    for node in range(network.node_count):
        count = 0
        for producer, origin in enumerate(producer_node):
            if origin == node:
                continue  # served locally
            hops = network.hops[node][origin]
            if hops <= 1:
                count += NAMES_PER_PRODUCER
            elif hops == 2:
                count += TYPE_COUNT
            else:
                count += 1
        entries.append(count)
    return tuple(entries)


def build(network: PhysicalNetwork, producer_node: list[int]) -> FsrPlan:
    return FsrPlan(
        fib_entries=fib_entries(network, producer_node),
        producer_node=tuple(producer_node),
    )


def fib_mean(plan: FsrPlan) -> float:
    return plan.fib_mean()
