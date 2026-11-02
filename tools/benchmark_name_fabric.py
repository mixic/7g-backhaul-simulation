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

"""Run the five pre-registered name-fabric experiments.

Thresholds are fixed here, before the run, and mirrored in
``docs/name-fabric.md``:

1. Transition floor: gradient p95 below 10 ms, and at least 5x lower than the
   DNS p95 at every TTL of 30 s or more.
2. Poisoning: immutable names accepted 0 times; service acceptance must fall
   monotonically with attestation strength.
3. Flooding: report both sustainable rates and which fails first; no threshold
   is asserted, because the expected result is that one regime is worse.
4. Latency: report the tail (p99), not only the mean.
5. Gateway: report utilisation and the external p95, so the seam is visible.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from simulation.name_fabric import (
    FabricConfig,
    experiment_flooding,
    experiment_gateway,
    experiment_latency,
    experiment_poisoning,
    experiment_transition,
    sustainable_rate,
)

#: Pre-registered thresholds (see module docstring).
TRANSITION_P95_LIMIT_MS = 10.0
TRANSITION_RATIO_LIMIT = 5.0


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _transition_rows(config: FabricConfig, output_dir: Path) -> list[dict[str, object]]:
    samples = experiment_transition(config)
    grouped: dict[tuple[str, float], list[float]] = {}
    failures: dict[tuple[str, float], int] = {}
    for sample in samples:
        key = (sample.strategy, sample.ttl_s)
        grouped.setdefault(key, []).append(sample.time_to_first_success_ms)
        failures[key] = failures.get(key, 0) + sample.failed_requests

    def percentile(values: list[float], p: float) -> float:
        ordered = sorted(values)
        rank = p / 100.0 * (len(ordered) - 1)
        lower = int(rank)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)

    rows: list[dict[str, object]] = []
    for (strategy, ttl), values in sorted(grouped.items()):
        rows.append(
            {
                "strategy": strategy,
                "dns_ttl_s": ttl,
                "mean_ms": sum(values) / len(values),
                "p95_ms": percentile(values, 95.0),
                "max_ms": max(values),
                "failed_requests_mean": failures[(strategy, ttl)] / len(values),
            }
        )
    _write_csv(output_dir / "name_fabric_transition.csv", rows)
    return rows


def _poisoning_rows(output_dir: Path) -> list[dict[str, object]]:
    rows = [asdict(result) for result in experiment_poisoning()]
    _write_csv(output_dir / "name_fabric_poisoning.csv", rows)
    return rows


def _flooding_rows(config: FabricConfig, output_dir: Path) -> list[dict[str, object]]:
    single = experiment_flooding(config, attack_nodes=1)
    rows = [asdict(row) for row in single]
    _write_csv(output_dir / "name_fabric_flooding.csv", rows)
    return rows


def _latency_rows(config: FabricConfig, output_dir: Path) -> list[dict[str, object]]:
    rows = [asdict(row) for row in experiment_latency(config)]
    _write_csv(output_dir / "name_fabric_latency.csv", rows)
    return rows


def _gateway_rows(config: FabricConfig, output_dir: Path) -> list[dict[str, object]]:
    rows = [asdict(row) for row in experiment_gateway(config)]
    _write_csv(output_dir / "name_fabric_gateway.csv", rows)
    return rows


def run_all(output_dir: Path) -> dict[str, list[dict[str, object]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    config = FabricConfig()
    results = {
        "transition": _transition_rows(config, output_dir),
        "poisoning": _poisoning_rows(output_dir),
        "flooding": _flooding_rows(config, output_dir),
        "latency": _latency_rows(config, output_dir),
        "gateway": _gateway_rows(config, output_dir),
    }
    print("Transition floor (service moves E2 -> E3 at t=0):")
    for row in results["transition"]:
        print(
            f"  {row['strategy']:9s} ttl={float(row['dns_ttl_s']):5.0f}s | "
            f"p95={float(row['p95_ms']):9.2f} ms | mean={float(row['mean_ms']):9.2f} ms | "
            f"stale attempts={float(row['failed_requests_mean']):6.1f}"
        )
    print("\nPoisoning acceptance by name class:")
    for row in results["poisoning"]:
        print(
            f"  {str(row['name_class']):10s} | {str(row['variant']):30s} | "
            f"{float(row['acceptance_percent']):6.3f} % +/- {float(row['ci95_percent']):.3f}"
        )
    print("\nFlooding: resolver versus pending-request table (per node):")
    for row in results["flooding"]:
        queue = float(row["dns_queue_ms"])
        queue_text = "inf" if queue == float("inf") else f"{queue:.0f} ms"
        print(
            f"  {float(row['offered_rps']):8.0f} rps | dns fail {float(row['dns_failure_percent']):5.1f} % "
            f"(queue {queue_text:>8s}) | pit fail {float(row['pit_failure_percent']):5.1f} % "
            f"(occupancy {float(row['pit_occupancy']):7.0f})"
        )
    dns_rate = sustainable_rate([_row(r) for r in results["flooding"]], "dns_failure_percent")
    pit_rate = sustainable_rate([_row(r) for r in results["flooding"]], "pit_failure_percent")
    print(f"  Sustainable (<1 % failure): dns={dns_rate:.0f} rps, pit={pit_rate:.0f} rps")
    print("\nLatency distributions at nominal load:")
    for row in results["latency"]:
        print(
            f"  {str(row['strategy']):15s} | p50={float(row['p50_ms']):7.2f} | "
            f"p95={float(row['p95_ms']):7.2f} | p99={float(row['p99_ms']):7.2f} | "
            f"max={float(row['max_ms']):7.2f} ms"
        )
    print("\nGateway seam (external requests must leave the fabric):")
    for row in results["gateway"]:
        print(
            f"  external={100.0 * float(row['external_fraction']):5.1f} % | "
            f"gateway util={100.0 * float(row['gateway_utilization']):5.1f} % | "
            f"internal p95={float(row['internal_p95_ms']):7.2f} ms | "
            f"external p95={float(row['external_p95_ms']):7.2f} ms"
        )
    _verdicts(results)
    print(f"\nCSVs: {output_dir}/name_fabric_*.csv")
    return results


def _row(row: dict[str, object]):
    from simulation.name_fabric import FloodingResult

    return FloodingResult(
        offered_rps=float(row["offered_rps"]),
        dns_failure_percent=float(row["dns_failure_percent"]),
        pit_failure_percent=float(row["pit_failure_percent"]),
        dns_queue_ms=float(row["dns_queue_ms"]),
        pit_occupancy=float(row["pit_occupancy"]),
    )


def _verdicts(results: dict[str, list[dict[str, object]]]) -> None:
    print("\nPre-registered checks:")
    gradient = {
        float(row["dns_ttl_s"]): float(row["p95_ms"])
        for row in results["transition"]
        if row["strategy"] == "gradient"
    }
    dns = {
        float(row["dns_ttl_s"]): float(row["p95_ms"])
        for row in results["transition"]
        if row["strategy"] == "dns"
    }
    for ttl, gradient_p95 in sorted(gradient.items()):
        dns_p95 = dns[ttl]
        ratio = dns_p95 / gradient_p95 if gradient_p95 else math.inf
        passed = gradient_p95 < TRANSITION_P95_LIMIT_MS and ratio >= TRANSITION_RATIO_LIMIT
        print(
            f"  transition floor @ ttl={ttl:.0f}s: gradient p95={gradient_p95:.2f} ms, "
            f"dns p95={dns_p95:.2f} ms, ratio={ratio:.1f}x -> "
            f"{'PASS' if passed else 'FAIL'}"
        )
    immutable = [
        row for row in results["poisoning"] if row["name_class"] == "immutable"
    ]
    zero = all(float(row["acceptance_percent"]) == 0.0 for row in immutable)
    print(f"  immutable poisoning is structurally zero: {'PASS' if zero else 'FAIL'}")
    strengths = sorted(
        (
            int(str(row["variant"]).split()[-1]),
            float(row["acceptance_percent"]),
        )
        for row in results["poisoning"]
        if row["name_class"] == "service"
    )
    monotone = all(
        strengths[index][1] >= strengths[index + 1][1]
        for index in range(len(strengths) - 1)
    )
    print(f"  service acceptance falls with attestation strength: {'PASS' if monotone else 'FAIL'}")


import math  # noqa: E402  (used by the verdict helper)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args()
    run_all(args.output_dir)


if __name__ == "__main__":
    main()
