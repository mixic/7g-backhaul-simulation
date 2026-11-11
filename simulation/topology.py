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

"""Name-space topology and persistent homology for T-NDN (M10).

This module defines the 10 000-name space every strategy is evaluated on, a
metric on it, and the Vietoris--Rips filtration that supplies the two invariants
the T-NDN forwarding plan uses:

* ``H0`` — connected components at ``EPS_CLUSTER``.  Each component is a
  *persistent name cluster* and becomes one FIB entry.
* ``H1`` — loops alive at ``EPS_HOLE``.  The clusters on a loop form a cycle in
  the name complex; those clusters get a second, loop-free next hop, which is
  what permits local repair after a link failure instead of a global
  reconvergence.

Both invariants are computed from the name set and the name metric only.  No
physical topology, no link-state and no producer labels enter the computation,
so a router can compute them from the name advertisements it already receives.

Distance
--------

``d(a, b) = 0.4 * prefix(a, b) + 0.6 * topic(a, b)``

* ``prefix`` is the weighted mismatch of (service, region, type, object),
  normalised to ``[0, 1]``.
* ``topic`` is the chord distance of two names on a circle with
  ``PRODUCER_COUNT`` positions, normalised to ``[0, 1]``.  The circle is a
  *stipulated semantic relation*: neighbouring service/region blocks are
  semantically close although their prefixes differ.  Without it the metric is
  an ultrametric, so every Vietoris--Rips complex is a disjoint union of cliques
  and ``H1`` is identically zero.  That limitation is stated in the results
  document, not hidden.

Filtration radii were frozen before the experiment:

* ``EPS_CLUSTER = 0.15`` — above the within-block diameter (<= 0.10) and below
  the closest inter-block distance (>= 0.219).
* ``EPS_HOLE = 0.43`` — just above the widest adjacent-block edge (0.419) so
  that the circle closes, and below the shortest lived micro-loop (0.447) so
  that only the persistent loop is reported.
* ``EPS_DEATH = 0.60`` — computation horizon for triangle reduction.  It lets a
  loop that dies just after ``EPS_HOLE`` be recognised as dead; it is not a
  routing threshold.

The default landmark sample yields ``b0 = 20`` clusters and ``b1 = 1`` loop;
:func:`analyse` reports the actual values and the measured cost of each step.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Sequence

import numpy as np

SERVICE_COUNT = 5
REGION_COUNT = 4
TYPE_COUNT = 5
OBJECT_COUNT = 100
NAME_COUNT = SERVICE_COUNT * REGION_COUNT * TYPE_COUNT * OBJECT_COUNT
PRODUCER_COUNT = SERVICE_COUNT * REGION_COUNT  # one producer per (service, region)

PREFIX_WEIGHTS = (0.35, 0.25, 0.15, 0.05)
PREFIX_TOTAL = sum(PREFIX_WEIGHTS)
PREFIX_WEIGHT = 0.4
TOPIC_WEIGHT = 0.6

#: Frozen filtration radii (see module docstring).
EPS_CLUSTER = 0.15
EPS_HOLE = 0.43
EPS_DEATH = 0.60

#: Default number of landmarks.  Bounded so that the invariant computation a
#: node pays for is measurable; every other name is assigned to the nearest
#: landmark.
LANDMARK_COUNT = 64


@dataclass(frozen=True, order=True)
class Name:
    """One name in the four-level hierarchy."""

    service: int
    region: int
    type: int
    obj: int

    @property
    def producer(self) -> int:
        """Producer block index in ``[0, PRODUCER_COUNT)``."""
        return self.service * REGION_COUNT + self.region

    @property
    def components(self) -> tuple[int, int, int, int]:
        return (self.service, self.region, self.type, self.obj)


def name_id(service: int, region: int, type: int, obj: int) -> int:
    """Flat index of a name, in ``[0, NAME_COUNT)``."""
    return (
        ((service * REGION_COUNT + region) * TYPE_COUNT + type) * OBJECT_COUNT
        + obj
    )


def decode(index: int) -> Name:
    """Inverse of :func:`name_id`."""
    obj = index % OBJECT_COUNT
    rest = index // OBJECT_COUNT
    typ = rest % TYPE_COUNT
    rest //= TYPE_COUNT
    region = rest % REGION_COUNT
    service = rest // REGION_COUNT
    return Name(service, region, typ, obj)


def build_names() -> tuple[Name, ...]:
    return tuple(decode(index) for index in range(NAME_COUNT))


#: The one name space every strategy is evaluated on.
NAMES: tuple[Name, ...] = build_names()

_COMPONENTS = np.array([name.components for name in NAMES], dtype=np.int64)
_WEIGHTS = np.array(PREFIX_WEIGHTS, dtype=np.float64)


def topic_position(service: int, region: int) -> int:
    """Position of a name block on the semantic circle.

    Blocks follow a Hamiltonian cycle of the 5x4 service/region grid (a snake),
    so consecutive positions differ in exactly one component.  That keeps the
    adjacent-block distance in a narrow band, which is what allows a single
    ``EPS_HOLE`` to close the circle without closing the chords across it.
    """
    if service % 2 == 0:
        return service * REGION_COUNT + region
    return service * REGION_COUNT + (REGION_COUNT - 1 - region)


_TOPIC_POSITION = np.array(
    [topic_position(name.service, name.region) for name in NAMES], dtype=np.int64
)
_TOPIC_STEPS = np.array(
    [math.sin(math.pi * step / PRODUCER_COUNT) for step in range(PRODUCER_COUNT + 1)],
    dtype=np.float64,
)


def prefix_distance(index_a: int, index_b: int) -> float:
    """Weighted prefix mismatch in ``[0, 1]``."""
    mismatch = _WEIGHTS[(_COMPONENTS[index_a] != _COMPONENTS[index_b])].sum()
    return float(mismatch) / PREFIX_TOTAL


def topic_distance(index_a: int, index_b: int) -> float:
    """Chord distance on the semantic circle in ``[0, 1]``."""
    delta = abs(int(_TOPIC_POSITION[index_a]) - int(_TOPIC_POSITION[index_b]))
    steps = min(delta, PRODUCER_COUNT - delta)
    return float(_TOPIC_STEPS[steps])


def distance(index_a: int, index_b: int) -> float:
    """Metric used by the filtration: prefix plus stipulated semantic distance."""
    if index_a == index_b:
        return 0.0
    return (
        PREFIX_WEIGHT * prefix_distance(index_a, index_b)
        + TOPIC_WEIGHT * topic_distance(index_a, index_b)
    )


def _distance_vector(landmark: int) -> np.ndarray:
    """Distance from one landmark to every name, vectorised."""
    mismatch = (_COMPONENTS != _COMPONENTS[landmark]) @ _WEIGHTS
    delta = np.abs(_TOPIC_POSITION - _TOPIC_POSITION[landmark])
    steps = np.minimum(delta, PRODUCER_COUNT - delta)
    return (
        PREFIX_WEIGHT * (mismatch / PREFIX_TOTAL)
        + TOPIC_WEIGHT * _TOPIC_STEPS[steps]
    )


def distance_matrix(indices: Sequence[int]) -> list[list[float]]:
    """Symmetric pairwise distance matrix over the given name indices."""
    size = len(indices)
    matrix = [[0.0] * size for _ in range(size)]
    for i in range(size):
        left = indices[i]
        for j in range(i + 1, size):
            value = distance(left, indices[j])
            matrix[i][j] = value
            matrix[j][i] = value
    return matrix


def landmarks(count: int = LANDMARK_COUNT, start: int = 0) -> list[int]:
    """Farthest-point sampling of the namespace; deterministic for a start."""
    if not 0 < count <= NAME_COUNT:
        raise ValueError("landmark count must be in (0, NAME_COUNT]")
    chosen = [start]
    nearest = _distance_vector(start)
    while len(chosen) < count:
        index = int(np.argmax(nearest))
        if nearest[index] <= 0.0:
            break
        chosen.append(index)
        np.minimum(nearest, _distance_vector(index), out=nearest)
    return chosen


def nearest_landmark(index: int, landmark_indices: Sequence[int]) -> int:
    """Local index of the closest landmark (ties go to the earlier landmark)."""
    best = 0
    best_distance = math.inf
    for position, landmark in enumerate(landmark_indices):
        value = distance(index, landmark)
        if value < best_distance:
            best_distance = value
            best = position
    return best


@dataclass(frozen=True)
class Hole:
    """One ``H1`` feature of the name complex."""

    birth: float
    death: float | None  # None means the loop is still alive at EPS_DEATH
    clusters: tuple[int, ...]  # cluster ids on the cycle


@dataclass(frozen=True)
class Persistence:
    """Result of the Vietoris--Rips filtration."""

    eps0: float
    eps1: float
    eps_death: float
    clusters: tuple[tuple[int, ...], ...]  # landmark indices per H0 component
    h0_intervals: tuple[tuple[float, float], ...]
    holes: tuple[Hole, ...]
    h1_alive: int

    @property
    def b0(self) -> int:
        return len(self.clusters)

    @property
    def b1(self) -> int:
        return self.h1_alive


def _canonical_cycle(
    start: int,
    end: int,
    tree: Sequence[Sequence[int]],
    cluster_of: Sequence[int],
) -> tuple[int, ...]:
    """Clusters on the tree path between two vertices, in order."""
    parent = {start: -1}
    queue = [start]
    for vertex in queue:
        if vertex == end:
            break
        for neighbour in tree[vertex]:
            if neighbour not in parent:
                parent[neighbour] = vertex
                queue.append(neighbour)
    if end not in parent:
        return ()
    path = []
    node = end
    while node != -1:
        path.append(node)
        node = parent[node]
    path.reverse()
    clusters = []
    for vertex in path:
        label = cluster_of[vertex]
        if not clusters or clusters[-1] != label:
            clusters.append(label)
    return tuple(clusters)


def persistence(
    points: Sequence[int],
    eps0: float = EPS_CLUSTER,
    eps1: float = EPS_HOLE,
    eps_death: float = EPS_DEATH,
) -> Persistence:
    """Vietoris--Rips persistence of the point sample.

    ``H0`` is computed by union-find; ``H1`` by a Z2 boundary-matrix reduction
    over the triangles with filtration value ``<= eps_death``.  An edge that
    merges two components is an ``H0`` death; an edge that closes a cycle is an
    ``H1`` birth and is paired with the triangle that kills it, if any.  A
    feature is *alive at* ``eps1`` when it is born at or below ``eps1`` and dies
    after it (or never within ``eps_death``).
    """
    size = len(points)
    if size < 2:
        raise ValueError("persistence needs at least two points")
    matrix = distance_matrix(points)

    edges: list[tuple[float, int, int]] = []
    for i in range(size):
        for j in range(i + 1, size):
            weight = matrix[i][j]
            if weight <= eps_death:
                edges.append((weight, i, j))
    edges.sort()

    # --- H0 at eps0 ---------------------------------------------------------
    def make_find() -> tuple[list[int], list[int]]:
        return list(range(size)), [0] * size

    def find_with(parent: list[int], node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union_with(
        parent: list[int], rank: list[int], left: int, right: int
    ) -> bool:
        root_left, root_right = find_with(parent, left), find_with(parent, right)
        if root_left == root_right:
            return False
        if rank[root_left] < rank[root_right]:
            root_left, root_right = root_right, root_left
        parent[root_right] = root_left
        if rank[root_left] == rank[root_right]:
            rank[root_left] += 1
        return True

    parent_at_eps0, rank_at_eps0 = make_find()
    for weight, i, j in edges:
        if weight > eps0:
            break
        union_with(parent_at_eps0, rank_at_eps0, i, j)
    at_eps0 = [find_with(parent_at_eps0, node) for node in range(size)]

    # --- merging tree, H0 intervals, and the positive edges ----------------
    parent, rank = make_find()
    h0_intervals: list[tuple[float, float]] = []
    tree: list[list[int]] = [[] for _ in range(size)]
    cycle_edges: set[int] = set()
    for position, (weight, i, j) in enumerate(edges):
        if union_with(parent, rank, i, j):
            h0_intervals.append((0.0, weight))
            tree[i].append(j)
            tree[j].append(i)
        else:
            cycle_edges.add(position)

    components: dict[int, list[int]] = {}
    for vertex in range(size):
        components.setdefault(at_eps0[vertex], []).append(vertex)
    clusters = tuple(tuple(members) for members in components.values())

    # --- H1: boundary reduction over triangles ------------------------------
    edge_index: dict[tuple[int, int], int] = {}
    for position, (_, i, j) in enumerate(edges):
        edge_index[(i, j)] = position

    triangles: list[tuple[float, int, int, int]] = []
    for i in range(size):
        for j in range(i + 1, size):
            weight_ij = matrix[i][j]
            if weight_ij > eps_death:
                continue
            for k in range(j + 1, size):
                weight = max(weight_ij, matrix[i][k], matrix[j][k])
                if weight <= eps_death:
                    triangles.append((weight, i, j, k))
    triangles.sort()

    paired: dict[int, float] = {}  # birth edge -> death weight
    low_to_column: dict[int, int] = {}
    for weight, i, j, k in triangles:
        column = (
            (1 << edge_index[(i, j)])
            ^ (1 << edge_index[(i, k)])
            ^ (1 << edge_index[(j, k)])
        )
        while column:
            low = column.bit_length() - 1
            if low in low_to_column:
                column ^= low_to_column[low]
                continue
            low_to_column[low] = column
            if low in cycle_edges:
                paired[low] = weight
            break

    cluster_of = [0] * size
    for label, members in enumerate(clusters):
        for vertex in members:
            cluster_of[vertex] = label

    holes: list[Hole] = []
    h1_alive = 0
    for birth_edge in sorted(cycle_edges):
        weight, i, j = edges[birth_edge]
        death = paired.get(birth_edge)
        if weight <= eps1 and (death is None or death > eps1):
            h1_alive += 1
        holes.append(
            Hole(
                birth=weight,
                death=death,
                clusters=_canonical_cycle(i, j, tree, cluster_of),
            )
        )

    return Persistence(
        eps0=eps0,
        eps1=eps1,
        eps_death=eps_death,
        clusters=clusters,
        h0_intervals=tuple(h0_intervals),
        holes=tuple(holes),
        h1_alive=h1_alive,
    )


@dataclass(frozen=True)
class Analysis:
    """Persistent homology plus the derived routing structures and its cost."""

    landmark_indices: tuple[int, ...]
    persistence: Persistence
    cluster_of_name: tuple[int, ...]
    cluster_producers: tuple[tuple[int, ...], ...]
    hole_clusters: frozenset[int]
    landmarks_ms: float
    persistence_ms: float
    assign_ms: float

    @property
    def clusters(self) -> int:
        return self.persistence.b0

    @property
    def holes(self) -> int:
        return self.persistence.b1

    @property
    def time_ms(self) -> float:
        return self.landmarks_ms + self.persistence_ms + self.assign_ms


def analyse(
    landmark_count: int = LANDMARK_COUNT,
    eps0: float = EPS_CLUSTER,
    eps1: float = EPS_HOLE,
) -> Analysis:
    """Select landmarks, compute persistence, assign names, and time each step."""
    started = time.perf_counter()
    landmark_indices = landmarks(landmark_count)
    landmarks_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    result = persistence(landmark_indices, eps0, eps1)
    persistence_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    cluster_of_landmark = [0] * len(landmark_indices)
    for label, members in enumerate(result.clusters):
        for vertex in members:
            cluster_of_landmark[vertex] = label

    # Nearest landmark for every name: (landmarks x names) matrix, then argmin.
    distances = np.empty((len(landmark_indices), NAME_COUNT), dtype=np.float64)
    for position, landmark in enumerate(landmark_indices):
        distances[position] = _distance_vector(landmark)
    nearest = distances.argmin(axis=0)
    cluster_of_name = tuple(
        cluster_of_landmark[int(nearest[index])] for index in range(NAME_COUNT)
    )

    producers: list[set[int]] = [set() for _ in result.clusters]
    for index, cluster in enumerate(cluster_of_name):
        producers[cluster].add(NAMES[index].producer)

    hole_clusters: set[int] = set()
    for hole in result.holes:
        if hole.birth <= eps1 and (hole.death is None or hole.death > eps1):
            hole_clusters.update(hole.clusters)
    assign_ms = (time.perf_counter() - started) * 1000.0

    return Analysis(
        landmark_indices=tuple(landmark_indices),
        persistence=result,
        cluster_of_name=cluster_of_name,
        cluster_producers=tuple(tuple(sorted(item)) for item in producers),
        hole_clusters=frozenset(hole_clusters),
        landmarks_ms=landmarks_ms,
        persistence_ms=persistence_ms,
        assign_ms=assign_ms,
    )


def cluster_summary(analysis: Analysis) -> dict[str, object]:
    """Compact, JSON-friendly summary used by the benchmark and the docs."""
    return {
        "clusters": analysis.clusters,
        "holes": analysis.holes,
        "landmarks": len(analysis.landmark_indices),
        "eps_cluster": analysis.persistence.eps0,
        "eps_hole": analysis.persistence.eps1,
        "hole_clusters": len(analysis.hole_clusters),
        "tda_ms": round(analysis.time_ms, 3),
        "tda_core_ms": round(analysis.persistence_ms, 3),
        "landmark_ms": round(analysis.landmarks_ms, 3),
        "assign_ms": round(analysis.assign_ms, 3),
    }
