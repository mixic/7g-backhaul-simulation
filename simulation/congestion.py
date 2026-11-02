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

from .environment import TransportMedium


class AIMDCongestionController:
    """TCP-Reno-inspired congestion window and pacing model for one simulated link."""

    def __init__(
        self,
        medium: TransportMedium,
        initial_window_segments: int = 10,
        minimum_window_segments: int = 2,
    ) -> None:
        if initial_window_segments < minimum_window_segments or minimum_window_segments < 1:
            raise ValueError("Initial window must be at least the positive minimum window.")
        self.medium = medium
        self.minimum_window_segments = minimum_window_segments
        self.smoothed_rtt_ms = max(1.0, medium.base_latency * (1.0 + medium.current_load))
        segment_size = max(1, medium.max_payload_bytes)
        self.congestion_window_bytes = float(segment_size * initial_window_segments)
        self._update_window_limit()
        self.congestion_window_bytes = min(self.congestion_window_bytes, self.window_limit_bytes)

    def _update_window_limit(self) -> None:
        capacity_mbps = self.medium.base_bandwidth * max(0.01, 1.0 - self.medium.current_load)
        rtt_seconds = max(0.001, self.smoothed_rtt_ms / 1000.0)
        bandwidth_delay_product = capacity_mbps * 1_000_000 / 8 * rtt_seconds
        self.window_limit_bytes = max(
            float(self.medium.max_payload_bytes * self.minimum_window_segments),
            bandwidth_delay_product,
        )

    @property
    def pacing_rate_mbps(self) -> float:
        if not self.medium.available:
            return 0.0
        self._update_window_limit()
        window_rate_mbps = self.congestion_window_bytes * 8 / (self.smoothed_rtt_ms * 1000)
        physical_rate_mbps = self.medium.base_bandwidth * max(0.01, 1.0 - self.medium.current_load)
        return min(physical_rate_mbps, window_rate_mbps)

    def on_ack(self, acknowledged_bytes: int, rtt_ms: float) -> None:
        if acknowledged_bytes <= 0 or rtt_ms <= 0:
            raise ValueError("Acknowledged bytes and measured RTT must be positive.")
        self.smoothed_rtt_ms = 0.875 * self.smoothed_rtt_ms + 0.125 * rtt_ms
        self.congestion_window_bytes += (acknowledged_bytes**2) / max(1.0, self.congestion_window_bytes)
        self._update_window_limit()
        self.congestion_window_bytes = min(self.congestion_window_bytes, self.window_limit_bytes)

    def on_loss(self) -> None:
        minimum_window = float(self.medium.max_payload_bytes * self.minimum_window_segments)
        self.congestion_window_bytes = max(minimum_window, self.congestion_window_bytes * 0.5)
