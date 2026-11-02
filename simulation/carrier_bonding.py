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
from typing import Dict, Iterable, Optional

from .congestion import AIMDCongestionController
from .environment import TransportMedium


@dataclass(frozen=True)
class CarrierAllocation:
    medium: str
    bytes: int
    weight: float


class BondedCarrierScheduler:
    """Allocate packet bytes over active carriers using capacity and congestion feedback."""

    def __init__(self, controllers: Optional[Dict[str, AIMDCongestionController]] = None) -> None:
        self.controllers = controllers or {}

    def weights(self, channels: Iterable[TransportMedium]) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for medium in channels:
            if not medium.available:
                continue
            controller = self.controllers.get(medium.name)
            physical_rate = medium.base_bandwidth * max(0.01, 1.0 - medium.current_load)
            rate = physical_rate
            if controller:
                window_ratio = min(
                    1.0,
                    controller.pacing_rate_mbps / physical_rate,
                )
                rate *= 0.5 + (0.5 * window_ratio)
            reliability = max(0.0, 1.0 - medium.packet_loss_base * (1.0 + medium.current_load))
            score = rate * reliability / ((medium.base_latency + 1.0) * (medium.get_pressure_score() + 0.01))
            if score > 0:
                scores[medium.name] = score
        return scores

    def allocate(
        self,
        total_bytes: int,
        channels: Iterable[TransportMedium],
        weights_override: Optional[Dict[str, float]] = None,
    ) -> Dict[str, int]:
        if total_bytes < 0:
            raise ValueError("Byte count must be non-negative.")
        scores = weights_override if weights_override is not None else self.weights(channels)
        scores = {name: score for name, score in scores.items() if score > 0}
        if total_bytes == 0 or not scores:
            return {name: 0 for name in scores}

        score_total = sum(scores.values())
        raw = {name: total_bytes * score / score_total for name, score in scores.items()}
        allocation = {name: int(value) for name, value in raw.items()}
        remainder = total_bytes - sum(allocation.values())
        ranked = sorted(scores, key=lambda name: (-(raw[name] - allocation[name]), name))
        for name in ranked[:remainder]:
            allocation[name] += 1
        return allocation

    def plan(self, total_bytes: int, channels: Iterable[TransportMedium]) -> list[CarrierAllocation]:
        channel_list = list(channels)
        scores = self.weights(channel_list)
        allocations = self.allocate(total_bytes, channel_list)
        total_score = sum(scores.values())
        return [
            CarrierAllocation(name, allocation, scores[name] / total_score)
            for name, allocation in allocations.items()
        ]
