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

import numpy as np


class SoftHandoverRouter:
    def __init__(self, media_channels):
        self.channels = media_channels

    def calculate_routing_distribution(self):
        """Allocate more traffic to links with usable capacity and favorable latency."""
        weights = np.array(
            [
                max(0.0, medium.base_bandwidth * (1.0 - medium.current_load))
                * max(0.0, 1.0 - medium.packet_loss_base * (1.0 + medium.current_load))
                / (medium.base_latency + 1.0)
                / (medium.get_pressure_score() + 0.01)
                for medium in self.channels
            ],
            dtype=float,
        )
        if weights.sum() <= 0:
            pressures = np.array([m.get_pressure_score() for m in self.channels])
            weights = 1.0 / (pressures + 1e-6)
        probabilities = weights / np.sum(weights)
        distribution = {self.channels[i].name: float(probabilities[i]) for i in range(len(self.channels))}
        return distribution

    def route_packet_flow(self, num_packets):
        """Sprays a burst of packets over available backhaul channels."""
        distribution = self.calculate_routing_distribution()
        media_names = list(distribution.keys())
        probabilities = list(distribution.values())

        assigned_channels = np.random.choice(media_names, size=num_packets, p=probabilities)
        unique, counts = np.unique(assigned_channels, return_counts=True)
        return dict(zip(unique, counts)), distribution
