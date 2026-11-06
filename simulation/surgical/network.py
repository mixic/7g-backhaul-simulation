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

"""SimPy discrete-event core for the heterogeneous 7G backhaul mesh.

Observation layer (from the vision paper)
----------------------------------------
Per node, a normalised pressure indicator

    p(t) = clip(0.70 u + 0.20 q/(d+q+1) + 0.10 loss, 0, 1)

with velocity v = dp/dt and acceleration a = d^2p/dt^2 by finite difference.
That is exactly the paper's quantity; this testbed adds the *control law* that
maps (p, v, a) to state changes.

Action layer (the contribution under test)
------------------------------------------
Controllers mutate S = (alpha, queue policy, FIB overrides) only through the
SimRun edit API, so every change is recorded by the StateLedger.

Traffic is simulated as coalesced batches: one SimPy event carries `batch`
requests of one name from one source region.  That is a flow-level device, not
a packet-level one -- the design mandate is explicitly not to micromanage.
"""
from __future__ import annotations

import math
import random

import numpy as np
import simpy

from .config import (K8S, PRESSURE, SAT, SURGICAL, SURGICAL_AB, SURGICAL_GLOBAL,
                     SURGICAL_UNLIM, STATIC_ISO)
from .kinematics import ABMonitor, EmaMonitor, RateTracker
from .link import (BULK, Item, OutputQueue, R_LOSS, R_LOOP, R_REORDER,
                   R_TOTAL, class_id)
from .state import NodeState, QueuePolicy, StateLedger
from .topology import Fib, build_topology
from .traffic import Demand, build_flows

REORDER_BYTES = 3_145_728    # reassembly (reorder) window at the boundary, bytes
REORDER_SLOTS = 24           # concurrent objects that can be reassembled
REORDER_TIMEOUT = 1.0        # HOL hold time before an incomplete object is dropped
MAX_HOPS = 24


class NodeTelemetry:
    __slots__ = ("served_bytes", "queued_bytes", "drops", "arrived", "cls_bytes")

    def __init__(self):
        self.served_bytes = 0.0
        self.queued_bytes = 0.0
        self.drops = 0
        self.arrived = 0
        # per-class bytes enqueued during the current control tick; this is the
        # per-class queue telemetry that makes a FlowSpec-style multi-router
        # edit possible without touching unrelated flows.
        self.cls_bytes = {}

class Batch:
    __slots__ = ("flow", "size", "count", "t0")

    def __init__(self, flow, size, count, t0):
        self.flow = flow
        self.size = size
        self.count = count
        self.t0 = t0


class SimRun:
    def __init__(self, cfg):
        self.cfg = cfg
        self.env = simpy.Environment()
        self.rng = random.Random(cfg.seed)
        self.np_rng = np.random.default_rng(cfg.seed + 7919)
        self.topo = build_topology(cfg.n_content, cfg.zipf_s, cfg.force_satellite,
                                   cfg.seed)
        self.fib = Fib(self.topo, self)
        self.states = {n: NodeState(n, self.topo.alpha0[n], QueuePolicy())
                       for n in range(self.topo.n_nodes)}
        self.tele = {n: NodeTelemetry() for n in range(self.topo.n_nodes)}
        self.ledger = StateLedger()
        self.egress = {}
        for (a, b), link in self.topo.links.items():
            self.egress[(a, b)] = OutputQueue(
                self.env, link, self.states[a], self.rng, a,
                self.topo.node_cap[a], self.tele[a])
        for q in self.egress.values():
            self.env.process(q._serve())

        self.flows, self.attack_target = build_flows(cfg, self.topo, self.np_rng)
        self.flow_by_id = {f.fid: f for f in self.flows}
        self.demand = Demand(self.flows, cfg.load_wave_amp, cfg.load_wave_period,
                             cfg.load_step_times)
        self.reasm = simpy.Container(self.env, capacity=REORDER_BYTES, init=0.0)
        self.reasm_slots = simpy.Container(self.env, capacity=REORDER_SLOTS, init=0.0)

        # monitors
        Mon = ABMonitor if cfg.controller == SURGICAL_AB else EmaMonitor
        self.monitors = {n: Mon(cfg.kin_tau_v, cfg.kin_tau_a, cfg.tick)
                         for n in range(self.topo.n_nodes)}
        for m in self.monitors.values():
            m.configure_trigger(cfg.spike_k, cfg.spike_floor_a, cfg.spike_floor_v)
        self.flow_rates = {f.fid: RateTracker(cfg.tick, cfg.kin_tau_v, cfg.kin_tau_a)
                           for f in self.flows}

        self.path_cache = {}
        self.node_pressure = {}
        self._next_log = 0.0
        self._next_sample = 0.0
        self._flow_acc = {f.fid: 0 for f in self.flows}
        self._vcache = {}

        self._setup_metrics()
        from .controllers import make_controller
        self.controller = make_controller(cfg, self)
        self._flow_paths_at_enable = {}

    # ------------------------------------------------------------------
    def _setup_metrics(self):
        self.done_t = []
        self.done_fid = []
        self.done_kind = []
        self.done_lat = []
        self.done_cnt = []
        self.done_content = []
        self.drop_t = []
        self.drop_reason = []
        self.drop_cnt = []
        self.drop_node = []
        self.drop_kind = []
        self.disp_t = []
        self.disp_cnt = []
        self.disp_content = []
        self.series = []
        self._prev_served = {n: 0.0 for n in self.tele}
        self._prev_drops = {n: 0 for n in self.tele}
        self._prev_t = 0.0

    # ------------------------------------------------------------------
    # Edit API -- every mutation of the state plane goes through here.
    # ------------------------------------------------------------------
    def state(self, n) -> NodeState:
        return self.states[n]

    def enable_class(self, node, cls, weight, limit_frac):
        st = self.states[node]
        if not st.policy.make_class(cls):
            return 0.0
        m = 0.0
        m += self.ledger.set_weight(self.env.now, st, cls, weight)
        m += self.ledger.set_limit(self.env.now, st, cls, limit_frac)
        return m

    def disable_class(self, node, cls):
        st = self.states[node]
        if cls not in st.policy.classes:
            return 0.0
        self.ledger.set_weight(self.env.now, st, cls, 1.0)
        self.ledger.set_limit(self.env.now, st, cls, 1.0)
        st.policy.drop_class(cls)
        return 1.0

    def set_weight(self, node, cls, w):
        return self.ledger.set_weight(self.env.now, self.states[node], cls, w)

    def set_limit(self, node, cls, frac):
        return self.ledger.set_limit(self.env.now, self.states[node], cls, frac)

    def set_alpha(self, node, a):
        a = min(0.98, max(0.0, a))
        return self.ledger.set_alpha(self.env.now, self.states[node], a)

    def set_total_scale(self, node, s):
        return self.ledger.set_total_scale(self.env.now, self.states[node],
                                           min(2.0, max(0.02, s)))

    def set_flow_override(self, node, flow, nexthop):
        """Install or clear a per-flow FIB override (the surgical edit target).

        One override is 1/400 of a normalised state unit, so a full
        routing-table flush is ~1.0 unit and the governor's units stay
        comparable across knobs.
        """
        key = (flow.fid, flow.content)
        st = self.states[node]
        if nexthop is None:
            if key in st.fib_flow:
                st.fib_flow.pop(key)
        else:
            st.fib_flow[key] = (node, nexthop)
        return self.ledger.set_flow_fib(self.env.now, st, flow.fid, flow.content,
                                        nexthop, scale=0.0025)

    def cache_path_dirty(self):
        self.path_cache.clear()

    # ------------------------------------------------------------------
    def flow_path(self, flow):
        """Current hop list for a flow (walking the live FIB)."""
        key = (flow.fid, flow.content)
        cached = self.path_cache.get(key)
        if cached is not None:
            return cached
        node = flow.src
        dest = self.topo.hosts[flow.content]
        path = [node]
        for _ in range(MAX_HOPS):
            if node == dest:
                break
            nh = self.fib.next_hop(node, flow.content, flow.fid)
            if nh is None:
                break
            node = nh
            path.append(node)
        self.path_cache[key] = path
        return path

    def invalidate_paths(self):
        self.path_cache.clear()

    def class_nodes(self, cls: int, min_bytes: float = 0.0):
        """Nodes that enqueued traffic of `cls` during the last control tick.

        Per-class queue telemetry: it lets a FlowSpec-style rule be pushed to
        every router the attack actually crosses, while leaving every other
        class untouched.
        """
        return [n for n, tel in self.tele.items()
                if tel.cls_bytes.get(cls, 0.0) > min_bytes]

    def best_alternate(self, node, flow):
        """Best loop-free alternate that reduces pressure on the next hop."""
        alts = self.fib.alternates(node, flow.content)
        if not alts:
            return None
        current = self.fib.next_hop(node, flow.content, flow.fid)
        cur_p = self.node_pressure.get(current, 0.0)
        best, best_score = None, -1e9
        for dist, nb in alts[:3]:
            p = self.node_pressure.get(nb, 0.0)
            score = (cur_p - p) - 1e-3 * dist
            if score > best_score:
                best_score, best = score, nb
        return best if best_score > 0 else None

    # ------------------------------------------------------------------
    def _dispatch(self, flow):
        b = Batch(flow, flow.batch * flow.payload, flow.batch, self.env.now)
        self._flow_acc[flow.fid] += flow.batch
        if flow.kind == "legit":
            self.disp_t.append(self.env.now)
            self.disp_cnt.append(flow.batch)
            self.disp_content.append(flow.content)
        self.env.process(self._carry(b))

    def _drop(self, batch, reason, node=-1):
        self.drop_t.append(self.env.now)
        self.drop_reason.append(reason)
        self.drop_cnt.append(batch.count)
        self.drop_node.append(node)
        self.drop_kind.append(1 if batch.flow.kind == "attack" else 0)

    def _complete(self, batch, lat):
        self.done_content.append(batch.flow.content)
        self.done_t.append(self.env.now)
        self.done_fid.append(batch.flow.fid)
        self.done_kind.append(batch.flow.kind)
        self.done_lat.append(lat)
        self.done_cnt.append(batch.count)

    def _carry(self, batch):
        env = self.env
        flow = batch.flow
        node = flow.src
        dest = self.topo.hosts[flow.content]
        hops = 0
        visited = set()
        while node != dest:
            visited.add(node)
            nh = self.fib.next_hop(node, flow.content, flow.fid)
            if nh is None or nh in visited or hops >= MAX_HOPS:
                self._drop(batch, R_LOOP, node)
                return
            cls = self.states[node].policy.cls_for(flow.content, flow.region)
            q = self.egress[(node, nh)]
            ev = q.enqueue(batch, cls)
            if ev is None:
                self._drop(batch, R_TOTAL, node)
                return
            # An object larger than this link's MTU must be reassembled at the
            # far end, so it occupies a reassembly slot for as long as it is in
            # flight.  The charge is taken AFTER queue admission so the class
            # byte limit binds first: an isolated flood is already throttled and
            # never reaches the window, whereas an unconstrained flood carries
            # 1 MB objects that monopolise it and block reassembly for everyone.
            # Charging only *partially admitted* objects (the earlier model) left
            # the mechanism permanently idle, because a full queue rejects whole
            # objects rather than truncating them.
            # Reassembly accounting is applied at the fiber->satellite boundary
            # only: that is the 9000 -> 576 byte MTU step the H3 claim is about.
            # Microwave segmentation is treated as handled by the radio's
            # segmentation offload, so it does not consume the reorder window.
            frag = q.link.kind == "satellite" and q.link.mtu < batch.size
            hold = 0.0
            if frag:
                hold = min(batch.size, REORDER_BYTES * 0.5)
                yield self.reasm_slots.put(1.0)
                yield self.reasm.put(hold)
            res = yield ev
            if frag:
                yield self.reasm.get(hold)
                yield self.reasm_slots.get(1.0)
            if res == R_LOSS:
                self._drop(batch, R_LOSS, node)
                return
            node = nh
            hops += 1
            if res == "partial":
                # the fragment train was cut, so the object can never be
                # reassembled; it dies here rather than at the origin.
                self._drop(batch, R_REORDER, node)
                return
            if node == dest:
                break
            st = self.states[node]
            if st.alpha > 0.02:
                aff = 0.70 if self.topo.hosts[flow.content] == node else 0.15
                if self.rng.random() < st.alpha * aff:
                    serve_rate = max(1.0, st.alpha * self.topo.node_cap[node] / 8.0)
                    yield env.timeout(batch.size / serve_rate)
                    self._complete(batch, env.now - batch.t0)
                    return
        self._complete(batch, env.now - batch.t0)

    # ------------------------------------------------------------------
    def _flow_gen(self, flow):
        env = self.env
        if flow.t_on > 0:
            yield env.timeout(flow.t_on)
        while env.now < min(self.cfg.duration, flow.t_off):
            r = self.demand.rate(flow, env.now)
            if r <= 0.0:
                yield env.timeout(0.05)
                continue
            if flow.kind == "attack":
                r *= max(0.75, 1.0 + 0.25 * math.sin(env.now * 13.0))
            mean_ia = flow.batch / max(r, 1e-9)
            ia = env.timeout(max(1e-6, -math.log(max(1e-12, self.rng.random())) * mean_ia))
            yield ia
            if env.now >= flow.t_off or env.now > self.cfg.duration:
                return
            self._dispatch(flow)

    # ------------------------------------------------------------------
    def _tick(self):
        cfg = self.cfg
        env = self.env
        dt = cfg.tick
        while True:
            yield env.timeout(dt)
            t = env.now
            if t > cfg.duration:
                return
            obs = {}
            for n in range(self.topo.n_nodes):
                tel = self.tele[n]
                served = tel.served_bytes - self._prev_served[n]
                drops = tel.drops - self._prev_drops[n]
                self._prev_served[n] = tel.served_bytes
                self._prev_drops[n] = tel.drops
                cap = self.topo.node_cap[n] / 8.0
                u = served / (cap * dt) if cap > 0 else 0.0
                q = tel.queued_bytes / cap if cap > 0 else 0.0
                tot = served + drops * 1.0
                loss = drops / tot if tot > 0 else 0.0
                d = self._base_delay(n)
                p = 0.70 * min(1.0, u) + 0.20 * (q / (d + q + 1.0)) + 0.10 * min(1.0, loss)
                p = min(1.0, max(0.0, p))
                self.node_pressure[n] = p
                obs[n] = self.monitors[n].update(t, p)
            # measured ingress rate per flow, sampled at 2 Hz
            if t >= self._next_sample - 1e-9:
                self._next_sample = t + 0.5
                for f in self.flows:
                    acc = self._flow_acc[f.fid]
                    self._flow_acc[f.fid] = 0
                    self.flow_rates[f.fid].update(t, acc / 0.5)
            self.controller.on_tick(t, obs)
            for tel in self.tele.values():
                if tel.cls_bytes:
                    tel.cls_bytes = {}
            sweep = getattr(self.controller, "sweep", None)
            if sweep is not None and int(t * 10) % 5 == 0:
                sweep()
            self._log(t)

    def _base_delay(self, n):
        return min(self.topo.links[(n, m)].prop_s for m in self.topo.adj[n])

    # ------------------------------------------------------------------
    def _log(self, t):
        cfg = self.cfg
        if t < getattr(self, "_next_log", 0.0) - 1e-9:
            return
        self._next_log = t + cfg.log_dt
        live = [q for q in self.egress.values() if q.tx_bytes > 0]
        util = 0.0
        qmax = 0.0
        for q in live:
            util = max(util, q.tx_bytes / max(1.0, q.service_rate() * t))
        for tel in self.tele.values():
            qmax = max(qmax, tel.queued_bytes)
        p = getattr(self, "node_pressure", {})
        pmax = max(p.values()) if p else 0.0
        pmean = float(np.mean(list(p.values()))) if p else 0.0
        nclasses = sum(len(s.policy.classes) for s in self.states.values())
        self.series.append((t, util, qmax, self.reasm.level, pmax, pmean, nclasses))

    # ------------------------------------------------------------------
    def run(self) -> dict:
        env = self.env
        for f in self.flows:
            env.process(self._flow_gen(f))
        env.process(self._tick())
        env.run(until=self.cfg.duration + 1.0)
        return self._collect()

    def _collect(self):
        dur = self.cfg.duration
        churn_t, churn_speed, churn_accel, churn_mag = self.ledger.churn_series(dur, 0.1)
        gov = getattr(self.controller, "governor_series", None)
        return {
            "cfg": self.cfg,
            "duration": dur,
            "done_t": np.asarray(self.done_t, dtype=np.float64),
            "done_kind": np.asarray([1 if k == "attack" else 0 for k in self.done_kind],
                                    dtype=np.int8),
            "done_lat": np.asarray(self.done_lat, dtype=np.float64),
            "done_cnt": np.asarray(self.done_cnt, dtype=np.float64),
            "drop_t": np.asarray(self.drop_t, dtype=np.float64),
            "drop_reason": np.asarray(self.drop_reason, dtype=object),
            "drop_cnt": np.asarray(self.drop_cnt, dtype=np.float64),
            "drop_node": np.asarray(self.drop_node, dtype=np.int32),
            "drop_kind": np.asarray(self.drop_kind, dtype=np.int8),
            "series": np.asarray(self.series, dtype=np.float64),
            "churn_t": churn_t,
            "churn_speed": churn_speed,
            "churn_accel": churn_accel,
            "churn_mag": churn_mag,
            "governor": gov if gov is not None else np.zeros((0, 3)),
            "edits": len(self.ledger.edits),
            "attack_target": self.attack_target,
            "disp_t": np.asarray(self.disp_t, dtype=np.float64),
            "disp_cnt": np.asarray(self.disp_cnt, dtype=np.float64),
            "done_content": np.asarray(self.done_content, dtype=np.int32),
            "disp_content": np.asarray(self.disp_content, dtype=np.int32),
            "ns_classes_peak": (float(max(r[6] for r in self.series))
                                if self.series else 0.0),
            "alpha_final": np.array([s.alpha for s in self.states.values()]),
        }


def run_one(cfg):
    return SimRun(cfg).run()
