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

from dataclasses import dataclass
from math import ceil, isfinite
from typing import Iterable, Literal, Optional

AIWorkloadKind = Literal["inference", "training", "model_distribution"]


@dataclass
class KubernetesEdgeCluster:
    """Simulated edge cluster whose cache replica count follows request demand."""

    name: str
    region: str
    target_requests_per_second_per_pod: float
    min_replicas: int = 1
    max_replicas: int = 8
    current_replicas: int = 1

    def __post_init__(self) -> None:
        if not self.name or not self.region:
            raise ValueError("Cluster name and region must not be empty.")
        if (
            not isfinite(self.target_requests_per_second_per_pod)
            or self.target_requests_per_second_per_pod <= 0
        ):
            raise ValueError("Target requests per second per pod must be positive and finite.")
        replica_counts = (self.min_replicas, self.max_replicas, self.current_replicas)
        if any(not isinstance(value, int) or isinstance(value, bool) for value in replica_counts):
            raise ValueError("Replica counts must be integers.")
        if self.min_replicas < 0 or self.max_replicas < self.min_replicas:
            raise ValueError("Replica limits must satisfy 0 <= minimum <= maximum.")
        if not self.min_replicas <= self.current_replicas <= self.max_replicas:
            raise ValueError("Current replicas must be within the configured replica limits.")


@dataclass(frozen=True)
class ReplicaDecision:
    cluster_name: str
    observed_requests_per_second: float
    forecast_requests_per_second: float
    desired_replicas: int
    modeled_capacity_requests_per_second: float
    capacity_saturated: bool


class KEDAInspiredScaler:
    """Model forecast-aware event scaling; this does not call a Kubernetes API."""

    def reconcile(
        self,
        cluster: KubernetesEdgeCluster,
        observed_requests_per_second: float,
        forecast_requests_per_second: float,
    ) -> ReplicaDecision:
        if (
            not isfinite(observed_requests_per_second)
            or observed_requests_per_second < 0
        ):
            raise ValueError("Observed request rate must be non-negative and finite.")
        if not isfinite(forecast_requests_per_second):
            raise ValueError("Forecast request rate must be finite.")

        forecast = max(0.0, forecast_requests_per_second)
        planned_rate = max(observed_requests_per_second, forecast)
        needed_replicas = ceil(planned_rate / cluster.target_requests_per_second_per_pod)
        desired_replicas = min(
            cluster.max_replicas,
            max(cluster.min_replicas, needed_replicas),
        )
        capacity = desired_replicas * cluster.target_requests_per_second_per_pod
        cluster.current_replicas = desired_replicas
        return ReplicaDecision(
            cluster_name=cluster.name,
            observed_requests_per_second=observed_requests_per_second,
            forecast_requests_per_second=forecast,
            desired_replicas=desired_replicas,
            modeled_capacity_requests_per_second=capacity,
            capacity_saturated=planned_rate > capacity,
        )


@dataclass(frozen=True)
class AIDataCenter:
    """Configured telemetry for one candidate AI compute site."""

    name: str
    provider: str
    region: str
    latency_ms: float
    egress_cost_per_gb: float
    available_accelerators: int
    accelerator_load: float = 0.0
    available: bool = True

    def __post_init__(self) -> None:
        if not self.name or not self.provider or not self.region:
            raise ValueError("Datacenter name, provider, and region must not be empty.")
        if not isfinite(self.latency_ms) or self.latency_ms < 0:
            raise ValueError("Datacenter latency must be non-negative and finite.")
        if not isfinite(self.egress_cost_per_gb) or self.egress_cost_per_gb < 0:
            raise ValueError("Configured egress cost must be non-negative and finite.")
        if (
            not isinstance(self.available_accelerators, int)
            or isinstance(self.available_accelerators, bool)
            or self.available_accelerators < 0
        ):
            raise ValueError("Available accelerator count must be non-negative.")
        if not isfinite(self.accelerator_load) or not 0 <= self.accelerator_load <= 1:
            raise ValueError("Accelerator load must be between zero and one.")


@dataclass(frozen=True)
class AIWorkload:
    workload_id: str
    kind: AIWorkloadKind
    billable_egress_bytes: int
    required_accelerators: int = 1
    latency_slo_ms: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.workload_id:
            raise ValueError("Workload ID must not be empty.")
        if self.kind not in {"inference", "training", "model_distribution"}:
            raise ValueError("Unsupported AI workload kind.")
        if (
            not isinstance(self.billable_egress_bytes, int)
            or isinstance(self.billable_egress_bytes, bool)
            or self.billable_egress_bytes < 0
        ):
            raise ValueError("Billable egress bytes must be non-negative.")
        if (
            not isinstance(self.required_accelerators, int)
            or isinstance(self.required_accelerators, bool)
            or self.required_accelerators <= 0
        ):
            raise ValueError("At least one accelerator must be required.")
        if self.latency_slo_ms is not None and (
            not isfinite(self.latency_slo_ms) or self.latency_slo_ms <= 0
        ):
            raise ValueError("Latency SLO must be positive and finite.")


@dataclass(frozen=True)
class AIPlacementDecision:
    workload_id: str
    workload_kind: AIWorkloadKind
    datacenter: str
    provider: str
    region: str
    estimated_latency_ms: float
    estimated_egress_cost: float
    objective_score: float


class CloudPlacementError(RuntimeError):
    """Raised when no configured AI datacenter satisfies workload constraints."""


class MultiCloudAIScheduler:
    """Rank AI datacenters by normalized latency, egress, and accelerator load."""

    def __init__(
        self,
        datacenters: Iterable[AIDataCenter],
        latency_weight: float = 0.5,
        egress_weight: float = 0.3,
        accelerator_load_weight: float = 0.2,
    ) -> None:
        self.datacenters = list(datacenters)
        if len({site.name for site in self.datacenters}) != len(self.datacenters):
            raise ValueError("AI datacenter names must be unique.")
        weights = (latency_weight, egress_weight, accelerator_load_weight)
        if any(not isfinite(weight) or weight < 0 for weight in weights):
            raise ValueError("Scheduler weights must be non-negative and finite.")
        if sum(weights) <= 0:
            raise ValueError("At least one scheduler weight must be positive.")
        self.latency_weight = latency_weight
        self.egress_weight = egress_weight
        self.accelerator_load_weight = accelerator_load_weight

    def schedule(self, workload: AIWorkload) -> AIPlacementDecision:
        candidates = [
            site
            for site in self.datacenters
            if site.available
            and site.available_accelerators >= workload.required_accelerators
            and (
                workload.latency_slo_ms is None
                or site.latency_ms <= workload.latency_slo_ms
            )
        ]
        if not candidates:
            raise CloudPlacementError(
                f"No available AI datacenter satisfies workload {workload.workload_id!r}."
            )

        egress_costs = {
            site.name: workload.billable_egress_bytes
            / 1_000_000_000
            * site.egress_cost_per_gb
            for site in candidates
        }
        max_latency = max(site.latency_ms for site in candidates)
        max_egress_cost = max(egress_costs.values())
        total_weight = (
            self.latency_weight + self.egress_weight + self.accelerator_load_weight
        )

        def rank(site: AIDataCenter) -> tuple[float, float, float, str]:
            normalized_latency = site.latency_ms / max_latency if max_latency else 0.0
            egress_cost = egress_costs[site.name]
            normalized_egress = egress_cost / max_egress_cost if max_egress_cost else 0.0
            score = (
                self.latency_weight * normalized_latency
                + self.egress_weight * normalized_egress
                + self.accelerator_load_weight * site.accelerator_load
            ) / total_weight
            return score, site.latency_ms, egress_cost, site.name

        selected = min(candidates, key=rank)
        return AIPlacementDecision(
            workload_id=workload.workload_id,
            workload_kind=workload.kind,
            datacenter=selected.name,
            provider=selected.provider,
            region=selected.region,
            estimated_latency_ms=selected.latency_ms,
            estimated_egress_cost=egress_costs[selected.name],
            objective_score=rank(selected)[0],
        )
