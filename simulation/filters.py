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

"""Dual-band filtering for DDoS detection (M7, H13/H14).

A dual-band filter separates a raw rate signal into two bands:

    LPF(t) = alpha * raw(t) + (1 - alpha) * LPF(t-1)     low-pass (baseline)
    HPF(t) = raw(t) - LPF(t)                             high-pass (residual)

The LPF is the EWMA from the 2010 thesis; it tracks the *normal* traffic and
lags (filters out) a sudden shockwave.  The HPF is the residual -- the sudden
change the LPF did not absorb -- and is therefore a derivative-like spike
detector.

Detection uses a dynamic, self-normalising threshold plus a stability gate::

    trigger  <=>  HPF(t) > k * noise_std        (the spike is k sigma above the
                                                 residual noise floor)
              AND LPF is stable                  (the baseline is not itself
                                                 ramping through a transient)

``noise_std`` is the rolling standard deviation of the residual ``HPF`` over a
window -- the standard deviation of the signal *around* the LPF baseline, i.e.
the "standard deviation of the LPF baseline" named in the goal.  Everything is a
pure function of the observed rate; nothing reads the attack schedule or flow
labels (anti-cheat: no hardcoded DDoS signature).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


class LpfEwma:
    """First-order low-pass (EWMA) filter: the baseline tracker."""

    __slots__ = ("alpha", "value")

    def __init__(self, tau: float, dt: float):
        # alpha = 1 - exp(-dt/tau); tau<=0 collapses to "raw" (alpha=1).
        self.alpha = 1.0 - math.exp(-dt / max(tau, 1e-9)) if tau > 0 else 1.0
        self.value = None

    def update(self, raw: float) -> float:
        if self.value is None:
            self.value = raw
        else:
            self.value += self.alpha * (raw - self.value)
        return self.value


@dataclass(frozen=True)
class DualBandResult:
    """One dual-band filter evaluation."""

    raw: float
    lpf: float
    hpf: float
    noise_std: float
    threshold: float
    stable: bool
    triggered: bool


class DualBandFilter:
    """LPF + HPF with a k-sigma dynamic threshold and a stability gate."""

    __slots__ = ("tau_lpf", "dt", "k", "window", "floor_abs", "lpf",
                 "_t", "_raw", "_hpf", "last")

    def __init__(self, tau_lpf: float = 2.0, dt: float = 0.2, k: float = 3.0,
                 window: float = 6.0, floor_abs: float = 0.02):
        self.tau_lpf = tau_lpf
        self.dt = dt
        self.k = k
        self.window = window
        self.floor_abs = floor_abs
        self.lpf = LpfEwma(tau_lpf, dt)
        self._t: list[float] = []
        self._raw: list[float] = []
        self._hpf: list[float] = []
        self.last: DualBandResult | None = None

    def update(self, t: float, raw: float) -> DualBandResult:
        lpf = self.lpf.update(raw)
        hpf = raw - lpf

        self._t.append(t)
        self._raw.append(raw)
        self._hpf.append(hpf)
        while self._t and self._t[0] < t - self.window:
            self._t.pop(0)
            self._raw.pop(0)
            self._hpf.pop(0)

        n = len(self._hpf)
        # residual noise floor = rolling std of HPF ("std of the LPF baseline")
        noise_std = float(np.std(self._hpf)) if n >= 2 else 0.0
        threshold = max(self.floor_abs, self.k * noise_std)

        # "LPF stable": enough history, and the baseline has not drifted by more
        # than the threshold across the window (it is not itself mid-transient).
        # The LPF at the window start is lpf_0 = raw_0 - hpf_0, so the drift is
        # |lpf_t - lpf_0|.
        lpf_0 = self._raw[0] - self._hpf[0] if n else 0.0
        stable = n >= 4 and abs(lpf - lpf_0) <= threshold

        triggered = stable and hpf > threshold
        self.last = DualBandResult(raw=raw, lpf=lpf, hpf=hpf, noise_std=noise_std,
                                   threshold=threshold, stable=stable,
                                   triggered=triggered)
        return self.last

    @property
    def series(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(t, raw, lpf, hpf) time series as arrays."""
        return (np.asarray(self._t, dtype=float),
                np.asarray(self._raw, dtype=float),
                np.asarray([r - h for r, h in zip(self._raw, self._hpf)], dtype=float),
                np.asarray(self._hpf, dtype=float))


class LpfOnlyFilter:
    """Single LPF baseline with a *fixed* residual threshold (the H13 baseline).

    This is the "only EWMA, no HPF" arm: it uses the same LPF as
    :class:`DualBandFilter` but detects with a fixed absolute threshold instead
    of the dynamic k-sigma threshold, so it has no noise-adaptive HPF gate.
    """

    __slots__ = ("lpf", "fixed_threshold", "last_triggered")

    def __init__(self, tau_lpf: float = 2.0, dt: float = 0.2,
                 fixed_threshold: float = 0.10):
        self.lpf = LpfEwma(tau_lpf, dt)
        self.fixed_threshold = fixed_threshold
        self.last_triggered = False

    def update(self, t: float, raw: float) -> DualBandResult:
        lpf = self.lpf.update(raw)
        hpf = raw - lpf
        triggered = hpf > self.fixed_threshold
        self.last_triggered = triggered
        return DualBandResult(raw=raw, lpf=lpf, hpf=hpf, noise_std=0.0,
                              threshold=self.fixed_threshold, stable=True,
                              triggered=triggered)
