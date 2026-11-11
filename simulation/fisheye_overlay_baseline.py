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

"""Fisheye-overlay baseline after Milic and Braun (IEEE LCN 2009).

The original mechanism builds an overlay view from *measured RTT distances
only* — no embedding, no link-state — and keeps a continuously refined
"fisheye" view: nearby peers are re-measured often, distant peers rarely, and
peer selection balances RTT proximity against geographic diversity.  This
baseline asks whether RTT-based topology awareness alone is enough, or whether
the name-space invariants add something.

Implementation: each node selects ``PEERS`` peers, eight by lowest RTT and four
by greedy max-min diversity.  Each node also keeps ``BUCKETS`` name-bucket
entries; a bucket's home is a node chosen by hashing the bucket, and the entry
points at the peer with the lowest RTT to that home.  A request goes
consumer -> selected peer -> producer, so the overlay pays one extra leg.  A
failed link is noticed when the next RTT probe round completes, which is what
sets its reconvergence time.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from simulation.ndn_network import PhysicalNetwork
from simulation.topology import NAME_COUNT

#: Stipulated overlay constants.
PEERS = 12
NEAR_PEERS = 8
BUCKETS = 128
PROBE_INTERVAL_S = 2.0


@dataclass(frozen=True)
class FisheyePlan:
    peers: tuple[tuple[int, ...], ...]
    bucket_peer: tuple[tuple[int, ...], ...]

    @property
    def fib_entries(self) -> tuple[int, ...]:
        return tuple(
            len(self.peers[node]) + len(self.bucket_peer[node])
            for node in range(len(self.peers))
        )

    def fib_mean(self) -> float:
        entries = self.fib_entries
        return sum(entries) / len(entries)

    def peer_for_bucket(self, consumer: int, name: int) -> int:
        return self.bucket_peer[consumer][name % BUCKETS]

    def recovery_s(self, rng: random.Random) -> float:
        """One probe round plus the time to re-map the affected buckets."""
        return PROBE_INTERVAL_S + rng.random()


def build(network: PhysicalNetwork, seed: int = 2026) -> FisheyePlan:
    count = network.node_count
    # Measured RTT, in ms: round trip over the shortest path.
    rtt = [
        [2.0 * network.distance_ms[a][b] for b in range(count)]
        for a in range(count)
    ]

    peers: list[tuple[int, ...]] = []
    for node in range(count):
        ranked = sorted(
            (other for other in range(count) if other != node),
            key=lambda other: (rtt[node][other], other),
        )
        selected = ranked[:NEAR_PEERS]
        # Greedy max-min diversity: add the node farthest from the current set.
        while len(selected) < PEERS:
            best = None
            best_score = -1.0
            for other in range(count):
                if other == node or other in selected:
                    continue
                score = min(rtt[other][member] for member in selected)
                if score > best_score:
                    best_score = score
                    best = other
            assert best is not None
            selected.append(best)
        peers.append(tuple(sorted(selected)))

    bucket_peer: list[tuple[int, ...]] = []
    for node in range(count):
        mapping = []
        for bucket in range(BUCKETS):
            home = bucket % count
            owner = min(peers[node], key=lambda peer: (rtt[peer][home], peer))
            mapping.append(owner)
        bucket_peer.append(tuple(mapping))

    return FisheyePlan(
        peers=tuple(peers),
        bucket_peer=tuple(bucket_peer),
    )


def fib_mean(plan: FisheyePlan) -> float:
    return plan.fib_mean()


def names_per_bucket() -> float:
    return NAME_COUNT / BUCKETS
