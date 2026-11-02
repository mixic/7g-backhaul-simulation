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

"""Event-driven synthetic multipath, real-time media, and cloud-failover study."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import simpy
from matplotlib.patches import Patch

SIMULATION_SECONDS = 240
VIDEO_FPS = 30
VIDEO_FRAME_SEGMENTS = 4
VIDEO_FRAME_DEADLINE_MS = 150.0
AUDIO_PACKETS_PER_SECOND = 50
AUDIO_PACKET_DEADLINE_MS = 50.0
VIDEO_BITRATE_MBPS = 4.0
AUDIO_BITRATE_MBPS = 0.128
MEDIA_BITRATE_MBPS = VIDEO_BITRATE_MBPS + AUDIO_BITRATE_MBPS
POLICIES = (
    "Reactive baseline",
    "Full cooperative",
    "Reactive with selective duplication",
    "Predictive paths only",
    "Prepared cloud only",
    "Predictive paths and prepared cloud",
)
POLICY_LABELS = (
    "Reactive",
    "Full\ncooperative",
    "Reactive\n+ duplication",
    "Predictive\npaths",
    "Prepared\ncloud",
    "Predictive\npaths + cloud",
)


@dataclass(frozen=True)
class Policy:
    predictive_paths: bool
    prepared_cloud: bool
    duplicate_media: bool


POLICY_CONFIGS = {
    POLICIES[0]: Policy(False, False, False),
    POLICIES[1]: Policy(True, True, True),
    POLICIES[2]: Policy(False, False, True),
    POLICIES[3]: Policy(True, False, False),
    POLICIES[4]: Policy(False, True, False),
    POLICIES[5]: Policy(True, True, False),
}


@dataclass(frozen=True)
class Scenario:
    name: str
    demand_scale: float = 1.0
    correlated_cell_failure: bool = False
    setup_delay_scale: float = 1.0
    cloud_startup_scale: float = 1.0


SCENARIOS = (
    Scenario("nominal"),
    Scenario("peak_demand", demand_scale=1.25),
    Scenario(
        "correlated_outage",
        demand_scale=1.1,
        correlated_cell_failure=True,
        setup_delay_scale=1.5,
        cloud_startup_scale=1.5,
    ),
)
PATHS = (
    ("fiber", 150.0, 8.0, 0.002),
    ("cellular", 100.0, 28.0, 0.008),
    ("microwave", 95.0, 16.0, 0.004),
    ("satellite", 140.0, 125.0, 0.012),
)


@dataclass(frozen=True)
class Metrics:
    demand_delivery_percent: float
    critical_service_availability_percent: float
    video_frames_on_time_percent: float
    audio_packets_on_time_percent: float
    p95_video_frame_delay_ms: float
    p95_audio_interarrival_variation_ms: float
    video_stall_seconds: float
    longest_video_freeze_seconds: float
    media_copy_loss_percent: float
    path_recovery_seconds: float
    path_recovery_censored: float
    cloud_recovery_seconds: float
    cloud_recovery_censored: float
    mean_active_paths: float
    duplicate_packet_percent: float
    duplicate_payload_percent: float
    secondary_region_capacity_mbps_seconds: float
    media_queue_drop_percent: float


@dataclass
class Packet:
    bits: float
    result: simpy.Event


class PathQueue:
    def __init__(
        self,
        env: simpy.Environment,
        path_index: int,
        scenario: Scenario,
        background_utilization: Callable[[], float],
        rng: np.random.Generator,
        buffer_packets: int = 256,
    ) -> None:
        self.env = env
        self.path_index = path_index
        self.scenario = scenario
        self.background_utilization = background_utilization
        self.rng = rng
        self.buffer_packets = buffer_packets
        self.pending = 0
        self.backlog = 0
        self.queue_drops = 0
        self.sequence = 0
        self.queue: simpy.PriorityStore = simpy.PriorityStore(env)
        env.process(self._serve())

    def capacity(self, time_ms: float) -> float:
        return _path_capacity(
            self.path_index,
            int(time_ms // 1000),
            self.scenario,
        )

    def submit(self, bits: float, priority: int) -> simpy.Event:
        result = self.env.event()
        if self.pending >= self.buffer_packets:
            self.queue_drops += 1
            result.succeed(None)
            return result
        self.pending += 1
        self.backlog += 1
        self.sequence += 1
        packet = Packet(bits=bits, result=result)
        self.queue.put((priority, self.sequence, packet))
        return result

    def _finish(self, packet: Packet, arrival_ms: float | None) -> None:
        self.pending -= 1
        if not packet.result.triggered:
            packet.result.succeed(arrival_ms)

    def _arrive(self, packet: Packet, propagation_ms: float):
        yield self.env.timeout(propagation_ms)
        self._finish(packet, self.env.now)

    def _serve(self):
        while True:
            _, _, packet = yield self.queue.get()
            capacity = self.capacity(self.env.now)
            if capacity <= 0.0:
                self.backlog -= 1
                self._finish(packet, None)
                continue

            utilization = min(0.95, self.background_utilization())
            effective_capacity = capacity * max(0.05, 1.0 - 0.75 * utilization)
            serialization_ms = packet.bits / (effective_capacity * 1000.0)
            yield self.env.timeout(serialization_ms)
            self.backlog -= 1
            if self.capacity(self.env.now) <= 0.0:
                self._finish(packet, None)
                continue

            _, _, base_delay, base_loss = PATHS[self.path_index]
            congestion_loss = max(0.0, utilization - 0.65) * 0.06
            if self.rng.random() < min(0.20, base_loss + congestion_loss):
                self._finish(packet, None)
                continue

            jitter_sigma = 0.5 + 0.025 * base_delay
            propagation_ms = max(
                0.0,
                base_delay + float(self.rng.normal(0.0, jitter_sigma)),
            )
            self.env.process(self._arrive(packet, propagation_ms))


def _demand(second: int, rng: np.random.Generator, scale: float) -> tuple[float, float]:
    critical = 18.0
    growth = 0.28 * min(second, 150)
    congestion_wave = 85.0 * np.exp(-((second - 95.0) / 13.0) ** 2)
    second_wave = 48.0 * np.exp(-((second - 180.0) / 16.0) ** 2)
    bulk = max(
        0.0,
        (
            72.0
            + growth
            + congestion_wave
            + second_wave
            + float(rng.normal(0.0, 2.0))
        )
        * scale,
    )
    return critical * scale, bulk


def _path_capacity(index: int, second: int, scenario: Scenario) -> float:
    capacity = PATHS[index][1]
    if index == 0:
        if 70 <= second < 95:
            return capacity * (95 - second) / 25.0
        if 95 <= second < 115:
            return 0.0
        if 115 <= second < 130:
            return capacity * (second - 115) / 15.0
    if index == 1 and scenario.correlated_cell_failure and 95 <= second < 115:
        return 0.0
    if index == 1 and 145 <= second < 155:
        return capacity * (second - 145) / 10.0
    if index == 1 and 155 <= second < 165:
        return 0.0
    return capacity


def _cloud_a_health(second: int) -> float:
    if second < 140:
        return 1.0
    if second < 155:
        return (155 - second) / 15.0
    if second < 180:
        return 0.0
    return 1.0


def _linear_forecast(history: list[float], horizon: int) -> float:
    if len(history) < 3:
        return history[-1] if history else 0.0
    recent = np.asarray(history[-5:], dtype=float)
    velocity = float(np.median(np.diff(recent)))
    return max(0.0, float(recent[-1] + velocity * horizon))


def _longest_failure_run(successes: list[bool]) -> int:
    longest = 0
    current = 0
    for success in successes:
        if success:
            longest = max(longest, current)
            current = 0
        else:
            current += 1
    return max(longest, current)


def _event_recovery(
    frame_success_by_second: dict[int, list[bool]],
    event_second: int,
) -> tuple[float, float]:
    for second in range(event_second, SIMULATION_SECONDS):
        interval = frame_success_by_second.get(second, [])
        if interval and np.mean(interval) >= 0.95:
            return float(second - event_second), 0.0
    return float(SIMULATION_SECONDS - event_second), 1.0


def _simulate(
    policy_name: str,
    seed: int,
    scenario: Scenario,
) -> tuple[Metrics, dict[str, list[float]]]:
    if policy_name not in POLICY_CONFIGS:
        raise ValueError(f"Unknown policy: {policy_name}")
    policy = POLICY_CONFIGS[policy_name]
    env = simpy.Environment()
    demand_rng = np.random.default_rng(seed)
    path_rngs = [
        np.random.default_rng(seed ^ (0x51A7 + index * 0x101))
        for index in range(len(PATHS))
    ]
    state: dict[str, object] = {
        "active_paths": {0, 1},
        "path_ready_at": {},
        "cloud_b_ready_at": None,
        "cloud_b_capacity": 0.0,
        "cloud_capacity": 300.0,
        "background_utilization": 0.0,
    }

    def background_utilization() -> float:
        return float(state["background_utilization"])

    path_queues = [
        PathQueue(
            env,
            index,
            scenario,
            background_utilization,
            path_rngs[index],
        )
        for index in range(len(PATHS))
    ]
    demand_history: list[float] = []
    capacity_history: list[float] = []
    demand_requested = 0.0
    demand_delivered = 0.0
    critical_ticks = 0
    critical_available_ticks = 0
    active_path_samples: list[int] = []
    secondary_capacity_time = 0.0
    cloud_failure_second = 155
    path_failure_second = 95
    video_frame_outcomes: dict[int, tuple[float, float | None, bool]] = {}
    audio_outcomes: dict[int, tuple[float, float | None, bool]] = {}
    duplicate_packets = 0
    duplicate_bits = 0.0
    original_packets = 0
    original_bits = 0.0
    packet_copies = 0
    failed_copies = 0
    per_second_capacity: list[float] = []
    per_second_demand: list[float] = []

    def cloud_capacity_at(time_ms: float) -> float:
        second = min(SIMULATION_SECONDS - 1, int(time_ms // 1000))
        cloud_a = 300.0 * _cloud_a_health(second)
        if cloud_a > 0.0:
            return cloud_a
        ready_at = state["cloud_b_ready_at"]
        if ready_at is not None and time_ms / 1000.0 >= float(ready_at):
            return 240.0
        return 0.0

    def control_loop():
        nonlocal demand_requested, demand_delivered
        nonlocal critical_ticks, critical_available_ticks
        nonlocal secondary_capacity_time
        for second in range(SIMULATION_SECONDS):
            critical, bulk = _demand(second, demand_rng, scenario.demand_scale)
            demand = critical + bulk
            demand_requested += demand
            demand_history.append(demand)
            demand_history[:] = demand_history[-5:]

            active_paths = state["active_paths"]
            path_ready_at = state["path_ready_at"]
            measured_capacity = sum(
                _path_capacity(index, second, scenario)
                for index in active_paths
                if path_ready_at.get(index, 0.0) <= second
            )
            capacity_history.append(measured_capacity)
            capacity_history[:] = capacity_history[-5:]
            if policy.predictive_paths:
                forecast_demand = _linear_forecast(demand_history, 8)
                forecast_capacity = (
                    max(1.0, min(capacity_history))
                    if len(capacity_history) >= 3
                    else measured_capacity
                )
                threshold = 0.72
                setup_delay = 1.0 * scenario.setup_delay_scale
            else:
                forecast_demand = demand
                forecast_capacity = measured_capacity
                threshold = 0.82
                setup_delay = 3.0 * scenario.setup_delay_scale
            fiber_health = _path_capacity(0, second, scenario) / PATHS[0][1]
            should_expand = (
                forecast_demand >= threshold * max(forecast_capacity, 1.0)
                or (
                    policy.predictive_paths
                    and 0.0 < fiber_health < 0.8
                )
            )
            if should_expand:
                for index in range(len(PATHS)):
                    if index in active_paths:
                        continue
                    active_paths.add(index)
                    path_ready_at[index] = second + setup_delay
                    break

            active_indices = [
                index
                for index in active_paths
                if path_ready_at.get(index, 0.0) <= second
                and _path_capacity(index, second, scenario) > 0.0
            ]
            network_capacity = sum(
                _path_capacity(index, second, scenario)
                for index in active_indices
            )
            cloud_a = 300.0 * _cloud_a_health(second)
            if (
                policy.prepared_cloud
                and cloud_a < 300.0
                and state["cloud_b_ready_at"] is None
            ):
                state["cloud_b_ready_at"] = (
                    second + 8.0 * scenario.cloud_startup_scale
                )
            elif (
                not policy.prepared_cloud
                and cloud_a <= 0.0
                and state["cloud_b_ready_at"] is None
            ):
                state["cloud_b_ready_at"] = (
                    second + 20.0 * scenario.cloud_startup_scale
                )
            ready_at = state["cloud_b_ready_at"]
            cloud_b = (
                240.0
                if ready_at is not None and second >= float(ready_at)
                else 0.0
            )
            state["cloud_b_capacity"] = cloud_b
            if cloud_b > 0.0 and cloud_a < 300.0:
                secondary_capacity_time += cloud_b
            cloud_capacity = cloud_a if cloud_a > 0.0 else cloud_b
            state["cloud_capacity"] = cloud_capacity
            system_capacity = min(network_capacity, cloud_capacity)
            delivered = min(demand, system_capacity)
            demand_delivered += delivered
            critical_ticks += 1
            critical_available_ticks += int(delivered >= 0.99 * critical)
            utilization = (
                max(0.0, demand - MEDIA_BITRATE_MBPS) / network_capacity
                if network_capacity > 0.0
                else 1.0
            )
            state["background_utilization"] = min(0.95, utilization)
            active_path_samples.append(len(active_indices))
            per_second_capacity.append(system_capacity)
            per_second_demand.append(demand)
            yield env.timeout(1000.0)

    def ranked_paths() -> list[int]:
        current_second = min(SIMULATION_SECONDS - 1, int(env.now // 1000))
        active_paths = state["active_paths"]
        path_ready_at = state["path_ready_at"]
        candidates: list[tuple[float, int]] = []
        packet_bits = VIDEO_BITRATE_MBPS * 1_000_000.0 / (
            VIDEO_FPS * VIDEO_FRAME_SEGMENTS
        )
        for index in active_paths:
            if path_ready_at.get(index, 0.0) > env.now / 1000.0:
                continue
            capacity = _path_capacity(index, current_second, scenario)
            if capacity <= 0.0:
                continue
            _, _, base_delay, base_loss = PATHS[index]
            effective_capacity = capacity * max(
                0.05,
                1.0 - 0.75 * background_utilization(),
            )
            service_ms = packet_bits / (effective_capacity * 1000.0)
            queue_ms = path_queues[index].backlog * service_ms
            score = base_delay + service_ms + queue_ms
            candidates.append((score, index))
        return [index for _, index in sorted(candidates)]

    def transmit_packet(
        path_index: int,
        bits: float,
        priority: int,
    ):
        nonlocal packet_copies, failed_copies
        packet_copies += 1
        packet_result = path_queues[path_index].submit(bits, priority)
        arrival = yield packet_result
        if arrival is None:
            failed_copies += 1
            return None
        cloud_capacity = cloud_capacity_at(float(arrival))
        if cloud_capacity <= 0.0:
            failed_copies += 1
            return None
        processing_ms = 2.0 + bits / (cloud_capacity * 1000.0)
        yield env.timeout(processing_ms)
        if cloud_capacity_at(env.now) <= 0.0:
            failed_copies += 1
            return None
        return env.now

    def video_frame(frame_index: int, release_ms: float):
        nonlocal duplicate_packets, duplicate_bits, original_packets, original_bits
        if release_ms > env.now:
            yield env.timeout(release_ms - env.now)
        candidates = ranked_paths()
        segment_events: list[list[simpy.Event]] = []
        frame_segment_bits = (
            VIDEO_BITRATE_MBPS
            * 1_000_000.0
            / (VIDEO_FPS * VIDEO_FRAME_SEGMENTS)
        )
        for segment_index in range(VIDEO_FRAME_SEGMENTS):
            original_packets += 1
            original_bits += frame_segment_bits
            if not candidates:
                segment_events.append([])
                continue
            primary = candidates[segment_index % min(2, len(candidates))]
            primary_score = next(
                score
                for score, index in _ranked_path_scores(
                    candidates,
                    path_queues,
                    scenario,
                    env.now,
                    background_utilization(),
                )
                if index == primary
            )
            _, _, _, primary_loss = PATHS[primary]
            route_events = [
                env.process(transmit_packet(primary, frame_segment_bits, 1))
            ]
            risk = (
                primary_score >= 0.65 * VIDEO_FRAME_DEADLINE_MS
                or primary_loss >= 0.015
                or background_utilization() >= 0.85
                or path_queues[primary].backlog >= 12
            )
            if policy.duplicate_media and risk and len(candidates) > 1:
                backups = [index for index in candidates if index != primary]
                backup = backups[0]
                route_events.append(
                    env.process(transmit_packet(backup, frame_segment_bits, 1))
                )
                duplicate_packets += 1
                duplicate_bits += frame_segment_bits
            segment_events.append(route_events)

        all_events = [
            event for segment in segment_events for event in segment
        ]
        if all_events:
            results = yield env.all_of(all_events)
            segment_arrivals = []
            for segment in segment_events:
                valid = [
                    float(results[event])
                    for event in segment
                    if results[event] is not None
                ]
                segment_arrivals.append(min(valid) if valid else None)
        else:
            segment_arrivals = [None] * VIDEO_FRAME_SEGMENTS
        complete = all(arrival is not None for arrival in segment_arrivals)
        completion = (
            max(float(arrival) for arrival in segment_arrivals)
            if complete
            else None
        )
        delay = completion - release_ms if completion is not None else None
        on_time = bool(delay is not None and delay <= VIDEO_FRAME_DEADLINE_MS)
        video_frame_outcomes[frame_index] = (release_ms, delay, on_time)

    def audio_packet(packet_index: int, release_ms: float):
        nonlocal duplicate_packets, duplicate_bits, original_packets, original_bits
        if release_ms > env.now:
            yield env.timeout(release_ms - env.now)
        candidates = ranked_paths()
        packet_bits = AUDIO_BITRATE_MBPS * 1_000_000.0 / AUDIO_PACKETS_PER_SECOND
        original_packets += 1
        original_bits += packet_bits
        events: list[simpy.Event] = []
        if candidates:
            primary = candidates[0]
            events.append(env.process(transmit_packet(primary, packet_bits, 0)))
            _, _, _, primary_loss = PATHS[primary]
            estimated_delay = next(
                score
                for score, index in _ranked_path_scores(
                    candidates,
                    path_queues,
                    scenario,
                    env.now,
                    background_utilization(),
                )
                if index == primary
            )
            risk = (
                estimated_delay >= 0.65 * AUDIO_PACKET_DEADLINE_MS
                or primary_loss >= 0.015
                or background_utilization() >= 0.85
                or path_queues[primary].backlog >= 12
            )
            if policy.duplicate_media and risk and len(candidates) > 1:
                events.append(
                    env.process(transmit_packet(candidates[1], packet_bits, 0))
                )
                duplicate_packets += 1
                duplicate_bits += packet_bits
        if events:
            results = yield env.all_of(events)
            arrivals = [
                float(results[event])
                for event in events
                if results[event] is not None
            ]
        else:
            arrivals = []
        arrival = min(arrivals) if arrivals else None
        delay = arrival - release_ms if arrival is not None else None
        audio_outcomes[packet_index] = (
            release_ms,
            delay,
            bool(delay is not None and delay <= AUDIO_PACKET_DEADLINE_MS),
        )

    def video_source():
        for frame_index in range(SIMULATION_SECONDS * VIDEO_FPS):
            release_ms = frame_index * 1000.0 / VIDEO_FPS
            if release_ms > env.now:
                yield env.timeout(release_ms - env.now)
            env.process(video_frame(frame_index, release_ms))

    def audio_source():
        for packet_index in range(SIMULATION_SECONDS * AUDIO_PACKETS_PER_SECOND):
            release_ms = packet_index * 1000.0 / AUDIO_PACKETS_PER_SECOND
            if release_ms > env.now:
                yield env.timeout(release_ms - env.now)
            env.process(audio_packet(packet_index, release_ms))

    env.process(control_loop())
    env.process(video_source())
    env.process(audio_source())
    env.run(until=SIMULATION_SECONDS * 1000.0 + 1000.0)

    video_ordered = [
        video_frame_outcomes[index]
        for index in sorted(video_frame_outcomes)
    ]
    video_successes = [outcome[2] for outcome in video_ordered]
    video_delays = [
        float(outcome[1])
        for outcome in video_ordered
        if outcome[1] is not None
    ]
    audio_ordered = [
        audio_outcomes[index] for index in sorted(audio_outcomes)
    ]
    audio_successes = [outcome[2] for outcome in audio_ordered]
    audio_arrivals = [
        (outcome[0], outcome[0] + float(outcome[1]))
        for outcome in audio_ordered
        if outcome[1] is not None
    ]
    interarrival_variation = [
        abs(
            (current_arrival - previous_arrival)
            - (current_release - previous_release)
        )
        for (previous_release, previous_arrival), (
            current_release,
            current_arrival,
        ) in zip(audio_arrivals, audio_arrivals[1:])
    ]
    frame_success_by_second: dict[int, list[bool]] = {}
    for release_ms, _, on_time in video_ordered:
        second = min(SIMULATION_SECONDS - 1, int(release_ms // 1000))
        frame_success_by_second.setdefault(second, []).append(on_time)
    path_recovery, path_censored = _event_recovery(
        frame_success_by_second,
        path_failure_second,
    )
    cloud_recovery, cloud_censored = _event_recovery(
        frame_success_by_second,
        cloud_failure_second,
    )
    copy_count = max(packet_copies, 1)
    original_count = max(original_packets, 1)
    frame_failures = [not success for success in video_successes]
    longest_freeze = _longest_failure_run(video_successes) / VIDEO_FPS
    demand_delivery = 100.0 * demand_delivered / max(demand_requested, 1e-9)
    metrics = Metrics(
        demand_delivery_percent=demand_delivery,
        critical_service_availability_percent=(
            100.0 * critical_available_ticks / max(critical_ticks, 1)
        ),
        video_frames_on_time_percent=(
            100.0 * float(np.mean(video_successes)) if video_successes else 0.0
        ),
        audio_packets_on_time_percent=(
            100.0 * float(np.mean(audio_successes)) if audio_successes else 0.0
        ),
        p95_video_frame_delay_ms=(
            float(np.percentile(video_delays, 95)) if video_delays else 0.0
        ),
        p95_audio_interarrival_variation_ms=(
            float(np.percentile(interarrival_variation, 95))
            if interarrival_variation
            else 0.0
        ),
        video_stall_seconds=float(sum(frame_failures) / VIDEO_FPS),
        longest_video_freeze_seconds=float(longest_freeze),
        media_copy_loss_percent=100.0 * failed_copies / copy_count,
        path_recovery_seconds=path_recovery,
        path_recovery_censored=path_censored,
        cloud_recovery_seconds=cloud_recovery,
        cloud_recovery_censored=cloud_censored,
        mean_active_paths=float(np.mean(active_path_samples)),
        duplicate_packet_percent=(
            100.0 * duplicate_packets / original_count
        ),
        duplicate_payload_percent=(
            100.0 * duplicate_bits / max(original_bits, 1e-9)
        ),
        secondary_region_capacity_mbps_seconds=secondary_capacity_time,
        media_queue_drop_percent=(
            100.0
            * sum(queue.queue_drops for queue in path_queues)
            / copy_count
        ),
    )
    trace = {
        "demand_mbps": per_second_demand,
        "system_capacity_mbps": per_second_capacity,
        "video_on_time_percent": [
            100.0 * float(np.mean(frame_success_by_second.get(second, [False])))
            for second in range(SIMULATION_SECONDS)
        ],
    }
    return metrics, trace


def _ranked_path_scores(
    candidates: list[int],
    path_queues: list[PathQueue],
    scenario: Scenario,
    time_ms: float,
    utilization: float,
) -> list[tuple[float, int]]:
    second = min(SIMULATION_SECONDS - 1, int(time_ms // 1000))
    packet_bits = VIDEO_BITRATE_MBPS * 1_000_000.0 / (
        VIDEO_FPS * VIDEO_FRAME_SEGMENTS
    )
    scores = []
    for index in candidates:
        capacity = _path_capacity(index, second, scenario)
        if capacity <= 0.0:
            continue
        _, _, base_delay, _ = PATHS[index]
        effective_capacity = capacity * max(0.05, 1.0 - 0.75 * utilization)
        service_ms = packet_bits / (effective_capacity * 1000.0)
        score = base_delay + service_ms * (path_queues[index].backlog + 1)
        scores.append((score, index))
    return scores


def simulate(
    policy: str,
    seed: int,
    scenario: Scenario = SCENARIOS[0],
) -> Metrics:
    return _simulate(policy, seed, scenario)[0]


def _mean_ci(values: list[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    mean = float(np.mean(array))
    ci = (
        float(1.96 * np.std(array, ddof=1) / np.sqrt(len(array)))
        if len(array) > 1
        else 0.0
    )
    return mean, ci


def run_benchmark(
    output_dir: Path,
    replicates: int = 20,
    seed: int = 2026,
) -> list[dict[str, object]]:
    if replicates < 2:
        raise ValueError("At least two independent replicates are required.")
    output_dir.mkdir(parents=True, exist_ok=True)
    seed_rng = np.random.default_rng(seed)
    seeds = [
        int(value)
        for value in seed_rng.integers(0, 2**31 - 1, replicates)
    ]
    metric_names = tuple(Metrics.__dataclass_fields__)
    observations: dict[tuple[str, str, str], list[float]] = {}
    trace_observations: dict[tuple[str, str, str], list[np.ndarray]] = {}
    rows: list[dict[str, object]] = []
    for scenario in SCENARIOS:
        for policy in POLICIES:
            policy_observations = {name: [] for name in metric_names}
            for replicate_seed in seeds:
                metrics, trace = _simulate(policy, replicate_seed, scenario)
                for name in metric_names:
                    value = float(getattr(metrics, name))
                    policy_observations[name].append(value)
                    observations.setdefault(
                        (scenario.name, policy, name),
                        [],
                    ).append(value)
                for name, values in trace.items():
                    trace_observations.setdefault(
                        (scenario.name, policy, name),
                        [],
                    ).append(np.asarray(values, dtype=float))
            row: dict[str, object] = {
                "scenario": scenario.name,
                "policy": policy,
                "replicates": replicates,
            }
            for name, values in policy_observations.items():
                row[name], row[f"{name}_ci95"] = _mean_ci(values)
                baseline = observations[(scenario.name, POLICIES[0], name)]
                if policy == POLICIES[0]:
                    paired_differences = [0.0] * replicates
                else:
                    paired_differences = [
                        current - base
                        for current, base in zip(values, baseline)
                    ]
                (
                    row[f"{name}_paired_delta_vs_reactive"],
                    row[f"{name}_paired_ci95"],
                ) = _mean_ci(paired_differences)
            rows.append(row)

    csv_path = output_dir / "brain_inspired_cooperative_benchmark.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    _plot(rows, output_dir)
    _plot_timeseries(trace_observations, output_dir, replicates)
    print(f"Replicates per policy and scenario: {replicates}; seed: {seed}")
    print(f"Summary CSV: {csv_path}")
    for row in rows:
        if row["scenario"] == SCENARIOS[0].name:
            print(
                f"{row['policy']} | video on-time="
                f"{row['video_frames_on_time_percent']:.2f}% | "
                f"audio on-time={row['audio_packets_on_time_percent']:.2f}% | "
                f"cloud service recovery={row['cloud_recovery_seconds']:.1f}s"
            )
    return rows


def _plot_metric_grid(
    rows: list[dict[str, object]],
    output_path: Path,
    metrics: tuple[tuple[str, str, bool], ...],
) -> None:
    figure, axes = plt.subplots(
        len(SCENARIOS),
        len(metrics),
        figsize=(5.0 * len(metrics), 4.1 * len(SCENARIOS)),
        squeeze=False,
        layout="constrained",
    )
    colors = ("#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2")
    for row_index, scenario in enumerate(SCENARIOS):
        scenario_rows = [
            row for row in rows if row["scenario"] == scenario.name
        ]
        for column_index, (metric, label, lower_is_better) in enumerate(metrics):
            axis = axes[row_index][column_index]
            means = [float(row[metric]) for row in scenario_rows]
            errors = [float(row[f"{metric}_ci95"]) for row in scenario_rows]
            positions = np.arange(len(scenario_rows))
            if any(value != 0.0 for value in means):
                bars = axis.bar(
                    positions,
                    means,
                    yerr=errors,
                    capsize=3,
                    color=colors,
                    edgecolor="white",
                    linewidth=0.5,
                )
                for bar, value in zip(bars, means):
                    axis.annotate(
                        f"{value:.1f}",
                        (bar.get_x() + bar.get_width() / 2.0, value),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha="center",
                        va="bottom",
                        fontsize=8,
                    )
                upper = max(mean + error for mean, error in zip(means, errors))
                axis.set_ylim(0.0, max(1.0, upper * 1.2))
            else:
                axis.scatter(
                    positions,
                    np.zeros(len(positions)),
                    color=colors,
                    edgecolors="black",
                    s=55,
                    zorder=3,
                )
                axis.set_ylim(-0.02, 0.3)
                for position in positions:
                    axis.annotate(
                        "0",
                        (position, 0),
                        xytext=(0, 7),
                        textcoords="offset points",
                        ha="center",
                        fontsize=8,
                    )
            axis.set_xticks(
                positions,
                POLICY_LABELS,
                rotation=20,
                ha="right",
                fontsize=8,
            )
            axis.set_ylabel(label)
            axis.set_title(
                "Resource tradeoff"
                if metric in {
                    "duplicate_payload_percent",
                    "secondary_region_capacity_mbps_seconds",
                }
                else "Lower is better"
                if lower_is_better
                else "Higher is better"
            )
            axis.grid(axis="y", alpha=0.25)
            if column_index == 0:
                axis.text(
                    -0.22,
                    0.5,
                    scenario.name.replace("_", " ").title(),
                    transform=axis.transAxes,
                    rotation=90,
                    va="center",
                    ha="center",
                    fontsize=10,
                    fontweight="bold",
                )
    figure.suptitle(
        "Event-driven synthetic multipath and multicloud study "
        f"(mean and 95% CI; n={rows[0]['replicates']} per policy/scenario)"
    )
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def _plot(rows: list[dict[str, object]], output_dir: Path) -> None:
    _plot_metric_grid(
        rows,
        output_dir / "brain_inspired_cooperative_benchmark.png",
        (
            (
                "video_frames_on_time_percent",
                "Reconstructed video frames on time (%)",
                False,
            ),
            (
                "audio_packets_on_time_percent",
                "Audio packets on time (%)",
                False,
            ),
            (
                "p95_video_frame_delay_ms",
                "p95 complete-frame delay (ms)",
                True,
            ),
            ("cloud_recovery_seconds", "Cloud QoS recovery (s)", True),
        ),
    )
    _plot_metric_grid(
        rows,
        output_dir / "brain_inspired_cooperative_resources.png",
        (
            ("demand_delivery_percent", "Demand delivered (%)", False),
            ("media_copy_loss_percent", "Media-copy loss (%)", True),
            ("duplicate_payload_percent", "Duplicate payload (%)", True),
            (
                "secondary_region_capacity_mbps_seconds",
                "Secondary-region capacity-time (Mbps·s)",
                True,
            ),
        ),
    )
    _plot_paired_effects(
        rows,
        output_dir / "brain_inspired_cooperative_effects.png",
    )


def _plot_paired_effects(rows: list[dict[str, object]], output_path: Path) -> None:
    metrics = (
        ("video_frames_on_time_percent", "Video on-time (percentage points)"),
        ("audio_packets_on_time_percent", "Audio on-time (percentage points)"),
        ("p95_video_frame_delay_ms", "p95 frame delay (ms)"),
        ("cloud_recovery_seconds", "Cloud QoS recovery (s)"),
    )
    figure, axes = plt.subplots(
        len(SCENARIOS),
        len(metrics),
        figsize=(5.0 * len(metrics), 4.1 * len(SCENARIOS)),
        squeeze=False,
        layout="constrained",
    )
    labels = POLICY_LABELS[1:]
    colors = ("#E45756", "#54A24B", "#F58518", "#B279A2", "#72B7B2")
    for row_index, scenario in enumerate(SCENARIOS):
        scenario_rows = [
            row
            for row in rows
            if row["scenario"] == scenario.name and row["policy"] != POLICIES[0]
        ]
        for column_index, (metric, label) in enumerate(metrics):
            axis = axes[row_index][column_index]
            deltas = [
                float(row[f"{metric}_paired_delta_vs_reactive"])
                for row in scenario_rows
            ]
            errors = [
                float(row[f"{metric}_paired_ci95"])
                for row in scenario_rows
            ]
            positions = np.arange(len(scenario_rows))
            axis.bar(
                positions,
                deltas,
                yerr=errors,
                capsize=3,
                color=colors,
                edgecolor="white",
                linewidth=0.5,
            )
            axis.axhline(0.0, color="#333333", linewidth=1.0)
            for position, delta in zip(positions, deltas):
                axis.annotate(
                    f"{delta:+.2f}",
                    (position, delta),
                    xytext=(0, 4 if delta >= 0.0 else -12),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                )
            endpoints = [
                value
                for delta, error in zip(deltas, errors)
                for value in (delta - error, delta + error)
            ]
            span = max(max(abs(value) for value in endpoints), 1e-6)
            axis.set_ylim(-1.25 * span, 1.25 * span)
            axis.set_xticks(
                positions,
                labels,
                rotation=20,
                ha="right",
                fontsize=8,
            )
            axis.set_title(label)
            axis.set_ylabel("Difference from reactive baseline")
            axis.grid(axis="y", alpha=0.25)
            if column_index == 0:
                axis.text(
                    -0.22,
                    0.5,
                    scenario.name.replace("_", " ").title(),
                    transform=axis.transAxes,
                    rotation=90,
                    va="center",
                    ha="center",
                    fontsize=10,
                    fontweight="bold",
                )
    figure.suptitle(
        "Paired policy effects vs reactive baseline (mean difference ± "
        f"95% normal paired interval; n={rows[0]['replicates']})"
    )
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def _plot_timeseries(
    traces: dict[tuple[str, str, str], list[np.ndarray]],
    output_dir: Path,
    replicates: int,
) -> None:
    figure, axes = plt.subplots(
        len(SCENARIOS),
        2,
        figsize=(15, 4.0 * len(SCENARIOS)),
        squeeze=False,
        layout="constrained",
    )
    time_seconds = np.arange(SIMULATION_SECONDS)
    policy_colors = {
        POLICIES[0]: "#4C78A8",
        POLICIES[1]: "#E45756",
    }
    fault_legend = [
        Patch(facecolor="#999999", alpha=0.25, label="Fiber outage"),
        Patch(facecolor="#B07AA1", alpha=0.2, label="Cellular outage"),
        Patch(facecolor="#F2CF5B", alpha=0.25, label="Cloud-A outage"),
    ]

    def mean_and_interval(samples: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
        values = np.asarray(samples, dtype=float)
        mean = np.mean(values, axis=0)
        if values.shape[0] < 2:
            return mean, np.zeros_like(mean)
        interval = 1.96 * np.std(values, axis=0, ddof=1) / np.sqrt(values.shape[0])
        return mean, interval

    for row_index, scenario in enumerate(SCENARIOS):
        capacity_axis, qos_axis = axes[row_index]
        demand_samples = traces[(scenario.name, POLICIES[0], "demand_mbps")]
        mean_demand, demand_interval = mean_and_interval(demand_samples)
        capacity_axis.plot(
            time_seconds,
            mean_demand,
            color="#333333",
            linewidth=1.5,
            label="Offered demand",
        )
        capacity_axis.fill_between(
            time_seconds,
            mean_demand - demand_interval,
            mean_demand + demand_interval,
            color="#333333",
            alpha=0.12,
        )
        for policy in (POLICIES[0], POLICIES[1]):
            samples = traces[
                (scenario.name, policy, "system_capacity_mbps")
            ]
            mean, interval = mean_and_interval(samples)
            capacity_axis.plot(
                time_seconds,
                mean,
                color=policy_colors[policy],
                linewidth=1.4,
                label=f"{policy} service capacity",
            )
            capacity_axis.fill_between(
                time_seconds,
                np.maximum(0.0, mean - interval),
                mean + interval,
                color=policy_colors[policy],
                alpha=0.12,
            )
            qos_samples = traces[
                (scenario.name, policy, "video_on_time_percent")
            ]
            qos_mean, qos_interval = mean_and_interval(qos_samples)
            qos_axis.plot(
                time_seconds,
                qos_mean,
                color=policy_colors[policy],
                linewidth=1.4,
                label=policy,
            )
            qos_axis.fill_between(
                time_seconds,
                np.maximum(0.0, qos_mean - qos_interval),
                np.minimum(100.0, qos_mean + qos_interval),
                color=policy_colors[policy],
                alpha=0.15,
            )
        for axis in (capacity_axis, qos_axis):
            axis.axvspan(95, 115, color="#999999", alpha=0.12)
            axis.axvspan(145, 165, color="#B07AA1", alpha=0.08)
            axis.axvspan(155, 180, color="#F2CF5B", alpha=0.08)
            axis.set_xlabel("Simulation time (s)")
            axis.grid(alpha=0.25)
        capacity_axis.legend(fontsize=8, loc="best")
        qos_axis.legend(
            handles=[
                plt.Line2D(
                    [0],
                    [0],
                    color=policy_colors[POLICIES[0]],
                    label=POLICIES[0],
                ),
                plt.Line2D(
                    [0],
                    [0],
                    color=policy_colors[POLICIES[1]],
                    label=POLICIES[1],
                ),
                *fault_legend,
            ],
            fontsize=8,
            loc="best",
        )
        capacity_axis.set_ylabel("Mbps")
        capacity_axis.set_title(
            f"{scenario.name.replace('_', ' ').title()}: load and capacity"
        )
        qos_axis.set_ylabel("Frames meeting 150 ms deadline (%)")
        qos_axis.set_ylim(-2, 102)
        qos_axis.set_title("Real-time video QoS")
    figure.suptitle(
        "Paired-seed time series (mean and pointwise 95% normal intervals; "
        f"n={replicates}); shaded bands mark modeled path/cloud faults"
    )
    figure.savefig(
        output_dir / "brain_inspired_cooperative_timeseries.png",
        dpi=180,
    )
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    parser.add_argument("--replicates", type=int, default=20)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    run_benchmark(args.output_dir, args.replicates, args.seed)


if __name__ == "__main__":
    main()
