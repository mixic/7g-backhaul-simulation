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

"""Dual-band (LPF + HPF) DDoS controller (M7, H13/H14).

Per node, a :class:`~simulation.filters.DualBandFilter` splits the normalised
served rate (utilization) into a low-pass baseline and a high-pass residual.
When the high-pass energy crosses its dynamic threshold while the baseline is
stable, the controller executes Random Early Redirection (RER) followed by the
surgical isolation edit -- the same actuators as the MKB/EWMA controllers, so the
arms differ only in the *trigger*.

The raw signal is the node's served-byte rate normalised by its capacity.  It is
read from ``NodeTelemetry.served_bytes``; the controller never reads the attack
schedule or ``flow.kind`` (anti-cheat: detection is a pure function of the
observed rate).
"""

from __future__ import annotations

from .filters import DualBandFilter, LpfOnlyFilter
from .surgical.config import DUAL_BAND, LPF_ONLY
from .surgical.controllers import SurgicalController


class DualBandController(SurgicalController):
    """Surgical isolation + RER, triggered by the dual-band (LPF+HPF) filter."""

    name = DUAL_BAND

    def __init__(self, cfg, sim, filter_class=DualBandFilter):
        super().__init__(cfg, sim)
        self.filters = {
            n: filter_class(
                tau_lpf=cfg.db_tau_lpf, dt=cfg.tick, k=cfg.db_k,
                window=cfg.db_window, floor_abs=cfg.db_floor_abs)
            if filter_class is DualBandFilter
            else filter_class(tau_lpf=cfg.db_tau_lpf, dt=cfg.tick,
                              fixed_threshold=cfg.db_fixed_threshold)
            for n in range(sim.topo.n_nodes)
        }
        self._cbf_samples = {n: [] for n in range(sim.topo.n_nodes)}
        self.detections = []        # (t, node) every HPF trigger
        self.dual_band_spikes = []  # (t, node) full surgical edits
        self.rer_events = []        # (t, node) Random Early Redirection
        self.filter_series = []     # (t, hot_raw, hot_lpf, hot_hpf)

    def on_tick(self, t, obs):
        dt = self._dt(t)
        self._release(t, obs)
        self._detect_dual_band(t, dt)
        self._top_up(t, obs)

    def _raw_rate(self, n: int, t: float) -> float:
        """Per-node served rate over a 1 s window, normalised to utilization.

        A single 0.2 s tick of served bytes is quantised at whole 400 kB batches
        (and is zero whenever a tick holds no arrival), which makes its residual
        heavy-tailed and trips a sigma threshold on pure Poisson jitter.  The 1 s
        window is the same smoothing the OEF controller already uses for its CBF
        baseline, and keeps the raw signal a genuine *rate*.
        """
        tel = self.sim.tele[n]
        samples = self._cbf_samples[n]
        samples.append((t, tel.served_bytes))
        while samples and samples[0][0] < t - 1.0:
            samples.pop(0)
        if len(samples) >= 2:
            span = samples[-1][0] - samples[0][0]
            cbf = (samples[-1][1] - samples[0][1]) / span if span > 0 else 0.0
        else:
            cbf = 0.0
        cap = self.sim.topo.node_cap[n] / 8.0   # B/s
        if cap <= 0:
            return 0.0
        return min(1.0, cbf / cap)

    def _detect_dual_band(self, t, dt):
        cfg = self.cfg
        n_nodes = self.sim.topo.n_nodes
        raw_sum = lpf_sum = hpf_sum = 0.0
        for n in range(n_nodes):
            raw = self._raw_rate(n, t)
            result = self.filters[n].update(t, raw)
            raw_sum += raw
            lpf_sum += result.lpf
            hpf_sum += result.hpf
            if not result.triggered:
                continue
            # Do not arm during cold start: before the baseline settles the
            # residual is an artifact of the initial ramp (same guard as the
            # scalar surgical trigger).
            if t < cfg.warmup:
                continue
            self.detections.append((t, n))
            e = self.active.get(n)
            if e is not None and e["phase"] == "in":
                continue
            flow = self._attribute(n, t)
            if flow is None:
                continue
            self._rer(t, n, flow)
            self.dual_band_spikes.append((t, n))
            self._apply(t, flow, n)
        # network-mean band series (single scalar per tick, for the plot)
        self.filter_series.append((t, raw_sum / n_nodes, lpf_sum / n_nodes,
                                   hpf_sum / n_nodes))

    def _rer(self, t, n, flow):
        """Probabilistic Random Early Redirection of one affected flow."""
        if self.sim.rng.random() >= self.cfg.mkb_rer_prob:
            return
        alt = self.sim.best_alternate(n, flow)
        if alt is None or not self._spend(n, 0.25, t):
            return
        self.sim.set_flow_override(n, flow, alt)
        self.sim.invalidate_paths()
        self._vcache.clear()
        self.rer_events.append((t, n))


class LpfOnlyController(DualBandController):
    """Single-LPF baseline arm: same actuator, fixed residual threshold (H13)."""

    name = LPF_ONLY

    def __init__(self, cfg, sim):
        super().__init__(cfg, sim, filter_class=LpfOnlyFilter)
