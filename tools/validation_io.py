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

"""Normalize and compare simulator, emulator, or testbed run-level metrics."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

NORMALIZED_FIELDS = (
    "source",
    "scenario",
    "policy",
    "seed",
    "metric",
    "value",
    "unit",
)
METRIC_UNITS = {
    "demand_delivery_percent": "percent",
    "critical_service_availability_percent": "percent",
    "video_frames_on_time_percent": "percent",
    "audio_packets_on_time_percent": "percent",
    "p95_video_frame_delay_ms": "ms",
    "p95_audio_interarrival_variation_ms": "ms",
    "video_stall_seconds": "s",
    "longest_video_freeze_seconds": "s",
    "media_copy_loss_percent": "percent",
    "path_recovery_seconds": "s",
    "path_recovery_censored": "boolean",
    "cloud_recovery_seconds": "s",
    "cloud_recovery_censored": "boolean",
    "mean_active_paths": "paths",
    "duplicate_packet_percent": "percent",
    "duplicate_payload_percent": "percent",
    "secondary_region_capacity_mbps_seconds": "Mbps*s",
    "media_queue_drop_percent": "percent",
    # Generic packet-level metrics used by the external cross-validation
    # scenarios in validation/scenario_s1.py.
    "packet_delivery_percent": "percent",
    "one_way_delay_p95_ms": "ms",
    "goodput_mbps": "Mbps",
    "active_paths_mean": "paths",
    "primary_share_percent": "percent",
    # RFMP role-transition metrics (validation/rfmp, docs/rfmp-validation.md).
    "in_order_delivery_percent": "percent",
    "duplicate_percent": "percent",
    "handoff_duplicate_percent": "percent",
    "transition_gap_6s_ms": "ms",
    "transition_gap_12s_ms": "ms",
    "reorder_stall_p95_ms": "ms",
    "reorder_stall_max_ms": "ms",
    "mean_delivery_delay_ms": "ms",
    "late_drop_percent": "percent",
}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file has no header: {path}")
        return list(reader.fieldnames), list(reader)


def _write_normalized(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError("No validation observations were produced.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=NORMALIZED_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def export_simulation_replicates(
    input_path: Path,
    output_path: Path,
    source: str = "python_simpy",
    metrics: tuple[str, ...] | None = None,
) -> int:
    fieldnames, records = _read_csv(input_path)
    required = {"scenario", "policy", "seed"}
    missing = required - set(fieldnames)
    if missing:
        raise ValueError(
            "Simulation replicate CSV is missing columns: "
            + ", ".join(sorted(missing))
        )
    selected = tuple(metrics) if metrics is not None else tuple(METRIC_UNITS)
    unknown = [metric for metric in selected if metric not in METRIC_UNITS]
    if unknown:
        raise ValueError("Unknown metrics: " + ", ".join(sorted(unknown)))
    present = tuple(metric for metric in selected if metric in fieldnames)
    if not present:
        raise ValueError(
            "Simulation replicate CSV contains none of the requested metrics."
        )
    normalized: list[dict[str, object]] = []
    for row_number, record in enumerate(records, start=2):
        for metric in present:
            value = float(record[metric])
            if not math.isfinite(value):
                raise ValueError(
                    f"Non-finite {metric} in simulation row {row_number}."
                )
            normalized.append(
                {
                    "source": source,
                    "scenario": record["scenario"],
                    "policy": record["policy"],
                    "seed": record["seed"],
                    "metric": metric,
                    "value": value,
                    "unit": METRIC_UNITS[metric],
                }
            )
    _write_normalized(output_path, normalized)
    return len(normalized)


def normalize_external_results(
    input_path: Path,
    output_path: Path,
    mapping_path: Path,
    source: str,
) -> int:
    fieldnames, records = _read_csv(input_path)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    identity_columns = {
        key: mapping.get(key)
        for key in ("scenario", "policy", "seed")
    }
    if any(not isinstance(value, str) or not value for value in identity_columns.values()):
        raise ValueError(
            "Mapping JSON must map scenario, policy, and seed to CSV columns."
        )
    metrics = mapping.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError(
            "Mapping JSON must include metrics with column and unit for each metric."
        )
    used_columns = set(identity_columns.values())
    for metric, spec in metrics.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("column"), str):
            raise ValueError(
                f"Metric mapping {metric!r} must include a source column."
            )
        if not isinstance(spec.get("unit"), str) or not spec["unit"]:
            raise ValueError(f"Metric mapping {metric!r} must include a unit.")
        used_columns.add(spec["column"])
    missing = used_columns - set(fieldnames)
    if missing:
        raise ValueError(
            "External CSV is missing mapped columns: "
            + ", ".join(sorted(missing))
        )

    policy_map = mapping.get("policy_values", {})
    if not isinstance(policy_map, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in policy_map.items()
    ):
        raise ValueError("policy_values must map external labels to string labels.")
    normalized: list[dict[str, object]] = []
    for row_number, record in enumerate(records, start=2):
        scenario = record[identity_columns["scenario"]]
        policy = policy_map.get(
            record[identity_columns["policy"]],
            record[identity_columns["policy"]],
        )
        seed = record[identity_columns["seed"]]
        if not scenario or not policy or not seed:
            raise ValueError(f"Missing scenario, policy, or seed on row {row_number}.")
        for metric, spec in metrics.items():
            try:
                value = float(record[spec["column"]])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid {metric} value on external row {row_number}."
                ) from error
            if not math.isfinite(value):
                raise ValueError(
                    f"Non-finite {metric} value on external row {row_number}."
                )
            normalized.append(
                {
                    "source": source,
                    "scenario": scenario,
                    "policy": policy,
                    "seed": seed,
                    "metric": metric,
                    "value": value,
                    "unit": spec["unit"],
                }
            )
    _write_normalized(output_path, normalized)
    return len(normalized)


def compare_normalized_results(
    left_path: Path,
    right_path: Path,
    output_path: Path,
    left_policy: str | None = None,
    right_policy: str | None = None,
) -> list[dict[str, object]]:
    if (left_policy is None) != (right_policy is None):
        raise ValueError("Specify both --left-policy and --right-policy, or neither.")
    _, left_rows = _read_csv(left_path)
    _, right_rows = _read_csv(right_path)
    for path, rows in ((left_path, left_rows), (right_path, right_rows)):
        if not rows:
            raise ValueError(f"Normalized result file is empty: {path}")
        missing = set(NORMALIZED_FIELDS) - set(rows[0])
        if missing:
            raise ValueError(
                f"Normalized result file {path} is missing: "
                + ", ".join(sorted(missing))
            )

    def keyed(
        rows: list[dict[str, str]],
        path: Path,
        policy_filter: str | None,
    ) -> dict[tuple[str, ...], dict[str, str]]:
        result = {}
        for row_number, row in enumerate(rows, start=2):
            if policy_filter is not None and row["policy"] != policy_filter:
                continue
            key = (
                (row["scenario"], row["seed"], row["metric"])
                if left_policy is not None
                else (
                    row["scenario"],
                    row["policy"],
                    row["seed"],
                    row["metric"],
                )
            )
            if key in result:
                raise ValueError(
                    f"Duplicate observation key in {path}, row {row_number}: {key}"
                )
            result[key] = row
        return result

    left = keyed(left_rows, left_path, left_policy)
    right = keyed(right_rows, right_path, right_policy)
    matched_keys = sorted(set(left) & set(right))
    if not matched_keys:
        raise ValueError(
            "No paired observations found. Scenario, seed, and metric must "
            "match. Without policy filters, policy labels must also match."
        )
    grouped: dict[
        tuple[str, str, str, str, str, str, str],
        list[tuple[float, float]],
    ] = {}
    unmatched: dict[tuple[str, str, str, str, str], list[int]] = {}
    for key in set(left) - set(right):
        row = left[key]
        group = (
            row["source"],
            row["scenario"],
            row["policy"],
            row["metric"],
            row["unit"],
        )
        unmatched.setdefault(group, [0, 0])[0] += 1
    for key in set(right) - set(left):
        row = right[key]
        group = (
            row["source"],
            row["scenario"],
            row["policy"],
            row["metric"],
            row["unit"],
        )
        unmatched.setdefault(group, [0, 0])[1] += 1
    for key in matched_keys:
        left_row = left[key]
        right_row = right[key]
        if left_row["unit"] != right_row["unit"]:
            raise ValueError(
                f"Unit mismatch for {key}: {left_row['unit']} vs {right_row['unit']}."
            )
        group = (
            left_row["source"],
            right_row["source"],
            left_row["scenario"],
            left_row["policy"],
            right_row["policy"],
            left_row["metric"],
            left_row["unit"],
        )
        grouped.setdefault(group, []).append(
            (float(left_row["value"]), float(right_row["value"]))
        )

    summary: list[dict[str, object]] = []
    for (
        left_source,
        right_source,
        scenario,
        compared_left_policy,
        compared_right_policy,
        metric,
        unit,
    ), pairs in sorted(grouped.items()):
        if len(pairs) < 2:
            raise ValueError(
                "At least two matched seed pairs are required for an "
                f"uncertainty interval ({scenario}, {metric})."
            )
        left_values = np.asarray([pair[0] for pair in pairs], dtype=float)
        right_values = np.asarray([pair[1] for pair in pairs], dtype=float)
        differences = left_values - right_values
        delta_ci95 = (
            1.96 * float(np.std(differences, ddof=1)) / np.sqrt(len(differences))
            if len(differences) > 1
            else 0.0
        )
        summary.append(
            {
                "left_source": left_source,
                "right_source": right_source,
                "scenario": scenario,
                "left_policy": compared_left_policy,
                "right_policy": compared_right_policy,
                "metric": metric,
                "unit": unit,
                "paired_seeds": len(pairs),
                "left_unmatched": unmatched.get(
                    (
                        left_source,
                        scenario,
                        compared_left_policy,
                        metric,
                        unit,
                    ),
                    [0, 0],
                )[0],
                "right_unmatched": unmatched.get(
                    (
                        right_source,
                        scenario,
                        compared_right_policy,
                        metric,
                        unit,
                    ),
                    [0, 0],
                )[1],
                "left_mean": float(np.mean(left_values)),
                "right_mean": float(np.mean(right_values)),
                "left_minus_right_mean": float(np.mean(differences)),
                "paired_ci95": float(delta_ci95),
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export-simulation")
    export.add_argument("--input", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--source", default="python_simpy")
    normalize = commands.add_parser("normalize-external")
    normalize.add_argument("--input", type=Path, required=True)
    normalize.add_argument("--mapping", type=Path, required=True)
    normalize.add_argument("--output", type=Path, required=True)
    normalize.add_argument("--source", required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--left", type=Path, required=True)
    compare.add_argument("--right", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    compare.add_argument("--left-policy")
    compare.add_argument("--right-policy")
    args = parser.parse_args()
    if args.command == "export-simulation":
        count = export_simulation_replicates(args.input, args.output, args.source)
    elif args.command == "normalize-external":
        count = normalize_external_results(
            args.input,
            args.output,
            args.mapping,
            args.source,
        )
    else:
        count = len(
            compare_normalized_results(
                args.left,
                args.right,
                args.output,
                args.left_policy,
                args.right_policy,
            )
        )
    print(f"Validation records: {count}")
    print(f"CSV: {args.output}")


if __name__ == "__main__":
    main()
