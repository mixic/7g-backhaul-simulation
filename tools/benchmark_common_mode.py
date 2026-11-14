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
from dataclasses import asdict, dataclass, replace
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


# --- Sensitivity and break-even ---------------------------------------------------------


@dataclass(frozen=True)
class Sweep:
    """One stipulated constant and the range over which it is varied."""

    key: str
    label: str
    field: str
    low: float
    high: float
    current: float
    unit: str


# The ranges are chosen so that every frozen value is inside them.  They are
# analysis ranges, not new scenario constants: the reported experiment still
# uses the frozen values.
SWEEPS: tuple[Sweep, ...] = (
    Sweep(
        "one_way_efficiency",
        "one-way local-policy efficiency",
        "one_way_efficiency",
        0.50,
        1.00,
        cm.ONE_WAY_EFFICIENCY,
        "fraction",
    ),
    Sweep(
        "fallback_tested_probability",
        "tested fallback activation probability",
        "fallback_tested_probability",
        0.00,
        1.00,
        cm.FALLBACK_TESTED_PROBABILITY,
        "fraction",
    ),
    Sweep(
        "fallback_untested_probability",
        "untested fallback activation probability",
        "fallback_untested_probability",
        0.00,
        1.00,
        cm.FALLBACK_UNTESTED_PROBABILITY,
        "fraction",
    ),
    Sweep(
        "fallback_tested_delay_s",
        "tested fallback activation delay",
        "fallback_tested_delay_s",
        0.00,
        25.00,
        cm.FALLBACK_TESTED_DELAY_S,
        "s",
    ),
    Sweep(
        "fallback_untested_delay_s",
        "untested fallback activation delay",
        "fallback_untested_delay_s",
        0.00,
        30.00,
        cm.FALLBACK_UNTESTED_DELAY_S,
        "s",
    ),
    Sweep(
        "fallback_tested_capacity_gbps",
        "tested fallback capacity",
        "fallback_tested_capacity_gbps",
        0.00,
        1.00,
        cm.FALLBACK_TESTED_CAPACITY_GBPS,
        "Gbps",
    ),
    Sweep(
        "fallback_untested_capacity_gbps",
        "untested fallback capacity",
        "fallback_untested_capacity_gbps",
        0.00,
        1.00,
        cm.FALLBACK_UNTESTED_CAPACITY_GBPS,
        "Gbps",
    ),
)


@dataclass(frozen=True)
class Criterion:
    """A frozen-style threshold used to locate a break-even value."""

    key: str
    label: str
    metric: str
    threshold: float
    comparator: str  # "ge" or "le"
    unit: str = "pct"


CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        "H18_normal_cost",
        "H18: normal-operation cost of the one-way boundary <= 15 points",
        "normal_cost",
        15.0,
        "le",
    ),
    Criterion(
        "H18_ai_level",
        "H18: A6 level under the AI failure >= 80 %",
        "a6_ai",
        80.0,
        "ge",
    ),
    Criterion(
        "H18_ai_gain",
        "H18: A6 - A5 under the AI failure >= 50 points",
        "a6_ai_gain",
        50.0,
        "ge",
    ),
    Criterion(
        "H19_interaction",
        "H19: (A6 - A3) - (A9 - A1) under AI + link >= 20 points",
        "interaction",
        20.0,
        "ge",
    ),
    Criterion(
        "H19_a6_level",
        "H19: A6 level under AI + link >= 80 %",
        "a6_ai_link",
        80.0,
        "ge",
    ),
    Criterion(
        "fallback_gap",
        "tested fallback beats untested under the backhaul cut (gap > 0)",
        "fallback_gap",
        0.0,
        "ge",
    ),
)


@dataclass(frozen=True)
class SensitivityPoint:
    value: float
    a5_ai: float
    a6_ai: float
    a5_none: float
    a6_none: float
    a6_ai_link: float
    a3_ai_link: float
    a9_ai_link: float
    a1_ai_link: float
    a6_backhaul: float
    a7_backhaul: float
    a9_link: float
    interaction: float

    @property
    def normal_cost(self) -> float:
        return self.a5_none - self.a6_none

    @property
    def a6_ai_gain(self) -> float:
        return self.a6_ai - self.a5_ai

    @property
    def fallback_gap(self) -> float:
        return self.a6_backhaul - self.a7_backhaul

    @property
    def h18_pass(self) -> bool:
        return (
            self.normal_cost <= 15.0
            and self.a6_ai >= 80.0
            and self.a6_ai_gain >= 50.0
        )

    @property
    def h19_pass(self) -> bool:
        return self.interaction >= 20.0 and self.a6_ai_link >= 80.0

    @property
    def fallback_pass(self) -> bool:
        return self.fallback_gap > 0.0


def _sweep_values(sweep: Sweep, points: int) -> tuple[float, ...]:
    if points < 2:
        raise ValueError("sensitivity needs at least two points per sweep")
    values = {
        round(sweep.low + (sweep.high - sweep.low) * index / (points - 1), 10)
        for index in range(points)
    }
    values.add(round(sweep.current, 10))
    return tuple(sorted(values))


def _mean_avail(
    arm: str,
    event: str,
    seeds: Sequence[int],
    scenario: cm.Scenario,
    params: cm.ScenarioParams,
) -> float:
    return mean(
        cm.simulate(
            cm.ARMS[arm], scenario=scenario, seed=seed, event_kind=event, params=params
        ).availability_event
        * 100.0
        for seed in seeds
    )


def measure_sensitivity_point(
    seeds: Sequence[int],
    scenario: cm.Scenario,
    params: cm.ScenarioParams,
    value: float,
) -> SensitivityPoint:
    """Measure the arms and events the break-even criteria depend on."""
    a5_ai = _mean_avail("A5", "ai", seeds, scenario, params)
    a6_ai = _mean_avail("A6", "ai", seeds, scenario, params)
    a5_none = _mean_avail("A5", "none", seeds, scenario, params)
    a6_none = _mean_avail("A6", "none", seeds, scenario, params)
    a6_ai_link = _mean_avail("A6", "ai_link", seeds, scenario, params)
    a3_ai_link = _mean_avail("A3", "ai_link", seeds, scenario, params)
    a9_ai_link = _mean_avail("A9", "ai_link", seeds, scenario, params)
    a1_ai_link = _mean_avail("A1", "ai_link", seeds, scenario, params)
    a6_backhaul = _mean_avail("A6", "backhaul_cut", seeds, scenario, params)
    a7_backhaul = _mean_avail("A7", "backhaul_cut", seeds, scenario, params)
    a9_link = _mean_avail("A9", "link", seeds, scenario, params)

    interaction = mean(
        (
            cm.simulate(
                cm.ARMS["A6"],
                scenario=scenario,
                seed=seed,
                event_kind="ai_link",
                params=params,
            ).availability_event
            - cm.simulate(
                cm.ARMS["A3"],
                scenario=scenario,
                seed=seed,
                event_kind="ai_link",
                params=params,
            ).availability_event
        )
        - (
            cm.simulate(
                cm.ARMS["A9"],
                scenario=scenario,
                seed=seed,
                event_kind="ai_link",
                params=params,
            ).availability_event
            - cm.simulate(
                cm.ARMS["A1"],
                scenario=scenario,
                seed=seed,
                event_kind="ai_link",
                params=params,
            ).availability_event
        )
        for seed in seeds
    ) * 100.0

    return SensitivityPoint(
        value=value,
        a5_ai=round(a5_ai, 4),
        a6_ai=round(a6_ai, 4),
        a5_none=round(a5_none, 4),
        a6_none=round(a6_none, 4),
        a6_ai_link=round(a6_ai_link, 4),
        a3_ai_link=round(a3_ai_link, 4),
        a9_ai_link=round(a9_ai_link, 4),
        a1_ai_link=round(a1_ai_link, 4),
        a6_backhaul=round(a6_backhaul, 4),
        a7_backhaul=round(a7_backhaul, 4),
        a9_link=round(a9_link, 4),
        interaction=round(interaction, 4),
    )


def _metric(point: SensitivityPoint, name: str) -> float:
    return float(getattr(point, name))


def _passes(value: float, criterion: Criterion) -> bool:
    if criterion.comparator == "ge":
        return value >= criterion.threshold
    if criterion.comparator == "le":
        return value <= criterion.threshold
    raise ValueError(f"unknown comparator: {criterion.comparator}")


def _crossing(
    value_pass: float,
    metric_pass: float,
    value_fail: float,
    metric_fail: float,
    criterion: Criterion,
) -> float:
    """Linear interpolation of the value where a metric crosses its threshold."""
    if criterion.comparator == "ge":
        denominator = metric_pass - metric_fail
        fraction = (
            (metric_pass - criterion.threshold) / denominator if denominator else 0.5
        )
    else:
        denominator = metric_fail - metric_pass
        fraction = (
            (criterion.threshold - metric_pass) / denominator if denominator else 0.5
        )
    fraction = max(0.0, min(1.0, fraction))
    return value_pass + fraction * (value_fail - value_pass)


def break_even_for(
    sweep: Sweep,
    points: Sequence[SensitivityPoint],
    criterion: Criterion,
) -> dict[str, object]:
    """Find the nearest value at which ``criterion`` stops passing.

    The search runs in both directions from the stipulated value.  A boundary
    between two grid points is located by linear interpolation of the metric;
    the full grid is written alongside this table so the approximation is
    visible.  ``None`` means the criterion passed at every grid point in the
    swept range.
    """
    ordered = sorted(points, key=lambda point: point.value)
    current_index = min(
        range(len(ordered)), key=lambda index: abs(ordered[index].value - sweep.current)
    )
    current_metric = _metric(ordered[current_index], criterion.metric)
    if not _passes(current_metric, criterion):
        return {
            "parameter": sweep.key,
            "current_value": round(sweep.current, 6),
            "unit": sweep.unit,
            "criterion": criterion.key,
            "criterion_label": criterion.label,
            "threshold": criterion.threshold,
            "comparator": criterion.comparator,
            "current_metric": round(current_metric, 4),
            "current_pass": False,
            "direction": "fails at the stipulated value",
            "break_even_value": "",
            "break_even_metric": "",
            "distance": "",
        }

    candidates: list[tuple[float, str, float]] = []
    for direction, indices in (
        ("increasing", range(current_index + 1, len(ordered))),
        ("decreasing", range(current_index - 1, -1, -1)),
    ):
        previous = ordered[current_index]
        for index in indices:
            point = ordered[index]
            if not _passes(_metric(point, criterion.metric), criterion):
                boundary = _crossing(
                    previous.value,
                    _metric(previous, criterion.metric),
                    point.value,
                    _metric(point, criterion.metric),
                    criterion,
                )
                candidates.append((abs(boundary - sweep.current), direction, boundary))
                break
            previous = point

    if not candidates:
        return {
            "parameter": sweep.key,
            "current_value": round(sweep.current, 6),
            "unit": sweep.unit,
            "criterion": criterion.key,
            "criterion_label": criterion.label,
            "threshold": criterion.threshold,
            "comparator": criterion.comparator,
            "current_metric": round(current_metric, 4),
            "current_pass": True,
            "direction": "none in range",
            "break_even_value": "",
            "break_even_metric": "",
            "distance": "",
        }

    distance, direction, boundary = min(candidates)
    return {
        "parameter": sweep.key,
        "current_value": round(sweep.current, 6),
        "unit": sweep.unit,
        "criterion": criterion.key,
        "criterion_label": criterion.label,
        "threshold": criterion.threshold,
        "comparator": criterion.comparator,
        "current_metric": round(current_metric, 4),
        "current_pass": True,
        "direction": direction,
        "break_even_value": round(boundary, 6),
        "break_even_metric": criterion.threshold,
        "distance": round(distance, 6),
    }


def run_sensitivity(
    seeds: Sequence[int],
    scenario: cm.Scenario,
    points: int = 25,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Sweep every stipulated constant and locate every criterion's break-even."""
    grid_rows: list[dict[str, object]] = []
    break_rows: list[dict[str, object]] = []
    for sweep in SWEEPS:
        sweep_points: list[SensitivityPoint] = []
        for value in _sweep_values(sweep, points):
            params = replace(cm.DEFAULT_PARAMS, **{sweep.field: value})
            point = measure_sensitivity_point(seeds, scenario, params, value)
            sweep_points.append(point)
            row = asdict(point)
            row["parameter"] = sweep.key
            row["unit"] = sweep.unit
            row["h18_pass"] = int(point.h18_pass)
            row["h19_pass"] = int(point.h19_pass)
            row["fallback_pass"] = int(point.fallback_pass)
            grid_rows.append(row)
        for criterion in CRITERIA:
            break_rows.append(break_even_for(sweep, sweep_points, criterion))
    return grid_rows, break_rows


_PRIMARY_CRITERION = {
    "one_way_efficiency": "H18_normal_cost",
    "fallback_tested_probability": "fallback_gap",
    "fallback_untested_probability": "fallback_gap",
    "fallback_tested_delay_s": "fallback_gap",
    "fallback_untested_delay_s": "fallback_gap",
    "fallback_tested_capacity_gbps": "fallback_gap",
    "fallback_untested_capacity_gbps": "fallback_gap",
}


def _fmt(value: object) -> str:
    if value == "" or value is None:
        return "none in range"
    return f"{float(value):g}"


def sensitivity_markdown(
    break_rows: Sequence[dict[str, object]],
    points: int,
    seeds: int,
) -> str:
    """Render the compact break-even table used by Paper D."""
    by_key = {
        (str(row["parameter"]), str(row["criterion"])): row for row in break_rows
    }
    lines = [
        "### Break-even values for the stipulated constants",
        "",
        f"Grid: {points} values per constant, {seeds} paired seeds, linear "
        "interpolation between adjacent grid points. A break-even is the value "
        "at which the named criterion stops passing; `none in range` means it "
        "passed at every swept value.",
        "",
        "| Constant | Stipulated | Sweep | Primary break-even | Claim that fails there | Margin |",
        "|---|---:|---|---:|---|---:|",
    ]
    for sweep in SWEEPS:
        criterion_key = _PRIMARY_CRITERION[sweep.key]
        row = by_key[(sweep.key, criterion_key)]
        break_value = row["break_even_value"]
        if break_value == "":
            margin = ""
            claim = "criterion survives the whole swept range"
        else:
            margin_value = float(break_value) - sweep.current
            margin = f"{margin_value:+g}"
            claim = str(row["criterion_label"])
        lines.append(
            "| {label} | {current:g} {unit} | {low:g}-{high:g} {unit} | {be} | "
            "{claim} | {margin} |".format(
                label=sweep.label,
                current=sweep.current,
                unit=sweep.unit,
                low=sweep.low,
                high=sweep.high,
                be=_fmt(break_value),
                claim=claim,
                margin=margin,
            )
        )
    efficiency_level = by_key[("one_way_efficiency", "H18_ai_level")]
    efficiency_cost = by_key[("one_way_efficiency", "H18_normal_cost")]
    if efficiency_level["break_even_value"] != "":
        lines += [
            "",
            "For H18, the binding clause is the normal-operation cost "
            f"(`{_fmt(efficiency_cost['break_even_value'])}`), not the absolute "
            f"80 % level (`{_fmt(efficiency_level['break_even_value'])}`); the "
            "model check fails at the higher of the two values.",
        ]
    lines += [
        "",
        "Full per-criterion results, including H18 and H19 sub-criteria, are in "
        "`common-mode-break-even.csv`; the grid is in "
        "`common-mode-sensitivity.csv`.",
        "",
        "### H19 criteria break-even",
        "",
        "| Constant | Stipulated | Criterion | Break-even | Direction |",
        "|---|---:|---|---:|---|",
    ]
    for sweep in SWEEPS:
        for criterion_key in ("H19_interaction", "H19_a6_level"):
            row = by_key[(sweep.key, criterion_key)]
            lines.append(
                "| {parameter} | {current:g} | {criterion} | {be} | {direction} |".format(
                    parameter=sweep.key,
                    current=sweep.current,
                    criterion=criterion_key,
                    be=_fmt(row["break_even_value"]),
                    direction=row["direction"],
                )
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def write_sensitivity(
    output_dir: Path,
    seeds: Sequence[int],
    scenario: cm.Scenario,
    points: int = 25,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    grid_rows, break_rows = run_sensitivity(seeds, scenario, points)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "common-mode-sensitivity.csv", grid_rows)
    _write_csv(output_dir / "common-mode-break-even.csv", break_rows)
    (output_dir / "common-mode-break-even.md").write_text(
        sensitivity_markdown(break_rows, points, len(seeds)), encoding="utf-8"
    )
    return grid_rows, break_rows


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
    parser.add_argument(
        "--sensitivity",
        action="store_true",
        help="sweep the stipulated constants and write break-even tables instead of the main run",
    )
    parser.add_argument(
        "--sensitivity-points",
        type=int,
        default=25,
        help="grid values per constant in sensitivity mode (default 25)",
    )
    parser.add_argument(
        "--sensitivity-out",
        type=Path,
        default=REPO / "docs" / "paper-tables",
        help="directory for the sensitivity CSV and Markdown tables",
    )
    args = parser.parse_args(argv)

    if args.seeds < 1:
        parser.error("--seeds must be at least 1")
    seeds = list(range(args.base_seed, args.base_seed + args.seeds))
    scenario = cm.build_backhaul_scenario()
    if args.sensitivity:
        if args.sensitivity_points < 2:
            parser.error("--sensitivity-points must be at least 2")
        grid_rows, break_rows = write_sensitivity(
            args.sensitivity_out, seeds, scenario, args.sensitivity_points
        )
        print(
            f"Sensitivity: {len(grid_rows)} grid rows, {len(break_rows)} break-even rows, "
            f"{args.sensitivity_points} points per constant, {len(seeds)} seeds"
        )
        for row in break_rows:
            if row["criterion"] == _PRIMARY_CRITERION.get(str(row["parameter"])):
                if row["break_even_value"] == "":
                    print(
                        f"  {row['parameter']}: no break-even in the swept range"
                    )
                else:
                    print(
                        "  {parameter}: break-even {be} ({direction})".format(
                            parameter=row["parameter"],
                            be=_fmt(row["break_even_value"]),
                            direction=row["direction"],
                        )
                    )
        print(f"Wrote sensitivity artifacts to {args.sensitivity_out}")
        return 0

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
