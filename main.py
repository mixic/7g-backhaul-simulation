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

import hashlib
import random
import secrets
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import simpy

from simulation.analytics import CSVNetworkLogger
from simulation.channels import build_default_channels
from simulation.cdn import SelfScalingContentNetwork
from simulation.continuity import SeamlessTransportSession
from simulation.mobility import RadioCell
from simulation.mesh import MeshLink, MeshPeer, PeerMesh
from simulation.orchestration import (
    AIDataCenter,
    AIWorkload,
    KEDAInspiredScaler,
    KubernetesEdgeCluster,
    MultiCloudAIScheduler,
)
from simulation.router import SoftHandoverRouter
from simulation.security import SessionAuthenticator
from simulation.telemetry import InBandTelemetry, INTCollector

CHANNELS = build_default_channels()
ROUTER = SoftHandoverRouter(CHANNELS)
FIGURES_DIR = Path(__file__).resolve().parent / "figures"
HISTORY_LOGGER = CSVNetworkLogger(Path(__file__).resolve().parent / "output" / "network_history.csv")

if "agg" not in plt.get_backend().lower():
    plt.ion()
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))


def update_dashboard(distribution, telemetry_data, sim_time, active_crisis):
    ax1.clear()
    ax2.clear()

    title_color = "red" if active_crisis != "None" else "black"
    fig.suptitle(
        f"7G Fluid Multi-Medium Backhaul Network Fabric | Step Tick: {sim_time}s\n[ENVIRONMENT ALERTS STATUS]: {active_crisis}",
        fontsize=13,
        fontweight="bold",
        color=title_color,
    )

    media_names = list(distribution.keys())
    shares = [distribution[m] * 100 for m in media_names]
    colors = plt.get_cmap("tab10")(np.arange(len(media_names)))

    bars = ax1.bar(media_names, shares, color=colors, edgecolor="black", alpha=0.85)
    ax1.set_ylabel("Packet Distribution Share (%)", fontsize=11)
    ax1.set_title("Data Plane Packet Spraying Matrix", fontsize=11, fontweight="semibold")
    ax1.set_ylim(0, 100)
    ax1.grid(axis="y", linestyle="--", alpha=0.4)

    for bar in bars:
        height = bar.get_height()
        ax1.annotate(
            f"{height:.1f}%",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontweight="bold",
        )

    pressure_scores = [CHANNELS[i].get_pressure_score() for i in range(len(CHANNELS))]
    y_pos = np.arange(len(media_names))

    ax2.barh(y_pos, pressure_scores, color="#34495e", edgecolor="black", alpha=0.75)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(media_names)
    ax2.set_xlabel("NPU INT Pressure Coefficient (0.0 = Clear Fluid, 1.0 = Maximally Saturated)", fontsize=11)
    ax2.set_title("In-Band Telemetry (INT) Link Overload Traces", fontsize=11, fontweight="semibold")
    ax2.set_xlim(0, 1.0)
    ax2.grid(axis="x", linestyle="--", alpha=0.4)

    for i, m_name in enumerate(media_names):
        tel = telemetry_data[m_name]
        is_damaged = " [CRISIS]" if CHANNELS[i].active_disaster != "None" else ""
        info_str = (
            f" Latency: {tel['hop_latency_ms']:.1f}ms | Loss Proxy: {CHANNELS[i].packet_loss_base * 100:.1f}%{is_damaged}"
        )
        ax2.text(
            0.02,
            i,
            info_str,
            va="center",
            color="white",
            fontweight="bold",
            fontsize=9,
            bbox={"facecolor": "black", "alpha": 0.7, "boxstyle": "round,pad=0.2"},
        )

    plt.tight_layout()
    FIGURES_DIR.mkdir(exist_ok=True)
    plt.savefig(FIGURES_DIR / f"7g_fabric_tick_{sim_time}.png")
    if "agg" not in plt.get_backend().lower():
        plt.draw()
        plt.pause(0.7)


def network_traffic_generator(env, collector, logger, burst_interval=1.0):
    active_crisis = "None"
    media_names = [medium.name for medium in CHANNELS]
    headings = " | ".join(f"{name + ' %':<12}" for name in media_names)
    print(f"{'Time (s)':<10} | {headings} | Primary Routing Action")
    print("-" * (25 + len(headings)))

    while True:
        if env.now % 4 == 0:
            active_crisis = random.choice(["None", "None", "Localized_Storm", "Solar_Flare"])

        for medium in CHANNELS:
            medium.update_dynamic_conditions(active_crisis)

        telemetry_data = InBandTelemetry.parse_telemetry_fabric(CHANNELS)
        packet_burst = 100000
        _, distribution = ROUTER.route_packet_flow(packet_burst)
        logger.log_network_snapshot(env.now, CHANNELS, distribution)
        best_medium = max(distribution, key=distribution.get)

        channel_states = {medium.name: round(medium.current_load, 4) for medium in CHANNELS}
        collector.record_frame(
            timestamp=env.now,
            channel_states=channel_states,
            routing_distribution=distribution,
            best_medium=best_medium,
            total_packets=packet_burst,
        )

        if active_crisis != "None":
            print(f"ALERT: {active_crisis} active across the 7G fabric; soft-rerouting is engaged.")

        print(
            f"{env.now:<10} | "
            + " | ".join(f"{distribution[name] * 100:7.1f}%" for name in media_names)
            + f" | Fluid allocation -> Heavy bias to {best_medium}"
        )

        update_dashboard(distribution, telemetry_data, env.now, active_crisis)

        yield env.timeout(burst_interval)


def main():
    authenticator = SessionAuthenticator(secrets.token_bytes(32))
    transport = SeamlessTransportSession(
        CHANNELS,
        rng=random.Random(2026),
        authenticator=authenticator,
    )
    initial_handover = transport.update_radio_measurements(
        "demo-mobile-session",
        [RadioCell("mobile-cell-bern", "Mobile", -78)],
    )
    transport.update_radio_measurements(
        "demo-mobile-session",
        [
            RadioCell("mobile-cell-bern", "Mobile", -88),
            RadioCell("wifi-ap-bern", "WiFi", -73),
        ],
    )
    handover = transport.update_radio_measurements(
        "demo-mobile-session",
        [
            RadioCell("mobile-cell-bern", "Mobile", -88),
            RadioCell("wifi-ap-bern", "WiFi", -73),
        ],
    )
    credential = authenticator.issue(
        principal="demo-mobile-user",
        session_id="demo-mobile-session",
        now=1000,
    )
    payload = (b"7G seamless multi-medium content delivery " * 400)
    transfer = transport.transmit(
        payload,
        session_id="demo-mobile-session",
        credential=credential,
        now=1001,
    )
    HISTORY_LOGGER.log_transfer(0.0, transfer)
    print(
        f"Continuous session: {len(transfer.payload)} bytes across "
        f"{', '.join(sorted(set(transfer.media_used)))}; retries={transfer.retries}, "
        f"goodput={transfer.goodput_mbps:.2f} Mbps"
    )
    print(
        f"Radio mobility: {initial_handover.status} -> {handover.status}; "
        f"stable IP={transfer.stable_ip}; authenticated principal={transfer.principal}"
    )

    cdn_transport = SeamlessTransportSession(CHANNELS, rng=random.Random(2027))
    cdn = SelfScalingContentNetwork(cdn_transport)
    for timestamp in (0.0, 1.0, 2.0):
        delivery = cdn.request("bern-edge", "thesis-video", payload, timestamp=timestamp)
        HISTORY_LOGGER.log_transfer(
            timestamp,
            delivery.transfer,
            cache_hit=delivery.cache_hit,
            cache_hit_ratio=cdn.hit_ratio,
        )
        print(
            f"CDN request at t={timestamp:.0f}s: cache_hit={delivery.cache_hit}, "
            f"cache_nodes={cdn.cache_node_count}, request_rate={cdn.demand_trends['bern-edge'].value:.2f}/s, "
            f"acceleration={cdn.demand_trends['bern-edge'].acceleration:.3f}/s^2"
        )

    edge_cluster = KubernetesEdgeCluster(
        name="bern-edge",
        region="bern",
        target_requests_per_second_per_pod=0.25,
        max_replicas=8,
    )
    scaling = KEDAInspiredScaler().reconcile(
        edge_cluster,
        observed_requests_per_second=cdn.demand_trends["bern-edge"].value,
        forecast_requests_per_second=cdn.demand_trends["bern-edge"].forecast,
    )
    print(
        f"Simulated Kubernetes scaling: cluster={scaling.cluster_name}, "
        f"replicas={scaling.desired_replicas}, "
        f"forecast_capacity={scaling.modeled_capacity_requests_per_second:.2f} requests/s"
    )

    ai_scheduler = MultiCloudAIScheduler(
        [
            AIDataCenter(
                "bern-ai",
                "private-cloud",
                "bern",
                latency_ms=8,
                egress_cost_per_gb=0.03,
                available_accelerators=8,
                accelerator_load=0.55,
            ),
            AIDataCenter(
                "eu-central-ai",
                "public-cloud",
                "eu-central",
                latency_ms=28,
                egress_cost_per_gb=0.02,
                available_accelerators=32,
                accelerator_load=0.25,
            ),
        ]
    )
    placement = ai_scheduler.schedule(
        AIWorkload(
            workload_id="demo-inference",
            kind="inference",
            billable_egress_bytes=4_000_000,
            required_accelerators=1,
            latency_slo_ms=40,
        )
    )
    print(
        f"Simulated AI workload placement: {placement.workload_id} -> "
        f"{placement.datacenter} ({placement.provider}/{placement.region}), "
        f"estimated_latency={placement.estimated_latency_ms:.1f} ms, "
        f"configured_egress_estimate={placement.estimated_egress_cost:.4f}"
    )

    mesh_peers = [
        MeshPeer("bern-edge", cache_capacity_bytes=100_000),
        MeshPeer("zurich-edge", cache_capacity_bytes=100_000),
        MeshPeer("ai-core", cache_capacity_bytes=100_000),
    ]
    mesh = PeerMesh(
        mesh_peers,
        [
            MeshLink("bern-edge", "ai-core", capacity_mbps=1000, base_latency_ms=3),
            MeshLink("bern-edge", "zurich-edge", capacity_mbps=1000, base_latency_ms=8),
            MeshLink("zurich-edge", "ai-core", capacity_mbps=1000, base_latency_ms=8),
        ],
        trusted_publishers={"model-registry"},
    )
    model_payload = b"demo AI model artifact"
    mesh.register_manifest(
        "edge-model-v1",
        "model-registry",
        hashlib.sha256(model_payload).hexdigest(),
    )
    mesh.publish("ai-core", "edge-model-v1", model_payload, "model-registry")
    for _ in range(3):
        mesh_telemetry = mesh.record_link_telemetry(
            "bern-edge",
            "ai-core",
            utilization=0.95,
            queue_delay_ms=50,
            loss_rate=0.02,
        )
    print(
        f"Peer mesh predicted congestion: bern-edge/ai-core "
        f"pressure={mesh_telemetry.predicted_pressure:.2f}; "
        f"active={mesh_telemetry.congestion_active}"
    )
    for request_number in range(1, 4):
        mesh_result = mesh.request("bern-edge", "edge-model-v1")
        print(
            f"Mesh request {request_number}: path={' -> '.join(mesh_result.path)}, "
            f"cache_action={mesh_result.cache_action}, "
            f"NPU-inspired anomaly_score={mesh_result.cache_admission_score}"
        )
    local_mesh_hit = mesh.request("bern-edge", "edge-model-v1")
    print(
        f"Mesh follow-up request: local_cache_hit={local_mesh_hit.cache_hit}, "
        f"path={' -> '.join(local_mesh_hit.path)}"
    )

    collector = INTCollector()
    env = simpy.Environment()
    env.process(network_traffic_generator(env, collector, HISTORY_LOGGER))
    env.run(until=10)

    latest = collector.latest()
    if latest is not None:
        print("\nINT telemetry summary:")
        print(f"Last best medium: {latest.best_medium}")
        print(f"Last packet distribution: {latest.routing_distribution}")
        print(f"Channel states: {latest.channel_states}")

    plt.close(fig)


if __name__ == "__main__":
    main()
