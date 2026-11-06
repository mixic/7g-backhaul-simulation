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

"""Control laws: the layer the vision paper leaves unspecified.

Every controller sees the same observations (pressure p, velocity v, acceleration
a, per-flow ingress rates) and the same queueing substrate.  They differ only in
(i) where they act -- one flow, one node, the whole network -- and
(ii) how fast they are allowed to move the state.

  k8s              Baseline A: static roles + slow central scaler
  pressure         Baseline B: the prior iteration's global alpha controller,
                   reproduced verbatim (alpha0=0.5, damping 0.5, trend gains
                   0.5/0.3, control period 2 ticks) and never given queues
  pressure_tuned   Baseline B given its best shot: alpha0 = initial role,
                   signed release, faster period
  surgical         kinematic trigger -> ONE (name, region) class at ONE node,
                   ramped through a double-integrator rate governor, held by
                   hysteresis
  surgical_unlimited   same, no speed/acceleration cap, no hysteresis
  surgical_ab      same, alpha-beta filter trigger
  surgical_global  same trigger + caps, but the edit lands on the whole node
  static_isolation per-flow isolation always on for every flow (FQ-CoDel style):
                   the confound control for H1
  vdr              spatial target: loop-free potential-gradient flux field,
                   installed the instant it is computed
  vdr_surgical     the SAME target field, installed through the rate governor
"""
from __future__ import annotations

import heapq
import math

import numpy as np

from .config import (K8S, MKB, MKB_EWMA, MKB_NO_OEF, OEF, PRESSURE, SAVANT,
                     STATIC_ISO, SURGICAL, SURGICAL_AB, SURGICAL_GLOBAL,
                     SURGICAL_UNLIM)
from .link import class_id

VDR = "vdr"
VDR_SURGICAL = "vdr_surgical"
PRESSURE_TUNED = "pressure_tuned"


# ----------------------------------------------------------------------
# Rate governor: a double integrator with explicit speed and acceleration
# caps.  This IS the contribution -- the map from observations to a bounded
# state trajectory.
# ----------------------------------------------------------------------
class Governor:
    __slots__ = ("value", "vel", "target", "vmax", "amax")

    def __init__(self, value, vmax, amax):
        self.value = float(value)
        self.vel = 0.0
        self.target = float(value)
        self.vmax = vmax
        self.amax = amax

    def step(self, dt):
        err = self.target - self.value
        v_des = max(-self.vmax, min(self.vmax, 6.0 * err))
        dv = max(-self.amax * dt, min(self.amax * dt, v_des - self.vel))
        self.vel += dv
        self.value += self.vel * dt
        if abs(self.target - self.value) < 1e-5 and abs(self.vel) < 1e-5:
            self.value = self.target
            self.vel = 0.0
        return abs(self.vel), abs(dv) / dt if dt > 0 else 0.0

    @property
    def done(self):
        return abs(self.target - self.value) < 1e-5 and abs(self.vel) < 1e-5


class Controller:
    name = "base"
    governor_series = None

    def __init__(self, cfg, sim):
        self.cfg = cfg
        self.sim = sim
        self._last_t = 0.0
        self._log = []

    def on_tick(self, t, obs):
        raise NotImplementedError

    def _dt(self, t):
        dt = t - self._last_t
        self._last_t = t
        return dt if dt > 0 else self.cfg.tick

    @property
    def governor_series(self):
        return np.asarray(self._log, dtype=np.float64) if self._log else np.zeros((0, 4))


# ----------------------------------------------------------------------
# Baseline A: Kubernetes-style.  Static roles, slow central scaling loop.
# ----------------------------------------------------------------------
class K8sController(Controller):
    name = K8S

    def __init__(self, cfg, sim):
        super().__init__(cfg, sim)
        self._next = 0.0

    def on_tick(self, t, obs):
        cfg = self.cfg
        if t < self._next:
            return
        self._next = t + cfg.k8s_period
        p = self.sim.node_pressure
        if not p:
            return
        mean_p = float(np.mean(list(p.values())))
        if mean_p < cfg.k8s_target_util * 0.5:
            return
        # central scaler: free forwarding capacity at the busiest transit nodes
        order = sorted(p.items(), key=lambda kv: -kv[1])[:8]
        for node, pn in order:
            st = self.sim.states[node]
            if pn > cfg.k8s_target_util and st.alpha > 0.02:
                step = min(cfg.k8s_max_step, st.alpha)
                self.sim.set_alpha(node, st.alpha - step)


# ----------------------------------------------------------------------
# Baseline B: the previous iteration's naive global controller, verbatim.
# ----------------------------------------------------------------------
class PressureController(Controller):
    name = PRESSURE

    def __init__(self, cfg, sim, tuned=False):
        super().__init__(cfg, sim)
        self.tuned = tuned
        self.alpha0 = None          # None -> node's initial role (tuned)
        self.hist = {n: [] for n in range(sim.topo.n_nodes)}
        self._next = 0.0
        self.period = 2.0 if not tuned else 1.0
        self.damping = 0.5 if not tuned else 0.35
        self.w_v = 0.5
        self.w_a = 0.3
        self.vel_ref = 0.05
        self.acc_ref = 0.01
        self.w_p = 1.0
        self.gain = 1.0
        self.signed = tuned

    def on_tick(self, t, obs):
        if t < self._next:
            return
        self._next = t + self.period
        dt = self.period
        p_all = self.sim.node_pressure
        for n in range(self.sim.topo.n_nodes):
            h = self.hist[n]
            h.append(p_all.get(n, 0.0))
            if len(h) > 3:
                h.pop(0)
            p = h[-1]
            if len(h) >= 3:
                v = (h[-1] - h[-2]) / dt
                a = (h[-1] - 2.0 * h[-2] + h[-3]) / (dt * dt)
            else:
                v = a = 0.0
            if self.signed:
                tv = self.w_v * v / self.vel_ref
                ta = self.w_a * a / self.acc_ref
            else:
                tv = self.w_v * max(0.0, v) / self.vel_ref
                ta = self.w_a * max(0.0, a) / self.acc_ref
            hit = 0.15
            serve = self.w_p * p * hit + tv + ta
            a0 = 0.5 if self.alpha0 is None else self.alpha0[n]
            target = min(1.0, max(0.0, a0 + self.gain * serve))
            st = self.sim.states[n]
            new = (1.0 - self.damping) * st.alpha + self.damping * target
            if abs(new - st.alpha) > 1e-6:
                self.sim.set_alpha(n, new)


# ----------------------------------------------------------------------
# The thesis: kinematic trigger -> surgical, rate-capped, hysteretic edit.
# ----------------------------------------------------------------------
class SurgicalController(Controller):
    """Kinematic trigger -> surgical, rate-capped, hysteretic edit.

    Two kinds of rate control, deliberately different:

    * A **discrete edit** (promote one class to its own WFQ lane, flip one FIB
      entry) is applied in a single step -- the spec's "single sharp spike" --
      and is bounded by a *per-node token bucket*: each node may spend at most
      `edit_speed_max` normalised state units per second, with a burst of
      `edit_burst` units.  A node that has just fired an edit cannot fire
      another for |dS|/vmax seconds.  That is what stops churn.
    * A **continuous knob** (alpha, total buffer scale) is moved by a double
      integrator with explicit speed and acceleration caps (Governor).

    Both quantities end up in the ledger, so the H2 speed/acceleration series is
    measured, not asserted.
    """

    name = SURGICAL

    def __init__(self, cfg, sim, unlimited=False, global_edit=False):
        super().__init__(cfg, sim)
        self.unlimited = unlimited
        self.global_edit = global_edit
        self.active = {}
        self.govs = {}
        self._vcache = {}
        self._buckets = {}          # node -> [tokens, last_refill_t]
        self.edit_latency = []      # detection -> mitigation installed

    # -- per-node token bucket ------------------------------------------
    def _spend(self, node, cost, t):
        if self.unlimited:
            return True
        b = self._buckets.get(node)
        cap = self.cfg.edit_burst
        if b is None:
            b = self._buckets[node] = [cap, t]
        else:
            b[0] = min(cap, b[0] + self.cfg.edit_speed_max * (t - b[1]))
            b[1] = t
        if b[0] + 1e-9 < cost:
            return False
        b[0] -= cost
        return True

    # -- governors (continuous knobs only) ------------------------------
    def _gov(self, node, key, value, target):
        g = self.govs.get((node, key))
        if g is None:
            vmax, amax = self.cfg.edit_speed_max, self.cfg.edit_accel_max
            if self.unlimited:
                vmax = amax = 1e9
            g = Governor(value, vmax, amax)
            self.govs[(node, key)] = g
        g.target = target
        return g

    def _step_governors(self, t, dt):
        for (node, key), g in list(self.govs.items()):
            prev = g.value
            sp, ac = g.step(dt)
            if abs(g.value - prev) > 1e-7:
                self._log.append((t, float(node), sp, ac))
            if key[0] == "a":
                self.sim.set_alpha(node, g.value)
            elif key[0] == "s":
                self.sim.set_total_scale(node, g.value)

    # -- spike attribution ---------------------------------------------
    def _attribute(self, node, t):
        best, bestval = None, 0.0
        rts = self.sim.flow_rates
        for f in self.sim.flows:
            tr = rts[f.fid]
            if tr.a_res <= 0.0 or tr.v < 2.0:
                continue
            nodes = self._vcache.get(f.fid)
            if nodes is None:
                nodes = self._vcache[f.fid] = set(self.sim.flow_path(f))
            if node not in nodes:
                continue
            if tr.a_res > bestval:
                bestval, best = tr.a_res, f
        return best

    def on_tick(self, t, obs):
        dt = self._dt(t)
        if self.global_edit:
            self._step_governors(t, dt)
        self._release(t, obs)
        self._detect(t, obs)
        self._top_up(t, obs)

    def _cost(self):
        return abs(1.0 - self.cfg.iso_weight) + abs(1.0 - self.cfg.iso_limit_frac)

    def _edit(self, node, cls, t):
        """Install the isolation step on one node, if its budget allows."""
        if not self._spend(node, self._cost(), t):
            return False
        self.sim.enable_class(node, cls, 1.0, 1.0)
        self.sim.set_weight(node, cls, self.cfg.iso_weight)
        self.sim.set_limit(node, cls, self.cfg.iso_limit_frac)
        self.active[node] = {"phase": "in", "cls": cls,
                             "until": t + (0.0 if self.unlimited
                                           else self.cfg.edit_hold),
                             "p0": max(0.2, self.sim.node_pressure.get(node, 0.5))}
        return True

    def _release(self, t, obs):
        for node, e in list(self.active.items()):
            if e["phase"] != "in" or t < e["until"]:
                continue
            o = obs.get(node)
            p_now = self.sim.node_pressure.get(node, 0.0)
            # Is the culprit still arriving at this router?  Pressure alone
            # oscillates during a flood, so a pressure-only test would release
            # the mitigation in the middle of the attack -- and a released
            # class sits at neutral weight, which is worse than never isolating.
            flowing = self.sim.tele[node].cls_bytes.get(e["cls"], 0.0) if e["cls"] else 0.0
            if self.unlimited:
                calm = (o is not None) and o.a <= 0.0 and o.resid_a < o.thr_a * 0.5
            else:
                calm = ((o is not None) and o.a <= 0.0
                        and p_now < 0.55 * e["p0"] and flowing < 1.0)
            e["calm"] = e.get("calm", 0) + 1 if calm else 0
            need = 1 if self.unlimited else 5
            if not calm or e["calm"] < need:
                continue
            if self.global_edit:
                self._gov(node, ("s", 0), self.sim.states[node].policy.total_scale, 1.0)
                self._gov(node, ("a", 0), self.sim.states[node].alpha,
                          self.sim.topo.alpha0[node])
                e["phase"] = "out"
                continue
            if not self._spend(node, self._cost(), t):
                continue
            self.sim.set_weight(node, e["cls"], 1.0)
            self.sim.set_limit(node, e["cls"], 1.0)
            e["phase"] = "out"

    def _detect(self, t, obs):
        # Do not fire during cold start: before the baseline has settled, the
        # ramp from zero is a large acceleration and the trigger will isolate
        # whatever class happens to be arriving.  Arming is standard practice
        # for a controller whose threshold is derived from its own history.
        if t < self.cfg.warmup:
            return
        for node, o in obs.items():
            e = self.active.get(node)
            if e is not None and e["phase"] == "in":
                continue
            if not o.spike or o.a <= 0.0:
                continue
            flow = self._attribute(node, t)
            if flow is None:
                continue
            self._apply(t, flow, node)

    def _apply(self, t, flow, node):
        sim = self.sim
        cfg = self.cfg
        if self.global_edit:
            self.active[node] = {"phase": "in", "cls": None,
                                 "until": t + cfg.edit_hold,
                                 "p0": max(0.2, sim.node_pressure.get(node, 0.5))}
            self._gov(node, ("s", 0), sim.states[node].policy.total_scale, 0.35)
            self._gov(node, ("a", 0), sim.states[node].alpha,
                      min(0.95, sim.states[node].alpha + 0.15))
            return

        cls = class_id(flow.content, flow.region)
        # Scope: the routers this (content, source-region) class crosses, plus
        # any router already under pressure.  ~15 routers, exactly one class.
        # The ingress routers must be included or the flood enters as bulk
        # traffic at the other bots and the mitigation is cosmetic.
        targets = {node}
        for f in sim.flows:
            if class_id(f.content, f.region) == cls:
                targets.update(sim.flow_path(f))
        for n, p in sim.node_pressure.items():
            if p > 0.30:
                targets.add(n)
        for n in sorted(targets)[:24]:
            if n in self.active and self.active[n]["phase"] == "in":
                continue
            self._edit(n, cls, t)
        sim.cache_path_dirty()
        alt = sim.best_alternate(node, flow)
        if alt is not None and self._spend(node, 0.25, t):
            sim.set_flow_override(node, flow, alt)
            sim.invalidate_paths()
            self._vcache.clear()

    def _top_up(self, t, obs):
        """Propagate an active mitigation to newly congested routers."""
        if not self.active or self.global_edit:
            return
        cls = None
        for e in self.active.values():
            if e["cls"] is not None:
                cls = e["cls"]
                break
        if cls is None:
            return
        for n, p in self.sim.node_pressure.items():
            if p <= 0.30 or n in self.active:
                continue
            if cls in self.sim.states[n].policy.classes:
                continue
            if len(self.active) > 24:
                return
            self._edit(n, cls, t)

    def sweep(self):
        for node, e in list(self.active.items()):
            if e["phase"] != "out":
                continue
            if e["cls"] is not None:
                self.sim.disable_class(node, e["cls"])
            self.active.pop(node, None)


# ----------------------------------------------------------------------
# Confound control: isolation always on, for every flow, for free.
# ----------------------------------------------------------------------
class StaticIsolationController(Controller):

    def __init__(self, cfg, sim):
        super().__init__(cfg, sim)
        for f in sim.flows:
            for node in sim.flow_path(f):
                cls = class_id(f.content, f.region)
                sim.enable_class(node, cls, 1.0, cfg.static_iso_limit)

    def on_tick(self, t, obs):
        return


# ----------------------------------------------------------------------
# Spatial target (VDR-like) and its rate-controlled wrapper.
# ----------------------------------------------------------------------
class FluxController(Controller):
    """Loop-free potential-gradient flux field.

    For destination host h and node n, Phi_h(n) is a Dijkstra potential on
    pressure-weighted link costs.  The flux sends a flow strictly downhill on
    Phi_h, which guarantees loop-freedom by construction (every hop strictly
    decreases a non-negative potential).  That is the *spatial* contribution.

    `wrap=True` installs the identical target field through the double
    integrator, so the only difference between the two arms is temporal.
    """
    name = VDR

    def __init__(self, cfg, sim, wrap=False):
        super().__init__(cfg, sim)
        self.wrap = wrap
        self.name = VDR_SURGICAL if wrap else VDR
        self.period = 1.0
        self._next = 0.0
        self.plans = {}      # node -> {"flow": nh}
        self.govs = {}
        self._lam = 8.0

    def _phi(self):
        topo = self.sim.topo
        p = self.sim.node_pressure
        wants = sorted(set(topo.hosts.values()))
        out = {}
        for h in wants:
            dist = {n: math.inf for n in range(topo.n_nodes)}
            dist[h] = 0.0
            pq = [(0.0, h)]
            done = set()
            while pq:
                d, n = heapq.heappop(pq)
                if n in done:
                    continue
                done.add(n)
                for m in topo.adj[n]:
                    w = topo.links[(n, m)].metric * (1.0 + self._lam * p.get(m, 0.0))
                    nd = d + w
                    if nd < dist[m] - 1e-12:
                        dist[m] = nd
                        heapq.heappush(pq, (nd, m))
            out[h] = dist
        return out

    def on_tick(self, t, obs):
        dt = self._dt(t)
        if self.wrap:
            self._step_governors(t, dt)
        if t < self._next:
            return
        self._next = t + self.period
        phi = self._phi()
        topo = self.sim.topo
        by_node = {}
        for f in self.sim.flows:
            if not f.active(t):
                continue
            h = topo.hosts[f.content]
            dist = phi[h]
            path = self.sim.flow_path(f)
            for node in path[:-1]:
                best, bestd = None, math.inf
                for nb in topo.adj[node]:
                    if dist[nb] < dist[node] - 1e-12:
                        d = topo.links[(node, nb)].metric * (1.0 + self._lam * self.sim.node_pressure.get(nb, 0.0))
                        if d + dist[nb] < bestd:
                            bestd, best = d + dist[nb], nb
                if best is not None:
                    cur = self.sim.fib.next_hop(node, f.content, f.fid)
                    if best != cur:
                        by_node.setdefault(node, []).append((f, best))
        for node, items in by_node.items():
            if not self.wrap:
                for f, nh in items:
                    self.sim.set_flow_override(node, f, nh)
                self.sim.invalidate_paths()
                self._log.append((t, float(node), len(items) / 400.0, 0.0))
            else:
                self.plans[node] = {"items": items, "done": 0}
                key = (node, "flux")
                g = self.govs.get(key)
                if g is None:
                    g = Governor(0.0, self.cfg.edit_speed_max,
                                 self.cfg.edit_accel_max)
                    self.govs[key] = g
                g.value = 0.0
                g.vel = 0.0
                g.target = 1.0
                self._log.append((t, float(node), 0.0, 0.0))

    def _step_governors(self, t, dt):
        for (node, _), g in list(self.govs.items()):
            sp, ac = g.step(dt)
            plan = self.plans.get(node)
            if plan is None:
                continue
            n = len(plan["items"])
            want = min(n, int(round(g.value * n)))
            while plan["done"] < want:
                f, nh = plan["items"][plan["done"]]
                self.sim.set_flow_override(node, f, nh)
                plan["done"] += 1
            self._log.append((t, float(node), sp, ac))
            if plan["done"] >= n:
                self.govs.pop((node, _), None)
                self.plans.pop(node, None)
        self.sim.invalidate_paths()


def make_controller(cfg, sim):
    c = cfg.controller
    if c == K8S:
        return K8sController(cfg, sim)
    if c == PRESSURE:
        return PressureController(cfg, sim, tuned=False)
    if c == PRESSURE_TUNED:
        return PressureController(cfg, sim, tuned=True)
    if c == SURGICAL:
        return SurgicalController(cfg, sim)
    if c == SURGICAL_UNLIM:
        return SurgicalController(cfg, sim, unlimited=True)
    if c == SURGICAL_AB:
        return SurgicalController(cfg, sim)
    if c == SURGICAL_GLOBAL:
        return SurgicalController(cfg, sim, global_edit=True)
    if c == STATIC_ISO:
        return StaticIsolationController(cfg, sim)
    if c == VDR:
        return FluxController(cfg, sim, wrap=False)
    if c == VDR_SURGICAL:
        return FluxController(cfg, sim, wrap=True)
    if c == SAVANT:
        from simulation.savant.controller import SavantController
        return SavantController(cfg, sim)
    if c in (OEF, MKB, MKB_NO_OEF, MKB_EWMA):
        from .homeostasis import make_homeostasis_controller
        controller = make_homeostasis_controller(cfg, sim)
        if controller is not None:
            return controller
    raise ValueError(f"unknown controller {c}")
