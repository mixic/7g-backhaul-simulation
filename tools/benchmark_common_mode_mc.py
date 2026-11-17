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

"""Run the Monte Carlo common-mode study and write its artifacts.

The protocol is frozen in ``docs/common-mode-mc-predictions.md`` at commit
``6c8d320``.  This tool runs four experiments:

* **E1 incident** -- nine arms x ten incident classes x ``--replications``
  replications of the 24 h continuous-time simulation;
* **E2 campaign** -- nine arms x ``--campaign-replications`` replications of a
  30-day campaign with every failure process active;
* **E3 one-factor sensitivity** -- each stipulated constant swept over 25 values
  to locate break-even points, as in the deterministic reference study;
* **E4 global sensitivity** -- Saltelli/Sobol first- and total-order indices,
  plus a two-factor efficiency x fallback-capacity grid.

Outputs
-------
``output/common-mode-mc/`` (raw, ignored by Git):

* ``common_mode_mc_per_replication.csv`` -- one row per replication, event, arm;
* ``common_mode_mc_summary.csv`` -- mean, sd and interval per event and arm;
* ``common_mode_mc_verdicts.csv`` -- every criterion with its interval, p-value
  and verdict;
* ``common_mode_mc_campaign.csv`` -- the 30-day campaign summary.

``docs/paper-tables/`` (committed): the compact tables the paper pastes, plus the
per-replication criterion differences that the figures are drawn from.

Usage
-----
``py -3 tools/benchmark_common_mode_mc.py``
    run E1 and E2 at the frozen replication counts;
``py -3 tools/benchmark_common_mode_mc.py --sensitivity``
    run E3 (one-factor break-even);
``py -3 tools/benchmark_common_mode_mc.py --sobol --two-factor``
    run E4;
``--quick``
    a small smoke run that writes to a separate directory.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulation import common_mode as cm  # noqa: E402
from simulation import common_mode_mc as mc  # noqa: E402
from tools import mc_stats  # noqa: E402
from tools.benchmark_common_mode import (  # noqa: E402
    CRITERIA as SENSITIVITY_CRITERIA,
    SWEEPS,
    SensitivityPoint,
    _sweep_values,
    break_even_for,
)

#: Default output locations.
RAW_DIR = REPO / "output" / "common-mode-mc"
TABLE_DIR = REPO / "docs" / "paper-tables"

#: Default replication counts of the frozen protocol.
DEFAULT_REPLICATIONS = mc.INCIDENT_REPLICATIONS
DEFAULT_CAMPAIGN_REPLICATIONS = mc.CAMPAIGN_REPLICATIONS
DEFAULT_BASE_SEED = mc.BASE_SEED

#: Nominal and Bonferroni levels.
NOMINAL = mc_stats.NOMINAL_LEVEL
BONFERRONI = mc_stats.BONFERRONI_LEVEL


@dataclass(frozen=True)
class Criterion:
    """One frozen hypothesis criterion and the quantity it bounds."""

    key: str
    hypothesis: str
    label: str
    event: str
    kind: str  # "diff", "abs_diff", "level" or "interaction"
    left: str
    right: str
    threshold: float
    comparator: str  # "ge", "le" or "abs_le"


CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        "H16a",
        "H16",
        "tenant isolation contains a tenant-shared fault",
        "tenant_gw",
        "diff",
        "A4",
        "A3",
        50.0,
        "ge",
    ),
    Criterion(
        "H16b",
        "H16",
        "tenant isolation does not contain a shared control-plane fault",
        "idp",
        "abs_diff",
        "A4",
        "A3",
        5.0,
        "abs_le",
    ),
    Criterion(
        "H17a",
        "H17",
        "SRLG-disjoint multipath under a conduit failure",
        "srlg",
        "diff",
        "A3",
        "A2",
        20.0,
        "ge",
    ),
    Criterion(
        "H17b",
        "H17",
        "multipath under an independent link failure",
        "link",
        "diff",
        "A2",
        "A1",
        50.0,
        "ge",
    ),
    Criterion(
        "H18a",
        "H18",
        "one-way boundary survives an AI control-plane failure",
        "ai",
        "diff",
        "A6",
        "A5",
        50.0,
        "ge",
    ),
    Criterion(
        "H18b",
        "H18",
        "fallback restores at least 80 % under an AI failure",
        "ai",
        "level",
        "A6",
        "",
        80.0,
        "ge",
    ),
    Criterion(
        "H18c",
        "H18",
        "normal-operation cost of isolation is at most 15 points",
        "none",
        "diff",
        "A5",
        "A6",
        15.0,
        "le",
    ),
    Criterion(
        "H19a",
        "H19",
        "super-additive interaction under AI + link failure",
        "ai_link",
        "interaction",
        "A6",
        "",
        20.0,
        "ge",
    ),
    Criterion(
        "H19b",
        "H19",
        "combined arm level under AI + link failure",
        "ai_link",
        "level",
        "A6",
        "",
        80.0,
        "ge",
    ),
    Criterion(
        "H19c",
        "H19",
        "isolation-only arm level under AI + link failure",
        "ai_link",
        "level",
        "A3",
        "",
        20.0,
        "le",
    ),
    Criterion(
        "H20a",
        "H20",
        "global controller failure erases the multipath gain",
        "controller_link",
        "diff",
        "A5",
        "A8",
        50.0,
        "ge",
    ),
    Criterion(
        "H20b",
        "H20",
        "global controller does not change normal operation",
        "none",
        "abs_diff",
        "A5",
        "A8",
        5.0,
        "abs_le",
    ),
)

#: Hypothesis -> the criteria that must all pass for the hypothesis to pass.
HYPOTHESES: dict[str, tuple[str, ...]] = {
    "H16": ("H16a", "H16b"),
    "H17": ("H17a", "H17b"),
    "H18": ("H18a", "H18b", "H18c"),
    "H19": ("H19a", "H19b", "H19c"),
    "H20": ("H20a", "H20b"),
}


# --- CSV helpers -----------------------------------------------------------------------


def write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    """Write a list of rows as a CSV with a stable header."""
    if not rows:
        raise ValueError(f"refusing to write an empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


# --- Experiment data -------------------------------------------------------------------


class ExperimentData:
    """Per-key arrays of the primary metrics of the incident experiment."""

    def __init__(self, results: Sequence[mc.RunResult]) -> None:
        self.fields: dict[str, dict[tuple[str, str], np.ndarray]] = {
            "availability_event": {},
            "availability_overall": {},
            "recovery_s": {},
            "blast_radius": {},
            "fallback_rate": {},
        }
        grouped: dict[tuple[str, str], dict[int, mc.RunResult]] = {}
        for result in results:
            grouped.setdefault((result.event, result.arm), {})[result.replication] = result
        for key, by_replication in grouped.items():
            order = sorted(by_replication)
            self.fields["availability_event"][key] = np.array(
                [by_replication[replication].availability_event * 100.0 for replication in order]
            )
            self.fields["availability_overall"][key] = np.array(
                [by_replication[replication].availability_overall * 100.0 for replication in order]
            )
            self.fields["recovery_s"][key] = np.array(
                [by_replication[replication].recovery_s for replication in order]
            )
            self.fields["blast_radius"][key] = np.array(
                [by_replication[replication].blast_radius * 100.0 for replication in order]
            )
            self.fields["fallback_rate"][key] = np.array(
                [by_replication[replication].fallback_rate * 100.0 for replication in order]
            )
        self.cost: dict[str, float] = {}
        self.independence: dict[str, float] = {}
        for result in results:
            self.cost[result.arm] = result.cost_index
            self.independence[result.arm] = result.path_independence

    def series(self, field: str, event: str, arm: str) -> np.ndarray:
        return self.fields[field][(event, arm)]


def criterion_values(index: Mapping[tuple[str, str], np.ndarray], criterion: Criterion) -> np.ndarray:
    """The per-replication quantity a criterion bounds, in percentage points."""
    if criterion.kind == "level":
        return np.asarray(index[(criterion.event, criterion.left)], dtype=float)
    if criterion.kind == "diff":
        return np.asarray(index[(criterion.event, criterion.left)], dtype=float) - np.asarray(
            index[(criterion.event, criterion.right)], dtype=float
        )
    if criterion.kind == "abs_diff":
        return np.asarray(index[(criterion.event, criterion.left)], dtype=float) - np.asarray(
            index[(criterion.event, criterion.right)], dtype=float
        )
    if criterion.kind == "interaction":
        event = criterion.event
        return (
            np.asarray(index[(event, "A6")], dtype=float)
            - np.asarray(index[(event, "A3")], dtype=float)
            - (
                np.asarray(index[(event, "A9")], dtype=float)
                - np.asarray(index[(event, "A1")], dtype=float)
            )
        )
    raise ValueError(f"unknown criterion kind: {criterion.kind}")


def _passes(criterion: Criterion, value: float) -> bool:
    if criterion.comparator == "ge":
        return value >= criterion.threshold
    if criterion.comparator == "le":
        return value <= criterion.threshold
    if criterion.comparator == "abs_le":
        return abs(value) <= criterion.threshold
    raise ValueError(f"unknown comparator: {criterion.comparator}")


def _verdict(criterion: Criterion, low: float, high: float) -> str:
    threshold = criterion.threshold
    if criterion.comparator == "ge":
        if low >= threshold:
            return "PASS"
        if high < threshold:
            return "FAIL"
        return "INCONCLUSIVE"
    if criterion.comparator == "le":
        if high <= threshold:
            return "PASS"
        if low > threshold:
            return "FAIL"
        return "INCONCLUSIVE"
    if criterion.comparator == "abs_le":
        if low >= -threshold and high <= threshold:
            return "PASS"
        if low > threshold or high < -threshold:
            return "FAIL"
        return "INCONCLUSIVE"
    raise ValueError(f"unknown comparator: {criterion.comparator}")


def evaluate_criterion(
    criterion: Criterion, values: np.ndarray
) -> dict[str, object]:
    """Interval-rule evaluation of one criterion over the per-replication values."""
    estimate = mc_stats.mean(values)
    replicates = mc_stats.bootstrap_means(values)
    low, high = mc_stats.bootstrap_interval(values, NOMINAL, replicates)
    bonferroni_low, bonferroni_high = mc_stats.bootstrap_interval(
        values, BONFERRONI, replicates
    )
    p_value = mc_stats.permutation_p_two_sided(values, criterion.threshold)
    pass_fraction = float(np.mean([_passes(criterion, float(value)) for value in values]))
    return {
        "key": criterion.key,
        "hypothesis": criterion.hypothesis,
        "criterion": criterion.label,
        "event": criterion.event,
        "arm": criterion.left,
        "reference_arm": criterion.right,
        "comparator": criterion.comparator,
        "threshold": criterion.threshold,
        "estimate_pct": _round(estimate),
        "value_pct": _round(abs(estimate) if criterion.comparator == "abs_le" else estimate),
        "ci95_low_pct": _round(low),
        "ci95_high_pct": _round(high),
        "bonferroni_low_pct": _round(bonferroni_low),
        "bonferroni_high_pct": _round(bonferroni_high),
        "p_value": _round(p_value, 6),
        "pass_fraction": _round(pass_fraction),
        "verdict": _verdict(criterion, low, high),
        "verdict_bonferroni": _verdict(criterion, bonferroni_low, bonferroni_high),
        "replications": int(values.size),
    }


def hypothesis_rows(criterion_rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Roll the criteria up to the five hypotheses."""
    by_key = {str(row["key"]): row for row in criterion_rows}
    rows: list[dict[str, object]] = []
    for hypothesis, keys in HYPOTHESES.items():
        verdicts = [str(by_key[key]["verdict"]) for key in keys]
        verdict = "FAIL" if "FAIL" in verdicts else ("PASS" if all(v == "PASS" for v in verdicts) else "INCONCLUSIVE")
        bonferroni = [
            str(by_key[key]["verdict_bonferroni"]) for key in keys
        ]
        verdict_bonferroni = (
            "FAIL"
            if "FAIL" in bonferroni
            else ("PASS" if all(v == "PASS" for v in bonferroni) else "INCONCLUSIVE")
        )
        rows.append(
            {
                "key": hypothesis,
                "hypothesis": hypothesis,
                "criterion": "all criteria of the hypothesis",
                "event": ", ".join(sorted({str(by_key[key]["event"]) for key in keys})),
                "arm": ", ".join(str(by_key[key]["arm"]) for key in keys),
                "reference_arm": "",
                "comparator": "all",
                "threshold": "",
                "estimate_pct": "",
                "value_pct": "",
                "ci95_low_pct": "",
                "ci95_high_pct": "",
                "bonferroni_low_pct": "",
                "bonferroni_high_pct": "",
                "p_value": "",
                "pass_fraction": _round(
                    min(float(by_key[key]["pass_fraction"]) for key in keys)
                ),
                "verdict": verdict,
                "verdict_bonferroni": verdict_bonferroni,
                "replications": int(by_key[keys[0]]["replications"]),
            }
        )
    return rows


# --- Deterministic reference values ----------------------------------------------------


def reference_index(
    scenario: cm.Scenario, seeds: Sequence[int]
) -> dict[tuple[str, str], np.ndarray]:
    """The deterministic reference model's availability, for comparison."""
    index: dict[tuple[str, str], np.ndarray] = {}
    for event in cm.EVENT_KINDS:
        for arm_name, arm in cm.ARMS.items():
            values = [
                cm.simulate(arm, scenario=scenario, seed=seed, event_kind=event).availability_event
                * 100.0
                for seed in seeds
            ]
            index[(event, arm_name)] = np.array(values)
    return index


def reference_rows(
    reference: Mapping[tuple[str, str], np.ndarray],
    mc_index: Mapping[tuple[str, str], np.ndarray],
) -> list[dict[str, object]]:
    """Side-by-side deterministic and simulated availability per cell."""
    rows: list[dict[str, object]] = []
    for event in cm.EVENT_KINDS:
        for arm_name in cm.ARMS:
            deterministic = reference[(event, arm_name)]
            simulated = mc_index[(event, arm_name)]
            rows.append(
                {
                    "event": event,
                    "arm": arm_name,
                    "deterministic_pct": _round(mc_stats.mean(deterministic)),
                    "simulated_mean_pct": _round(mc_stats.mean(simulated)),
                    "simulated_sd_pct": _round(mc_stats.sd(simulated)),
                    "difference_pct": _round(
                        mc_stats.mean(simulated) - mc_stats.mean(deterministic)
                    ),
                }
            )
    return rows


# --- Summary ---------------------------------------------------------------------------


def summary_rows(data: ExperimentData, events: Sequence[str], arms: Sequence[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for event in events:
        for arm_name in arms:
            values = data.series("availability_event", event, arm_name)
            centre, low, high = mc_stats.t_interval(values)
            recovery = data.series("recovery_s", event, arm_name)
            rows.append(
                {
                    "event": event,
                    "arm": arm_name,
                    "label": cm.ARMS[arm_name].label,
                    "availability_event_mean_pct": _round(centre),
                    "availability_event_ci95_pct": _round(0.5 * (high - low)),
                    "availability_event_sd_pct": _round(mc_stats.sd(values)),
                    "availability_overall_mean_pct": _round(
                        mc_stats.mean(data.series("availability_overall", event, arm_name))
                    ),
                    "recovery_mean_s": _round(mc_stats.mean(recovery)),
                    "recovery_median_s": _round(float(np.median(recovery))),
                    "recovery_p90_s": _round(float(np.percentile(recovery, 90))),
                    "blast_radius_mean_pct": _round(
                        mc_stats.mean(data.series("blast_radius", event, arm_name))
                    ),
                    "fallback_rate_mean_pct": _round(
                        mc_stats.mean(data.series("fallback_rate", event, arm_name))
                    ),
                    "path_independence": _round(data.independence[arm_name]),
                    "cost_index": _round(data.cost[arm_name]),
                    "replications": int(values.size),
                }
            )
    return rows


def campaign_rows(results: Sequence[mc.CampaignResult], arms: Sequence[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for arm_name in arms:
        selected = [result for result in results if result.arm == arm_name]
        availability = np.array([result.availability_ss * 100.0 for result in selected])
        centre, low, high = mc_stats.t_interval(availability)
        rows.append(
            {
                "arm": arm_name,
                "label": cm.ARMS[arm_name].label,
                "availability_ss_mean_pct": _round(centre),
                "availability_ss_ci95_pct": _round(0.5 * (high - low)),
                "availability_ss_sd_pct": _round(mc_stats.sd(availability)),
                "policy_loss_pct": _round(
                    100.0 * mc_stats.mean([result.policy_loss for result in selected])
                ),
                "congestion_loss_pct": _round(
                    100.0 * mc_stats.mean([result.congestion_loss for result in selected])
                ),
                "dependency_loss_pct": _round(
                    100.0 * mc_stats.mean([result.dependency_loss for result in selected])
                ),
                "shared_attrib": _round(
                    mc_stats.mean([result.shared_attrib for result in selected])
                ),
                "slo_breach_days": _round(
                    mc_stats.mean([result.slo_breach_days for result in selected])
                ),
                "shared_incidents": _round(
                    mc_stats.mean([result.shared_incidents for result in selected])
                ),
                "replications": len(selected),
            }
        )
    return rows


def difference_rows(
    index: Mapping[tuple[str, str], np.ndarray],
) -> tuple[list[dict[str, object]], dict[str, np.ndarray]]:
    """The per-replication criterion quantities, in long and wide form."""
    wide: dict[str, np.ndarray] = {}
    rows: list[dict[str, object]] = []
    for criterion in CRITERIA:
        values = criterion_values(index, criterion)
        wide[criterion.key] = values
        for replication, value in enumerate(values):
            rows.append(
                {
                    "criterion": criterion.key,
                    "replication": replication,
                    "value_pct": _round(value),
                }
            )
    gap = np.asarray(index[("backhaul_cut", "A6")], dtype=float) - np.asarray(
        index[("backhaul_cut", "A7")], dtype=float
    )
    wide["fallback_gap"] = gap
    for replication, value in enumerate(gap):
        rows.append(
            {
                "criterion": "fallback_gap",
                "replication": replication,
                "value_pct": _round(value),
            }
        )
    return rows, wide


def per_replication_rows(
    results: Sequence[mc.RunResult],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in sorted(results, key=lambda item: (item.event, item.arm, item.replication)):
        rows.append(
            {
                "replication": result.replication,
                "event": result.event,
                "arm": result.arm,
                "availability_event_pct": _round(result.availability_event * 100.0),
                "availability_overall_pct": _round(result.availability_overall * 100.0),
                "recovery_s": _round(result.recovery_s),
                "blast_radius_pct": _round(result.blast_radius * 100.0),
                "fallback_rate_pct": _round(result.fallback_rate * 100.0),
                "path_independence": _round(result.path_independence),
                "cost_index": _round(result.cost_index),
            }
        )
    return rows


# --- Sensitivity (E3) ------------------------------------------------------------------


def _mean_availability(
    arms: Sequence[str],
    event: str,
    replications: Sequence[int],
    scenario: cm.Scenario,
    params: mc.MCParams,
    base_seed: int,
) -> dict[str, float]:
    results = mc.incident_runs(
        [event], [cm.ARMS[name] for name in arms], replications, scenario, params, base_seed
    )
    grouped: dict[str, list[float]] = {name: [] for name in arms}
    for result in results:
        grouped[result.arm].append(result.availability_event)
    return {
        name: 100.0 * mc_stats.mean(values) for name, values in grouped.items()
    }


def measure_sensitivity_point(
    replications: Sequence[int],
    scenario: cm.Scenario,
    params: mc.MCParams,
    value: float,
    base_seed: int = DEFAULT_BASE_SEED,
) -> SensitivityPoint:
    """Measure the quantities the break-even criteria depend on."""
    ai = _mean_availability(("A5", "A6"), "ai", replications, scenario, params, base_seed)
    none = _mean_availability(("A5", "A6"), "none", replications, scenario, params, base_seed)
    ai_link = _mean_availability(
        ("A1", "A3", "A6", "A9"), "ai_link", replications, scenario, params, base_seed
    )
    backhaul = _mean_availability(
        ("A6", "A7"), "backhaul_cut", replications, scenario, params, base_seed
    )
    link = _mean_availability(("A9",), "link", replications, scenario, params, base_seed)

    interaction_results = mc.incident_runs(
        ["ai_link"],
        [cm.ARMS[name] for name in ("A1", "A3", "A6", "A9")],
        replications,
        scenario,
        params,
        base_seed,
    )
    by_replication: dict[int, dict[str, float]] = {}
    for result in interaction_results:
        by_replication.setdefault(result.replication, {})[result.arm] = result.availability_event
    interaction = 100.0 * mc_stats.mean(
        [
            values["A6"] - values["A3"] - (values["A9"] - values["A1"])
            for values in by_replication.values()
        ]
    )
    return SensitivityPoint(
        value=value,
        a5_ai=_round(ai["A5"]),
        a6_ai=_round(ai["A6"]),
        a5_none=_round(none["A5"]),
        a6_none=_round(none["A6"]),
        a6_ai_link=_round(ai_link["A6"]),
        a3_ai_link=_round(ai_link["A3"]),
        a9_ai_link=_round(ai_link["A9"]),
        a1_ai_link=_round(ai_link["A1"]),
        a6_backhaul=_round(backhaul["A6"]),
        a7_backhaul=_round(backhaul["A7"]),
        a9_link=_round(link["A9"]),
        interaction=_round(interaction),
    )


def run_sensitivity(
    replications: Sequence[int],
    scenario: cm.Scenario,
    points: int = 25,
    base_seed: int = DEFAULT_BASE_SEED,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Sweep every stipulated constant and locate every criterion's break-even."""
    grid_rows: list[dict[str, object]] = []
    break_rows: list[dict[str, object]] = []
    for sweep in SWEEPS:
        sweep_points: list[SensitivityPoint] = []
        for value in _sweep_values(sweep, points):
            params = replace(mc.MCParams(), **{sweep.field: value})
            point = measure_sensitivity_point(
                replications, scenario, params, value, base_seed
            )
            sweep_points.append(point)
            row = asdict(point)
            row["parameter"] = sweep.key
            row["unit"] = sweep.unit
            row["h18_pass"] = int(point.h18_pass)
            row["h19_pass"] = int(point.h19_pass)
            row["fallback_pass"] = int(point.fallback_pass)
            grid_rows.append(row)
        for criterion in SENSITIVITY_CRITERIA:
            break_rows.append(break_even_for(sweep, sweep_points, criterion))
    return grid_rows, break_rows


def sensitivity_markdown(
    break_rows: Sequence[dict[str, object]], points: int, replications: int
) -> str:
    """Render the compact break-even table used by the paper."""
    by_key = {
        (str(row["parameter"]), str(row["criterion"])): row for row in break_rows
    }
    lines = [
        "### Break-even values under the Monte Carlo engine",
        "",
        f"Grid: {points} values per constant, {replications} replications per point, "
        "linear interpolation between adjacent grid points. A break-even is the "
        "value at which the named criterion stops passing; `none in range` means "
        "it passed at every swept value.",
        "",
        "| Constant | Stipulated | Sweep | Primary break-even | Claim that fails there | Margin |",
        "|---|---:|---|---:|---|---:|",
    ]
    primary = {
        "one_way_efficiency": "H18_normal_cost",
        "fallback_tested_probability": "fallback_gap",
        "fallback_untested_probability": "fallback_gap",
        "fallback_tested_delay_s": "fallback_gap",
        "fallback_untested_delay_s": "fallback_gap",
        "fallback_tested_capacity_gbps": "fallback_gap",
        "fallback_untested_capacity_gbps": "fallback_gap",
    }
    for sweep in SWEEPS:
        row = by_key[(sweep.key, primary[sweep.key])]
        break_value = row["break_even_value"]
        if break_value == "":
            margin = ""
            claim = "criterion survives the whole swept range"
        else:
            margin = f"{float(break_value) - sweep.current:+g}"
            claim = str(row["criterion_label"])
        shown = "none in range" if break_value == "" else f"{float(break_value):g}"
        lines.append(
            "| {label} | {current:g} {unit} | {low:g}-{high:g} {unit} | {be} | "
            "{claim} | {margin} |".format(
                label=sweep.label,
                current=sweep.current,
                unit=sweep.unit,
                low=sweep.low,
                high=sweep.high,
                be=shown,
                claim=claim,
                margin=margin,
            )
        )
    lines += [
        "",
        "Full per-criterion results, including the H18 and H19 sub-criteria, are in "
        "`common-mode-mc-break-even.csv`; the full grid is in "
        "`common-mode-mc-sensitivity.csv`.",
        "",
        "### H19 criteria break-even",
        "",
        "| Constant | Stipulated | Criterion | Break-even | Direction |",
        "|---|---:|---|---:|---|",
    ]
    for sweep in SWEEPS:
        for criterion_key in ("H19_interaction", "H19_a6_level"):
            row = by_key[(sweep.key, criterion_key)]
            shown = (
                "none in range"
                if row["break_even_value"] == ""
                else f"{float(row['break_even_value']):g}"
            )
            lines.append(
                "| {parameter} | {current:g} | {criterion} | {be} | {direction} |".format(
                    parameter=sweep.key,
                    current=sweep.current,
                    criterion=criterion_key,
                    be=shown,
                    direction=row["direction"],
                )
            )
    lines.append("")
    return "\n".join(lines) + "\n"


# --- Global sensitivity (E4) -----------------------------------------------------------

#: Sobol parameter ranges (analysis ranges, not scenario constants).
SOBOL_RANGES: tuple[tuple[str, float, float], ...] = (
    ("one_way_efficiency", 0.50, 1.00),
    ("fallback_tested_probability", 0.0, 1.0),
    ("fallback_untested_probability", 0.0, 1.0),
    ("fallback_tested_delay_s", 0.5, 25.0),
    ("fallback_untested_delay_s", 0.5, 30.0),
    ("fallback_tested_capacity_gbps", 0.0, 1.0),
    ("fallback_untested_capacity_gbps", 0.0, 1.0),
    ("shared_mtbf_days", 7.0, 60.0),
)

SOBOL_OUTPUTS: tuple[str, ...] = ("a6_ai", "a6_cut", "a7_cut", "interaction")

SOBOL_BASE = 256
SOBOL_REPLICATIONS = 20


def _sobol_model(
    point: np.ndarray,
    scenario: cm.Scenario,
    base_seed: int,
) -> dict[str, float]:
    """Evaluate the four outputs of interest at one parameter vector."""
    overrides = {
        name: low + (high - low) * float(value)
        for (name, low, high), value in zip(SOBOL_RANGES, point)
    }
    params = replace(mc.MCParams(), **overrides)
    replications = list(range(SOBOL_REPLICATIONS))
    ai = _mean_availability(("A6",), "ai", replications, scenario, params, base_seed)
    backhaul = _mean_availability(
        ("A6", "A7"), "backhaul_cut", replications, scenario, params, base_seed
    )
    interaction_results = mc.incident_runs(
        ["ai_link"],
        [cm.ARMS[name] for name in ("A1", "A3", "A6", "A9")],
        replications,
        scenario,
        params,
        base_seed,
    )
    by_replication: dict[int, dict[str, float]] = {}
    for result in interaction_results:
        by_replication.setdefault(result.replication, {})[result.arm] = result.availability_event
    interaction = 100.0 * mc_stats.mean(
        [
            values["A6"] - values["A3"] - (values["A9"] - values["A1"])
            for values in by_replication.values()
        ]
    )
    return {
        "a6_ai": ai["A6"],
        "a6_cut": backhaul["A6"],
        "a7_cut": backhaul["A7"],
        "interaction": interaction,
    }


def run_sobol(
    scenario: cm.Scenario, base_seed: int = DEFAULT_BASE_SEED
) -> list[dict[str, object]]:
    """Saltelli/Sobol first- and total-order indices for the four outputs."""
    parameters = len(SOBOL_RANGES)
    rng = np.random.default_rng([base_seed, 9001])
    matrix_a = rng.random((SOBOL_BASE, parameters))
    matrix_b = rng.random((SOBOL_BASE, parameters))

    def evaluate(matrix: np.ndarray) -> dict[str, np.ndarray]:
        out: dict[str, list[float]] = {name: [] for name in SOBOL_OUTPUTS}
        for row in matrix:
            values = _sobol_model(row, scenario, base_seed)
            for name in SOBOL_OUTPUTS:
                out[name].append(values[name])
        return {name: np.asarray(values) for name, values in out.items()}

    base_a = evaluate(matrix_a)
    base_b = evaluate(matrix_b)
    crossed: dict[str, list[np.ndarray]] = {name: [] for name in SOBOL_OUTPUTS}
    for index in range(parameters):
        matrix = matrix_a.copy()
        matrix[:, index] = matrix_b[:, index]
        crossed_values = evaluate(matrix)
        for name in SOBOL_OUTPUTS:
            crossed[name].append(crossed_values[name])

    rows: list[dict[str, object]] = []
    for name in SOBOL_OUTPUTS:
        a_values, b_values = base_a[name], base_b[name]
        variance = float(np.var(np.concatenate([a_values, b_values])))
        for index, (parameter, low, high) in enumerate(SOBOL_RANGES):
            crossed_values = crossed[name][index]
            if variance <= 1e-12:
                first_order = 0.0
                total_order = 0.0
            else:
                first_order = float(
                    np.mean(b_values * (crossed_values - a_values)) / variance
                )
                total_order = float(
                    np.mean((a_values - crossed_values) ** 2) / (2.0 * variance)
                )
            rows.append(
                {
                    "output": name,
                    "parameter": parameter,
                    "range_low": low,
                    "range_high": high,
                    "first_order": _round(first_order),
                    "total_order": _round(total_order),
                    "variance": _round(variance),
                    "base": SOBOL_BASE,
                    "replications_per_evaluation": SOBOL_REPLICATIONS,
                }
            )
    return rows


def run_two_factor(
    scenario: cm.Scenario,
    replications: int,
    base_seed: int = DEFAULT_BASE_SEED,
) -> list[dict[str, object]]:
    """Efficiency x tested-fallback-capacity grid for the H18 and H19 criteria."""
    efficiencies = [0.70, 0.80, 0.85, 0.90, 0.95]
    capacities = [0.20, 0.35, 0.50, 0.75, 1.00]
    rows: list[dict[str, object]] = []
    reps = list(range(replications))
    for efficiency in efficiencies:
        for capacity in capacities:
            params = replace(
                mc.MCParams(),
                one_way_efficiency=efficiency,
                fallback_tested_capacity_gbps=capacity,
            )
            ai = _mean_availability(("A5", "A6"), "ai", reps, scenario, params, base_seed)
            none = _mean_availability(("A5", "A6"), "none", reps, scenario, params, base_seed)
            backhaul = _mean_availability(
                ("A6", "A7"), "backhaul_cut", reps, scenario, params, base_seed
            )
            ai_link_results = mc.incident_runs(
                ["ai_link"],
                [cm.ARMS[name] for name in ("A1", "A3", "A6", "A9")],
                reps,
                scenario,
                params,
                base_seed,
            )
            by_replication: dict[int, dict[str, float]] = {}
            for result in ai_link_results:
                by_replication.setdefault(result.replication, {})[result.arm] = (
                    result.availability_event
                )
            interaction = 100.0 * mc_stats.mean(
                [
                    values["A6"] - values["A3"] - (values["A9"] - values["A1"])
                    for values in by_replication.values()
                ]
            )
            rows.append(
                {
                    "one_way_efficiency": efficiency,
                    "fallback_capacity_gbps": capacity,
                    "a6_ai_pct": _round(ai["A6"]),
                    "normal_cost_pct": _round(none["A5"] - none["A6"]),
                    "fallback_gap_pct": _round(backhaul["A6"] - backhaul["A7"]),
                    "interaction_pct": _round(interaction),
                    "h18_normal_cost_pass": int(none["A5"] - none["A6"] <= 15.0),
                    "h19_interaction_pass": int(interaction >= 20.0),
                    "replications": replications,
                }
            )
    return rows


# --- Entry point -----------------------------------------------------------------------


def run_incident_and_campaign(args: argparse.Namespace) -> int:
    scenario = cm.build_backhaul_scenario()
    replications = list(range(args.base_seed, args.base_seed + args.replications))
    arms = [cm.ARMS[name] for name in args.arms]
    events = list(args.events)

    results = mc.incident_runs(events, arms, replications, scenario, base_seed=args.base_seed)
    data = ExperimentData(results)
    arm_names = [arm.name for arm in arms]
    summaries = summary_rows(data, events, arm_names)
    index = data.fields["availability_event"]

    criterion_rows = [
        evaluate_criterion(criterion, criterion_values(index, criterion))
        for criterion in CRITERIA
    ]
    hypotheses = hypothesis_rows(criterion_rows)

    seeds = list(range(2026, 2026 + 30))
    reference = reference_index(scenario, seeds)
    comparison = reference_rows(reference, index)

    campaigns = mc.campaign_runs(
        arms,
        list(range(args.base_seed, args.base_seed + args.campaign_replications)),
        scenario,
        base_seed=args.base_seed,
    )
    campaign_summary = campaign_rows(campaigns, arm_names)

    args.raw_dir.mkdir(parents=True, exist_ok=True)
    args.table_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.raw_dir / "common_mode_mc_per_replication.csv", per_replication_rows(results))
    write_csv(args.raw_dir / "common_mode_mc_summary.csv", summaries)
    write_csv(args.raw_dir / "common_mode_mc_verdicts.csv", criterion_rows)
    write_csv(args.raw_dir / "common_mode_mc_campaign.csv", campaign_summary)
    write_csv(args.raw_dir / "common_mode_mc_comparison.csv", comparison)

    write_csv(args.table_dir / "common-mode-mc-summary.csv", summaries)
    write_csv(args.table_dir / "common-mode-mc-verdicts.csv", criterion_rows + hypotheses)
    write_csv(args.table_dir / "common-mode-mc-campaign.csv", campaign_summary)
    write_csv(args.table_dir / "common-mode-mc-comparison.csv", comparison)
    differences, _ = difference_rows(index)
    write_csv(args.table_dir / "common-mode-mc-differences.csv", differences)

    print(
        f"E1: {len(results)} arm-runs "
        f"({len(events)} events x {len(arms)} arms x {len(replications)} replications)"
    )
    print(f"E2: {len(campaigns)} arm-campaigns ({args.campaign_replications} campaigns)")
    print("\nAvailability during the event (%, mean over replications)")
    header = "event".ljust(16) + "".join(arm.rjust(8) for arm in args.arms)
    print(header)
    for event in events:
        row = event.ljust(16)
        for arm in args.arms:
            row += f"{mc_stats.mean(data.series('availability_event', event, arm)):8.2f}"
        print(row)
    print("\nCriteria (95 % interval rule)")
    for row in criterion_rows:
        print(
            "  {key:5s} {value:8.2f} [{low:8.2f}, {high:8.2f}] "
            "p={p:.4f} {verdict:12s} {bonferroni}".format(
                key=row["key"],
                value=float(row["value_pct"]),
                low=float(row["ci95_low_pct"]),
                high=float(row["ci95_high_pct"]),
                p=float(row["p_value"]),
                verdict=row["verdict"],
                bonferroni=row["verdict_bonferroni"],
            )
        )
    for row in hypotheses:
        print(f"  {row['key']}: {row['verdict']} (Bonferroni: {row['verdict_bonferroni']})")
    print("\nCampaign (30 d)")
    for row in campaign_summary:
        print(
            "  {arm}: ss={ss:.2f}% policy={pol:.2f} congestion={con:.2f} "
            "dependency={dep:.2f} shared_attrib={att:.2f} breach_days={br:.2f}".format(
                arm=row["arm"],
                ss=float(row["availability_ss_mean_pct"]),
                pol=float(row["policy_loss_pct"]),
                con=float(row["congestion_loss_pct"]),
                dep=float(row["dependency_loss_pct"]),
                att=float(row["shared_attrib"]),
                br=float(row["slo_breach_days"]),
            )
        )
    print(f"\nWrote raw CSVs to {args.raw_dir}")
    print(f"Wrote paper tables to {args.table_dir}")
    return 0


def run_sensitivity_experiment(args: argparse.Namespace) -> int:
    scenario = cm.build_backhaul_scenario()
    replications = list(
        range(args.base_seed, args.base_seed + args.sensitivity_replications)
    )
    grid_rows, break_rows = run_sensitivity(
        replications, scenario, args.sensitivity_points, args.base_seed
    )
    write_csv(args.raw_dir / "common_mode_mc_sensitivity.csv", grid_rows)
    write_csv(args.raw_dir / "common_mode_mc_break_even.csv", break_rows)
    write_csv(args.table_dir / "common-mode-mc-sensitivity.csv", grid_rows)
    write_csv(args.table_dir / "common-mode-mc-break-even.csv", break_rows)
    markdown = sensitivity_markdown(break_rows, args.sensitivity_points, len(replications))
    (args.table_dir / "common-mode-mc-break-even.md").write_text(markdown, encoding="utf-8")
    print(
        f"E3: {len(grid_rows)} grid rows, {len(break_rows)} break-even rows, "
        f"{args.sensitivity_points} points, {len(replications)} replications per point"
    )
    for row in break_rows:
        if row["criterion"] in ("H18_normal_cost", "H19_interaction", "fallback_gap"):
            shown = (
                "none in range"
                if row["break_even_value"] == ""
                else f"{float(row['break_even_value']):g}"
            )
            print(f"  {row['parameter']:32s} {row['criterion']:20s} {shown}")
    print(f"Wrote sensitivity artifacts to {args.table_dir}")
    return 0


def run_sobol_experiment(args: argparse.Namespace) -> int:
    scenario = cm.build_backhaul_scenario()
    rows = run_sobol(scenario, args.base_seed)
    write_csv(args.raw_dir / "common_mode_mc_sobol.csv", rows)
    write_csv(args.table_dir / "common-mode-mc-sobol.csv", rows)
    print(f"E4: {len(rows)} Sobol rows (base {SOBOL_BASE})")
    for row in rows:
        print(
            "  {output:12s} {parameter:32s} S1={s1:+.3f} ST={st:+.3f}".format(
                output=row["output"],
                parameter=row["parameter"],
                s1=float(row["first_order"]),
                st=float(row["total_order"]),
            )
        )
    print(f"Wrote Sobol table to {args.table_dir}")
    return 0


def run_two_factor_experiment(args: argparse.Namespace) -> int:
    scenario = cm.build_backhaul_scenario()
    rows = run_two_factor(scenario, args.two_factor_replications, args.base_seed)
    write_csv(args.raw_dir / "common_mode_mc_two_factor.csv", rows)
    write_csv(args.table_dir / "common-mode-mc-two-factor.csv", rows)
    print(f"E5: {len(rows)} two-factor cells")
    print(f"Wrote two-factor table to {args.table_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replications", type=int, default=DEFAULT_REPLICATIONS)
    parser.add_argument(
        "--campaign-replications", type=int, default=DEFAULT_CAMPAIGN_REPLICATIONS
    )
    parser.add_argument("--base-seed", type=int, default=DEFAULT_BASE_SEED)
    parser.add_argument("--events", nargs="+", default=list(cm.EVENT_KINDS))
    parser.add_argument("--arms", nargs="+", default=list(cm.ARMS))
    parser.add_argument("--sensitivity", action="store_true", help="run E3")
    parser.add_argument("--sensitivity-points", type=int, default=25)
    parser.add_argument("--sensitivity-replications", type=int, default=500)
    parser.add_argument("--sobol", action="store_true", help="run E4")
    parser.add_argument("--two-factor", action="store_true", help="run the E4 grid")
    parser.add_argument("--two-factor-replications", type=int, default=500)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--table-dir", type=Path, default=TABLE_DIR)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="smoke run: 40 replications, 5 campaign replications, 5 sweep points",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.quick:
        args.replications = min(args.replications, 40)
        args.campaign_replications = min(args.campaign_replications, 5)
        args.sensitivity_points = min(args.sensitivity_points, 5)
        args.sensitivity_replications = min(args.sensitivity_replications, 20)
        args.two_factor_replications = min(args.two_factor_replications, 20)
        if args.raw_dir == RAW_DIR:
            args.raw_dir = REPO / "output" / "common-mode-mc-smoke"
        if args.table_dir == TABLE_DIR:
            args.table_dir = REPO / "output" / "common-mode-mc-smoke"
    if args.replications < 1 or args.campaign_replications < 1:
        parser.error("replication counts must be positive")
    unknown = [event for event in args.events if event not in cm.EVENT_KINDS]
    if unknown:
        parser.error(f"unknown events: {unknown}")
    unknown_arms = [arm for arm in args.arms if arm not in cm.ARMS]
    if unknown_arms:
        parser.error(f"unknown arms: {unknown_arms}")

    if args.sensitivity:
        return run_sensitivity_experiment(args)
    if args.sobol:
        return run_sobol_experiment(args)
    if args.two_factor:
        return run_two_factor_experiment(args)
    return run_incident_and_campaign(args)


if __name__ == "__main__":
    raise SystemExit(main())
