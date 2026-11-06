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

"""OEF (oxygen extraction fraction) compensation controller (H5).

The Fick-principle mapping for network metabolism:

    CMRO2 = CBF * OEF * Ca

  * CMRO2 -- legitimate goodput (the useful work actually delivered)
  * CBF   -- total delivered throughput (the "cerebral blood flow")
  * OEF   -- the fraction of queue service dedicated to legitimate traffic
  * Ca    -- nominal payload capacity (the "arterial content")

The actuator ``OEF`` is a continuous fraction in [0, 1] per flow class.  When
the CBF monitor sees delivered throughput fall below ``oef_trigger * EMA(CBF)``,
the OEF actuator raises the legitimate (bulk) class's WFQ weight.  The increase
is computed from the CBF deficit (``oef_gain * deficit``) -- never hard-coded --
and is rate-limited by a double integrator (OEF speed and acceleration caps) so
the queue does not oscillate.

This controller builds on, and does not replace, the surgical isolation edit.
"""
from __future__ import annotations

import math

from .surgical.config import OEF
from .surgical.controllers import Governor, SurgicalController
from .surgical.link import BULK


class OefController(SurgicalController):
    """Surgical isolation plus an OEF actuator on the legitimate class."""

    name = OEF

    def __init__(self, cfg, sim, oef_on: bool = True):
        super().__init__(cfg, sim)
        self.oef_on = oef_on
        self.oef_govs = {}
        self._cbf_ema = {}
        self._prev_served = {n: sim.tele[n].served_bytes
                             for n in range(sim.topo.n_nodes)}
        self._prev_drops = {n: sim.tele[n].drops
                            for n in range(sim.topo.n_nodes)}
        self.oef_log = []        # (t, node, oef, speed, accel)
        self.oef_series = []     # (t, mean_oef, total_cbf_Bps, max_oef)
        self.state_series = []   # (t, mean_util, mean_queue, mean_loss, mean_oef)
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
        oef_max_node = 0.0
        util_sum = 0.0
        queue_sum = 0.0
        loss_sum = 0.0
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

            util_sum += util
            queue_sum += queue_dim
            loss_sum += loss_ema

            ema = self._cbf_ema.get(n, cbf)
            ema += alpha * (cbf - ema)
            self._cbf_ema[n] = ema

            if not self.oef_on:
                target = 0.0
            elif t < cfg.warmup:
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
            oef_max_node = max(oef_max_node, g.value)
            if abs(g.value - prev) > 1e-9:
                self.oef_log.append((t, float(n), g.value, sp, ac))
                if sp >= cfg.oef_speed_max - 1e-9:
                    self.oef_limit_hit = True
            # apply extraction: legitimate (bulk) class weight rises with OEF
            if self.oef_on:
                weight = 1.0 + (cfg.oef_max - 1.0) * g.value
                self.sim.states[n].policy.weights[BULK] = weight
            self._state[n] = [util, queue_dim, loss_ema, g.value]

        self.oef_series.append((t, oef_sum / self.sim.topo.n_nodes, total_cbf,
                                oef_max_node))
        n_nodes = self.sim.topo.n_nodes
        self.state_series.append((t, util_sum / n_nodes, queue_sum / n_nodes,
                                  loss_sum / n_nodes, oef_sum / n_nodes))

    def on_tick(self, t, obs):
        dt = self._dt(t)
        self._oef_step(t, dt)
        self._release(t, obs)
        self._detect(t, obs)         # the inherited scalar (1-D) trigger
        self._top_up(t, obs)


#: Backwards-compatible name -- the class previously lived in
#: ``simulation.surgical.homeostasis``.
OefSurgicalController = OefController
