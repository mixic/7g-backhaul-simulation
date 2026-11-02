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

"""Reproducible comparison of Reno, LIA and OLIA on a heterogeneous two-path flow.

Scenario (fixed module-level constants)
---------------------------------------
Path A: 20 Mbit/s bottleneck, 5 ms propagation RTT, 1460-byte MSS.
Path B:  8 Mbit/s bottleneck, 25 ms propagation RTT, 1460-byte MSS.

The two paths are independent bottlenecks, so a multipath flow can in
principle use up to 28 Mbit/s. The capacities and RTTs are stipulated; this
is a simulator experiment, not a measurement of a deployed MPTCP stack.

Simulation model
----------------
The controller is driven by a fixed 5 ms time step (``STEP_SECONDS``), which
is the smallest path RTT and therefore resolves the faster path's feedback
loop. The step is short enough that 60 simulated seconds contain 12,000
steps. Each path has a drop-tail bottleneck queue of ``2 * BDP`` bytes,
where BDP is the path's bandwidth-delay product. At every step:

* the controller's current window implies an offered rate ``cwnd / rtt``;
* the offered bytes are appended to the queue, overflow beyond the queue
  limit is dropped, and up to ``capacity * STEP_SECONDS`` bytes are served;
* served bytes are acknowledged after the path's propagation RTT (queueing
  delay is deliberately not fed back: the controller sees a fixed-RTT path,
  which keeps the comparison focused on the congestion-control algorithm);
* at most one congestion response is applied per RTT, even if the queue
  remains full across steps. This models a single fast-retransmit episode
  per congestion event instead of halving the window on every 5 ms tick.

ACKs are batched per path per step: one ACK event acknowledges all bytes
served on that path during the step. All three increase rules are linear in
the acknowledged byte count, so batching doesn't change the cumulative
window growth; it only changes the bookkeeping granularity. The reported
``ack_increase_fraction`` is therefore the fraction of ACK *events* that
increased the window, not the fraction of individual segments.

Each replicate is paired across algorithms: the replicate seed initialises
the same per-path initial windows (uniformly 8-12 segments) for all three
algorithms, and adds independent +/-2% uniform RTT measurement noise for the
controller. The physical service rate uses the true path RTT; the noise only
perturbs the controller's RTT estimate. Run seeds are generated with
``numpy.random.default_rng(seed).integers(...)`` in the same way as
``tools/benchmark_vision.py``.

Metrics
-------
For each algorithm and seed the benchmark records total goodput, per-path
goodput and goodput share, Jain's fairness index over the two path goodputs,
convergence time, and two ACK diagnostics. Convergence is the last time the
2-second trailing mean total goodput was outside +/-10% of the mean total
goodput over the final 20% of the run; it is zero when the run started inside
that band. ``coupled_ack_fraction`` counts ACK events whose window change
differs from the uncoupled per-path Reno increase by more than 1%; it is the
measure that shows whether coupling is actually active. Summary rows carry
the mean and a two-sided 95% Student-t interval across replicates, and the
paired-difference CSV reports LIA-Reno, OLIA-LIA and OLIA-Reno differences
with their paired 95% intervals.

The printed verdict is descriptive: it names the algorithm with the highest
mean total goodput and the highest mean Jain index, and leaves paired
intervals to the reader. No significance claim beyond those intervals is
made, and the results do not establish behaviour of a production MPTCP
implementation.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Sequence

import numpy as np

from simulation.congestion import CoupledCongestionGroup

ALGORITHMS = ("reno", "lia", "olia")
SCENARIO_KEY = "heterogeneous_two_path"


@dataclass(frozen=True)
class PathSpec:
    """One stipulated bottleneck path in the benchmark."""

    name: str
    capacity_mbps: float
    rtt_ms: float
    mss_bytes: int


# The scenario required for the fair comparison: path A is faster and has a
# shorter RTT; path B is slower and has a much longer RTT.
PATH_SPECS: tuple[PathSpec, ...] = (
    PathSpec(name="A", capacity_mbps=20.0, rtt_ms=5.0, mss_bytes=1460),
    PathSpec(name="B", capacity_mbps=8.0, rtt_ms=25.0, mss_bytes=1460),
)
TOTAL_CAPACITY_MBPS = sum(spec.capacity_mbps for spec in PATH_SPECS)

STEP_SECONDS = 0.005
DEFAULT_DURATION_SECONDS = 60.0
DEFAULT_REPLICATES = 8
DEFAULT_SEED = 2026

QUEUE_LIMIT_BDP_MULTIPLE = 2.0
INITIAL_WINDOW_MIN_SEGMENTS = 8
INITIAL_WINDOW_MAX_SEGMENTS = 12
RTT_MEASUREMENT_NOISE_FRACTION = 0.02
COUPLED_INCREASE_TOLERANCE = 0.01
CONVERGENCE_WINDOW_SECONDS = 2.0
CONVERGENCE_TOLERANCE = 0.10
FINAL_WINDOW_FRACTION = 0.20

SUMMARY_FILENAME = "congestion_benchmark_summary.csv"
REPLICATES_FILENAME = "congestion_benchmark_replicates.csv"
PAIRED_FILENAME = "congestion_benchmark_paired_differences.csv"

_METRICS = (
    "total_goodput_mbps",
    "path_a_goodput_mbps",
    "path_b_goodput_mbps",
    "path_a_goodput_share_percent",
    "path_b_goodput_share_percent",
    "jain_index",
    "convergence_seconds",
    "ack_increase_fraction",
    "coupled_ack_fraction",
)

# Two-sided 95% Student-t critical values for small samples. Using t rather
# than 1.96 matters at the default eight replicates (t_7 = 2.365).
_T95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def _t_critical_95(degrees_of_freedom: int) -> float:
    if degrees_of_freedom in _T95:
        return _T95[degrees_of_freedom]
    if degrees_of_freedom > 30:
        # Normal approximation is adequate for larger samples.
        return 1.96
    raise ValueError("At least two observations are required for an interval.")


def _mean_ci(values: Sequence[float]) -> tuple[float, float]:
    """Return (mean, half-width) of a two-sided 95% Student-t interval."""
    array = np.asarray(values, dtype=float)
    count = int(array.size)
    mean = float(array.mean()) if count else 0.0
    if count < 2:
        return mean, 0.0
    standard_deviation = float(array.std(ddof=1))
    half_width = _t_critical_95(count - 1) * standard_deviation / math.sqrt(count)
    return mean, half_width


def _paired_ci(left: Sequence[float], right: Sequence[float]) -> tuple[float, float]:
    if len(left) != len(right):
        raise ValueError("Paired samples must have the same length.")
    differences = [float(a) - float(b) for a, b in zip(left, right)]
    return _mean_ci(differences)


def _jain_index(values: Sequence[float]) -> float:
    total = float(sum(values))
    sum_of_squares = float(sum(value * value for value in values))
    if sum_of_squares <= 0.0:
        return 0.0
    return total * total / (len(values) * sum_of_squares)


def _convergence_seconds(
    total_goodput_series: np.ndarray,
    step_seconds: float,
) -> float:
    """Time after which the trailing mean stayed within 10% of the final mean."""
    count = int(total_goodput_series.size)
    if count == 0:
        return 0.0
    final_count = max(1, int(round(count * FINAL_WINDOW_FRACTION)))
    final_mean = float(np.mean(total_goodput_series[-final_count:]))
    if final_mean <= 0.0:
        return float(count * step_seconds)
    window = max(1, int(round(CONVERGENCE_WINDOW_SECONDS / step_seconds)))
    window = min(window, count)
    smoothed = np.convolve(
        np.asarray(total_goodput_series, dtype=float),
        np.ones(window) / window,
        mode="valid",
    )
    low = (1.0 - CONVERGENCE_TOLERANCE) * final_mean
    high = (1.0 + CONVERGENCE_TOLERANCE) * final_mean
    outside = np.flatnonzero((smoothed < low) | (smoothed > high))
    if outside.size == 0:
        return 0.0
    return min(
        float(count * step_seconds),
        float((int(outside[-1]) + window) * step_seconds),
    )


@dataclass(frozen=True)
class SeedResult:
    """Per-seed metrics for one algorithm."""

    algorithm: str
    seed: int
    initial_window_a_segments: int
    initial_window_b_segments: int
    total_goodput_mbps: float
    path_a_goodput_mbps: float
    path_b_goodput_mbps: float
    path_a_goodput_share_percent: float
    path_b_goodput_share_percent: float
    jain_index: float
    convergence_seconds: float
    final_total_goodput_mbps: float
    ack_events: int
    ack_increase_fraction: float
    coupled_ack_fraction: float
    mean_window_a_segments: float
    mean_window_b_segments: float
    loss_events_a: int
    loss_events_b: int


def simulate(
    algorithm: str,
    seed: int,
    *,
    duration_seconds: float = DEFAULT_DURATION_SECONDS,
    step_seconds: float = STEP_SECONDS,
) -> SeedResult:
    """Run one seeded replicate of the two-path scenario for one algorithm."""
    if algorithm not in ALGORITHMS:
        raise ValueError(
            f"Unknown congestion-control algorithm {algorithm!r}; "
            f"expected one of {ALGORITHMS}."
        )
    if duration_seconds <= 0.0 or step_seconds <= 0.0:
        raise ValueError("Duration and time step must be positive.")
    if len(PATH_SPECS) != 2:
        raise ValueError("This benchmark is defined for exactly two paths.")

    step_count = int(round(duration_seconds / step_seconds))
    if step_count < 2:
        raise ValueError("The run must contain at least two simulation steps.")

    rng = np.random.default_rng(seed)
    initial_windows = {
        spec.name: int(
            rng.integers(
                INITIAL_WINDOW_MIN_SEGMENTS,
                INITIAL_WINDOW_MAX_SEGMENTS + 1,
            )
        )
        for spec in PATH_SPECS
    }
    controller = CoupledCongestionGroup(
        algorithm,
        [(spec.name, spec.mss_bytes, spec.rtt_ms) for spec in PATH_SPECS],
        initial_window_segments=initial_windows,
        capacity_mbps={spec.name: spec.capacity_mbps for spec in PATH_SPECS},
    )

    delay_steps = {
        spec.name: max(1, int(round(spec.rtt_ms / (step_seconds * 1000.0))))
        for spec in PATH_SPECS
    }
    ack_rings = {
        spec.name: [0.0] * (delay_steps[spec.name] + 1) for spec in PATH_SPECS
    }
    queue_bytes = {spec.name: 0.0 for spec in PATH_SPECS}
    last_loss_step = {spec.name: -10**9 for spec in PATH_SPECS}
    queue_limit_bytes = {
        spec.name: QUEUE_LIMIT_BDP_MULTIPLE
        * spec.capacity_mbps
        * 1e6
        / 8.0
        * (spec.rtt_ms / 1000.0)
        for spec in PATH_SPECS
    }
    capacity_bytes_per_step = {
        spec.name: spec.capacity_mbps * 1e6 / 8.0 * step_seconds
        for spec in PATH_SPECS
    }

    delivered_bytes = {spec.name: 0.0 for spec in PATH_SPECS}
    window_segment_sum = {spec.name: 0.0 for spec in PATH_SPECS}
    loss_events = {spec.name: 0 for spec in PATH_SPECS}
    total_goodput_series = np.empty(step_count, dtype=float)
    ack_events = 0
    increase_events = 0
    coupled_events = 0

    for step in range(step_count):
        step_total_mbps = 0.0
        for spec in PATH_SPECS:
            name = spec.name
            ring = ack_rings[name]
            ring_index = step % len(ring)
            acknowledged_bytes = ring[ring_index]
            ring[ring_index] = 0.0

            window = controller.windows_bytes()[name]
            if acknowledged_bytes > 0.0:
                before = window
                measured_rtt_ms = spec.rtt_ms * (
                    1.0
                    + RTT_MEASUREMENT_NOISE_FRACTION
                    * (2.0 * float(rng.random()) - 1.0)
                )
                controller.on_ack(name, acknowledged_bytes, measured_rtt_ms)
                window = controller.windows_bytes()[name]
                window_increase = window - before
                reno_increase = acknowledged_bytes * spec.mss_bytes / before
                ack_events += 1
                if window > before:
                    increase_events += 1
                if abs(window_increase - reno_increase) > (
                    COUPLED_INCREASE_TOLERANCE * max(reno_increase, 1e-12)
                ):
                    coupled_events += 1

            window_segment_sum[name] += window / spec.mss_bytes

            offered_bytes = (
                window * 8.0 / (spec.rtt_ms / 1000.0) * step_seconds / 8.0
            )
            queue = queue_bytes[name] + offered_bytes
            dropped_bytes = max(0.0, queue - queue_limit_bytes[name])
            queue -= dropped_bytes
            served_bytes = min(queue, capacity_bytes_per_step[name])
            queue -= served_bytes
            queue_bytes[name] = queue

            if (
                dropped_bytes > 0.0
                and step - last_loss_step[name] >= delay_steps[name]
            ):
                last_loss_step[name] = step
                loss_events[name] += 1
                controller.on_loss(name)

            ack_rings[name][(step + delay_steps[name]) % len(ring)] += served_bytes
            delivered_bytes[name] += served_bytes
            step_total_mbps += served_bytes * 8.0 / (step_seconds * 1e6)

        total_goodput_series[step] = step_total_mbps

    duration = step_count * step_seconds
    path_goodputs = {
        name: delivered_bytes[name] * 8.0 / (duration * 1e6)
        for name in delivered_bytes
    }
    total_goodput = sum(path_goodputs.values())
    shares = {
        name: (
            100.0 * path_goodputs[name] / total_goodput
            if total_goodput > 0.0
            else 0.0
        )
        for name in path_goodputs
    }
    final_count = max(1, int(round(step_count * FINAL_WINDOW_FRACTION)))
    final_total = float(np.mean(total_goodput_series[-final_count:]))

    return SeedResult(
        algorithm=algorithm,
        seed=seed,
        initial_window_a_segments=initial_windows["A"],
        initial_window_b_segments=initial_windows["B"],
        total_goodput_mbps=total_goodput,
        path_a_goodput_mbps=path_goodputs["A"],
        path_b_goodput_mbps=path_goodputs["B"],
        path_a_goodput_share_percent=shares["A"],
        path_b_goodput_share_percent=shares["B"],
        jain_index=_jain_index([path_goodputs["A"], path_goodputs["B"]]),
        convergence_seconds=_convergence_seconds(
            total_goodput_series,
            step_seconds,
        ),
        final_total_goodput_mbps=final_total,
        ack_events=ack_events,
        ack_increase_fraction=(
            increase_events / ack_events if ack_events else 0.0
        ),
        coupled_ack_fraction=(
            coupled_events / ack_events if ack_events else 0.0
        ),
        mean_window_a_segments=window_segment_sum["A"] / step_count,
        mean_window_b_segments=window_segment_sum["B"] / step_count,
        loss_events_a=loss_events["A"],
        loss_events_b=loss_events["B"],
    )


def _summary_rows(
    results: Sequence[SeedResult],
    replicates: int,
    duration_seconds: float,
    step_seconds: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for algorithm in ALGORITHMS:
        subset = [result for result in results if result.algorithm == algorithm]
        if not subset:
            raise ValueError(f"No results for algorithm {algorithm!r}.")
        row: dict[str, object] = {
            "scenario": SCENARIO_KEY,
            "algorithm": algorithm,
            "replicates": replicates,
            "duration_seconds": duration_seconds,
            "step_ms": round(step_seconds * 1000.0, 6),
            "path_a_capacity_mbps": PATH_SPECS[0].capacity_mbps,
            "path_a_rtt_ms": PATH_SPECS[0].rtt_ms,
            "path_b_capacity_mbps": PATH_SPECS[1].capacity_mbps,
            "path_b_rtt_ms": PATH_SPECS[1].rtt_ms,
        }
        for metric in _METRICS:
            samples = [float(getattr(result, metric)) for result in subset]
            mean, half_width = _mean_ci(samples)
            row[metric] = mean
            row[f"{metric}_ci95"] = half_width
        rows.append(row)
    return rows


def _paired_rows(
    results: Sequence[SeedResult],
    replicates: int,
) -> list[dict[str, object]]:
    by_key = {(result.algorithm, result.seed): result for result in results}
    seeds = sorted({result.seed for result in results})
    rows: list[dict[str, object]] = []
    for left, right in (("lia", "reno"), ("olia", "lia"), ("olia", "reno")):
        for metric in _METRICS:
            left_values = [float(getattr(by_key[(left, seed)], metric)) for seed in seeds]
            right_values = [float(getattr(by_key[(right, seed)], metric)) for seed in seeds]
            mean, half_width = _paired_ci(left_values, right_values)
            rows.append(
                {
                    "scenario": SCENARIO_KEY,
                    "comparison": f"{left}_minus_{right}",
                    "metric": metric,
                    "replicates": replicates,
                    "mean_difference": mean,
                    "ci95_low": mean - half_width,
                    "ci95_high": mean + half_width,
                }
            )
    return rows


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"No rows to write to {path}.")
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _print_table(rows: Sequence[dict[str, object]]) -> None:
    header = (
        "Algorithm        Total Mbit/s          A share %   B share %   "
        "Jain     Conv. s   ACK inc. %   Coupled %"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{str(row['algorithm']):16s} "
            f"{float(row['total_goodput_mbps']):6.2f} +/- "
            f"{float(row['total_goodput_mbps_ci95']):5.2f}      "
            f"{float(row['path_a_goodput_share_percent']):7.1f}     "
            f"{float(row['path_b_goodput_share_percent']):7.1f}     "
            f"{float(row['jain_index']):6.3f}   "
            f"{float(row['convergence_seconds']):7.2f}   "
            f"{100.0 * float(row['ack_increase_fraction']):8.1f}     "
            f"{100.0 * float(row['coupled_ack_fraction']):7.1f}"
        )


def _print_paired(rows: Sequence[dict[str, object]]) -> None:
    print()
    print("Paired differences (mean [95% t interval], n = replicates)")
    print("-" * 78)
    for row in rows:
        if row["metric"] not in (
            "total_goodput_mbps",
            "jain_index",
            "convergence_seconds",
            "coupled_ack_fraction",
        ):
            continue
        print(
            f"{str(row['comparison']):14s} {str(row['metric']):24s} "
            f"{float(row['mean_difference']):+8.4f} "
            f"[{float(row['ci95_low']):+8.4f}, {float(row['ci95_high']):+8.4f}]"
        )


def _print_verdict(rows: Sequence[dict[str, object]]) -> None:
    best_goodput = max(rows, key=lambda row: float(row["total_goodput_mbps"]))
    best_fairness = max(rows, key=lambda row: float(row["jain_index"]))
    print()
    print(
        f"Highest mean total goodput: {best_goodput['algorithm']} "
        f"({float(best_goodput['total_goodput_mbps']):.2f} Mbit/s of "
        f"{TOTAL_CAPACITY_MBPS:.0f} Mbit/s combined capacity)."
    )
    print(
        f"Highest mean Jain index: {best_fairness['algorithm']} "
        f"({float(best_fairness['jain_index']):.4f})."
    )
    print(
        "The paired CSV reports per-seed LIA-Reno, OLIA-LIA and OLIA-Reno "
        "differences with 95% t intervals. This is a stipulated simulation "
        "result, not a measurement of a production MPTCP stack."
    )


def run_benchmark(
    output_dir: Path,
    replicates: int = DEFAULT_REPLICATES,
    seed: int = DEFAULT_SEED,
    *,
    duration_seconds: float = DEFAULT_DURATION_SECONDS,
    step_seconds: float = STEP_SECONDS,
) -> list[dict[str, object]]:
    """Run all algorithms, write the CSVs, print the tables, return summary rows."""
    if replicates < 2:
        raise ValueError("At least two independent replicates are required.")
    if duration_seconds <= 0.0 or step_seconds <= 0.0:
        raise ValueError("Duration and time step must be positive.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    seed_generator = np.random.default_rng(seed)
    run_seeds = [
        int(value)
        for value in seed_generator.integers(0, 2**31 - 1, size=replicates)
    ]

    results: list[SeedResult] = []
    for algorithm in ALGORITHMS:
        for run_seed in run_seeds:
            results.append(
                simulate(
                    algorithm,
                    run_seed,
                    duration_seconds=duration_seconds,
                    step_seconds=step_seconds,
                )
            )

    summary_rows = _summary_rows(
        results,
        replicates,
        duration_seconds,
        step_seconds,
    )
    paired_rows = _paired_rows(results, replicates)

    summary_path = output_dir / SUMMARY_FILENAME
    replicates_path = output_dir / REPLICATES_FILENAME
    paired_path = output_dir / PAIRED_FILENAME
    _write_csv(summary_path, summary_rows)
    _write_csv(
        replicates_path,
        [
            {field.name: getattr(result, field.name) for field in fields(SeedResult)}
            for result in results
        ],
    )
    _write_csv(paired_path, paired_rows)

    print(f"Scenario: {SCENARIO_KEY}")
    for spec in PATH_SPECS:
        print(
            f"  path {spec.name}: {spec.capacity_mbps:.1f} Mbit/s, "
            f"{spec.rtt_ms:.1f} ms RTT, MSS {spec.mss_bytes} bytes"
        )
    print(
        f"Time step: {step_seconds * 1000.0:.1f} ms; "
        f"duration: {duration_seconds:.1f} s; replicates: {replicates}"
    )
    print(f"Base seed: {seed}")
    print(f"Summary CSV: {summary_path}")
    print(f"Per-seed CSV: {replicates_path}")
    print(f"Paired-difference CSV: {paired_path}")
    print()
    _print_table(summary_rows)
    _print_paired(paired_rows)
    _print_verdict(summary_rows)
    return summary_rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare Reno, LIA and OLIA congestion control on the stipulated "
            "heterogeneous two-path scenario."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory for the summary, per-seed and paired CSVs (default: output).",
    )
    parser.add_argument(
        "--replicates",
        type=int,
        default=DEFAULT_REPLICATES,
        help=f"Independent seeds per algorithm (default: {DEFAULT_REPLICATES}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Base seed used to generate run seeds (default: {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=DEFAULT_DURATION_SECONDS,
        help=f"Simulated seconds per run (default: {DEFAULT_DURATION_SECONDS}).",
    )
    parser.add_argument(
        "--step-ms",
        type=float,
        default=STEP_SECONDS * 1000.0,
        help=f"Simulation time step in milliseconds (default: {STEP_SECONDS * 1000.0}).",
    )
    arguments = parser.parse_args(argv)
    run_benchmark(
        arguments.output_dir,
        replicates=arguments.replicates,
        seed=arguments.seed,
        duration_seconds=arguments.duration_seconds,
        step_seconds=arguments.step_ms / 1000.0,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
