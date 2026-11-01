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

import argparse

from .engine import (
    build_tomahawk_cdn_scenario,
    build_reference_scenario,
    simulate_reference_scenario,
    simulate_tomahawk_cdn_scenario,
)


def _print_summary(scenario_name: str) -> None:
    outcome = (
        simulate_tomahawk_cdn_scenario() if scenario_name == "tomahawk-cdn" else simulate_reference_scenario()
    )
    print(f"Scenario: {outcome['scenario_name']}")
    print(f"Average latency: {outcome['average_latency_ms']} ms")
    print(f"Average reliability: {outcome['average_reliability']}")
    print(f"Average throughput: {outcome['average_throughput_gbps']} Gbps")
    print()

    print("Flow routing summary:")
    for flow in outcome['flows']:
        best_result = None
        for result in outcome['route_results']:
            if result.flow_name == flow.name:
                if best_result is None or result.latency_ms < best_result.latency_ms:
                    best_result = result
        if best_result is None:
            continue
        print(
            f"- {flow.name}: {flow.source} -> {flow.destination} | "
            f"route={' -> '.join(best_result.route)} | "
            f"latency={best_result.latency_ms} ms | "
            f"throughput={best_result.estimated_throughput_gbps} Gbps | "
            f"reliability={best_result.reliability}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="7G backhaul network simulation")
    parser.add_argument(
        "--scenario",
        choices=["reference", "tomahawk-cdn"],
        default="reference",
        help="Predefined scenario to simulate",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _print_summary(args.scenario)


if __name__ == "__main__":
    main()
