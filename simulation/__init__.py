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

"""7G multi-medium soft-handover backhaul simulation package."""

from .environment import TransportMedium, clip
from .router import SoftHandoverRouter
from .channels import build_default_channels
from .telemetry import INTCollector, InBandTelemetry, TelemetryFrame
from .continuity import (
    AdaptiveMTULearner,
    FragmentReassembler,
    PacketFragment,
    SeamlessTransportSession,
    TransferError,
    TransferResult,
)
from .cdn import CachePlacementLearner, SelfScalingContentNetwork
from .trends import RequestDemandLearner, SecondOrderTrendEstimator, TrendEstimate

__all__ = [
    "AdaptiveMTULearner",
    "CachePlacementLearner",
    "FragmentReassembler",
    "InBandTelemetry",
    "PacketFragment",
    "RequestDemandLearner",
    "SecondOrderTrendEstimator",
    "SeamlessTransportSession",
    "SelfScalingContentNetwork",
    "TransportMedium",
    "TransferError",
    "TransferResult",
    "TrendEstimate",
    "clip",
    "SoftHandoverRouter",
    "build_default_channels",
    "INTCollector",
    "TelemetryFrame",
]
