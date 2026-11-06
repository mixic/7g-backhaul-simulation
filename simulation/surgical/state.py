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

"""The state plane: what a surgical edit is allowed to touch.

Node state vector S = (alpha, queue_policy, fib_overrides)

  alpha            role fraction  (0 = pure router, 1 = pure cache/server)
  queue_policy     per-class queue weights and byte limits
  fib_overrides    per-flow next-hop overrides in the local FIB

Every mutation goes through StateLedger.record(), which is the only place that
computes state-change SPEED and ACCELERATION.  Those two numbers are the
dependent variables of H2, so they must be measured at the point of edit and
nowhere else.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_ALPHA_SCALE = 1.0
_LIMIT_SCALE = 1.0
_WEIGHT_SCALE = 1.0
_FIB_SCALE = 0.25


class QueuePolicy:
    """Per-node WFQ/drop-tail policy, shared by all of that node's egress links."""

    __slots__ = ("total_scale", "weights", "limits", "classes")

    def __init__(self):
        self.total_scale = 1.0         # multiplier on nominal link buffer
        self.weights = {}              # class -> weight (default 1.0)
        self.limits = {}               # class -> fraction of nominal buffer
        self.classes = set()

    def weight(self, cls: int) -> float:
        return self.weights.get(cls, 1.0)

    def limit_frac(self, cls: int) -> float:
        return self.limits.get(cls, 1.0)

    def make_class(self, cls: int) -> bool:
        if cls in self.classes:
            return False
        self.classes.add(cls)
        return True

    def cls_for(self, content: int, region: int) -> int:
        """Class selector used at enqueue time.

        A class identity is a name-based match: content name + source region.
        If the controller has not promoted it, the flow rides the bulk FIFO.
        """
        cid = 1 + content * 8 + region
        return cid if cid in self.classes else 0

    def drop_class(self, cls: int) -> None:
        self.classes.discard(cls)
        self.weights.pop(cls, None)
        self.limits.pop(cls, None)


@dataclass
class NodeState:
    node: int
    alpha: float
    policy: QueuePolicy
    fib_flow: dict = field(default_factory=dict)   # (flow_id, content) -> (node, nh)

    def state_norm(self) -> float:
        """Scalar magnitude of the editable state (for reporting only)."""
        return (self.alpha
                + sum(self.policy.weights.values())
                + sum(self.policy.limits.values())
                + _FIB_SCALE * len(self.fib_flow))


@dataclass
class Edit:
    t: float
    node: int
    component: str
    key: object
    old: float
    new: float
    magnitude: float


class StateLedger:
    """Records every edit and derives speed / acceleration of state change.

    speed(t) = |dS| / dt          (normalised state units per second)
    accel(t) = |dspeed| / dt      (normalised state units per second^2)
    """

    def __init__(self):
        self.edits = []          # list[Edit]
        self.series = []         # (t, node, speed, accel, magnitude)
        self._last_t = {}
        self._last_speed = {}

    def record(self, t: float, node: int, component: str, key, old, new,
               scale: float) -> float:
        mag = abs(float(new) - float(old)) / scale
        if mag <= 0.0:
            return 0.0
        self.edits.append(Edit(t, node, component, key, float(old), float(new), mag))
        last = self._last_t.get(node, 0.0)
        dt = max(t - last, 1e-3)
        speed = mag / dt
        prev_speed = self._last_speed.get(node, 0.0)
        accel = abs(speed - prev_speed) / dt
        self._last_t[node] = t
        self._last_speed[node] = speed
        self.series.append((t, node, speed, accel, mag))
        return mag

    # convenience wrappers -- all edits must land in the ledger -------------
    def set_alpha(self, t, state: NodeState, new_alpha: float) -> float:
        old = state.alpha
        state.alpha = new_alpha
        return self.record(t, state.node, "alpha", "alpha", old, new_alpha,
                           _ALPHA_SCALE)

    def set_weight(self, t, state: NodeState, cls: int, new_w: float) -> float:
        old = state.policy.weight(cls)
        state.policy.weights[cls] = new_w
        return self.record(t, state.node, "weight", cls, old, new_w, _WEIGHT_SCALE)

    def set_limit(self, t, state: NodeState, cls: int, new_lim: float) -> float:
        old = state.policy.limit_frac(cls)
        state.policy.limits[cls] = new_lim
        return self.record(t, state.node, "limit", cls, old, new_lim, _LIMIT_SCALE)

    def set_total_scale(self, t, state: NodeState, new_s: float) -> float:
        old = state.policy.total_scale
        state.policy.total_scale = new_s
        return self.record(t, state.node, "total_scale", "*", old, new_s,
                           _LIMIT_SCALE)

    def set_flow_fib(self, t, state: NodeState, flow_id: int, content: int,
                     nexthop, scale: float = _FIB_SCALE):
        key = (flow_id, content)
        old = state.fib_flow.get(key)
        state.fib_flow[key] = (state.node, nexthop) if nexthop is not None else None
        oldv = 0.0 if old is None else 1.0
        newv = 1.0 if nexthop is not None else 0.0
        return self.record(t, state.node, "fib", key, oldv, newv, scale)

    # ------------------------------------------------------------------
    def churn_series(self, duration: float, dt: float = 0.25):
        """Aggregate state-change speed/acceleration onto a uniform grid."""
        import numpy as np
        n = int(round(duration / dt)) + 1
        speed = np.zeros(n)
        accel = np.zeros(n)
        mag = np.zeros(n)
        if self.edits:
            for (t, node, sp, ac, m) in self.series:
                i = min(n - 1, max(0, int(round(t / dt))))
                speed[i] += sp * dt      # integral of speed = total |dS| this bin
                accel[i] = max(accel[i], ac)
                mag[i] += m
        return np.arange(n) * dt, speed, accel, mag
