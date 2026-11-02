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

import hashlib
import heapq
import hmac
from collections import deque
from dataclasses import dataclass, field
from math import ceil, exp, isfinite
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from .cdn import EdgeCache
from .trends import SecondOrderTrendEstimator, TrendEstimate


@dataclass
class MeshPeer:
    """A mesh participant with an independent cache and forwarding policy."""

    name: str
    cache_capacity_bytes: int
    can_serve: bool = True
    can_forward: bool = True
    cache: EdgeCache = field(init=False)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Peer name must not be empty.")
        if (
            not isinstance(self.cache_capacity_bytes, int)
            or isinstance(self.cache_capacity_bytes, bool)
            or self.cache_capacity_bytes < 0
        ):
            raise ValueError("Peer cache capacity must be a non-negative integer.")
        self.cache = EdgeCache(self.name, self.cache_capacity_bytes)


@dataclass
class MeshLink:
    """An undirected peer link with sampled telemetry and forecast hysteresis."""

    peer_a: str
    peer_b: str
    capacity_mbps: float
    base_latency_ms: float
    congestion_threshold: float = 0.7
    congestion_hysteresis: float = 0.1
    utilization: float = 0.0
    queue_delay_ms: float = 0.0
    loss_rate: float = 0.0
    congestion_active: bool = False
    classical_mtu_bytes: int = 1500
    encapsulation_overhead_bytes: int = 0
    cost_per_gb: float = 0.0
    available: bool = True
    _pressure_samples: Deque[float] = field(
        default_factory=lambda: deque([0.0, 0.0, 0.0], maxlen=3),
        init=False,
        repr=False,
    )
    _clear_observation_count: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.peer_a or not self.peer_b or self.peer_a == self.peer_b:
            raise ValueError("A mesh link must connect two distinct named peers.")
        if not isfinite(self.capacity_mbps) or self.capacity_mbps <= 0:
            raise ValueError("Link capacity must be positive and finite.")
        if not isfinite(self.base_latency_ms) or self.base_latency_ms < 0:
            raise ValueError("Base latency must be non-negative and finite.")
        if (
            not isinstance(self.classical_mtu_bytes, int)
            or isinstance(self.classical_mtu_bytes, bool)
            or self.classical_mtu_bytes <= 0
        ):
            raise ValueError("Classical MTU must be a positive integer number of bytes.")
        if (
            not isinstance(self.encapsulation_overhead_bytes, int)
            or isinstance(self.encapsulation_overhead_bytes, bool)
            or not 0 <= self.encapsulation_overhead_bytes < self.classical_mtu_bytes
        ):
            raise ValueError("Encapsulation overhead must be non-negative and smaller than the MTU.")
        if not isfinite(self.cost_per_gb) or self.cost_per_gb < 0:
            raise ValueError("Link cost per GB must be non-negative and finite.")
        if (
            not isfinite(self.congestion_threshold)
            or not 0 < self.congestion_threshold <= 1
        ):
            raise ValueError("Congestion threshold must be in (0, 1].")
        if (
            not isfinite(self.congestion_hysteresis)
            or not 0 <= self.congestion_hysteresis < self.congestion_threshold
        ):
            raise ValueError("Congestion hysteresis must be in [0, threshold).")
        self._validate_measurement(self.utilization, "Utilization", 0.0, 1.0)
        self._validate_measurement(self.queue_delay_ms, "Queue delay", 0.0, None)
        self._validate_measurement(self.loss_rate, "Loss rate", 0.0, 1.0)
        self._pressure_samples = deque(
            [self.current_pressure] * 3,
            maxlen=3,
        )
        self.congestion_active = self.current_pressure >= self.congestion_threshold

    @property
    def max_classical_payload_bytes(self) -> int:
        return self.classical_mtu_bytes - self.encapsulation_overhead_bytes

    @staticmethod
    def _validate_measurement(
        value: float,
        label: str,
        minimum: float,
        maximum: Optional[float],
    ) -> None:
        if not isfinite(value) or value < minimum or (maximum is not None and value > maximum):
            upper_bound = f" and at most {maximum}" if maximum is not None else ""
            raise ValueError(f"{label} must be at least {minimum}{upper_bound}.")

    @property
    def current_pressure(self) -> float:
        queue_pressure = self.queue_delay_ms / (
            self.base_latency_ms + self.queue_delay_ms + 1.0
        )
        return min(
            1.0,
            0.7 * self.utilization + 0.2 * queue_pressure + 0.1 * self.loss_rate,
        )

    @property
    def observed_latency_ms(self) -> float:
        return self.base_latency_ms + self.queue_delay_ms

    def record_telemetry(
        self,
        utilization: float,
        queue_delay_ms: float,
        loss_rate: float,
    ) -> None:
        self._validate_measurement(utilization, "Utilization", 0.0, 1.0)
        self._validate_measurement(queue_delay_ms, "Queue delay", 0.0, None)
        self._validate_measurement(loss_rate, "Loss rate", 0.0, 1.0)
        self.utilization = utilization
        self.queue_delay_ms = queue_delay_ms
        self.loss_rate = loss_rate
        self._pressure_samples.append(self.current_pressure)

        forecast = self.predicted_pressure()
        if forecast >= self.congestion_threshold:
            self.congestion_active = True
            self._clear_observation_count = 0
        elif self.congestion_active:
            clear_threshold = self.congestion_threshold - self.congestion_hysteresis
            if self.current_pressure < clear_threshold:
                self._clear_observation_count += 1
                if self._clear_observation_count >= 2:
                    self.congestion_active = False
                    self._clear_observation_count = 0
            else:
                self._clear_observation_count = 0

    def predicted_pressure(self, horizon_samples: float = 1.0) -> float:
        if not isfinite(horizon_samples) or horizon_samples < 0:
            raise ValueError("Forecast horizon must be non-negative and finite.")
        return min(1.0, max(0.0, self.pressure_trend(horizon_samples).forecast))

    def pressure_trend(self, horizon_samples: float = 1.0) -> TrendEstimate:
        if not isfinite(horizon_samples) or horizon_samples < 0:
            raise ValueError("Forecast horizon must be non-negative and finite.")
        older, previous, current = self._pressure_samples
        return SecondOrderTrendEstimator.estimate(
            current,
            previous,
            older,
            sample_interval=1.0,
            horizon=horizon_samples,
        )

    def telemetry_snapshot(self) -> MeshLinkTelemetry:
        trend = self.pressure_trend()
        return MeshLinkTelemetry(
            peer_a=self.peer_a,
            peer_b=self.peer_b,
            capacity_mbps=self.capacity_mbps,
            utilization=self.utilization,
            latency_ms=self.observed_latency_ms,
            queue_delay_ms=self.queue_delay_ms,
            loss_rate=self.loss_rate,
            current_pressure=self.current_pressure,
            predicted_pressure=min(1.0, max(0.0, trend.forecast)),
            congestion_active=self.congestion_active,
            cost_per_gb=self.cost_per_gb,
            available=self.available,
            pressure_velocity=trend.velocity,
            pressure_acceleration=trend.acceleration,
        )


@dataclass(frozen=True)
class MeshLinkTelemetry:
    peer_a: str
    peer_b: str
    capacity_mbps: float
    utilization: float
    latency_ms: float
    queue_delay_ms: float
    loss_rate: float
    current_pressure: float
    predicted_pressure: float
    congestion_active: bool
    cost_per_gb: float
    available: bool
    pressure_velocity: float
    pressure_acceleration: float


@dataclass(frozen=True)
class MeshRequestResult:
    requesting_peer: str
    serving_peer: str
    content_id: str
    payload: bytes
    path: Tuple[str, ...]
    cache_hit: bool
    congestion_detected: bool
    route_avoided_congestion: bool
    cache_action: str
    cache_admission_score: Optional[float] = None
    security_events: Tuple[str, ...] = ()
    classical_path_payload_mtu_bytes: Optional[int] = None
    classical_fragment_count: int = 0
    cache_trigger: Optional[str] = None
    active_active_paths: Tuple[MeshPathAllocation, ...] = ()


@dataclass(frozen=True)
class MeshPathAllocation:
    path: Tuple[str, ...]
    allocated_bytes: int
    traffic_share: float
    capacity_mbps: float
    predicted_pressure: float
    pressure_velocity: float
    pressure_acceleration: float
    estimated_cost_per_gb: float


@dataclass(frozen=True)
class ContentManifest:
    content_id: str
    publisher_id: str
    sha256_digest: str


@dataclass(frozen=True)
class CacheAdmissionDecision:
    admitted: bool
    anomaly_score: float
    observations: int


class NPUInspiredCacheGuard:
    """Score novelty, reuse, and cache footprint with a small edge admission model."""

    def __init__(
        self,
        minimum_reuse_observations: int = 3,
        anomaly_threshold: float = 0.3,
    ) -> None:
        if (
            not isinstance(minimum_reuse_observations, int)
            or isinstance(minimum_reuse_observations, bool)
            or minimum_reuse_observations < 2
        ):
            raise ValueError("Minimum reuse observations must be an integer of at least two.")
        if not isfinite(anomaly_threshold) or not 0 <= anomaly_threshold <= 1:
            raise ValueError("Anomaly threshold must be between zero and one.")
        self.minimum_reuse_observations = minimum_reuse_observations
        self.anomaly_threshold = anomaly_threshold
        self._observations: Dict[Tuple[str, str], int] = {}

    def evaluate(
        self,
        peer_name: str,
        content_id: str,
        payload_bytes: int,
        cache_capacity_bytes: int,
    ) -> CacheAdmissionDecision:
        key = (peer_name, content_id)
        observations = self._observations.get(key, 0) + 1
        self._observations[key] = observations
        novelty = 1.0 / observations
        reuse_deficit = max(
            0.0,
            1.0 - observations / self.minimum_reuse_observations,
        )
        cache_footprint = (
            min(1.0, payload_bytes / cache_capacity_bytes)
            if cache_capacity_bytes
            else 1.0
        )
        anomaly_score = (
            0.55 * novelty
            + 0.35 * reuse_deficit
            + 0.10 * cache_footprint
        )
        admitted = (
            observations >= self.minimum_reuse_observations
            and anomaly_score <= self.anomaly_threshold
            and payload_bytes <= cache_capacity_bytes
        )
        return CacheAdmissionDecision(admitted, anomaly_score, observations)


class MeshPeerNotFound(KeyError):
    """Raised when a request or link refers to a peer outside the mesh."""


class MeshContentNotFound(LookupError):
    """Raised when no serving peer has the requested content."""


class MeshContentRejected(ValueError):
    """Raised when publisher authorization or cached-content integrity fails."""


class PeerMesh:
    """Small undirected peer mesh with predictive routing and local replication."""

    def __init__(
        self,
        peers: Iterable[MeshPeer],
        links: Iterable[MeshLink],
        congestion_penalty_ms: float = 100.0,
        trusted_publishers: Iterable[str] = (),
        cache_guard: Optional[NPUInspiredCacheGuard] = None,
        cost_weight: float = 0.5,
        pressure_velocity_weight: float = 3.0,
        pressure_acceleration_weight: float = 2.0,
        max_active_paths: int = 4,
    ) -> None:
        peer_list = list(peers)
        self.peers = {peer.name: peer for peer in peer_list}
        if not self.peers:
            raise ValueError("A peer mesh requires at least one peer.")
        if len(self.peers) != len(peer_list):
            raise ValueError("Peer names must be unique.")
        if not isfinite(congestion_penalty_ms) or congestion_penalty_ms < 0:
            raise ValueError("Congestion penalty must be non-negative and finite.")
        policy_weights = (
            cost_weight,
            pressure_velocity_weight,
            pressure_acceleration_weight,
        )
        if any(not isfinite(weight) or weight < 0 for weight in policy_weights):
            raise ValueError("Cooperative routing weights must be non-negative and finite.")
        if (
            not isinstance(max_active_paths, int)
            or isinstance(max_active_paths, bool)
            or max_active_paths <= 0
        ):
            raise ValueError("Maximum active path count must be a positive integer.")
        self.congestion_penalty_ms = congestion_penalty_ms
        self.cost_weight = cost_weight
        self.pressure_velocity_weight = pressure_velocity_weight
        self.pressure_acceleration_weight = pressure_acceleration_weight
        self.max_active_paths = max_active_paths
        self.trusted_publishers = set(trusted_publishers)
        if any(not publisher for publisher in self.trusted_publishers):
            raise ValueError("Trusted publisher IDs must not be empty.")
        self.manifests: Dict[str, ContentManifest] = {}
        self.cache_guard = cache_guard or NPUInspiredCacheGuard()
        self.links: Dict[Tuple[str, str], MeshLink] = {}
        self._adjacency: Dict[str, List[str]] = {name: [] for name in self.peers}
        for link in links:
            if link.peer_a not in self.peers or link.peer_b not in self.peers:
                raise MeshPeerNotFound(
                    f"Link {link.peer_a!r}-{link.peer_b!r} references an unknown peer."
                )
            key = self._link_key(link.peer_a, link.peer_b)
            if key in self.links:
                raise ValueError(f"Duplicate mesh link between {link.peer_a!r} and {link.peer_b!r}.")
            self.links[key] = link
            self._adjacency[link.peer_a].append(link.peer_b)
            self._adjacency[link.peer_b].append(link.peer_a)
        for neighbors in self._adjacency.values():
            neighbors.sort()

    def _simple_paths(
        self,
        source: str,
        destination: str,
        max_candidates: int = 256,
    ) -> List[Tuple[str, ...]]:
        if source not in self.peers:
            raise MeshPeerNotFound(source)
        if destination not in self.peers:
            raise MeshPeerNotFound(destination)
        paths: List[Tuple[str, ...]] = []
        stack: List[Tuple[str, Tuple[str, ...]]] = [(source, (source,))]
        while stack and len(paths) < max_candidates:
            current, path = stack.pop()
            if current == destination:
                paths.append(path)
                continue
            for neighbor in reversed(self._adjacency[current]):
                link = self.links[self._link_key(current, neighbor)]
                if not link.available or neighbor in path:
                    continue
                if neighbor != destination and not self.peers[neighbor].can_forward:
                    continue
                if current != source and not self.peers[current].can_forward:
                    continue
                stack.append((neighbor, (*path, neighbor)))
        return paths

    def plan_active_active_paths(
        self,
        source: str,
        destination: str,
        total_bytes: int,
        max_active_paths: int = 4,
    ) -> Tuple[MeshPathAllocation, ...]:
        if (
            not isinstance(total_bytes, int)
            or isinstance(total_bytes, bool)
            or total_bytes < 0
        ):
            raise ValueError("Payload size must be a non-negative integer.")
        if (
            not isinstance(max_active_paths, int)
            or isinstance(max_active_paths, bool)
            or max_active_paths <= 0
        ):
            raise ValueError("Maximum active path count must be a positive integer.")
        if source == destination:
            return ()
        paths = self._simple_paths(source, destination)
        if not paths:
            return ()

        costs = {
            path: sum(
                self.links[self._link_key(left, right)].cost_per_gb
                for left, right in zip(path, path[1:])
            )
            for path in paths
        }
        max_cost = max(costs.values(), default=0.0)
        ranked: List[
            Tuple[float, Tuple[str, ...], float, float, float, float, float, float]
        ] = []
        for path in paths:
            links = [
                self.links[self._link_key(left, right)]
                for left, right in zip(path, path[1:])
            ]
            trends = [link.pressure_trend() for link in links]
            capacity = min(link.capacity_mbps for link in links)
            latency = sum(link.observed_latency_ms for link in links)
            predicted_pressure = (
                sum(link.predicted_pressure() for link in links) / len(links)
            )
            pressure_velocity = sum(trend.velocity for trend in trends) / len(trends)
            pressure_acceleration = sum(trend.acceleration for trend in trends) / len(trends)
            normalized_cost = costs[path] / max_cost if max_cost else 0.0
            risk = (
                2.0 * max(0.0, predicted_pressure)
                + self.pressure_velocity_weight * max(0.0, pressure_velocity)
                + self.pressure_acceleration_weight * max(0.0, pressure_acceleration)
            )
            score = (
                capacity
                / (latency + 1.0)
                * exp(-min(40.0, risk))
                / (1.0 + self.cost_weight * normalized_cost)
            )
            ranked.append(
                (
                    score,
                    path,
                    capacity,
                    predicted_pressure,
                    pressure_velocity,
                    pressure_acceleration,
                    costs[path],
                    latency,
                )
            )

        selected = sorted(ranked, key=lambda item: (-item[0], item[1]))[:max_active_paths]
        score_total = sum(item[0] for item in selected)
        if score_total <= 0:
            return ()

        raw_allocations = [total_bytes * item[0] / score_total for item in selected]
        byte_allocations = [int(value) for value in raw_allocations]
        remainder = total_bytes - sum(byte_allocations)
        remainder_order = sorted(
            range(len(selected)),
            key=lambda index: (
                -(raw_allocations[index] - byte_allocations[index]),
                selected[index][1],
            ),
        )
        for index in remainder_order[:remainder]:
            byte_allocations[index] += 1

        allocations = tuple(
            MeshPathAllocation(
                path=item[1],
                allocated_bytes=byte_allocations[index],
                traffic_share=(
                    byte_allocations[index] / total_bytes
                    if total_bytes
                    else item[0] / score_total
                ),
                capacity_mbps=item[2],
                predicted_pressure=item[3],
                pressure_velocity=item[4],
                pressure_acceleration=item[5],
                estimated_cost_per_gb=item[6],
            )
            for index, item in enumerate(selected)
        )
        if total_bytes:
            return tuple(item for item in allocations if item.allocated_bytes > 0)
        return allocations

    def register_manifest(
        self,
        content_id: str,
        publisher_id: str,
        sha256_digest: str,
    ) -> ContentManifest:
        if not content_id or not publisher_id:
            raise ValueError("Content ID and publisher ID must not be empty.")
        if publisher_id not in self.trusted_publishers:
            raise MeshContentRejected(
                f"Publisher {publisher_id!r} is not in the trusted publisher set."
            )
        digest = sha256_digest.lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("A manifest digest must be a 64-character SHA-256 hex string.")
        manifest = ContentManifest(content_id, publisher_id, digest)
        existing = self.manifests.get(content_id)
        if existing is not None and existing != manifest:
            raise MeshContentRejected(
                f"Conflicting content manifest registration for {content_id!r}."
            )
        self.manifests[content_id] = manifest
        return manifest

    def publish(
        self,
        peer_name: str,
        content_id: str,
        payload: bytes,
        publisher_id: str,
    ) -> bool:
        if peer_name not in self.peers:
            raise MeshPeerNotFound(peer_name)
        if not isinstance(payload, bytes):
            raise TypeError("Content payload must be bytes.")
        manifest = self.manifests.get(content_id)
        if manifest is None:
            raise MeshContentRejected(f"No trusted manifest is registered for {content_id!r}.")
        if publisher_id not in self.trusted_publishers or publisher_id != manifest.publisher_id:
            raise MeshContentRejected(
                f"Publisher {publisher_id!r} is not authorized for {content_id!r}."
            )
        actual_digest = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(actual_digest, manifest.sha256_digest):
            raise MeshContentRejected(
                f"Payload digest does not match the manifest for {content_id!r}."
            )
        return self.peers[peer_name].cache.put(content_id, payload)

    def _remove_cache_entry(self, peer: MeshPeer, content_id: str) -> None:
        peer.cache.contents.pop(content_id, None)
        peer.cache.popularity.pop(content_id, None)

    def _verify_cached_content(
        self,
        peer: MeshPeer,
        content_id: str,
        payload: bytes,
    ) -> Optional[str]:
        manifest = self.manifests.get(content_id)
        if manifest is None:
            reason = "missing trusted content manifest"
        elif not hmac.compare_digest(
            hashlib.sha256(payload).hexdigest(),
            manifest.sha256_digest,
        ):
            reason = "cached payload failed SHA-256 integrity verification"
        else:
            return None
        self._remove_cache_entry(peer, content_id)
        return f"{peer.name}: rejected {content_id!r} ({reason})"

    @staticmethod
    def _link_key(peer_a: str, peer_b: str) -> Tuple[str, str]:
        return tuple(sorted((peer_a, peer_b)))

    def record_link_telemetry(
        self,
        peer_a: str,
        peer_b: str,
        utilization: float,
        queue_delay_ms: float,
        loss_rate: float,
    ) -> MeshLinkTelemetry:
        key = self._link_key(peer_a, peer_b)
        if key not in self.links:
            if peer_a not in self.peers:
                raise MeshPeerNotFound(peer_a)
            if peer_b not in self.peers:
                raise MeshPeerNotFound(peer_b)
            raise KeyError(f"No link exists between {peer_a!r} and {peer_b!r}.")
        link = self.links[key]
        link.record_telemetry(utilization, queue_delay_ms, loss_rate)
        return link.telemetry_snapshot()

    def telemetry_snapshot(self) -> Tuple[MeshLinkTelemetry, ...]:
        return tuple(
            self.links[key].telemetry_snapshot()
            for key in sorted(self.links)
        )

    def _shortest_path(
        self,
        source: str,
        destination: str,
        congestion_aware: bool,
    ) -> Optional[Tuple[Tuple[str, ...], float]]:
        if source == destination:
            return (source,), 0.0
        distances = {source: 0.0}
        previous: Dict[str, str] = {}
        queue: List[Tuple[float, str]] = [(0.0, source)]
        while queue:
            distance, current = heapq.heappop(queue)
            if distance != distances.get(current):
                continue
            if current == destination:
                break
            for neighbor in self._adjacency[current]:
                if neighbor != destination and not self.peers[neighbor].can_forward:
                    continue
                if current != source and not self.peers[current].can_forward:
                    continue
                link = self.links[self._link_key(current, neighbor)]
                if not link.available:
                    continue
                predicted_pressure = link.predicted_pressure()
                cost = link.base_latency_ms + 100.0 * link.loss_rate
                if congestion_aware:
                    cost += link.queue_delay_ms
                    cost += self.congestion_penalty_ms * predicted_pressure
                    if link.congestion_active:
                        cost += self.congestion_penalty_ms
                candidate = distance + cost
                if candidate < distances.get(neighbor, float("inf")):
                    distances[neighbor] = candidate
                    previous[neighbor] = current
                    heapq.heappush(queue, (candidate, neighbor))

        if destination not in distances:
            return None
        path = [destination]
        while path[-1] != source:
            path.append(previous[path[-1]])
        path.reverse()
        return tuple(path), distances[destination]

    def request(
        self,
        requesting_peer: str,
        content_id: str,
        allow_cache_replication: bool = False,
    ) -> MeshRequestResult:
        if requesting_peer not in self.peers:
            raise MeshPeerNotFound(requesting_peer)
        if not content_id:
            raise ValueError("Content ID must not be empty.")

        requester = self.peers[requesting_peer]
        local_payload = requester.cache.get(content_id)
        if local_payload is not None:
            security_event = self._verify_cached_content(
                requester,
                content_id,
                local_payload,
            )
            if security_event is not None:
                raise MeshContentRejected(security_event)
            return MeshRequestResult(
                requesting_peer=requesting_peer,
                serving_peer=requesting_peer,
                content_id=content_id,
                payload=local_payload,
                path=(requesting_peer,),
                cache_hit=True,
                congestion_detected=False,
                route_avoided_congestion=False,
                cache_action="local_hit",
                security_events=(),
                classical_path_payload_mtu_bytes=None,
                classical_fragment_count=0,
            )

        security_events: List[str] = []
        candidates: List[
            Tuple[float, str, bytes, Tuple[str, ...], Tuple[str, ...], bool]
        ] = []
        for peer_name, peer in self.peers.items():
            if peer_name == requesting_peer or not peer.can_serve:
                continue
            payload = peer.cache.contents.get(content_id)
            if payload is None:
                continue
            security_event = self._verify_cached_content(peer, content_id, payload)
            if security_event is not None:
                security_events.append(security_event)
                continue
            baseline = self._shortest_path(requesting_peer, peer_name, congestion_aware=False)
            selected = self._shortest_path(requesting_peer, peer_name, congestion_aware=True)
            if baseline is None or selected is None:
                continue
            congestion_detected = any(
                self.links[self._link_key(left, right)].congestion_active
                for left, right in zip(baseline[0], baseline[0][1:])
            )
            route_avoided_congestion = (
                congestion_detected
                and selected[0] != baseline[0]
            )
            candidates.append(
                (
                    selected[1],
                    peer_name,
                    payload,
                    selected[0],
                    baseline[0],
                    congestion_detected,
                )
            )

        if not candidates:
            if security_events:
                raise MeshContentRejected("; ".join(security_events))
            raise MeshContentNotFound(
                f"No reachable serving peer has content {content_id!r}."
            )

        _, serving_peer, payload, path, baseline_path, congestion_detected = min(
            candidates,
            key=lambda candidate: (candidate[0], candidate[1]),
        )
        self.peers[serving_peer].cache.get(content_id)

        active_paths = self.plan_active_active_paths(
            requesting_peer,
            serving_peer,
            len(payload),
            max_active_paths=self.max_active_paths,
        )
        if not active_paths:
            raise MeshContentNotFound(
                f"No available route connects {requesting_peer!r} to {serving_peer!r}."
            )
        path = active_paths[0].path
        route_avoided_congestion = congestion_detected and path != baseline_path
        cache_action = "not_cached"
        cache_trigger = None
        admission: Optional[CacheAdmissionDecision] = None
        if congestion_detected or allow_cache_replication:
            cache_trigger = "congestion" if congestion_detected else "predicted_demand"
            admission = self.cache_guard.evaluate(
                requesting_peer,
                content_id,
                len(payload),
                requester.cache.capacity_bytes,
            )
            if admission.admitted and requester.cache.put(content_id, payload):
                cache_action = f"replicated_for_{cache_trigger}"
            elif len(payload) > requester.cache.capacity_bytes:
                cache_action = "replication_capacity_exceeded"
            else:
                cache_action = "rejected_cache_pollution"

        path_payload_mtu = min(
            self.links[self._link_key(left, right)].max_classical_payload_bytes
            for allocation in active_paths
            for left, right in zip(allocation.path, allocation.path[1:])
        )
        fragment_count = (len(payload) + path_payload_mtu - 1) // path_payload_mtu
        return MeshRequestResult(
            requesting_peer=requesting_peer,
            serving_peer=serving_peer,
            content_id=content_id,
            payload=payload,
            path=path,
            cache_hit=False,
            congestion_detected=congestion_detected,
            route_avoided_congestion=route_avoided_congestion,
            cache_action=cache_action,
            cache_admission_score=admission.anomaly_score if admission else None,
            security_events=tuple(security_events),
            classical_path_payload_mtu_bytes=path_payload_mtu,
            classical_fragment_count=fragment_count,
            cache_trigger=cache_trigger,
            active_active_paths=active_paths,
        )
