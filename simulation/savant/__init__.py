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

"""Compensatory hyper-specialisation ("savant") controller.

The savant mechanism is a control law, not a biological claim.  On a kinematic
shockwave a node sheds its general routing role -- driving `alpha` toward
`savant_alpha` -- and hands the affected circuit everything that remains.  The
cost is measured, never assumed: :class:`StarvationLogger` counts every request
of an *other* flow dropped at the node while savant mode is active, and the
experiment reports the cascading-failure rate in the rest of the network.

The savant edit is node-local.  It does not propagate to other nodes unless a
spatial baseline (VDR) explicitly reroutes traffic in response to the induced
failure.
"""

from __future__ import annotations

from .controller import SavantController
from .starvation import StarvationLogger

__all__ = ["SavantController", "StarvationLogger"]
