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

from __future__ import annotations

from math import prod
from typing import List, Sequence

from .models import Link, NetworkScenario, Node, RouteResult, TrafficFlow


class AIContentDistributionPolicy:
    def __init__(self, router_intelligence: float = 1.0) -> None:
        self.router_intelligence = router_intelligence

    def score(self, path: Sequence[str], flow: TrafficFlow, scenario: NetworkScenario) -> float:
        if len(path) < 2:
            return -1.0

        links: List[Link] = []
        for i in range(len(path) - 1):
            source = path[i]
            target = path[i + 1]
            match = next((link for link in scenario.adjacency.get(source, []) if link.target == target), None)
            if match is not None:
                links.append(match)

        if not links:
            return -1.0

        edge_penalty = sum(0.12 for node in path if node.startswith("cdn") or node.startswith("tomahawk"))
        total_latency = sum(link.latency_ms for link in links)
        total_loss = 1.0 - prod(link.reliability for link in links)
        capacity = min(link.effective_capacity for link in links)
        priority_weight = 1.0 + (flow.priority * 0.25)
        learning_bonus = self.router_intelligence * max(0.0, 1.0 - total_loss)

        score = ((capacity * priority_weight) / (total_latency + 1.0))
        score += learning_bonus * 25.0
        score -= total_loss * 180.0
        score -= edge_penalty
        return score


class RoutingEngine:
    def __init__(self, scenario: NetworkScenario) -> None:
        self.scenario = scenario

    def best_route_for_flow(self, flow: TrafficFlow, step: int = 0) -> List[str]:
        queue = [(flow.source, [flow.source])]
        best_path: List[str] | None = None
        best_score = float("-inf")

        while queue:
            current, path = queue.pop(0)
            if current == flow.destination:
                score = self._path_score(path, flow)
                if score > best_score:
                    best_score = score
                    best_path = path
                continue

            for link in self.scenario.adjacency.get(current, []):
                if link.target in path:
                    continue
                if len(path) > self.scenario.node_count() + 2:
                    continue
                queue.append((link.target, path + [link.target]))

        if best_path is None:
            return [flow.source, flow.destination]

        return best_path

    def _path_score(self, path: Sequence[str], flow: TrafficFlow) -> float:
        if len(path) < 2:
            return -1.0

        links: List[Link] = []
        for i in range(len(path) - 1):
            source = path[i]
            target = path[i + 1]
            match = next((link for link in self.scenario.adjacency.get(source, []) if link.target == target), None)
            if match is not None:
                links.append(match)

        if not links:
            return -1.0

        total_latency = sum(link.latency_ms for link in links)
        total_loss = 1.0 - prod(link.reliability for link in links)
        capacity = min(link.effective_capacity for link in links)
        priority_weight = 1.0 + (flow.priority * 0.2)

        score = (capacity * priority_weight) / (total_latency + 1.0)
        score -= total_loss * 150.0
        return score

    def evaluate_route(self, flow: TrafficFlow, path: Sequence[str], step: int = 0) -> RouteResult:
        link_chain: List[Link] = []
        for i in range(len(path) - 1):
            current = path[i]
            next_node = path[i + 1]
            match = next((link for link in self.scenario.adjacency.get(current, []) if link.target == next_node), None)
            if match is not None:
                link_chain.append(match)

        if not link_chain:
            return RouteResult(
                flow_name=flow.name,
                route=[flow.source, flow.destination],
                latency_ms=999.0,
                estimated_throughput_gbps=0.0,
                reliability=0.0,
                utilization=1.0,
            )

        latency = sum(link.latency_ms for link in link_chain)
        effective_capacity = min(link.effective_capacity for link in link_chain)
        reliability = prod(link.reliability for link in link_chain)
        utilization = min(1.0, flow.demand_gbps / max(0.1, effective_capacity))

        if step >= 3 and any(link.medium.lower() in {"wireless", "thz", "mmwave"} for link in link_chain):
            latency *= 1.35
            reliability *= 0.92
            utilization = min(1.0, utilization * 1.08)

        if any(node.startswith("tomahawk") for node in path):
            latency *= 0.9
            reliability *= 1.02
            reliability = min(reliability, 0.9999)

        throughput = min(flow.demand_gbps, effective_capacity * (1.0 - max(0.0, utilization - 0.65) * 0.5))
        return RouteResult(
            flow_name=flow.name,
            route=list(path),
            latency_ms=round(latency, 2),
            estimated_throughput_gbps=round(max(0.0, throughput), 2),
            reliability=round(reliability, 4),
            utilization=round(utilization, 4),
        )

    def reinforcement_route(self, flow: TrafficFlow, policy: AIContentDistributionPolicy | None = None) -> List[str]:
        policy = policy or AIContentDistributionPolicy(router_intelligence=1.25)
        queue = [(flow.source, [flow.source])]
        best_path: List[str] | None = None
        best_score = float("-inf")

        while queue:
            current, path = queue.pop(0)
            if current == flow.destination:
                score = policy.score(path, flow, self.scenario)
                if score > best_score:
                    best_score = score
                    best_path = path
                continue

            for link in self.scenario.adjacency.get(current, []):
                if link.target in path:
                    continue
                if len(path) > self.scenario.node_count() + 2:
                    continue
                queue.append((link.target, path + [link.target]))

        if best_path is None:
            return [flow.source, flow.destination]
        return best_path


def build_reference_scenario() -> NetworkScenario:
    scenario = NetworkScenario(
        "7G Hybrid Backhaul",
        "AI-optimized multi-cloud backhaul connecting edge sites, cloud regions, satellites, and wireless relay layers.",
    )

    scenario.add_node(Node("campus-a", "site", "europe", capacity_gbps=25.0, notes="Local manufacturing campus"))
    scenario.add_node(Node("campus-b", "site", "north-america", capacity_gbps=30.0, notes="Regional logistics hub"))
    scenario.add_node(Node("edge-router", "router", "edge", capacity_gbps=150.0, notes="Programmable edge router"))
    scenario.add_node(Node("core-router", "router", "core", capacity_gbps=400.0, notes="AI-driven routing backbone"))
    scenario.add_node(Node("cloud-aws", "cloud", "aws", capacity_gbps=500.0, notes="Public cloud analytics region"))
    scenario.add_node(Node("cloud-azure", "cloud", "azure", capacity_gbps=500.0, notes="Enterprise workloads"))
    scenario.add_node(Node("cloud-gcp", "cloud", "gcp", capacity_gbps=500.0, notes="Data-intensive AI workloads"))
    scenario.add_node(Node("drone-relay", "drone", "air", capacity_gbps=120.0, notes="Mobile relay for outages and temporary coverage"))
    scenario.add_node(Node("satellite-leo", "satellite", "space", capacity_gbps=180.0, notes="Non-terrestrial backhaul"))
    scenario.add_node(Node("ris-surface", "smart-surface", "urban", capacity_gbps=80.0, notes="Reconfigurable intelligent surface"))

    scenario.add_link("campus-a", "edge-router", "fiber", 12.0, 1.2, packet_loss_pct=0.05, reliability=0.995, cost_index=0.7)
    scenario.add_link("campus-b", "edge-router", "fiber", 14.0, 1.6, packet_loss_pct=0.04, reliability=0.996, cost_index=0.8)
    scenario.add_link("edge-router", "core-router", "fiber", 80.0, 3.0, packet_loss_pct=0.03, reliability=0.999, cost_index=1.1)
    scenario.add_link("core-router", "cloud-aws", "fiber", 120.0, 12.0, packet_loss_pct=0.04, reliability=0.999, cost_index=1.4)
    scenario.add_link("core-router", "cloud-azure", "fiber", 110.0, 14.0, packet_loss_pct=0.05, reliability=0.998, cost_index=1.5)
    scenario.add_link("core-router", "cloud-gcp", "fiber", 130.0, 16.0, packet_loss_pct=0.03, reliability=0.999, cost_index=1.6)
    scenario.add_link("edge-router", "drone-relay", "thz", 28.0, 2.6, packet_loss_pct=0.8, reliability=0.95, cost_index=1.2)
    scenario.add_link("drone-relay", "satellite-leo", "wireless", 35.0, 7.8, packet_loss_pct=1.2, reliability=0.94, cost_index=1.4)
    scenario.add_link("drone-relay", "core-router", "mmwave", 24.0, 5.2, packet_loss_pct=0.9, reliability=0.96, cost_index=1.0)
    scenario.add_link("edge-router", "ris-surface", "wireless", 18.0, 1.8, packet_loss_pct=0.7, reliability=0.97, cost_index=0.9)
    scenario.add_link("ris-surface", "core-router", "wireless", 20.0, 2.7, packet_loss_pct=0.9, reliability=0.96, cost_index=1.1)
    scenario.add_link("satellite-leo", "cloud-aws", "wireless", 40.0, 22.0, packet_loss_pct=1.9, reliability=0.93, cost_index=1.7)
    scenario.add_link("satellite-leo", "cloud-gcp", "wireless", 45.0, 24.0, packet_loss_pct=1.7, reliability=0.94, cost_index=1.8)
    scenario.add_link("cloud-aws", "cloud-azure", "fiber", 90.0, 6.0, packet_loss_pct=0.02, reliability=0.9995, cost_index=0.9)
    scenario.add_link("cloud-azure", "cloud-gcp", "fiber", 95.0, 7.0, packet_loss_pct=0.02, reliability=0.9995, cost_index=0.9)

    return scenario


def build_reference_flows() -> List[TrafficFlow]:
    return [
        TrafficFlow("edge-ai-analytics", "campus-a", "cloud-aws", 18.0, priority=3),
        TrafficFlow("finance-sync", "campus-a", "cloud-azure", 12.0, priority=2),
        TrafficFlow("global-model-train", "campus-b", "cloud-gcp", 20.0, priority=3),
        TrafficFlow("millimeter-backup", "campus-b", "satellite-leo", 9.0, priority=2),
        TrafficFlow("edge-visibility", "campus-a", "core-router", 6.0, priority=1),
    ]


def build_tomahawk_cdn_scenario() -> NetworkScenario:
    scenario = NetworkScenario(
        "Tomahawk AI CDN Fabric",
        "NPU-based Tomahawk-class routers optimize a self-scaling content distribution network with reinforcement-learning driven traffic steering.",
    )

    scenario.add_node(Node("regional-edge", "site", "us-east", capacity_gbps=80.0, notes="Regional content ingestion point"))
    scenario.add_node(Node("cdn-cache-1", "cache", "us-east", capacity_gbps=500.0, notes="Popular object cache"))
    scenario.add_node(Node("tomahawk-npu-1", "router", "core", capacity_gbps=1200.0, notes="Broadcom Tomahawk-class NPU fabric router with AI telemetry"))
    scenario.add_node(Node("tomahawk-npu-2", "router", "core", capacity_gbps=1200.0, notes="Adaptive route decision engine using reinforcement learning"))
    scenario.add_node(Node("tomahawk-npu-3", "router", "core", capacity_gbps=1200.0, notes="Self-scaling transit node for cross-region traffic"))
    scenario.add_node(Node("cdn-cache-2", "cache", "eu-west", capacity_gbps=500.0, notes="Regional cache with local delivery"))
    scenario.add_node(Node("content-origin", "origin", "global", capacity_gbps=600.0, notes="Origin media service and APIs"))
    scenario.add_node(Node("video-edge", "site", "eu-west", capacity_gbps=70.0, notes="Subscriber edge with live video demand"))
    scenario.add_node(Node("ai-analytics", "cloud", "multi-cloud", capacity_gbps=800.0, notes="AI planner for content placement and cache warm-up"))

    scenario.add_link("regional-edge", "tomahawk-npu-1", "fiber", 160.0, 1.0, packet_loss_pct=0.02, reliability=0.999, cost_index=0.8)
    scenario.add_link("regional-edge", "cdn-cache-1", "fiber", 180.0, 0.9, packet_loss_pct=0.03, reliability=0.999, cost_index=0.7)
    scenario.add_link("cdn-cache-1", "tomahawk-npu-1", "fiber", 200.0, 1.1, packet_loss_pct=0.02, reliability=0.9995, cost_index=0.8)
    scenario.add_link("tomahawk-npu-1", "tomahawk-npu-2", "fiber", 800.0, 1.8, packet_loss_pct=0.01, reliability=0.9998, cost_index=0.9)
    scenario.add_link("tomahawk-npu-2", "tomahawk-npu-3", "fiber", 850.0, 2.0, packet_loss_pct=0.01, reliability=0.9998, cost_index=0.9)
    scenario.add_link("tomahawk-npu-3", "cdn-cache-2", "fiber", 220.0, 1.2, packet_loss_pct=0.03, reliability=0.9995, cost_index=0.7)
    scenario.add_link("cdn-cache-2", "video-edge", "fiber", 200.0, 1.0, packet_loss_pct=0.02, reliability=0.999, cost_index=0.8)
    scenario.add_link("tomahawk-npu-2", "content-origin", "fiber", 240.0, 2.4, packet_loss_pct=0.04, reliability=0.999, cost_index=1.1)
    scenario.add_link("tomahawk-npu-3", "ai-analytics", "fiber", 260.0, 2.8, packet_loss_pct=0.02, reliability=0.9995, cost_index=1.0)
    scenario.add_link("ai-analytics", "tomahawk-npu-1", "fiber", 240.0, 2.2, packet_loss_pct=0.02, reliability=0.9995, cost_index=1.0)
    scenario.add_link("content-origin", "ai-analytics", "fiber", 180.0, 2.5, packet_loss_pct=0.03, reliability=0.999, cost_index=1.0)
    scenario.add_link("video-edge", "tomahawk-npu-3", "wireless", 120.0, 3.4, packet_loss_pct=0.6, reliability=0.97, cost_index=1.0)
    scenario.add_link("regional-edge", "tomahawk-npu-2", "wireless", 100.0, 4.0, packet_loss_pct=0.8, reliability=0.96, cost_index=1.1)

    return scenario


def build_tomahawk_cdn_flows() -> List[TrafficFlow]:
    return [
        TrafficFlow("live-video-pop", "regional-edge", "video-edge", 95.0, priority=3),
        TrafficFlow("global-asset-delivery", "content-origin", "video-edge", 120.0, priority=3),
        TrafficFlow("cache-warmup", "ai-analytics", "cdn-cache-2", 75.0, priority=2),
        TrafficFlow("regional-analytics-sync", "regional-edge", "ai-analytics", 40.0, priority=2),
    ]


def simulate_tomahawk_cdn_scenario() -> dict:
    scenario = build_tomahawk_cdn_scenario()
    engine = RoutingEngine(scenario)
    flows = build_tomahawk_cdn_flows()

    route_results: List[RouteResult] = []
    policy = AIContentDistributionPolicy(router_intelligence=1.65)
    for flow in flows:
        route = engine.reinforcement_route(flow, policy)
        result = engine.evaluate_route(flow, route)
        route_results.append(result)

    average_latency = sum(item.latency_ms for item in route_results) / max(1, len(route_results))
    average_reliability = sum(item.reliability for item in route_results) / max(1, len(route_results))
    average_throughput = sum(item.estimated_throughput_gbps for item in route_results) / max(1, len(route_results))

    return {
        "scenario_name": scenario.name,
        "flows": flows,
        "route_results": route_results,
        "average_latency_ms": round(average_latency, 2),
        "average_reliability": round(average_reliability, 4),
        "average_throughput_gbps": round(average_throughput, 2),
    }


def simulate_reference_scenario() -> tuple:
    scenario = build_reference_scenario()
    flows = build_reference_flows()
    engine = RoutingEngine(scenario)

    route_results: List[RouteResult] = []
    for step in range(4):
        for flow in flows:
            route = engine.best_route_for_flow(flow, step=step)
            result = engine.evaluate_route(flow, route, step=step)
            route_results.append(result)

    average_latency = sum(item.latency_ms for item in route_results) / max(1, len(route_results))
    average_reliability = sum(item.reliability for item in route_results) / max(1, len(route_results))
    average_throughput = sum(item.estimated_throughput_gbps for item in route_results) / max(1, len(route_results))

    return {
        "scenario_name": scenario.name,
        "flows": flows,
        "route_results": route_results,
        "average_latency_ms": round(average_latency, 2),
        "average_reliability": round(average_reliability, 4),
        "average_throughput_gbps": round(average_throughput, 2),
    }
