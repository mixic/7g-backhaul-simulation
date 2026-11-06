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

"""100-node heterogeneous mesh with dual-role nodes.

Topology (ns-3 mapping)
-----------------------
* 10x10 grid, 100 nodes, index n = row*10 + col.
* Horizontal edges   -> PointToPoint  (fiber:      1 Gbps, 2 ms, 0% PER, MTU 9000)
* Vertical edges     -> Csma           (microwave: 100 Mbps, 10 ms, 1% PER, MTU 1500)
* n <-> n+50 edges   -> Satellite      (satellite:  10 Mbps, 500 ms, 0% PER, MTU 576)

230 links: 90 fiber, 90 microwave, 50 satellite.  The satellite edges span five
rows, so intra-half routing almost never selects them (500 ms delay) unless the
scenario forces it -- which is exactly what Experiment 3 does.

Dual-role nodes
---------------
Every node carries alpha in [0,1]:
  alpha = 0.0 -> pure router/balancer
  alpha = 1.0 -> pure cache/server
Node switching capacity C_n = max incident link rate.  Forwarding capacity is
(1-alpha)*C_n; serving capacity is alpha*C_n.  A node that a workload hosts
content on gets a large cache affinity, every other node a small one (LCN-style
universal caching), so alpha is a genuine trade, not a free win.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import numpy as np

from .config import FIBER, LINK_SPECS, MICRO, SAT

GRID = 10
N_NODES = GRID * GRID

#: Content origins: aggregation-core nodes, each with exactly one fiber uplink.
HOST_UPLINK = {43: 42, 46: 45, 53: 52, 56: 55}
HOST_NODES = sorted(HOST_UPLINK)


@dataclass
class Link:
    a: int
    b: int
    kind: str
    capacity_bps: float
    prop_s: float
    loss: float
    mtu: int
    buffer_bytes: float

    @property
    def key(self):
        return (self.a, self.b)

    @property
    def metric(self) -> float:
        """Routing metric: propagation + transfer time of one nominal object."""
        return self.prop_s + (100_000 * 8.0) / self.capacity_bps


@dataclass
class Topology:
    n_nodes: int
    links: dict            # (a,b) -> Link   (directed both ways)
    adj: dict              # node -> list of neighbours
    coords: dict           # node -> (row, col)
    hosts: dict            # content id -> hosting node
    content_pop: np.ndarray
    node_cap: dict         # node -> switching capacity (bps)
    dist_to_host: dict     # (host_node) -> {node: distance}
    alpha0: dict           # node -> initial role fraction
    # forced flow specification for exp3
    sat_boundary: tuple = ()   # (ingress_node, egress_node)

    def neighbours(self, n):
        return self.adj[n]

    @property
    def n_content(self) -> int:
        return len(self.content_pop)

    def link(self, a, b) -> Link:
        return self.links[(a, b)]


def _spec_for(kind: str):
    return {"fiber": FIBER, "microwave": MICRO, "satellite": SAT}[kind]


def build_topology(n_content: int = 8, zipf_s: float = 0.9,
                   force_satellite: bool = False,
                   seed: int = 0) -> Topology:
    coords = {n: (n // GRID, n % GRID) for n in range(N_NODES)}
    undirected = []
    for r in range(GRID):
        for c in range(GRID):
            n = r * GRID + c
            if c + 1 < GRID:
                undirected.append((n, n + 1, "fiber"))
            if r + 1 < GRID:
                undirected.append((n, n + GRID, "microwave"))
    for n in range(N_NODES // 2):
        undirected.append((n, n + 50, "satellite"))

    if force_satellite:
        # Node 5 becomes a remote site whose ONLY backhaul is the satellite
        # hop to node 55.  That is the fiber->satellite boundary of H3, and it
        # makes the 10 Mbps / MTU 576 channel the bottleneck rather than a
        # curiosity that shortest-path routing avoids.
        undirected = [e for e in undirected
                      if not (5 in (e[0], e[1]) and e[2] != "satellite")]

    # Content origins are single-uplink leaves attached to the aggregation
    # core.  That is how a CDN is actually deployed, and it guarantees that a
    # name-targeted shockwave and the legitimate traffic for *other* names on
    # the same origin share one bottleneck -- otherwise the attack is dropped
    # on links no legitimate flow ever crosses and the comparison is vacuous.
    undirected = [e for e in undirected
                  if not ((e[0] in HOST_UPLINK and e[1] != HOST_UPLINK[e[0]])
                          or (e[1] in HOST_UPLINK and e[0] != HOST_UPLINK[e[1]]))]
    # The last mile to an origin is 100 Mbps microwave backhaul, not fiber.
    # This matters: otherwise the mesh's 100 Mbps hops throttle a flood before
    # it ever reaches the 1 Gbps origin uplink, and no controller is tested.
    undirected = [(a, b, "microwave" if (a in HOST_UPLINK or b in HOST_UPLINK)
                   else kind) for (a, b, kind) in undirected]

    links = {}
    adj = {n: [] for n in range(N_NODES)}
    for a, b, kind in undirected:
        spec = _spec_for(kind)
        for (x, y) in ((a, b), (b, a)):
            links[(x, y)] = Link(x, y, kind, spec.capacity_bps, spec.prop_s,
                                 spec.loss, spec.mtu, spec.buffer_bytes)
        adj[a].append(b)
        adj[b].append(a)
    for n in adj:
        adj[n].sort()

    node_cap = {}
    for n in range(N_NODES):
        node_cap[n] = max(links[(n, m)].capacity_bps for m in adj[n])

    rng = np.random.default_rng(seed)
    # content popularity: zipf over ranks 1..n_content
    ranks = np.arange(1, n_content + 1, dtype=float)
    pop = 1.0 / np.power(ranks, zipf_s)
    pop = pop / pop.sum()

    # Content origins: four aggregation-core leaves.  A CDN puts origins where
    # the traffic aggregates, and that is also what makes a name-targeted
    # shockwave hit a *shared* bottleneck instead of one corner.
    host_nodes = HOST_NODES
    hosts = {}
    for c in range(n_content):
        hosts[c] = int(host_nodes[c % len(host_nodes)])

    # static routing metric = link.metric ; Dijkstra from each host
    dist_to_host = {}
    for h in set(hosts.values()):
        dist_to_host[h] = _dijkstra(adj, links, h)

    # Initial role assignment.  Content hosts are *interior* nodes in a mesh,
    # so alpha=1.0 would leave them 2% forwarding capacity and partition the
    # fabric (observed in calibration: 8% goodput with no attack present).
    # Static baseline therefore reserves 20% of a host's capacity for transit.
    # See results.md, "Calibration".
    host_set = set(hosts.values())
    alpha0 = {n: (0.8 if n in host_set else 0.0) for n in range(N_NODES)}

    sat_boundary = ()
    if force_satellite:
        # node 5 (row 0) -> node 55 (row 5) across the satellite edge;
        # the ingress queue is node 5's satellite egress.
        sat_boundary = (5, 55)

    return Topology(N_NODES, links, adj, coords, hosts, pop, node_cap,
                    dist_to_host, alpha0, sat_boundary)


def _dijkstra(adj, links, src):
    dist = {n: math.inf for n in adj}
    dist[src] = 0.0
    pq = [(0.0, src)]
    done = set()
    while pq:
        d, n = heapq.heappop(pq)
        if n in done:
            continue
        done.add(n)
        for m in adj[n]:
            nd = d + links[(n, m)].metric
            if nd < dist[m] - 1e-12:
                dist[m] = nd
                heapq.heappush(pq, (nd, m))
    return dist


class Fib:
    """Local Name-Based Forwarding table.

    Base entry:  content name -> next hop (shortest loop-free path).
    Flow entry:  flow id      -> next hop override  (the surgical edit target)

    Only *downhill* alternates are permitted so a local repair cannot create a
    forwarding loop; this is the classic Loop-Free Alternate condition.
    """

    def __init__(self, topo: Topology, router):
        self.topo = topo
        self.router = router
        self.base = {}      # content -> nexthop
        self.flow = {}      # (flow_id, content) -> nexthop override
        self._alt_cache = {}
        n = topo.n_nodes
        for c, h in topo.hosts.items():
            dist = topo.dist_to_host[h]
            for node in range(n):
                if node == h:
                    self.base[(node, c)] = None
                    continue
                best, bestd = None, math.inf
                for nb in topo.adj[node]:
                    d = topo.links[(node, nb)].metric + dist[nb]
                    if d < bestd:
                        bestd, best = d, nb
                self.base[(node, c)] = best

    def next_hop(self, node: int, content: int, flow_id: int):
        ov = self.flow.get((flow_id, content))
        if ov is not None and node == ov[0]:
            return ov[1]
        return self.base.get((node, content))

    def alternates(self, node: int, content: int):
        """Loop-free alternates: neighbours whose own path avoids `node`."""
        key = (node, content)
        if key in self._alt_cache:
            return self._alt_cache[key]
        h = self.topo.hosts[content]
        dist = self.topo.dist_to_host[h]
        primary = self.base.get((node, content))
        out = []
        for nb in self.topo.adj[node]:
            if nb == primary:
                continue
            if not self._path_avoids(nb, content, node):
                continue
            d = self.topo.links[(node, nb)].metric + dist[nb]
            out.append((d, nb))
        out.sort()
        self._alt_cache[key] = out
        return out

    def _path_avoids(self, start: int, content: int, forbidden: int) -> bool:
        h = self.topo.hosts[content]
        node = start
        seen = set()
        for _ in range(24):
            if node == forbidden:
                return False
            if node == h:
                return True
            if node in seen:
                return False
            seen.add(node)
            node = self.base.get((node, content))
            if node is None:
                return False
        return False
