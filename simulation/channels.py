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

from .environment import TransportMedium


def build_default_channels():
    return [
        TransportMedium(
            name="Microwave",
            base_bandwidth=1200,
            base_latency=3,
            packet_loss_base=0.015,
            mtu_bytes=9000,
        ),
        TransportMedium(name="HF", base_bandwidth=50, base_latency=120, packet_loss_base=0.08, mtu_bytes=512),
        TransportMedium(
            name="Satellite",
            base_bandwidth=1000,
            base_latency=35,
            packet_loss_base=0.01,
            mtu_bytes=1280,
        ),
        TransportMedium(name="Mobile", base_bandwidth=800, base_latency=12, packet_loss_base=0.015, mtu_bytes=1500),
        TransportMedium(
            name="WiFi",
            base_bandwidth=2000,
            base_latency=4,
            packet_loss_base=0.005,
            mtu_bytes=1500,
        ),
        TransportMedium(name="Drones", base_bandwidth=500, base_latency=15, packet_loss_base=0.02, mtu_bytes=1200),
    ]
