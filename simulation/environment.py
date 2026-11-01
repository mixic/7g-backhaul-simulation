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

import random

import numpy as np


def clip(val, min_val, max_val):
    return max(min_val, min(val, max_val))


class TransportMedium:
    def __init__(
        self,
        name,
        base_bandwidth,
        base_latency,
        packet_loss_base,
        mtu_bytes=1500,
        encapsulation_overhead_bytes=48,
    ):
        if mtu_bytes <= encapsulation_overhead_bytes:
            raise ValueError("MTU must exceed encapsulation overhead.")
        self.name = name
        self.base_bandwidth = base_bandwidth
        self.base_latency = base_latency
        self.packet_loss_base = packet_loss_base
        self.base_packet_loss = packet_loss_base
        self.mtu_bytes = mtu_bytes
        self.encapsulation_overhead_bytes = encapsulation_overhead_bytes
        self.current_load = 0.0
        self.active_disaster = "None"

    @property
    def current_mtu_bytes(self):
        load_factor = 1.0 - (0.35 * self.current_load)
        minimum_mtu = min(self.mtu_bytes, self.encapsulation_overhead_bytes + 128)
        return min(self.mtu_bytes, max(minimum_mtu, int(self.mtu_bytes * load_factor)))

    @property
    def max_payload_bytes(self):
        return self.current_mtu_bytes - self.encapsulation_overhead_bytes

    def update_dynamic_conditions(self, disaster_event="None"):
        """Simulates environmental fluctuations modulated by stochastic climate disasters."""
        self.active_disaster = "None"

        if self.name in {"Satellite", "Mixed"}:
            self.current_load = clip(0.2 + 0.4 * np.sin(random.random()), 0.1, 0.9)
        elif self.name == "Microwave":
            self.current_load = clip(0.2 + random.normalvariate(0, 0.1), 0.05, 0.9)
        elif self.name == "Mobile":
            self.current_load = clip(0.35 + random.normalvariate(0, 0.18), 0.05, 0.95)
        elif self.name == "Drones":
            self.current_load = clip(0.3 + random.normalvariate(0, 0.15), 0.1, 0.9)
        elif self.name == "HF":
            self.current_load = clip(0.2 + 0.5 * random.random(), 0.05, 0.9)
        elif self.name == "WiFi":
            self.current_load = random.choice([0.1, 0.25, 0.6, 0.8])
        else:
            self.current_load = clip(random.uniform(0.1, 0.8), 0.05, 0.95)

        self.packet_loss_base = self.base_packet_loss
        if disaster_event == "Solar_Flare" and self.name == "HF":
            self.active_disaster = disaster_event
            self.current_load = 1.0
            self.packet_loss_base = 0.85
        elif disaster_event == "Localized_Storm":
            if self.name == "WiFi":
                self.active_disaster = disaster_event
                self.current_load = 0.95
            if self.name in {"Drones", "Microwave"}:
                self.active_disaster = disaster_event
                self.packet_loss_base = 0.40

    def get_pressure_score(self):
        """Calculates channel constraint weight metrics (0 = clear fluidity, 1 = saturated boundary)."""
        effective_loss = self.packet_loss_base * (1 + self.current_load)
        disaster_penalty = 0.3 if self.active_disaster != "None" else 0.0
        pressure = (self.current_load * 0.5) + (effective_loss * 0.4) + disaster_penalty
        return clip(pressure, 0.0, 1.0)

    def telemetry_snapshot(self):
        return {
            "name": self.name,
            "load": round(self.current_load, 4),
            "bandwidth_mbps": self.base_bandwidth,
            "latency_ms": self.base_latency,
            "packet_loss_base": self.packet_loss_base,
            "mtu_bytes": self.current_mtu_bytes,
            "max_payload_bytes": self.max_payload_bytes,
            "pressure": round(self.get_pressure_score(), 4),
            "active_disaster": self.active_disaster,
        }
