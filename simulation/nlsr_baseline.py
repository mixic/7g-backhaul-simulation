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

"""NLSR baseline: global link-state flooding and per-name FIB entries.

Classical NLSR (Hoque et al., ICN 2013): every node receives every link-state
advertisement, computes a shortest-path tree, and installs a FIB entry for every
routed name.  The cost that matters here is that the FIB is not aggregated —
each of the 10 000 names is one entry — and that a topology change requires a
global flood and a full SPF run before any affected name can be routed again.

The parameters are stipulated, not measured: one second to detect a failed
link, 20 ms of flood time per hop, 10 ms for the SPF.  They are the same
parameters used by the FSR and T-NDN models, so the comparison differs in the
mechanism (global flood versus scoped refresh versus local repair), not in the
speed of a single message.
"""

from __future__ import annotations

from dataclasses import dataclass

from simulation.ndn_network import PhysicalNetwork
from simulation.topology import NAME_COUNT

#: Stipulated control-plane constants.
DETECTION_S = 1.0
FLOOD_MS_PER_HOP = 20.0
SPF_S = 0.01


@dataclass(frozen=True)
class NlsrPlan:
    fib_entries: tuple[int, ...]
    detection_s: float
    flood_s: float
    spf_s: float

    @property
    def convergence_s(self) -> float:
        return self.detection_s + self.flood_s + self.spf_s

    def recovery_s(self, node: int, producer: int) -> float:
        """NLSR repairs every name at the same time, after the global flood."""
        return self.convergence_s


def build(
    network: PhysicalNetwork,
    producer_node: list[int],
    after_network: PhysicalNetwork | None = None,
) -> NlsrPlan:
    """Install one FIB entry per non-local name and time the reconvergence."""
    local = {node: 0 for node in range(network.node_count)}
    for node in producer_node:
        # A producer serves its own block locally; it does not install a FIB
        # entry for its own names.
        local[node] += NAME_COUNT // len(producer_node)
    fib_entries = tuple(NAME_COUNT - local[node] for node in range(network.node_count))

    # The flood runs over the surviving topology, so the diameter is the one
    # after the failure.
    flooded = after_network if after_network is not None else network
    return NlsrPlan(
        fib_entries=fib_entries,
        detection_s=DETECTION_S,
        flood_s=flooded.diameter_hops() * FLOOD_MS_PER_HOP / 1000.0,
        spf_s=SPF_S,
    )


def fib_mean(plan: NlsrPlan) -> float:
    return sum(plan.fib_entries) / len(plan.fib_entries)


def aggregated_fib_entries(
    network: PhysicalNetwork, producer_node: list[int]
) -> tuple[int, ...]:
    """NLSR FIB if each producer announced its block prefix, not each name.

    Not part of H13: the frozen scenario announces names individually.  This is
    reported as a sensitivity, because it is the strongest thing a prefix-
    aggregating NLSR could do and it changes the FIB comparison completely.
    """
    blocks = len(producer_node)
    local = set(producer_node)
    return tuple(
        blocks - (1 if node in local else 0)
        for node in range(network.node_count)
    )


def aggregated_fib_mean(
    network: PhysicalNetwork, producer_node: list[int]
) -> float:
    entries = aggregated_fib_entries(network, producer_node)
    return sum(entries) / len(entries)
