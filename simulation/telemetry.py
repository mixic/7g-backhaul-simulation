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

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class TelemetryFrame:
    timestamp: float
    channel_states: Dict[str, float]
    routing_distribution: Dict[str, float]
    best_medium: str
    total_packets: int


class INTCollector:
    def __init__(self):
        self.frames: List[TelemetryFrame] = []

    def record_frame(self, timestamp, channel_states, routing_distribution, best_medium, total_packets):
        frame = TelemetryFrame(
            timestamp=timestamp,
            channel_states=channel_states,
            routing_distribution=routing_distribution,
            best_medium=best_medium,
            total_packets=total_packets,
        )
        self.frames.append(frame)
        return frame

    def latest(self):
        if not self.frames:
            return None
        return self.frames[-1]

    def summary(self):
        return {
            "frames": len(self.frames),
            "last_best_medium": self.latest().best_medium if self.latest() else None,
            "last_total_packets": self.latest().total_packets if self.latest() else 0,
        }


class InBandTelemetry:
    @staticmethod
    def parse_telemetry_fabric(channels):
        telemetry_data = {}
        for medium in channels:
            telemetry_data[medium.name] = {
                "pressure": round(medium.get_pressure_score(), 4),
                "hop_latency_ms": round(medium.base_latency * (1 + medium.current_load), 2),
                "packet_loss_proxy": round(medium.packet_loss_base * (1 + medium.current_load), 4),
                "disaster": medium.active_disaster,
                "load": round(medium.current_load, 4),
            }
        return telemetry_data
