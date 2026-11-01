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

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .continuity import SeamlessTransportSession, TransferResult
from .trends import RequestDemandLearner, TrendEstimate


class CachePlacementLearner:
    """Learns per-region object popularity from observed content requests."""

    def __init__(self) -> None:
        self._requests: Counter[Tuple[str, str]] = Counter()

    def observe(self, region: str, content_id: str) -> int:
        self._requests[(region, content_id)] += 1
        return self._requests[(region, content_id)]

    def ranked_content(self, region: str) -> List[Tuple[str, int]]:
        entries = (
            (content_id, count)
            for (known_region, content_id), count in self._requests.items()
            if known_region == region
        )
        return sorted(entries, key=lambda item: (-item[1], item[0]))


@dataclass
class EdgeCache:
    region: str
    capacity_bytes: int
    contents: Dict[str, bytes] = field(default_factory=dict)
    popularity: Counter[str] = field(default_factory=Counter)

    @property
    def used_bytes(self) -> int:
        return sum(len(payload) for payload in self.contents.values())

    def get(self, content_id: str) -> Optional[bytes]:
        payload = self.contents.get(content_id)
        if payload is not None:
            self.popularity[content_id] += 1
        return payload

    def put(self, content_id: str, payload: bytes) -> bool:
        if len(payload) > self.capacity_bytes:
            return False
        if content_id in self.contents:
            self.contents[content_id] = payload
            return True

        while self.used_bytes + len(payload) > self.capacity_bytes and self.contents:
            least_popular = min(self.contents, key=lambda key: (self.popularity[key], key))
            del self.contents[least_popular]
            del self.popularity[least_popular]
        self.contents[content_id] = payload
        self.popularity[content_id] = 0
        return True


@dataclass
class ContentDelivery:
    content_id: str
    region: str
    cache_hit: bool
    transfer: TransferResult


class SelfScalingContentNetwork:
    """Scales regional caches and warms popular objects using learned demand."""

    def __init__(
        self,
        transport: SeamlessTransportSession,
        cache_capacity_bytes: int = 1_000_000,
        requests_to_scale: int = 3,
        max_caches: int = 8,
        forecast_horizon_seconds: float = 5.0,
    ) -> None:
        if cache_capacity_bytes <= 0 or requests_to_scale <= 0 or max_caches <= 0:
            raise ValueError("Cache capacity, scale threshold and cache limit must be positive.")
        self.transport = transport
        self.cache_capacity_bytes = cache_capacity_bytes
        self.requests_to_scale = requests_to_scale
        self.max_caches = max_caches
        self.learner = CachePlacementLearner()
        self.demand_learner = RequestDemandLearner(forecast_horizon_seconds=forecast_horizon_seconds)
        self.caches: Dict[str, List[EdgeCache]] = {}
        self.region_requests: Counter[str] = Counter()
        self.demand_trends: Dict[str, TrendEstimate] = {}
        self._known_payloads: Dict[Tuple[str, str], bytes] = {}
        self._automatic_time = 0.0
        self.cache_hits = 0
        self.cache_misses = 0

    @property
    def hit_ratio(self) -> float:
        requests = self.cache_hits + self.cache_misses
        return self.cache_hits / requests if requests else 0.0

    @property
    def cache_node_count(self) -> int:
        return sum(len(region_caches) for region_caches in self.caches.values())

    def _scale_cache_if_needed(self, region: str) -> None:
        trend = self.demand_trends[region]
        region_caches = self.caches.setdefault(region, [])
        next_scale_threshold = self.requests_to_scale * (len(region_caches) + 1)
        if (
            self.cache_node_count < self.max_caches
            and (
                self.region_requests[region] >= next_scale_threshold
                or trend.forecast >= next_scale_threshold
            )
        ):
            new_cache = EdgeCache(region, self.cache_capacity_bytes)
            region_caches.append(new_cache)
            for content_id, _ in self.learner.ranked_content(region):
                if not new_cache.put(content_id, self._known_payloads[(region, content_id)]):
                    break

    def _find_cached_content(self, region: str, content_id: str) -> Optional[bytes]:
        for cache in self.caches.get(region, []):
            payload = cache.get(content_id)
            if payload is not None:
                return payload
        return None

    def _cache_content(self, region: str, content_id: str, payload: bytes) -> None:
        for cache in self.caches.get(region, []):
            if cache.put(content_id, payload):
                return

    def request(
        self,
        region: str,
        content_id: str,
        payload: bytes,
        timestamp: Optional[float] = None,
    ) -> ContentDelivery:
        if not region or not content_id:
            raise ValueError("Region and content ID must not be empty.")
        if not isinstance(payload, bytes):
            raise TypeError("Content payload must be bytes.")
        if timestamp is None:
            self._automatic_time += 1.0
            timestamp = self._automatic_time
        self.demand_trends[region] = self.demand_learner.observe(region, timestamp)
        self._known_payloads[(region, content_id)] = payload
        self.region_requests[region] += 1
        self.learner.observe(region, content_id)
        self._scale_cache_if_needed(region)

        cached_payload = self._find_cached_content(region, content_id)
        cache_hit = cached_payload is not None
        if cache_hit:
            self.cache_hits += 1
            content = cached_payload
        else:
            self.cache_misses += 1
            content = payload
            self._cache_content(region, content_id, payload)

        transfer = self.transport.transmit(content, session_id=f"{region}:{content_id}")
        return ContentDelivery(content_id, region, cache_hit, transfer)
