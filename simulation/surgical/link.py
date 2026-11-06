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

"""Queue plane: per-egress drop-tail with weighted fair queueing.

The substrate is deliberately shared by every controller under test.  What
differs is *which* knob a controller turns, and *when*:

  Baseline A  -- never turns a per-flow knob (static roles only)
  Baseline B  -- turns alpha on every node, from global pressure
  Surgical    -- promotes ONE (content, source-region) class into its own
                 weighted, tightly-limited queue at ONE node

That is the FlowSpec distinction (rate-limit only the attack traffic) expressed
as a queueing structure rather than an operator's policy document.

Class 0 is the default FIFO/bulk class.  An isolated class is
1 + content*8 + region, so a class identity is a name-based match, which is what
a Name-Based Forwarding plane can install surgically.

Fragment-train admission
------------------------
When a class cannot fit an entire object, the queue admits the *fragment train*
that fits and drops the remainder, instead of dropping the whole object.  On a
satellite link (MTU 576) a 100 kB object is 174 fragments, so losing the tail
guarantees an incomplete reassembly at the receiver -- which is precisely the
MTU-mismatch pathology H3 is about.
"""
from __future__ import annotations

import heapq
import math
from collections import deque

BULK = 0

R_CLASS = "class_limit"
R_TOTAL = "buffer_full"
R_LOSS = "link_loss"
R_LOOP = "routing_loop"
R_REORDER = "reorder_overflow"


def class_id(content: int, region: int) -> int:
    return 1 + content * 8 + region


class Item:
    __slots__ = ("batch", "size", "cls", "nfrag", "ev", "partial")

    def __init__(self, batch, size, cls, nfrag, ev, partial=False):
        self.batch = batch
        self.size = size
        self.cls = cls
        self.nfrag = nfrag
        self.ev = ev
        self.partial = partial


class OutputQueue:
    def __init__(self, env, link, node_state, rng, node_id, node_cap_bps, tele):
        self.env = env
        self.link = link
        self.state = node_state
        self.policy = node_state.policy
        self.rng = rng
        self.node_id = node_id
        self.node_cap = node_cap_bps
        self.tele = tele
        self.nominal = link.buffer_bytes
        self.q = {}
        self.qb = {}
        self.vf = {}
        self.heap = []
        self._seq = 0
        self.total_bytes = 0.0
        self._signal = None
        self.vtime = 0.0
        self.tx_bytes = 0.0
        self.busy = False
        self.drops = {}

    # -- capacity after the role split ----------------------------------
    def service_rate(self) -> float:
        fwd = max(0.02, 1.0 - self.state.alpha) * self.node_cap
        cap = min(self.link.capacity_bps, fwd)
        return max(cap, 1.0) / 8.0

    def enqueue(self, batch, cls):
        buf = self.nominal * self.policy.total_scale
        cls_lim = buf * self.policy.limit_frac(cls)
        room_total = buf - self.total_bytes
        room_cls = cls_lim - self.qb.get(cls, 0.0)
        room = min(room_total, room_cls)
        size = batch.size
        partial = False
        if room <= 0.0:
            self._drop(cls, R_CLASS if room_cls <= room_total else R_TOTAL)
            return None
        if size > room:
            # admit the fragment train that fits, drop the rest
            if room < self.link.mtu:
                self._drop(cls, R_CLASS if room_cls <= room_total else R_TOTAL)
                return None
            size = room
            partial = True
        ev = self.env.event()
        nfrag = max(1, math.ceil(size / self.link.mtu))
        item = Item(batch, size, cls, nfrag, ev, partial)
        dq = self.q.get(cls)
        if dq is None:
            dq = self.q[cls] = deque()
            self.qb[cls] = 0.0
        dq.append(item)
        self.qb[cls] += size
        self.total_bytes += size
        self.tele.queued_bytes += size
        if cls != BULK:
            b = self.tele.cls_bytes
            b[cls] = b.get(cls, 0.0) + size
        w = max(1e-6, self.policy.weight(cls))
        vf = max(self.vf.get(cls, self.vtime), self.vtime) + size / w
        self.vf[cls] = vf
        self._seq += 1
        heapq.heappush(self.heap, (vf, cls, self._seq))
        if self._signal is not None and not self._signal.triggered:
            self._signal.succeed()
            self._signal = None
        return ev

    def _drop(self, cls, reason):
        self.drops[reason] = self.drops.get(reason, 0) + 1
        self.tele.drops += 1

    def _pick(self):
        h = self.heap
        while h:
            vf, cls, seq = h[0]
            dq = self.q.get(cls)
            if not dq:
                heapq.heappop(h)
                continue
            if abs(vf - self.vf.get(cls, -1.0)) > 1e-9:
                heapq.heappop(h)
                continue
            return cls
        return None

    def _serve(self):
        env = self.env
        while True:
            if self.total_bytes <= 0.0:
                self.busy = False
                self._signal = env.event()
                yield self._signal
                continue
            self.busy = True
            cls = self._pick()
            if cls is None:
                yield env.timeout(1e-6)
                continue
            dq = self.q[cls]
            item = dq.popleft()
            self.qb[cls] -= item.size
            self.total_bytes -= item.size
            self.tele.queued_bytes -= item.size
            self.vtime = max(self.vtime, self.vf.get(cls, 0.0))
            svc = item.size / self.service_rate()
            if svc > 0.0:
                yield env.timeout(svc)
            self.tx_bytes += item.size
            self.tele.served_bytes += item.size
            p = self.link.loss
            lost = False
            if p > 0.0:
                # The coalesced batch is the transmission unit, so the link's
                # packet error rate applies once per item.  Retransmission is
                # out of scope (see results.md, "Model scope"); applying PER per
                # fragment instead would lose 93% of a 400 kB object on a 1%
                # microwave link, which models TCP with no ARQ at all.
                lost = self.rng.random() < p
            if lost:
                item.ev.succeed(R_LOSS)
            elif item.partial:
                item.ev.succeed("partial")
            else:
                item.ev.succeed("ok")
