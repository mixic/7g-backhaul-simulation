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

Two additions to the surgical controller, framed strictly as control theory:

OEF (oxygen extraction fraction) -- the Fick-principle mapping
CMRO2 = CBF x OEF x Ca.  Here CMRO2 is legitimate goodput, CBF the delivered
throughput, Ca the nominal capacity, and OEF the fraction of queue service
dedicated to legitimate traffic.  When the CBF monitor sees delivered
throughput fall below ``oef_trigger * EMA(CBF)``, the OEF actuator raises the
legitimate class's WFQ weight, rate-limited by a double integrator.  The
increase is computed from the CBF deficit -- never hard-coded.

MKB (multidimensional kinematic baselining) -- the network state is a vector
``S = [CBF, queue, drop, OEF]``.  A spike is the vector acceleration ``a``
deviating from its moving-average manifold (``||a - EMA(a)|| > k * EWMA``) or
the velocity vector turning away from the baseline trajectory by more than an
angle.  This replaces scalar thresholding with a threshold on the geometry of
the state trajectory.

Both build on, and do not replace, the surgical isolation edit.
"""

from __future__ import annotations

import math

import numpy as np

from .config import MKB, OEF
from .controllers import Governor, SurgicalController
from .link import BULK

#: state-vector normalisation: queue delay expressed in units of buffer time
_BUFFER_SECONDS = 0.15


class OefSurgicalController(SurgicalController):
    """Surgical isolation plus an OEF actuator on the legitimate class."""

    name = OEF

    def __init__(self, cfg, sim):
        super().__init__(cfg, sim)
        self.oef_govs = {}
        self._cbf_ema = {}
        self._prev_served = {n: sim.tele[n].served_bytes
                             for n in range(sim.topo.n_nodes)}
        self._prev_drops = {n: sim.tele[n].drops
                            for n in range(sim.topo.n_nodes)}
        self.oef_log = []        # (t, node, oef, speed, accel)
        self.oef_series = []     # (t, mean_oef, total_cbf_Bps)
        self.oef_peak = 0.0
        self.oef_limit_hit = False
        self._state = {}         # node -> state vector (for MKB)
        self._loss_ema = {}      # node -> smoothed loss rate (a router's loss ratio)
        self._cbf_samples = {}   # node -> [(t, served_bytes)] for a 1 s window
        self._low_count = {}     # node -> consecutive ticks below the CBF trigger
        self._high_count = {}    # node -> consecutive ticks above the release band
        self._oef_engaged = {}   # node -> bool (Schmitt hysteresis state)

    # -- state vector + OEF actuator -----------------------------------
    def _oef_step(self, t, dt):
        cfg = self.cfg
        alpha = 1.0 - math.exp(-dt / max(cfg.oef_cbf_tau, 1e-6))
        total_cbf = 0.0
        oef_sum = 0.0
        for n in range(self.sim.topo.n_nodes):
            tel = self.sim.tele[n]
            cap = self.sim.topo.node_cap[n] / 8.0
            served = tel.served_bytes - self._prev_served[n]
            self._prev_served[n] = tel.served_bytes
            drops = tel.drops - self._prev_drops[n]
            self._prev_drops[n] = tel.drops
            # CBF is the delivered rate over a 1 s window: a per-tick count is
            # quantised at whole batches and reads zero whenever a tick holds no
            # arrival, which a light-flow node sees constantly.
            samples = self._cbf_samples.setdefault(n, [])
            samples.append((t, tel.served_bytes))
            while samples and samples[0][0] < t - 1.0:
                samples.pop(0)
            if len(samples) >= 2:
                span = samples[-1][0] - samples[0][0]
                cbf = (samples[-1][1] - samples[0][1]) / span if span > 0 else 0.0
            else:
                cbf = 0.0
            total_cbf += cbf
            # state-vector dims are the same bounded, smooth quantities the
            # scalar pressure signal is built from, plus the OEF actuator -- a
            # raw queue-length sawtooth would dominate ||a|| and fire the vector
            # trigger every tick.
            util = min(1.0, cbf / cap) if cap > 0 else 0.0
            q_sec = tel.queued_bytes / cap if cap > 0 else 0.0
            d = self.sim._base_delay(n)
            queue_dim = q_sec / (d + q_sec + 1.0)
            # a loss *rate*, smoothed, so a single drop event does not dominate
            # the vector's acceleration the way it would as a 0/1 spike
            raw_loss = drops / (served + drops + 1.0)
            alpha_loss = 1.0 - math.exp(-dt / 1.0)
            loss_ema = self._loss_ema.get(n, raw_loss)
            loss_ema += alpha_loss * (raw_loss - loss_ema)
            self._loss_ema[n] = loss_ema

            ema = self._cbf_ema.get(n, cbf)
            ema += alpha * (cbf - ema)
            self._cbf_ema[n] = ema

            if t < cfg.warmup:
                # cold start: the CBF baseline has not settled yet, so a zero or
                # rising throughput is not a collapse; update the EMA only.
                target = 0.0
            elif cfg.oef_force_max:
                target = 1.0
            else:
                # Schmitt hysteresis: a per-tick Poisson rate crosses the 0.8x
                # band constantly, so OEF engages only after a sustained drop and
                # releases only after a sustained recovery.  Without this the
                # actuator self-oscillates and the rate limits are hit at idle.
                low = ema > 1e-3 and cbf < cfg.oef_trigger * ema
                self._low_count[n] = self._low_count.get(n, 0) + (1 if low else 0)
                self._high_count[n] = self._high_count.get(n, 0) + (0 if low else 1)
                engaged = self._oef_engaged.get(n, False)
                if not engaged and self._low_count[n] >= 3:
                    engaged = True
                elif engaged and self._high_count[n] >= 5:
                    engaged = False
                self._oef_engaged[n] = engaged
                if engaged:
                    deficit = 1.0 - cbf / max(ema, 1e-9)
                    target = min(1.0, cfg.oef_gain * deficit)
                else:
                    target = 0.0

            g = self.oef_govs.get(n)
            if g is None:
                g = Governor(0.0, cfg.oef_speed_max, cfg.oef_accel_max)
                self.oef_govs[n] = g
            g.target = target
            prev = g.value
            sp, ac = g.step(dt)
            # the actuator is a fraction in [0,1]; clamp any integrator overshoot
            if g.value > 1.0:
                g.value, g.vel = 1.0, 0.0
            elif g.value < 0.0:
                g.value, g.vel = 0.0, 0.0
            self.oef_peak = max(self.oef_peak, g.value)
            oef_sum += g.value
            if abs(g.value - prev) > 1e-9:
                self.oef_log.append((t, float(n), g.value, sp, ac))
                if sp >= cfg.oef_speed_max - 1e-9:
                    self.oef_limit_hit = True
            # apply extraction: legitimate (bulk) class weight rises with OEF
            weight = 1.0 + (cfg.oef_max - 1.0) * g.value
            self.sim.states[n].policy.weights[BULK] = weight
            self._state[n] = [util, queue_dim, loss_ema, g.value]

        self.oef_series.append((t, oef_sum / self.sim.topo.n_nodes, total_cbf))

    def on_tick(self, t, obs):
        dt = self._dt(t)
        self._oef_step(t, dt)
        self._release(t, obs)
        self._detect(t, obs)         # the inherited scalar (1-D) trigger
        self._top_up(t, obs)


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


class MkbController(OefSurgicalController):
    """Surgical isolation + OEF, triggered by the multidimensional monitor."""

    name = MKB

    def __init__(self, cfg, sim):
        super().__init__(cfg, sim)
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


def make_homeostasis_controller(cfg, sim):
    if cfg.controller == OEF:
        return OefSurgicalController(cfg, sim)
    if cfg.controller == MKB:
        return MkbController(cfg, sim)
    return None
