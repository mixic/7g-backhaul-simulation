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

import random
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import simpy

from simulation.channels import build_default_channels
from simulation.cdn import SelfScalingContentNetwork
from simulation.continuity import SeamlessTransportSession
from simulation.router import SoftHandoverRouter
from simulation.telemetry import InBandTelemetry, INTCollector

CHANNELS = build_default_channels()
ROUTER = SoftHandoverRouter(CHANNELS)
FIGURES_DIR = Path(__file__).resolve().parent / "figures"

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


def network_traffic_generator(env, collector, burst_interval=1.0):
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
    transport = SeamlessTransportSession(CHANNELS, rng=random.Random(2026))
    payload = (b"7G seamless multi-medium content delivery " * 400)
    transfer = transport.transmit(payload, session_id="demo-mobile-session")
    print(
        f"Continuous session: {len(transfer.payload)} bytes across "
        f"{', '.join(sorted(set(transfer.media_used)))}; retries={transfer.retries}"
    )

    cdn = SelfScalingContentNetwork(transport)
    for timestamp in (0.0, 1.0, 2.0):
        delivery = cdn.request("bern-edge", "thesis-video", payload, timestamp=timestamp)
        print(
            f"CDN request at t={timestamp:.0f}s: cache_hit={delivery.cache_hit}, "
            f"cache_nodes={cdn.cache_node_count}, request_rate={cdn.demand_trends['bern-edge'].value:.2f}/s, "
            f"acceleration={cdn.demand_trends['bern-edge'].acceleration:.3f}/s^2"
        )

    collector = INTCollector()
    env = simpy.Environment()
    env.process(network_traffic_generator(env, collector))
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
