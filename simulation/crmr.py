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

"""Complex-Rotation Manifold Routing (CRMR), H15.

CRMR is the continuous counterpart of DDMR.  Instead of jumping from a 1-D
prefix metric to a 4-D defensive metric, the fabric carries a phasor

    psi(t) = R(t) * exp(i * theta(t)),    theta in [0, pi/2],

and rotates the metric continuously between the real (prefix) axis and the
imaginary (defence) axes.  The phase follows a damped second-order law driven
only by the local anomaly, so there is no clock, no attack flag and no discrete
threshold in the controller.

Two properties matter and are implemented literally:

* A rigid rotation of the point cloud would be an isometry and would leave every
  persistence diagram unchanged.  The rotation therefore acts on the *metric
  weights*: for a fixed theta the points are re-weighted,
  ``x' = [cos(theta) * prefix, R sin(theta) * (latency, jitter, anomaly)]``, and
  the Vietoris--Rips filtration is computed on the re-weighted cloud.  Each
  theta is an ordinary real filtration, so `ripser` is the only TDA dependency.
* The routing is phase-aligned rather than switched: a legitimate flow is sent
  to a healthy replica with probability ``sin^2(theta)``, so the migration is
  spread over the rotation instead of happening in a single tick.

This module is self-contained; the scenario in ``crmr_scenario.py`` runs it
against static T-NDN and discrete DDMR on the same requests.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np

from simulation import ddmr

#: Frozen phase constants (see docs/crmr-predictions.md).
PHASE_MAX = math.pi / 2.0
ANOMALY_LO = 0.20
ANOMALY_HI = 0.80
ZETA = 1.0
OMEGA = 3.0  # rad/s
RADIUS_GAIN = 1.0
GATE = math.pi / 4.0
CALM_EPS = 0.05

#: Manifold constants inherited from DDMR.
EPS_BASE = ddmr.EPS_MANIFOLD


def phase_target(anomaly: float) -> float:
    """Continuous target phase in ``[0, pi/2]``; no threshold on time."""
    fraction = (anomaly - ANOMALY_LO) / (ANOMALY_HI - ANOMALY_LO)
    return PHASE_MAX * min(1.0, max(0.0, fraction))


@dataclass
class PhaseController:
    """Damped rotation with saturated phase and a radius driven by the anomaly."""

    theta: float = 0.0
    theta_dot: float = 0.0
    radius: float = 1.0
    tv_theta: float = 0.0
    tv_fraction: float = 0.0
    peak_fraction_change: float = 0.0
    crossings: int = 0
    _last_fraction: float = 0.0
    _last_theta: float = 0.0
    _last_side: int = -1

    def fraction(self) -> float:
        """Phase-aligned share of legitimate traffic: sin^2(theta)."""
        return math.sin(self.theta) ** 2

    def update(self, anomaly: float, dt: float) -> None:
        target = phase_target(anomaly)
        acceleration = -2.0 * ZETA * OMEGA * self.theta_dot - OMEGA**2 * (
            self.theta - target
        )
        self.theta_dot += acceleration * dt
        self.theta += self.theta_dot * dt
        if self.theta <= 0.0:
            self.theta = 0.0
            self.theta_dot = max(0.0, self.theta_dot)
        elif self.theta >= PHASE_MAX:
            self.theta = PHASE_MAX
            self.theta_dot = min(0.0, self.theta_dot)
        self.radius = 1.0 + RADIUS_GAIN * min(1.0, max(0.0, anomaly))

        fraction = self.fraction()
        self.tv_theta += abs(self.theta - self._last_theta)
        self._last_theta = self.theta
        self.tv_fraction += abs(fraction - self._last_fraction)
        self.peak_fraction_change = max(
            self.peak_fraction_change, abs(fraction - self._last_fraction)
        )
        self._last_fraction = fraction

        side = 1 if self.theta >= GATE else 0
        if side != self._last_side:
            if self._last_side != -1:
                self.crossings += 1
            self._last_side = side


@dataclass(frozen=True)
class PhaseManifold:
    """Phase-weighted H0/H1 with the centroids used for routing."""

    theta: float
    radius: float
    eps: float
    b0: int
    b1: int
    centroids: np.ndarray  # re-weighted coordinates
    attack: tuple[bool, ...]
    blocks: tuple[int, ...]
    time_ms: float

    def transform(self, point: np.ndarray) -> np.ndarray:
        cosine = math.cos(self.theta)
        sine = self.radius * math.sin(self.theta)
        return np.array(
            [
                cosine * point[0],
                sine * point[1],
                sine * point[2],
                sine * point[3],
            ],
            dtype=np.float64,
        )

    def nearest(self, point: np.ndarray) -> int:
        coordinates = self.transform(point)
        distances = np.linalg.norm(self.centroids - coordinates, axis=1)
        return int(np.argmin(distances))

    def is_attack(self, point: np.ndarray) -> bool:
        return self.attack[self.nearest(point)]

    @property
    def attacked_blocks(self) -> frozenset[int]:
        return frozenset(
            block for block, flagged in zip(self.blocks, self.attack) if flagged
        )


def compute_phase_manifold(
    points: np.ndarray, theta: float, radius: float
) -> PhaseManifold:
    """Re-weight the cloud by the phase and run ripser on the real filtration."""
    if ddmr._ripser is None:  # pragma: no cover
        raise RuntimeError("ripser is required for CRMR")
    started = time.perf_counter()
    cosine = math.cos(theta)
    sine = radius * math.sin(theta)
    coordinates = np.column_stack(
        [
            cosine * points[:, 0],
            sine * points[:, 1],
            sine * points[:, 2],
            sine * points[:, 3],
        ]
    )
    eps = EPS_BASE * math.sqrt(cosine**2 + 3.0 * sine**2)

    result = ddmr._ripser(coordinates, maxdim=1, metric="euclidean")
    diagrams = result["dgms"]
    h0 = diagrams[0]
    b0 = int(np.sum(h0[:, 1] > eps))
    if diagrams[1].size:
        h1 = diagrams[1]
        b1 = int(np.sum((h1[:, 0] <= eps) & (h1[:, 1] > eps)))
    else:
        b1 = 0

    labels = ddmr._components(coordinates, eps)
    cluster_count = len(set(labels))
    centroids = []
    attack = []
    blocks = []
    for cluster in range(cluster_count):
        members = [index for index, label in enumerate(labels) if label == cluster]
        centroids.append(coordinates[members].mean(axis=0))
        original = points[members].mean(axis=0)
        attack.append(bool(original[3] > ddmr.ANOMALY_HIGH and original[2] > 0.20))
        blocks.append(int(round(original[0] / ddmr.PREFIX_SCALE * 19.0)))

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return PhaseManifold(
        theta=theta,
        radius=radius,
        eps=eps,
        b0=b0,
        b1=b1,
        centroids=np.array(centroids),
        attack=tuple(attack),
        blocks=tuple(blocks),
        time_ms=elapsed_ms,
    )


class CrmrRouter:
    """Phase-aligned routing: attack component primary, legitimate fraction healthy."""

    def choose(
        self,
        consumer: int,
        block: int,
        flow_point: np.ndarray,
        manifold: PhaseManifold | None,
        controller: PhaseController,
        instances: list[int],
        instance_latency_ms: dict[int, float],
        attacked_blocks: frozenset[int] | set[int] | None = None,
    ) -> int:
        primary = instances[0]
        if manifold is None or controller.theta <= CALM_EPS:
            return primary
        if manifold.is_attack(flow_point):
            return primary
        flagged = (
            manifold.attacked_blocks if attacked_blocks is None else attacked_blocks
        )
        if block not in flagged:
            return primary
        share = controller.fraction()
        if share <= 0.0:
            return primary
        # Deterministic per-flow draw, so the same flow keeps its choice while
        # the phase is stationary and migrates smoothly as the phase rotates.
        draw = (
            (consumer * 73_856_093) ^ (block * 19_349_663) ^ 0x9E37_79B9
        ) % 10_000 / 10_000.0
        if draw >= share:
            return primary
        candidates = instances[1:]
        if not candidates:
            return primary
        return min(
            candidates,
            key=lambda node: (instance_latency_ms.get(node, math.inf), node),
        )
