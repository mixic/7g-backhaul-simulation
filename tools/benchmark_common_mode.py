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

"""Run the common-mode resilience experiment (H16-H20) over paired seeds.

The protocol is frozen in ``docs/common-mode-predictions.md``.  The benchmark
runs every arm on the same scenario, seed, demand vector, event and fallback
draw, then writes:

* ``common_mode_per_seed.csv`` — one row per seed, event and arm;
* ``common_mode_summary.csv`` — mean and 95 % CI per event and arm;
* ``common_mode_verdicts.csv`` — every H16-H20 criterion with its 30-seed mean,
  threshold, per-seed pass fraction and verdict.

The scenario is the stipulated cooperative AI backhaul in
``simulation/common_mode.py``.  It is a flow-level testbed, not a measurement of
a production network.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Iterable, Sequence

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulation import common_mode as cm  # noqa: E402


def mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def ci95(values: Iterable[float]) -> float:
    items = list(values)
    if len(items) < 2:
        return 0.0
    centre = mean(items)
    variance = sum((value - centre) ** 2 for value in items) / (len(items) - 1)
    return 1.96 * math.sqrt(variance / len(items))


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write an empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(
    seeds: Sequence[int],
    events: Sequence[str],
    arms: Sequence[str],
    scenario: cm.Scenario,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for event in events:
        for seed in seeds:
            for arm_name in arms:
                result = cm.simulate(arm=cm.ARMS[arm_name], scenario=scenario, seed=seed, event_kind=event)
                rows.append(
                    {
                        "seed": seed,
                        "event": event,
                        "arm": arm_name,
                        "availability_event_pct": round(
                            result.availability_event * 100.0, 4
                        ),
                        "availability_overall_pct": round(
                            result.availability_overall * 100.0, 4
                        ),
                        "recovery_s": round(result.recovery_s, 4),
                        "blast_radius_pct": round(result.blast_radius * 100.0, 4),
                        "path_independence": round(result.path_independence, 4),
                        "fallback_rate_pct": round(result.fallback_rate * 100.0, 4),
                        "cost_index": round(result.cost_index, 4),
                    }
                )
    return rows


def summary_rows(
    rows: Sequence[dict[str, object]],
    events: Sequence[str],
    arms: Sequence[str],
) -> list[dict[str, object]]:
    summary: list[dict[str, object]] = []
    for event in events:
        for arm_name in arms:
            selected = [
                row
                for row in rows
                if row["event"] == event and row["arm"] == arm_name
            ]
            availability = [float(row["availability_event_pct"]) for row in selected]
            overall = [float(row["availability_overall_pct"]) for row in selected]
            recovery = [float(row["recovery_s"]) for row in selected]
            blast = [float(row["blast_radius_pct"]) for row in selected]
            independence = [float(row["path_independence"]) for row in selected]
            fallback = [float(row["fallback_rate_pct"]) for row in selected]
            summary.append(
                {
                    "event": event,
                    "arm": arm_name,
                    "label": cm.ARMS[arm_name].label,
                    "availability_event_mean_pct": round(mean(availability), 4),
                    "availability_event_ci95_pct": round(ci95(availability), 4),
                    "availability_overall_mean_pct": round(mean(overall), 4),
                    "recovery_mean_s": round(mean(recovery), 4),
                    "blast_radius_mean_pct": round(mean(blast), 4),
                    "path_independence_mean": round(mean(independence), 4),
                    "fallback_rate_mean_pct": round(mean(fallback), 4),
                    "cost_index": round(float(selected[0]["cost_index"]), 4)
                    if selected
                    else 0.0,
                }
            )
    return summary


def _availability_index(
    rows: Sequence[dict[str, object]],
) -> dict[tuple[int, str, str], float]:
    return {
        (int(row["seed"]), str(row["event"]), str(row["arm"])): float(
            row["availability_event_pct"]
        )
        for row in rows
    }


def _criterion(
    index: dict[tuple[int, str, str], float],
    seeds: Sequence[int],
    hypothesis: str,
    criterion: str,
    event: str,
    arm: str,
    threshold: float,
    comparator: str,
    reference_arm: str | None = None,
    detail: str = "",
) -> dict[str, object]:
    values = []
    for seed in seeds:
        left = index[(seed, event, arm)]
        right = index[(seed, event, reference_arm)] if reference_arm else 0.0
        values.append(left - right)
    centre = mean(values)
    if comparator == "ge":
        passes = [value >= threshold for value in values]
        ok = centre >= threshold
        threshold_text = f">= {threshold:g}"
    elif comparator == "le":
        passes = [value <= threshold for value in values]
        ok = centre <= threshold
        threshold_text = f"<= {threshold:g}"
    elif comparator == "abs_le":
        passes = [abs(value) <= threshold for value in values]
        ok = abs(centre) <= threshold
        threshold_text = f"|value| <= {threshold:g}"
    else:
        raise ValueError(f"unknown comparator: {comparator}")
    return {
        "hypothesis": hypothesis,
        "criterion": criterion,
        "event": event,
        "arm": arm,
        "reference_arm": reference_arm or "",
        "value": round(centre, 4),
        "threshold": threshold_text,
        "pass_fraction": round(sum(passes) / len(passes), 4),
        "verdict": "PASS" if ok else "FAIL",
        "detail": detail,
    }


def verdict_rows(
    rows: Sequence[dict[str, object]], seeds: Sequence[int]
) -> list[dict[str, object]]:
    index = _availability_index(rows)
    verdicts: list[dict[str, object]] = []

    h16a = _criterion(
        index,
        seeds,
        "H16",
        "tenant isolation contains a tenant-shared fault",
        "tenant_gw",
        "A4",
        50.0,
        "ge",
        "A3",
        "A4 - A3, A4 = A3 + tenant isolation",
    )
    h16b = _criterion(
        index,
        seeds,
        "H16",
        "tenant isolation does not contain a shared control-plane fault",
        "idp",
        "A4",
        5.0,
        "abs_le",
        "A3",
        "|A4 - A3| under global identity failure",
    )
    verdicts.extend([h16a, h16b])
    verdicts.append(
        {
            "hypothesis": "H16",
            "criterion": "overall",
            "event": "tenant_gw, idp",
            "arm": "A4 vs A3",
            "reference_arm": "",
            "value": "",
            "threshold": "both criteria",
            "pass_fraction": round(
                min(float(h16a["pass_fraction"]), float(h16b["pass_fraction"])), 4
            ),
            "verdict": "PASS"
            if h16a["verdict"] == "PASS" and h16b["verdict"] == "PASS"
            else "FAIL",
            "detail": "isolation is a boundary, not a control-plane cut",
        }
    )

    h17a = _criterion(
        index,
        seeds,
        "H17",
        "SRLG-disjoint multipath under a conduit failure",
        "srlg",
        "A3",
        20.0,
        "ge",
        "A2",
        "A3 - A2, disjoint minus shared-fate",
    )
    h17b = _criterion(
        index,
        seeds,
        "H17",
        "multipath under an independent link failure",
        "link",
        "A2",
        50.0,
        "ge",
        "A1",
        "A2 - A1, multipath minus single path",
    )
    verdicts.extend([h17a, h17b])
    verdicts.append(
        {
            "hypothesis": "H17",
            "criterion": "overall",
            "event": "srlg, link",
            "arm": "A2, A3 vs A1",
            "reference_arm": "",
            "value": "",
            "threshold": "both criteria",
            "pass_fraction": round(
                min(float(h17a["pass_fraction"]), float(h17b["pass_fraction"])), 4
            ),
            "verdict": "PASS"
            if h17a["verdict"] == "PASS" and h17b["verdict"] == "PASS"
            else "FAIL",
            "detail": "independence, not path count",
        }
    )

    h18a = _criterion(
        index,
        seeds,
        "H18",
        "one-way boundary survives an AI control-plane failure",
        "ai",
        "A6",
        50.0,
        "ge",
        "A5",
        "A6 - A5 under AI failure",
    )
    h18b = _criterion(
        index,
        seeds,
        "H18",
        "fallback restores at least 80 % under an AI failure",
        "ai",
        "A6",
        80.0,
        "ge",
        None,
        "A6 level under AI failure",
    )
    h18c = _criterion(
        index,
        seeds,
        "H18",
        "normal-operation cost of isolation is at most 15 points",
        "none",
        "A5",
        15.0,
        "le",
        "A6",
        "A5 - A6 with no failure",
    )
    verdicts.extend([h18a, h18b, h18c])
    verdicts.append(
        {
            "hypothesis": "H18",
            "criterion": "overall",
            "event": "ai, none",
            "arm": "A5, A6",
            "reference_arm": "",
            "value": "",
            "threshold": "all three criteria",
            "pass_fraction": round(
                min(
                    float(h18a["pass_fraction"]),
                    float(h18b["pass_fraction"]),
                    float(h18c["pass_fraction"]),
                ),
                4,
            ),
            "verdict": "PASS"
            if all(row["verdict"] == "PASS" for row in (h18a, h18b, h18c))
            else "FAIL",
            "detail": "a boundary without capacity is a partition",
        }
    )

    interaction_values = []
    for seed in seeds:
        interaction_values.append(
            (index[(seed, "ai_link", "A6")] - index[(seed, "ai_link", "A3")])
            - (index[(seed, "ai_link", "A9")] - index[(seed, "ai_link", "A1")])
        )
    interaction = mean(interaction_values)
    interaction_passes = [value >= 20.0 for value in interaction_values]
    h19a = {
        "hypothesis": "H19",
        "criterion": "super-additive interaction under AI + link failure",
        "event": "ai_link",
        "arm": "A6 vs A3, A9 vs A1",
        "reference_arm": "",
        "value": round(interaction, 4),
        "threshold": ">= 20",
        "pass_fraction": round(sum(interaction_passes) / len(interaction_passes), 4),
        "verdict": "PASS" if interaction >= 20.0 else "FAIL",
        "detail": "(A6 - A3) - (A9 - A1)",
    }
    h19b = _criterion(
        index,
        seeds,
        "H19",
        "combined arm level under AI + link failure",
        "ai_link",
        "A6",
        80.0,
        "ge",
        None,
        "A6 level",
    )
    h19c = _criterion(
        index,
        seeds,
        "H19",
        "isolation-only arm level under AI + link failure",
        "ai_link",
        "A3",
        20.0,
        "le",
        None,
        "A3 level",
    )
    verdicts.extend([h19a, h19b, h19c])
    verdicts.append(
        {
            "hypothesis": "H19",
            "criterion": "overall",
            "event": "ai_link",
            "arm": "A1, A3, A6, A9",
            "reference_arm": "",
            "value": "",
            "threshold": "all three criteria",
            "pass_fraction": round(
                min(
                    float(h19a["pass_fraction"]),
                    float(h19b["pass_fraction"]),
                    float(h19c["pass_fraction"]),
                ),
                4,
            ),
            "verdict": "PASS"
            if all(row["verdict"] == "PASS" for row in (h19a, h19b, h19c))
            else "FAIL",
            "detail": "isolation and multipath are not substitutes",
        }
    )

    h20a = _criterion(
        index,
        seeds,
        "H20",
        "global controller failure erases the multipath gain",
        "controller_link",
        "A5",
        50.0,
        "ge",
        "A8",
        "A5 - A8 under controller + link failure",
    )
    h20b = _criterion(
        index,
        seeds,
        "H20",
        "global controller does not change normal operation",
        "none",
        "A5",
        5.0,
        "abs_le",
        "A8",
        "|A5 - A8| with no failure",
    )
    verdicts.extend([h20a, h20b])
    verdicts.append(
        {
            "hypothesis": "H20",
            "criterion": "overall",
            "event": "controller_link, none",
            "arm": "A5 vs A8",
            "reference_arm": "",
            "value": "",
            "threshold": "both criteria",
            "pass_fraction": round(
                min(float(h20a["pass_fraction"]), float(h20b["pass_fraction"])), 4
            ),
            "verdict": "PASS"
            if h20a["verdict"] == "PASS" and h20b["verdict"] == "PASS"
            else "FAIL",
            "detail": "locality is a design variable",
        }
    )
    return verdicts


def _print_summary(
    summary: Sequence[dict[str, object]],
    verdicts: Sequence[dict[str, object]],
    events: Sequence[str],
    arms: Sequence[str],
) -> None:
    print("Common-mode resilience - availability during the event (%)")
    header = "event".ljust(16) + "".join(f"{arm:>8}" for arm in arms)
    print(header)
    for event in events:
        line = event.ljust(16)
        for arm in arms:
            row = next(
                item
                for item in summary
                if item["event"] == event and item["arm"] == arm
            )
            line += f"{float(row['availability_event_mean_pct']):8.1f}"
        print(line)
    print()
    if verdicts:
        print("Verdicts")
        for row in verdicts:
            if row["criterion"] == "overall":
                print(
                    f"{row['hypothesis']}: {row['verdict']} "
                    f"(min per-seed pass fraction {float(row['pass_fraction']):.3f})"
                )
    else:
        print("Verdicts skipped: run all arms and events to score H16-H20.")
    print()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seeds",
        type=int,
        default=cm.SEEDS,
        help=f"number of paired seeds (default {cm.SEEDS})",
    )
    parser.add_argument(
        "--base-seed",
        type=int,
        default=cm.BASE_SEED,
        help=f"first seed (default {cm.BASE_SEED})",
    )
    parser.add_argument(
        "--events",
        nargs="*",
        default=list(cm.EVENT_KINDS),
        choices=list(cm.EVENT_KINDS),
        help="event kinds to run (default: all)",
    )
    parser.add_argument(
        "--arms",
        nargs="*",
        default=list(cm.ARMS),
        choices=list(cm.ARMS),
        help="arms to run (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO / "output" / "common-mode",
        help="directory for the three CSV files",
    )
    args = parser.parse_args(argv)

    if args.seeds < 1:
        parser.error("--seeds must be at least 1")
    seeds = list(range(args.base_seed, args.base_seed + args.seeds))
    scenario = cm.build_backhaul_scenario()
    rows = run(seeds, args.events, args.arms, scenario)
    summary = summary_rows(rows, args.events, args.arms)
    full_set = set(args.events) == set(cm.EVENT_KINDS) and set(args.arms) == set(
        cm.ARMS
    )
    verdicts = verdict_rows(rows, seeds) if full_set else []

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_dir / "common_mode_per_seed.csv", rows)
    _write_csv(args.output_dir / "common_mode_summary.csv", summary)
    if verdicts:
        _write_csv(args.output_dir / "common_mode_verdicts.csv", verdicts)

    _print_summary(summary, verdicts, args.events, args.arms)
    print(f"Wrote {len(rows)} per-seed rows to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
