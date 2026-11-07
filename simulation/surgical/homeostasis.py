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

"""Network homeostasis: OEF compensation and multidimensional baselining.

The OEF (H5) and MKB (H6) controllers now live in the standalone modules
``simulation.oef_controller`` and ``simulation.mkb_controller``.  This module
re-exports their public names so existing callers (``controllers.make_controller``
and the CI tests) keep working unchanged.
"""
from __future__ import annotations

from ..mkb_controller import EwmaMkbController, MkbController, MkbMonitor
from ..oef_controller import OefController, OefSurgicalController

__all__ = ["OefController", "OefSurgicalController", "MkbController",
           "MkbMonitor", "EwmaMkbController", "make_homeostasis_controller"]


def make_homeostasis_controller(cfg, sim):
    from .config import DUAL_BAND, LPF_ONLY, MKB, MKB_EWMA, MKB_NO_OEF, OEF

    if cfg.controller == OEF:
        return OefController(cfg, sim)
    if cfg.controller == MKB:
        return MkbController(cfg, sim, oef_on=True)
    if cfg.controller == MKB_NO_OEF:
        return MkbController(cfg, sim, oef_on=False)
    if cfg.controller == MKB_EWMA:
        return EwmaMkbController(cfg, sim)
    if cfg.controller == DUAL_BAND:
        from ..dual_band_controller import DualBandController
        return DualBandController(cfg, sim)
    if cfg.controller == LPF_ONLY:
        from ..dual_band_controller import LpfOnlyController
        return LpfOnlyController(cfg, sim)
    return None
