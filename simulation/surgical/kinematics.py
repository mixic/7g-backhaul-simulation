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

"""Kinematic monitor: moving baselines of velocity and acceleration.

Velocity  v(t) = arrival rate (requests/s)
Accel     a(t) = dv/dt (requests/s^2)
Baseline  EMA(v), EMA(a) over a sliding window (exponentially weighted).

Two estimators are provided so the testbed can compare them:

  EmaMonitor  -- plain exponentially weighted baseline (the thesis default)
  ABMonitor   -- alpha-beta filter.  The alpha-beta filter propagates a
                 position/velocity pair and predicts the next sample; the
                 innovation (measured - predicted) drives the spike trigger.
                 This is the estimator the 2018 RTT-filter patent argues for,
                 and it is included as an ablation rather than assumed better.

Both expose the same interface: .update(t, v) -> Observation
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass


@dataclass
class Observation:
    t: float
    v: float          # measured velocity
    a: float          # measured acceleration
    v_base: float     # baseline velocity
    a_base: float     # baseline acceleration
    resid_v: float    # |v - v_base|
    resid_a: float    # |a - a_base|
    thr_a: float      # adaptive acceleration threshold
    thr_v: float      # adaptive velocity threshold
    spike: bool       # |a - a_base| > thr_a  (the mandate of the design)
    ramp: bool        # velocity elevated but acceleration quiet -> smooth scale


class KinematicMonitor:
    """Shared adaptive-threshold machinery."""

    def __init__(self, tau_v: float = 1.0, tau_a: float = 1.0, dt: float = 0.1):
        self.tau_v = tau_v
        self.tau_a = tau_a
        self.dt = dt
        # residual baselines use a long time constant so they track the noise
        # floor, not the spike itself.
        self.tau_r = 10.0
        self.v_base = 0.0
        self.a_base = 0.0
        self.resid_v_base = 0.0
        self.resid_a_base = 0.0
        self.a = 0.0
        self._v_prev = None
        self._t_prev = None
        self._init = False
        self._own_baseline = False   # filter supplies v_base itself
        self.spike_k = 4.0
        self.floor_a = 400.0
        self.floor_v = 60.0

    # -- helpers ---------------------------------------------------------
    def _alpha(self, tau: float, dt: float) -> float:
        if tau <= 0:
            return 1.0
        return 1.0 - math.exp(-dt / tau)

    def configure_trigger(self, k: float, floor_a: float, floor_v: float) -> None:
        self.spike_k = k
        self.floor_a = floor_a
        self.floor_v = floor_v

    def _finish(self, t: float, v: float) -> Observation:
        alpha_a = self._alpha(self.tau_a, self.dt)
        alpha_v = self._alpha(self.tau_v, self.dt)
        alpha_r = self._alpha(self.tau_r, self.dt)

        resid_v = abs(v - self.v_base)
        resid_a = abs(self.a - self.a_base)

        # adaptive thresholds: k * EWMA(|residual|), floored so that an
        # entirely idle node cannot trip on numerical dust.
        thr_a = max(self.floor_a, self.spike_k * self.resid_a_base)
        thr_v = max(self.floor_v, self.spike_k * self.resid_v_base)

        spike = resid_a > thr_a
        ramp = (not spike) and resid_v > thr_v and self.a > 0

        # update baselines AFTER evaluating the current sample
        if not self._own_baseline:
            self.v_base += alpha_v * (v - self.v_base)
        self.a_base += alpha_a * (self.a - self.a_base)
        self.resid_v_base += alpha_r * (resid_v - self.resid_v_base)
        self.resid_a_base += alpha_r * (resid_a - self.resid_a_base)

        return Observation(t=t, v=v, a=self.a, v_base=self.v_base,
                           a_base=self.a_base, resid_v=resid_v,
                           resid_a=resid_a, thr_a=thr_a, thr_v=thr_v,
                           spike=spike, ramp=ramp)


class EmaMonitor(KinematicMonitor):
    """EMA baseline + finite-difference acceleration."""

    name = "ema"

    def update(self, t: float, v: float) -> Observation:
        if self._v_prev is None:
            self._v_prev, self._t_prev = v, t
            self.v_base = v
            self.a_base = 0.0
            return self._finish(t, v)
        dt = max(t - self._t_prev, 1e-9)
        self.a = (v - self._v_prev) / dt
        self._v_prev, self._t_prev = v, t
        return self._finish(t, v)


class RateTracker:
    """Compact per-flow ingress kinematics (measured, not stipulated).

    The controller samples ingress request counts every 0.5 s and feeds the
    resulting rate here.  No controller is allowed to read `flow.kind`.
    """

    __slots__ = ("_av", "_aa", "_ar", "v", "v_base", "a", "a_base",
                 "a_res", "rv_res", "_prev", "_tprev", "init")

    def __init__(self, dt: float, tau_v: float = 1.0, tau_a: float = 1.0):
        self._av = 1.0 - math.exp(-dt / max(tau_v, 1e-6))
        self._aa = 1.0 - math.exp(-dt / max(tau_a, 1e-6))
        self._ar = 1.0 - math.exp(-0.5 / 8.0)
        self.v = 0.0
        self.v_base = 0.0
        self.a = 0.0
        self.a_base = 0.0
        self.a_res = 0.0
        self.rv_res = 0.0
        self._prev = 0.0
        self._tprev = 0.0
        self.init = False

    def update(self, t: float, v: float) -> None:
        if not self.init:
            self.init = True
            self.v = v
            self.v_base = v
            self._prev = v
            self._tprev = t
            return
        dt = max(t - self._tprev, 1e-6)
        a = (v - self._prev) / dt
        self._prev = v
        self._tprev = t
        self.v = v
        self.a = a
        self.v_base += self._av * (v - self.v_base)
        self.a_base += self._aa * (a - self.a_base)
        self.a_res += self._ar * (abs(a - self.a_base) - self.a_res)
        self.rv_res += self._ar * (abs(v - self.v_base) - self.rv_res)


class ABMonitor(KinematicMonitor):
    """alpha-beta filter: a position/velocity state, no EWMA baseline.

    x_{k+1} = x_k + v_k * dt
    r       = z_k - x_k                 (innovation)
    x_k    += alpha_ab * r
    v_k    += beta_ab * r / dt
    """

    name = "ab"

    def __init__(self, tau_v: float = 1.0, tau_a: float = 1.0, dt: float = 0.1,
                 alpha_ab: float = 0.60, beta_ab: float = 0.45):
        super().__init__(tau_v, tau_a, dt)
        self.alpha_ab = alpha_ab
        self.beta_ab = beta_ab
        self.x = None
        self.v_hat = 0.0
        self._own_baseline = False

    def update(self, t: float, v: float) -> Observation:
        if self.x is None:
            self.x = v
            self.v_hat = 0.0
            self.v_base = 0.0
            self.a_base = 0.0
            self._prev = v
            self._tprev = t
            return self._finish(t, 0.0)
        dt = max(t - self._tprev, 1e-9) if self._tprev is not None else self.dt
        self._tprev = t
        # predict
        x_pred = self.x + self.v_hat * dt
        r = v - x_pred
        # correct
        self.x = x_pred + self.alpha_ab * r
        v_prev = self.v_hat
        self.v_hat = self.v_hat + self.beta_ab * r / dt
        self.a = (self.v_hat - v_prev) / dt
        # The filter's velocity estimate is the measured velocity; its baseline
        # is the EWMA of that estimate, exactly as in the EMA monitor.  Mixing
        # units here (pressure vs 1/s) would silently disable the trigger.
        return self._finish(t, self.v_hat)


class ArrivalAccelerometer:
    """Second derivative of the arrival-count process, from raw timestamps.

    The anti-cheat rule requires the acceleration to be computed from raw arrival
    times, never from smoothed averages.  ``note(t)`` records a raw arrival;
    ``sample(t, dt)`` returns

        a(t) = ( N(t) - 2 N(t-dt) + N(t-2dt) ) / dt^2

    where ``N(x)`` is the number of arrivals in ``(x - window, x]``.  This is a
    finite difference of an unsmoothed counting process, so it is noisy by
    construction; that is the point.
    """

    __slots__ = ("window", "_times")

    def __init__(self, window: float = 1.0):
        self.window = window
        self._times: list = []

    def note(self, t: float) -> None:
        bisect.insort(self._times, t)

    def _count(self, t: float) -> int:
        return (bisect.bisect_right(self._times, t)
                - bisect.bisect_right(self._times, t - self.window))

    def sample(self, t: float, dt: float) -> float:
        n0 = self._count(t)
        n1 = self._count(t - dt)
        n2 = self._count(t - 2.0 * dt)
        return (n0 - 2.0 * n1 + n2) / (dt * dt)
