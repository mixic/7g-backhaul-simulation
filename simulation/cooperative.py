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
from math import isfinite
from typing import Iterable, Optional, Tuple

from .mesh import MeshRequestResult, PeerMesh
from .quantum import QuantumResourceLink, QuantumResourceUnavailable
from .trends import RequestDemandLearner, TrendEstimate


@dataclass(frozen=True)
class CooperativeBackhaulDecision:
    delivery: MeshRequestResult
    demand_forecast: TrendEstimate
    quantum_link: Optional[str]
    reserved_key_bits: int
    classical_fragment_count: int
    classical_path_payload_mtu_bytes: Optional[int]


class CooperativeBackhaulCoordinator:
    """Coordinate shared mesh telemetry, cache decisions, and quantum key resources."""

    def __init__(
        self,
        mesh: PeerMesh,
        quantum_links: Iterable[QuantumResourceLink] = (),
        demand_forecast_horizon_seconds: float = 5.0,
        replica_demand_threshold: float = 3.0,
    ) -> None:
        if not isfinite(replica_demand_threshold) or replica_demand_threshold <= 0:
            raise ValueError("Replica demand threshold must be positive and finite.")
        self.mesh = mesh
        self.quantum_links = list(quantum_links)
        self.replica_demand_threshold = replica_demand_threshold
        self.demand_learner = RequestDemandLearner(
            forecast_horizon_seconds=demand_forecast_horizon_seconds,
        )
        self._timestamp = 0.0
        endpoint_pairs = [
            tuple(sorted((link.peer_a, link.peer_b)))
            for link in self.quantum_links
        ]
        if len(set(endpoint_pairs)) != len(endpoint_pairs):
            raise ValueError("Quantum links between the same peers must be unique.")
        for link in self.quantum_links:
            if link.peer_a not in mesh.peers or link.peer_b not in mesh.peers:
                raise ValueError(
                    f"Quantum link {link.peer_a!r}-{link.peer_b!r} "
                    "references an unknown mesh peer."
                )

    def request(
        self,
        requesting_peer: str,
        content_id: str,
        timestamp: Optional[float] = None,
        requires_quantum_key: bool = False,
        quantum_key_bits: int = 256,
    ) -> CooperativeBackhaulDecision:
        if timestamp is None:
            self._timestamp += 1.0
            timestamp = self._timestamp
        if requires_quantum_key and (
            not isinstance(quantum_key_bits, int)
            or isinstance(quantum_key_bits, bool)
            or quantum_key_bits <= 0
        ):
            raise ValueError("Quantum key size must be a positive integer number of bits.")
        demand_forecast = self.demand_learner.observe(
            requesting_peer,
            timestamp,
        )
        forecast_replication = (
            demand_forecast.forecast >= self.replica_demand_threshold
        )
        delivery = self.mesh.request(
            requesting_peer,
            content_id,
            allow_cache_replication=forecast_replication,
        )
        selected_quantum_link: Optional[str] = None
        reserved_key_bits = 0

        if requires_quantum_key and delivery.serving_peer != requesting_peer:
            matching_links = sorted(
                (
                    link
                    for link in self.quantum_links
                    if link.available
                    and link.connects(requesting_peer, delivery.serving_peer)
                    and link.buffered_key_bits >= quantum_key_bits
                ),
                key=lambda link: (-link.buffered_key_bits, link.peer_a, link.peer_b),
            )
            if not matching_links:
                raise QuantumResourceUnavailable(
                    "No available quantum link has sufficient buffered key material "
                    "for the requesting and serving peers."
                )
            quantum_link = matching_links[0]
            reserved_key_bits = quantum_link.reserve_key_bits(quantum_key_bits)
            selected_quantum_link = f"{quantum_link.peer_a}<->{quantum_link.peer_b}"

        return CooperativeBackhaulDecision(
            delivery=delivery,
            demand_forecast=demand_forecast,
            quantum_link=selected_quantum_link,
            reserved_key_bits=reserved_key_bits,
            classical_fragment_count=delivery.classical_fragment_count,
            classical_path_payload_mtu_bytes=delivery.classical_path_payload_mtu_bytes,
        )
