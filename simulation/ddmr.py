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

"""Dynamic Dimensionality Manifold Routing (DDMR), M11.

The state vector is

    S(t) = [D_prefix, L_latency, J_jitter, A_anomaly]

with one dimension per axis.  In calm conditions only ``D_prefix`` is used and
the complex is one-dimensional.  When the *local* rate anomaly of a flow crosses
``ANOMALY_HIGH`` for ``UP_TICKS`` consecutive telemetry ticks, the filtration
expands to all four axes; it contracts again only after the anomaly stays below
``ANOMALY_LOW`` for ``DOWN_TICKS`` ticks.  The thresholds are on the anomaly, not
on the clock: there is no ``if t == 30`` anywhere in this module, and the
scenario never tells the router that an attack is running.

Persistent homology is computed with the `ripser` library on a Vietoris--Rips
filtration of the observed flow points.  ``H0`` is read at ``EPS_MANIFOLD``: the
number of components, and their centroids, are what the router uses.  Under the
shock the attack flows leave the legitimate component, the complex gains a new
component, and the router keeps traffic whose nearest centroid is the attack
component on the default instance while sending the legitimate component to a
healthy replica.  ``H1`` is reported as measured; in this scenario it stays
zero, and the results document says so rather than describing a component split
as a loop.

The anomaly is the M5/M6 kinematic form: a short-window request rate is compared
with the flow's nominal rate, so a flow that starts sending tens of requests per
second (a bot) is anomalous while a legitimate flow at one request per second
is not.  ``A`` is the clipped normalised excess.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np

try:  # pragma: no cover - exercised by the import guard test
    from ripser import ripser as _ripser
except ImportError:  # pragma: no cover
    _ripser = None

#: State-vector dimensions.
DIMENSION_CALM = 1
DIMENSION_SHOCK = 4

#: Frozen thresholds.
EPS_MANIFOLD = 0.25
ANOMALY_HIGH = 0.70
ANOMALY_LOW = 0.45
UP_TICKS = 2
DOWN_TICKS = 4

#: Flow telemetry.
FLOW_WINDOW_S = 2.0
FLOW_LEGIT_RATE = 2.0  # requests/s above which a flow is anomalous
JITTER_SCALE_MS = 50.0
LATENCY_SCALE_MS = 100.0
PREFIX_SCALE = 0.1
ANOMALY_SMOOTHING = 0.5  # EMA time constant for jitter/latency, seconds

#: Manifold epochs.
MANIFOLD_PERIOD_S = 2.0
MAX_MANIFOLD_POINTS = 150


def ripser_available() -> bool:
    return _ripser is not None


@dataclass
class FlowState:
    """Per-(consumer, prefix block) telemetry and its point in the manifold."""

    consumer: int
    block: int
    baseline_latency_ms: float
    timestamps: deque[float] = field(default_factory=deque)
    jitter_ms: float = 0.0
    latency_ms: float = 0.0
    last_seen_s: float = 0.0
    last_jitter_s: float = 0.0
    last_latency_s: float = 0.0

    def observe(self, time_s: float, jitter_ms: float) -> None:
        self.timestamps.append(time_s)
        self.last_seen_s = time_s
        while self.timestamps and time_s - self.timestamps[0] > FLOW_WINDOW_S:
            self.timestamps.popleft()
        elapsed = time_s - self.last_jitter_s
        alpha = (
            1.0
            if elapsed <= 1e-9
            else 1.0 - math.exp(-elapsed / ANOMALY_SMOOTHING)
        )
        if self.jitter_ms == 0.0:
            self.jitter_ms = jitter_ms
        else:
            self.jitter_ms += alpha * (jitter_ms - self.jitter_ms)
        self.last_jitter_s = time_s

    def add_latency(self, time_s: float, latency_ms: float) -> None:
        elapsed = time_s - self.last_latency_s
        alpha = (
            1.0
            if elapsed <= 1e-9
            else 1.0 - math.exp(-elapsed / ANOMALY_SMOOTHING)
        )
        if self.latency_ms == 0.0:
            self.latency_ms = latency_ms
        else:
            self.latency_ms += alpha * (latency_ms - self.latency_ms)
        self.last_latency_s = time_s

    @property
    def rate(self) -> float:
        return len(self.timestamps) / FLOW_WINDOW_S if self.timestamps else 0.0

    @property
    def anomaly(self) -> float:
        excess = (self.rate - FLOW_LEGIT_RATE) / FLOW_LEGIT_RATE
        return float(min(1.0, max(0.0, excess)))

    @property
    def prefix_coordinate(self) -> float:
        return PREFIX_SCALE * self.block / 19.0

    def point(self) -> np.ndarray:
        latency_deviation = max(
            0.0, self.latency_ms - self.baseline_latency_ms
        ) / LATENCY_SCALE_MS
        return np.array(
            [
                self.prefix_coordinate,
                min(1.0, latency_deviation),
                min(1.0, self.jitter_ms / JITTER_SCALE_MS),
                self.anomaly,
            ],
            dtype=np.float64,
        )


class AnomalyMonitor:
    """Local kinematic anomaly: the maximum flow-rate anomaly in a prefix block."""

    def __init__(self) -> None:
        self.flows: dict[tuple[int, int], FlowState] = {}

    def flow(self, consumer: int, block: int, baseline_latency_ms: float) -> FlowState:
        key = (consumer, block)
        state = self.flows.get(key)
        if state is None:
            state = FlowState(consumer, block, baseline_latency_ms)
            self.flows[key] = state
        return state

    def block_anomaly(self, block: int) -> float:
        values = [
            state.anomaly
            for state in self.flows.values()
            if state.block == block and state.timestamps
        ]
        return max(values) if values else 0.0

    def global_anomaly(self) -> float:
        values = [state.anomaly for state in self.flows.values() if state.timestamps]
        return max(values) if values else 0.0

    def active_points(self, time_s: float, limit: int = MAX_MANIFOLD_POINTS) -> np.ndarray:
        active = [
            state
            for state in self.flows.values()
            if state.timestamps and time_s - state.last_seen_s <= FLOW_WINDOW_S
        ]
        active.sort(key=lambda state: (state.rate, state.block, state.consumer), reverse=True)
        return np.vstack([state.point() for state in active[:limit]]) if active else np.empty((0, 4))


class BlockMonitor:
    """Block-level level anomaly with a frozen nominal baseline.

    The M5/M6 kinematic trigger is a *spike* detector: it fires on the change
    and then the adaptive baseline absorbs the new level.  A 15 s DDoS would
    therefore make the dimension collapse mid-attack.  To keep the dimension
    tied to the level of the attack, this monitor measures the nominal rate per
    prefix block during a 10 s warm-up and freezes it; the anomaly is a
    z-score over Poisson noise, mapped to ``[0, 1]`` by ``(z - 3) / 3``.  The
    warm-up is stated in the results as the reason the collapse happens *after*
    the attack ends rather than in the middle of it.
    """

    def __init__(self, warmup_s: float = 10.0, window_s: float = 5.0) -> None:
        self.warmup_s = warmup_s
        self.window_s = window_s
        self._timestamps: dict[int, deque[float]] = {}
        self._warmup_count: dict[int, int] = {}
        self._baseline: dict[int, float] = {}

    def observe(self, block: int, time_s: float) -> None:
        times = self._timestamps.setdefault(block, deque())
        times.append(time_s)
        while times and time_s - times[0] > self.window_s:
            times.popleft()
        if time_s < self.warmup_s:
            self._warmup_count[block] = self._warmup_count.get(block, 0) + 1
        elif block not in self._baseline:
            self._baseline[block] = self._warmup_count.get(block, 0) / self.warmup_s

    def rate(self, block: int) -> float:
        times = self._timestamps.get(block)
        return len(times) / self.window_s if times else 0.0

    def anomaly(self, block: int, time_s: float) -> float:
        if time_s < self.warmup_s or block not in self._baseline:
            return 0.0
        baseline = max(0.5, self._baseline[block])
        sigma = math.sqrt(baseline / self.window_s)
        z_score = (self.rate(block) - baseline) / sigma
        return float(min(1.0, max(0.0, (z_score - 3.0) / 3.0)))

    def global_anomaly(self, time_s: float) -> float:
        return max(
            (self.anomaly(block, time_s) for block in self._timestamps),
            default=0.0,
        )


class DimensionController:
    """Hysteretic expansion/contraction driven only by the anomaly score."""

    def __init__(
        self,
        high: float = ANOMALY_HIGH,
        low: float = ANOMALY_LOW,
        up_ticks: int = UP_TICKS,
        down_ticks: int = DOWN_TICKS,
    ) -> None:
        self.high = high
        self.low = low
        self.up_ticks = up_ticks
        self.down_ticks = down_ticks
        self.dimension = DIMENSION_CALM
        self._up = 0
        self._down = 0
        self.expansions = 0
        self.collapses = 0
        self.last_switch_s = 0.0

    def update(self, anomaly: float, time_s: float) -> tuple[int, bool]:
        switched = False
        if self.dimension == DIMENSION_CALM:
            if anomaly > self.high:
                self._up += 1
                if self._up >= self.up_ticks:
                    self.dimension = DIMENSION_SHOCK
                    self.expansions += 1
                    self._up = 0
                    self.last_switch_s = time_s
                    switched = True
            else:
                self._up = 0
        else:
            if anomaly < self.low:
                self._down += 1
                if self._down >= self.down_ticks:
                    self.dimension = DIMENSION_CALM
                    self.collapses += 1
                    self._down = 0
                    self.last_switch_s = time_s
                    switched = True
            else:
                self._down = 0
        return self.dimension, switched


@dataclass(frozen=True)
class Manifold:
    """H0/H1 of one epoch plus the centroids the router uses."""

    dimension: int
    b0: int
    b1: int
    centroids: np.ndarray
    attack: tuple[bool, ...]
    blocks: tuple[int, ...]
    points: np.ndarray
    time_ms: float

    def nearest(self, point: np.ndarray) -> int:
        coordinates = point[: self.centroids.shape[1]]
        distances = np.linalg.norm(self.centroids - coordinates, axis=1)
        return int(np.argmin(distances))

    @property
    def attacked_blocks(self) -> frozenset[int]:
        return frozenset(
            block for block, flagged in zip(self.blocks, self.attack) if flagged
        )


def _components(points: np.ndarray, eps: float) -> list[int]:
    """Connected components of the eps graph (union-find)."""
    size = len(points)
    parent = list(range(size))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for i in range(size):
        for j in range(i + 1, size):
            if float(np.linalg.norm(points[i] - points[j])) <= eps:
                root_i, root_j = find(i), find(j)
                if root_i != root_j:
                    parent[root_j] = root_i
    labels = {}
    result = []
    for node in range(size):
        root = find(node)
        if root not in labels:
            labels[root] = len(labels)
        result.append(labels[root])
    return result


def compute_manifold(points: np.ndarray, dimension: int) -> Manifold:
    """Run ripser and derive the centroids used for routing."""
    if _ripser is None:  # pragma: no cover
        raise RuntimeError("ripser is required for DDMR (pip install ripser)")
    started = time.perf_counter()
    coordinates = points[:, :1] if dimension == DIMENSION_CALM else points
    result = _ripser(coordinates, maxdim=1, metric="euclidean")
    diagrams = result["dgms"]

    h0 = diagrams[0]
    b0 = int(np.sum(h0[:, 1] > EPS_MANIFOLD))
    if diagrams[1].size:
        h1 = diagrams[1]
        b1 = int(np.sum((h1[:, 0] <= EPS_MANIFOLD) & (h1[:, 1] > EPS_MANIFOLD)))
    else:
        b1 = 0

    labels = _components(coordinates, EPS_MANIFOLD)
    cluster_count = len(set(labels))
    centroid_rows = []
    attack = []
    blocks = []
    for cluster in range(cluster_count):
        members = [index for index, label in enumerate(labels) if label == cluster]
        centroid = coordinates[members].mean(axis=0)
        centroid_rows.append(centroid)
        full = points[members].mean(axis=0)
        attack.append(
            bool(
                dimension == DIMENSION_SHOCK
                and full[3] > ANOMALY_HIGH
                and full[2] > 0.20
            )
        )
        blocks.append(int(round(full[0] / PREFIX_SCALE * 19.0)))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return Manifold(
        dimension=dimension,
        b0=b0,
        b1=b1,
        centroids=np.array(centroid_rows),
        attack=tuple(attack),
        blocks=tuple(blocks),
        points=points,
        time_ms=elapsed_ms,
    )


class DdmrRouter:
    """Dimension-aware instance selection for one prefix block."""

    def choose(
        self,
        flow: FlowState,
        manifold: Manifold | None,
        dimension: int,
        instances: list[int],
        instance_latency_ms: dict[int, float],
    ) -> int:
        primary = instances[0]
        if (
            dimension == DIMENSION_CALM
            or manifold is None
            or flow.block not in manifold.attacked_blocks
        ):
            return primary
        point = flow.point()
        nearest = manifold.nearest(point)
        if manifold.attack[nearest]:
            # The flow belongs to the attack component: keep it on the default
            # instance so it cannot displace legitimate traffic.
            return primary
        candidates = instances[1:]
        if not candidates:
            return primary
        return min(
            candidates,
            key=lambda node: (instance_latency_ms.get(node, math.inf), node),
        )


class StaticTndnRouter:
    """Same anomaly detection, fixed 1-D manifold: always the default instance."""

    def choose(
        self,
        flow: FlowState,
        manifold: Manifold | None,
        dimension: int,
        instances: list[int],
        instance_latency_ms: dict[int, float],
    ) -> int:
        return instances[0]
