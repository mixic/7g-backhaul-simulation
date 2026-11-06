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

"""Multidimensional kinematic baselining (MKB) controller (H6).

The network state is a vector ``S = [CBF, OEF, Queue_Depth, Drop_Rate]``.  The
vector velocity and acceleration are the discrete derivatives of an EMA of that
state,

    V(t) = (S(t) - S(t-1)) / dt,      A(t) = (V(t) - V(t-1)) / dt,

and a spike is declared when the *geometry* of the trajectory deviates from its
moving-average manifold:

    ||A(t) - EMA(A)|| > k * EWMA(||A - EMA(A)||)

or when the velocity vector turns away from the baseline trajectory by more than
an angle threshold.  This replaces scalar thresholding with a threshold on the
acceleration magnitude of the whole state vector.

The controller inherits the OEF actuator (whose double-integrator governor caps
the OEF rate) and the surgical isolation edit, but its trigger is the vector
monitor rather than the scalar (1-D) pressure trigger.
"""
from __future__ import annotations

import math

import numpy as np

from .surgical.config import MKB
from .oef_controller import OefController


class MkbMonitor:
    """Vector baselining: EMA of S, v and a; trigger on the geometry."""

    __slots__ = ("dt", "tau_s", "tau_v", "k", "floor_a", "floor_v", "cos_thr",
                 "s_ema", "v_ema", "a_ema", "resid_ema", "s_prev", "v_prev",
                 "init", "dims")

    def __init__(self, dims: int, dt: float, tau_s: float = 0.3,
                 tau_v: float = 1.0, k: float = 4.0, angle_deg: float = 45.0,
                 floor_a: float = 2.0, floor_v: float = 0.08):
        self.dims = dims
        self.dt = dt
        self.tau_s = tau_s
        self.tau_v = tau_v
        self.k = k
        self.floor_a = floor_a
        self.floor_v = floor_v
        self.cos_thr = math.cos(math.radians(angle_deg))
        self.s_ema = None
        self.v_ema = None
        self.a_ema = None
        self.resid_ema = 0.0
        self.s_prev = None
        self.v_prev = None
        self.init = False

    def update(self, s) -> bool:
        s = np.asarray(s, dtype=float)
        if not self.init:
            self.init = True
            self.s_ema = s.copy()
            self.v_ema = np.zeros(self.dims)
            self.a_ema = np.zeros(self.dims)
            self.v_prev = np.zeros(self.dims)
            return False
        av = 1.0 - math.exp(-self.dt / self.tau_v)
        as_ = 1.0 - math.exp(-self.dt / self.tau_s)
        # velocity/acceleration are the curvature of the *baseline manifold*: a
        # short-window EMA of the state.  Per-tick served bytes are Poisson, so
        # their raw second difference is dominated by noise; the manifold is not.
        prev_ema = self.s_ema.copy()
        self.s_ema += as_ * (s - self.s_ema)
        v = (self.s_ema - prev_ema) / self.dt
        a = (v - self.v_prev) / self.dt
        self.v_prev = v.copy()
        self.v_ema += av * (v - self.v_ema)
        a_resid = float(np.linalg.norm(a - self.a_ema))
        self.a_ema += av * (a - self.a_ema)
        self.resid_ema += av * (a_resid - self.resid_ema)

        mag_trigger = a_resid > max(self.floor_a, self.k * self.resid_ema)
        # the angle test is only meaningful along a *persistent* trajectory
        nv = float(np.linalg.norm(v))
        nve = float(np.linalg.norm(self.v_ema))
        cosang = (float(np.dot(v, self.v_ema) / (nv * nve))
                  if nv > 1e-9 and nve > 1e-9 else 1.0)
        angle_trigger = (nv > self.floor_v and nve > self.floor_v
                         and cosang < self.cos_thr)
        return bool(mag_trigger or angle_trigger)


class MkbController(OefController):
    """Surgical isolation + OEF, triggered by the multidimensional monitor."""

    name = MKB

    def __init__(self, cfg, sim, oef_on: bool = True):
        super().__init__(cfg, sim, oef_on=oef_on)
        self.monitors = {n: MkbMonitor(4, cfg.tick, 0.3, cfg.mkb_tau_v,
                                       cfg.mkb_k, cfg.mkb_angle_deg,
                                       cfg.mkb_floor_a, cfg.mkb_floor_v)
                         for n in range(sim.topo.n_nodes)}
        self.mkb_spikes = []   # (t, node) when the vector trigger fired an edit

    def on_tick(self, t, obs):
        dt = self._dt(t)
        self._oef_step(t, dt)
        self._release(t, obs)
        self._mkb_detect(t, obs)
        self._top_up(t, obs)

    def _mkb_detect(self, t, obs):
        if t < self.cfg.warmup:
            return
        for n in range(self.sim.topo.n_nodes):
            e = self.active.get(n)
            if e is not None and e["phase"] == "in":
                continue
            state = self._state.get(n)
            if state is None:
                continue
            if not self.monitors[n].update(state):
                continue
            flow = self._attribute(n, t)
            if flow is None:
                continue
            self.mkb_spikes.append((t, n))
            self._apply(t, flow, n)
