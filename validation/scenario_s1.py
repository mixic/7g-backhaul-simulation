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

"""Cross-validation scenario S1: multipath scheduling with a handover window.

This module is the Python half of the external cross-validation experiment
described in ``docs/external-validation.md``. The same scenario, with the same
path parameters, packet stream, scheduler rule and handover window, is modelled
independently in ns-3 (``validation/ns3/s1-multipath-handover.cc``). All shared
constants live at the top of this file and are mirrored verbatim in the ns-3
program; changing one without the other invalidates the comparison.

Two model variants are provided for the same scenario:

``v0.1-noqueue``
    The transport model used by this repository's benchmarks: a packet is
    delayed by the path latency plus transmission time at the path capacity,
    and is lost independently with the path loss probability. There is no
    queue, so offered demand above a path's capacity is only attenuated by the
    loss probability.

``v0.2-fifo``
    The same model with a finite first-in-first-out per-path buffer (the
    default ns-3 point-to-point drop-tail queue of 100 packets). This is the
    corrected model: overloaded paths build backlog, delay rises and excess
    packets are dropped.

Serialization uses the 1200-byte application payload plus the 28-byte IPv4/UDP
header, so the Python model and ns-3 account for the same on-wire bytes.

The experiment reports whether the repository's default transport abstraction
(v0.1) agrees with a packet-level reference implementation (ns-3), and whether
the corrected model (v0.2) closes the gap.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from simulation.link_queue import DEFAULT_QUEUE_LIMIT_PACKETS, DropTailQueue

DURATION_SECONDS = 20.0
PACKET_BYTES = 1200
#: IPv4 (20 B) and UDP (8 B) headers add to on-wire serialization in ns-3.
IP_UDP_HEADER_BYTES = 28
WIRE_BYTES = PACKET_BYTES + IP_UDP_HEADER_BYTES
OFFERED_RATE_MBPS = 12.0
HANDOVER_WINDOW_SECONDS = (8.0, 12.0)
QUEUE_LIMIT_PACKETS = DEFAULT_QUEUE_LIMIT_PACKETS
DECISION_INTERVAL_SECONDS = 0.1

#: One path score per packet: capacity / (latency + 1 ms). Mirrored in ns-3.
SCORE_LATENCY_OFFSET_MS = 1.0


@dataclass(frozen=True)
class ValidationPath:
    name: str
    capacity_mbps: float
    one_way_delay_ms: float
    loss_probability: float


PATHS: tuple[ValidationPath, ...] = (
    ValidationPath("fiber_primary", 20.0, 5.0, 0.001),
    ValidationPath("cellular_secondary", 8.0, 25.0, 0.005),
)

SCENARIOS: tuple[str, ...] = ("s0_nominal", "s1_handover")
POLICIES: tuple[str, ...] = (
    "capacity_weighted_swrr_v0.1-noqueue",
    "capacity_weighted_swrr_v0.2-fifo",
)
METRIC_COLUMNS: tuple[str, ...] = (
    "packet_delivery_percent",
    "one_way_delay_p95_ms",
    "goodput_mbps",
    "active_paths_mean",
    "primary_share_percent",
)


def scenario_spec(scenario: str) -> dict[str, object]:
    """Return the shared scenario description consumed by both implementations."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    return {
        "scenario": scenario,
        "duration_seconds": DURATION_SECONDS,
        "packet_bytes": PACKET_BYTES,
        "ip_udp_header_bytes": IP_UDP_HEADER_BYTES,
        "wire_bytes": WIRE_BYTES,
        "offered_rate_mbps": OFFERED_RATE_MBPS,
        "queue_limit_packets": QUEUE_LIMIT_PACKETS,
        "decision_interval_seconds": DECISION_INTERVAL_SECONDS,
        "score_latency_offset_ms": SCORE_LATENCY_OFFSET_MS,
        "handover_window_seconds": (
            list(HANDOVER_WINDOW_SECONDS) if scenario == "s1_handover" else None
        ),
        "paths": [
            {
                "name": path.name,
                "capacity_mbps": path.capacity_mbps,
                "one_way_delay_ms": path.one_way_delay_ms,
                "loss_probability": path.loss_probability,
            }
            for path in PATHS
        ],
    }


def _primary_available(timestamp_seconds: float, scenario: str) -> bool:
    if scenario != "s1_handover":
        return True
    start, end = HANDOVER_WINDOW_SECONDS
    return not (start <= timestamp_seconds < end)


def _path_scores(timestamp_seconds: float, scenario: str) -> list[float]:
    """Capacity/latency score per path; unavailable paths score zero."""
    scores: list[float] = []
    for index, path in enumerate(PATHS):
        if index == 0 and not _primary_available(timestamp_seconds, scenario):
            scores.append(0.0)
        else:
            scores.append(
                path.capacity_mbps / (path.one_way_delay_ms + SCORE_LATENCY_OFFSET_MS)
            )
    return scores


def _normalised_weights(scores: Sequence[float]) -> list[float]:
    total = sum(max(0.0, score) for score in scores)
    if total <= 0.0:
        raise RuntimeError("No path is available, which the S1 scenario never allows.")
    return [max(0.0, score) / total for score in scores]


def _select_path(deficits: list[float], weights: Sequence[float]) -> int:
    """Smooth weighted round-robin, identical to the ns-3 implementation."""
    for index, weight in enumerate(weights):
        deficits[index] += weight
    selected = max(range(len(deficits)), key=lambda index: (deficits[index], -index))
    deficits[selected] -= 1.0
    return selected


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = 0.95 * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def simulate(
    scenario: str,
    policy: str,
    seed: int,
) -> dict[str, object]:
    """Run one replicate of the S1 scenario with the Python transport model."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    if policy not in POLICIES:
        raise ValueError(f"Unknown policy: {policy}")

    fifo = policy == POLICIES[1]
    rng = random.Random(seed)
    interval_seconds = PACKET_BYTES * 8 / (OFFERED_RATE_MBPS * 1_000_000)
    packet_count = int(round(DURATION_SECONDS / interval_seconds))
    deficits = [0.0] * len(PATHS)
    #: One drop-tail link queue per path for the throughput-limited variant.
    queues = [DropTailQueue(QUEUE_LIMIT_PACKETS) for _ in PATHS]
    delivered_bytes = 0
    delivered_delays_ms: list[float] = []
    assigned_to_primary = 0
    active_path_samples = 0.0

    for packet_index in range(packet_count):
        timestamp_seconds = packet_index * interval_seconds
        scores = _path_scores(timestamp_seconds, scenario)
        active_path_samples += sum(1 for score in scores if score > 0.0)
        weights = _normalised_weights(scores)
        selected = _select_path(deficits, weights)
        if selected == 0:
            assigned_to_primary += 1
        path = PATHS[selected]
        serialization_seconds = WIRE_BYTES * 8 / (path.capacity_mbps * 1_000_000)
        queue_delay_seconds = 0.0

        if fifo:
            outcome = queues[selected].arrive(timestamp_seconds, serialization_seconds)
            if outcome.dropped:
                # Drop-tail overflow: the packet never reaches the link.
                continue
            queue_delay_seconds = outcome.queue_delay_seconds

        if rng.random() < path.loss_probability:
            continue
        delivered_delays_ms.append(
            (queue_delay_seconds + serialization_seconds) * 1000.0
            + path.one_way_delay_ms
        )
        delivered_bytes += PACKET_BYTES

    return {
        "scenario": scenario,
        "policy": policy,
        "seed": seed,
        "packet_delivery_percent": 100.0 * delivered_bytes / (PACKET_BYTES * packet_count),
        "one_way_delay_p95_ms": _p95(delivered_delays_ms),
        "goodput_mbps": delivered_bytes * 8 / (DURATION_SECONDS * 1_000_000),
        "active_paths_mean": active_path_samples / packet_count,
        "primary_share_percent": 100.0 * assigned_to_primary / packet_count,
    }


def run_scenario(
    output_path: Path,
    scenario: str,
    policy: str,
    seeds: Sequence[int],
) -> list[dict[str, object]]:
    rows = [simulate(scenario, policy, seed) for seed in seeds]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def write_spec(output_path: Path, scenario: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(scenario_spec(scenario), indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--policy", choices=POLICIES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--write-spec", type=Path)
    args = parser.parse_args()
    if args.write_spec is not None:
        write_spec(args.write_spec, args.scenario)
    rows = run_scenario(args.output, args.scenario, args.policy, args.seeds)
    print(f"Replicates: {len(rows)}")
    print(f"CSV: {args.output}")
    for row in rows:
        print(
            f"{row['scenario']} seed={row['seed']} "
            f"delivery={row['packet_delivery_percent']:.2f}% "
            f"p95={row['one_way_delay_p95_ms']:.2f} ms "
            f"goodput={row['goodput_mbps']:.3f} Mbps"
        )


if __name__ == "__main__":
    main()
