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

"""Analysis for the postmortem study (E1-E8).

The protocol is frozen in ``docs/postmortem-study-predictions.md``.  This
script implements the verdict rules of section 6, the reliability and size
gates of section 5, the with/without-known comparison, the ``unclear`` counts
and the Brier score of section 8.

It is deliberately a *scaffold*: it is tested on synthetic coded data before
any real coding is read.  The agent does not code real postmortems; that is the
human M8 step.

Inputs (all CSV, UTF-8):

* ``study/frame.csv`` — incident_id, provider, report_url, report_sha256,
  publication_date, eligible, duplicate_of, notes
* ``study/coded_c1.csv`` — coder C1, template columns
* ``study/coded_c2.csv`` — coder C2, template columns
* ``study/coded_final.csv`` — C3 final codes, template columns

If ``--reports-dir`` is supplied, every frame row's ``report_sha256`` is checked
against the saved report text; a mismatch is a frame-gate failure.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]

VARIABLES = (
    "V1_trigger",
    "V1b_secondary_trigger",
    "V2_failed_plane",
    "V3_shared_dependency",
    "V4_blast_radius",
    "V5_independence_breach",
    "V6_fallback_outcome",
    "V7_central_controller",
    "V8a_tenant_isolation_retained",
    "V8b_multipath_or_multiprovider_retained",
    "V8c_tested_local_fallback_retained",
    "V9_duration_minutes",
    "V10_known_before_freeze",
)

PREDICTION_VARIABLES = {
    "E1": ("V3_shared_dependency", "V2_failed_plane", "V4_blast_radius"),
    "E2": ("V1_trigger",),
    "E3": ("V4_blast_radius", "V8a_tenant_isolation_retained"),
    "E4": ("V1_trigger", "V2_failed_plane", "V8b_multipath_or_multiprovider_retained"),
    "E5": ("V6_fallback_outcome",),
    "E6": ("V4_blast_radius", "V7_central_controller"),
    "E7": ("V4_blast_radius", "V5_independence_breach"),
    "E8": ("V1_trigger", "V2_failed_plane"),
}

CREDENCES = {
    "E1": 0.80,
    "E2": 0.70,
    "E3": 0.80,
    "E4": 0.70,
    "E5": 0.55,
    "E6": 0.60,
    "E7": 0.60,
    "E8": 0.65,
}

BIG = {"multi_region", "global"}
CHANGE = {"config_change", "software_release", "capacity_or_network_upgrade"}
CONTROL_PLANES = {
    "control_plane",
    "identity_auth",
    "dns_naming",
    "config_distribution_orchestration",
}
V4_ORDER = {"single_zone": 1, "single_region": 2, "multi_region": 3, "global": 4}
Z95 = 1.959963984540054


# --- Statistics ------------------------------------------------------------------------


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for one proportion, returned as fractions."""
    if n <= 0:
        raise ValueError("n must be positive")
    p = successes / n
    denominator = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denominator
    half = (
        z
        * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
        / denominator
    )
    return max(0.0, centre - half), min(1.0, centre + half)


def newcombe(
    successes_a: int,
    n_a: int,
    successes_b: int,
    n_b: int,
    z: float = Z95,
) -> tuple[float, float]:
    """Newcombe method 10 interval for p_a - p_b."""
    p_a = successes_a / n_a
    p_b = successes_b / n_b
    l_a, u_a = wilson(successes_a, n_a, z)
    l_b, u_b = wilson(successes_b, n_b, z)
    difference = p_a - p_b
    lower = difference - math.sqrt((p_a - l_a) ** 2 + (u_b - p_b) ** 2)
    upper = difference + math.sqrt((u_a - p_a) ** 2 + (p_b - l_b) ** 2)
    return max(-1.0, lower), min(1.0, upper)


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def mann_whitney_one_sided(
    wider: Sequence[float], narrower: Sequence[float]
) -> tuple[float, float]:
    """One-sided Mann-Whitney U for ``wider`` stochastically above ``narrower``.

    Returns (U for the wider group, normal-approximation p-value with tie
    correction).  The size gate keeps both groups at 30 or more, so the normal
    approximation is adequate; the synthetic tests also check the direction.
    """
    n1, n2 = len(wider), len(narrower)
    if n1 == 0 or n2 == 0:
        raise ValueError("both groups need at least one observation")
    combined = [(value, 1) for value in wider] + [(value, 0) for value in narrower]
    combined.sort(key=lambda item: item[0])
    ranks: dict[int, float] = {}
    index = 0
    while index < len(combined):
        end = index + 1
        while end < len(combined) and combined[end][0] == combined[index][0]:
            end += 1
        average_rank = (index + 1 + end) / 2.0
        for position in range(index, end):
            ranks[position] = average_rank
        index = end
    rank_sum_wider = sum(
        ranks[position]
        for position, (_, group) in enumerate(combined)
        if group == 1
    )
    u_wider = rank_sum_wider - n1 * (n1 + 1) / 2.0
    mean_u = n1 * n2 / 2.0
    # Tie correction: Var(U) = n1*n2/12 * ((N+1) - sum(t^3 - t)/(N*(N-1))).
    tie_counts: dict[float, int] = {}
    for value, _ in combined:
        tie_counts[value] = tie_counts.get(value, 0) + 1
    n_total = n1 + n2
    tie_term = sum(t ** 3 - t for t in tie_counts.values())
    if n_total > 1:
        variance = (n1 * n2 / 12.0) * (
            (n_total + 1) - tie_term / (n_total * (n_total - 1))
        )
    else:
        variance = 0.0
    if variance <= 0:
        return u_wider, 0.5
    z_value = (u_wider - mean_u) / math.sqrt(variance)
    return u_wider, 1.0 - _normal_cdf(z_value)


def cohen_kappa(first: Sequence[str], second: Sequence[str]) -> float:
    """Unweighted Cohen's kappa for two equal-length label sequences."""
    if len(first) != len(second):
        raise ValueError("label sequences must have the same length")
    if not first:
        raise ValueError("no labels")
    categories = sorted(set(first) | set(second))
    counts = {category: [0, 0] for category in categories}
    for left, right in zip(first, second):
        counts[left][0] += 1
        counts[right][1] += 1
    n = len(first)
    observed = sum(1 for left, right in zip(first, second) if left == right) / n
    expected = sum((counts[category][0] / n) * (counts[category][1] / n) for category in categories)
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


# --- Data loading ----------------------------------------------------------------------


@dataclass
class FrameRow:
    incident_id: str
    provider: str
    report_url: str
    report_sha256: str
    publication_date: str
    eligible: str = "yes"
    duplicate_of: str = ""
    notes: str = ""


@dataclass
class CodeRow:
    incident_id: str
    values: dict[str, str]
    coder: str = ""


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_frame(path: Path) -> list[FrameRow]:
    rows = []
    for row in _read_csv(path):
        rows.append(
            FrameRow(
                incident_id=row.get("incident_id", "").strip(),
                provider=row.get("provider", "").strip(),
                report_url=row.get("report_url", "").strip(),
                report_sha256=row.get("report_sha256", "").strip(),
                publication_date=row.get("publication_date", "").strip(),
                eligible=(row.get("eligible", "yes") or "yes").strip().lower(),
                duplicate_of=row.get("duplicate_of", "").strip(),
                notes=row.get("notes", "").strip(),
            )
        )
    if len({row.incident_id for row in rows}) != len(rows):
        raise ValueError("frame has duplicate incident_id values")
    return rows


def load_codes(path: Path) -> dict[str, CodeRow]:
    codes: dict[str, CodeRow] = {}
    for row in _read_csv(path):
        incident_id = row.get("incident_id", "").strip()
        if not incident_id:
            continue
        values = {variable: (row.get(variable, "") or "").strip() for variable in VARIABLES}
        codes[incident_id] = CodeRow(
            incident_id=incident_id, values=values, coder=row.get("coder", "").strip()
        )
    return codes


def verify_frame_hashes(frame: Sequence[FrameRow], reports_dir: Path) -> list[str]:
    problems = []
    for row in frame:
        path = reports_dir / f"{row.incident_id}.txt"
        if not path.exists():
            problems.append(f"{row.incident_id}: saved report missing ({path})")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if row.report_sha256 and digest != row.report_sha256:
            problems.append(
                f"{row.incident_id}: report hash {digest[:12]} != frame {row.report_sha256[:12]}"
            )
    return problems


# --- Verdicts --------------------------------------------------------------------------


@dataclass
class Verdict:
    id: str
    claim: str
    n: int
    value: float | None
    low: float | None
    high: float | None
    verdict: str
    reason: str
    details: dict[str, object] = field(default_factory=dict)


def _size_ok(n: int) -> bool:
    return n >= 30


def _invalid_for(
    prediction: str,
    kappa: dict[str, float | None],
) -> list[str]:
    return [
        variable
        for variable in PREDICTION_VARIABLES[prediction]
        if kappa.get(variable) is None or kappa[variable] < 0.60
    ]


def _verdict_from_wilson(
    prediction: str,
    claim: str,
    successes: int,
    n: int,
    threshold: float,
    direction: str,
    kappa: dict[str, float | None],
) -> Verdict:
    invalid = _invalid_for(prediction, kappa)
    if invalid:
        return Verdict(
            prediction,
            claim,
            n,
            successes / n if n else None,
            None,
            None,
            "INVALID",
            f"kappa unavailable or below 0.60: {', '.join(invalid)}",
            {"successes": successes, "invalid_variables": invalid},
        )
    if not _size_ok(n):
        return Verdict(
            prediction,
            claim,
            n,
            successes / n if n else None,
            None,
            None,
            "INCONCLUSIVE",
            f"size gate: n={n} < 30",
            {"successes": successes},
        )
    low, high = wilson(successes, n)
    value = successes / n
    if direction == "ge":
        verdict = "CONFIRMED" if low >= threshold else "REFUTED" if high < threshold else "INCONCLUSIVE"
    else:
        verdict = "CONFIRMED" if high <= threshold else "REFUTED" if low > threshold else "INCONCLUSIVE"
    return Verdict(
        prediction,
        claim,
        n,
        value,
        low,
        high,
        verdict,
        f"Wilson [{low:.4f}, {high:.4f}] vs threshold {threshold:g}",
        {"successes": successes, "threshold": threshold, "direction": direction},
    )


def _subset(
    rows: Sequence[CodeRow],
    predicate,
) -> list[CodeRow]:
    return [row for row in rows if predicate(row.values)]


def _value(row: CodeRow, variable: str) -> str:
    return row.values.get(variable, "").strip().lower()


def _is_unclear(value: str) -> bool:
    return value in {"", "unclear"}


def analyse_set(rows: Sequence[CodeRow], kappa: dict[str, float | None]) -> list[Verdict]:
    """Compute E1-E8 for one coded set (full, or without known-before-freeze)."""
    verdicts: list[Verdict] = []

    big = _subset(rows, lambda values: _value_from(values, "V4_blast_radius") in BIG)
    e1_success = sum(
        1
        for row in big
        if _value(row, "V3_shared_dependency") == "shared_global"
        or _value(row, "V2_failed_plane") in CONTROL_PLANES
    )
    verdicts.append(
        _verdict_from_wilson(
            "E1",
            "control-plane concentration in multi-region/global incidents",
            e1_success,
            len(big),
            0.50,
            "ge",
            kappa,
        )
    )

    e2_success = sum(1 for row in rows if _value(row, "V1_trigger") in CHANGE)
    verdicts.append(
        _verdict_from_wilson(
            "E2",
            "change-induced triggers",
            e2_success,
            len(rows),
            0.30,
            "ge",
            kappa,
        )
    )

    e3_rows = [
        row for row in big if _value(row, "V8a_tenant_isolation_retained") != "unclear"
    ]
    e3_success = sum(
        1 for row in e3_rows if _value(row, "V8a_tenant_isolation_retained") == "yes"
    )
    verdicts.append(
        _verdict_from_wilson(
            "E3",
            "tenant isolation rarely preserves service in big incidents",
            e3_success,
            len(e3_rows),
            0.20,
            "le",
            kappa,
        )
    )

    path_group = [
        row
        for row in rows
        if _value(row, "V1_trigger") == "hardware_or_physical"
        or _value(row, "V2_failed_plane") == "network_backbone_physical"
    ]
    control_group = [
        row for row in rows if _value(row, "V2_failed_plane") in CONTROL_PLANES
    ]
    path_yes = [
        row
        for row in path_group
        if _value(row, "V8b_multipath_or_multiprovider_retained") != "unclear"
    ]
    control_yes = [
        row
        for row in control_group
        if _value(row, "V8b_multipath_or_multiprovider_retained") != "unclear"
    ]
    path_success = sum(
        1 for row in path_yes if _value(row, "V8b_multipath_or_multiprovider_retained") == "yes"
    )
    control_success = sum(
        1
        for row in control_yes
        if _value(row, "V8b_multipath_or_multiprovider_retained") == "yes"
    )
    invalid = _invalid_for("E4", kappa)
    if invalid:
        verdicts.append(
            Verdict(
                "E4",
                "independence helps path/physical failures more than control-plane failures",
                len(path_yes) + len(control_yes),
                None,
                None,
                None,
                "INVALID",
                f"kappa unavailable or below 0.60: {', '.join(invalid)}",
                {"path_n": len(path_yes), "control_n": len(control_yes)},
            )
        )
    elif not (_size_ok(len(path_yes)) and _size_ok(len(control_yes))):
        verdicts.append(
            Verdict(
                "E4",
                "independence helps path/physical failures more than control-plane failures",
                len(path_yes) + len(control_yes),
                None,
                None,
                None,
                "INCONCLUSIVE",
                f"size gate: path n={len(path_yes)}, control n={len(control_yes)}",
                {"path_n": len(path_yes), "control_n": len(control_yes)},
            )
        )
    else:
        point = path_success / len(path_yes) - control_success / len(control_yes)
        low, high = newcombe(
            path_success, len(path_yes), control_success, len(control_yes)
        )
        if point >= 0.25 and low >= 0.10:
            verdict = "CONFIRMED"
        elif high < 0.25:
            verdict = "REFUTED"
        else:
            verdict = "INCONCLUSIVE"
        verdicts.append(
            Verdict(
                "E4",
                "independence helps path/physical failures more than control-plane failures",
                len(path_yes) + len(control_yes),
                point,
                low,
                high,
                verdict,
                f"Newcombe [{low:.4f}, {high:.4f}] for difference; point {point:.4f}",
                {
                    "path_success": path_success,
                    "path_n": len(path_yes),
                    "control_success": control_success,
                    "control_n": len(control_yes),
                },
            )
        )

    e5_rows = [
        row for row in rows if _value(row, "V6_fallback_outcome") != "none_mentioned"
    ]
    e5_success = sum(
        1
        for row in e5_rows
        if _value(row, "V6_fallback_outcome")
        in {"failed_or_not_triggered", "slow_or_manual"}
    )
    verdicts.append(
        _verdict_from_wilson(
            "E5",
            "fallback is the weak link",
            e5_success,
            len(e5_rows),
            0.20,
            "ge",
            kappa,
        )
    )

    invalid = _invalid_for("E6", kappa)
    yes = [
        V4_ORDER[_value(row, "V4_blast_radius")]
        for row in rows
        if _value(row, "V7_central_controller") == "yes"
        and _value(row, "V4_blast_radius") in V4_ORDER
    ]
    no = [
        V4_ORDER[_value(row, "V4_blast_radius")]
        for row in rows
        if _value(row, "V7_central_controller") == "no"
        and _value(row, "V4_blast_radius") in V4_ORDER
    ]
    if invalid:
        verdicts.append(
            Verdict(
                "E6",
                "controllers widen blast radius",
                len(yes) + len(no),
                None,
                None,
                None,
                "INVALID",
                f"kappa unavailable or below 0.60: {', '.join(invalid)}",
                {"yes_n": len(yes), "no_n": len(no)},
            )
        )
    elif not (_size_ok(len(yes)) and _size_ok(len(no))):
        verdicts.append(
            Verdict(
                "E6",
                "controllers widen blast radius",
                len(yes) + len(no),
                None,
                None,
                None,
                "INCONCLUSIVE",
                f"size gate: yes n={len(yes)}, no n={len(no)}",
                {"yes_n": len(yes), "no_n": len(no)},
            )
        )
    else:
        u_value, p_value = mann_whitney_one_sided(yes, no)
        yes_median = statistics.median(yes)
        no_median = statistics.median(no)
        if p_value < 0.05 and yes_median > no_median:
            verdict = "CONFIRMED"
        elif yes_median <= no_median or p_value > 0.50:
            verdict = "REFUTED"
        else:
            verdict = "INCONCLUSIVE"
        verdicts.append(
            Verdict(
                "E6",
                "controllers widen blast radius",
                len(yes) + len(no),
                yes_median - no_median,
                None,
                None,
                verdict,
                f"one-sided Mann-Whitney p={p_value:.4f}; medians {yes_median:g} vs {no_median:g}",
                {"u": u_value, "p": p_value, "yes_n": len(yes), "no_n": len(no)},
            )
        )

    e7_rows = [
        row for row in big if _value(row, "V5_independence_breach") != "unclear"
    ]
    e7_success = sum(
        1 for row in e7_rows if _value(row, "V5_independence_breach") == "yes"
    )
    verdicts.append(
        _verdict_from_wilson(
            "E7",
            "redundancy fails together in big incidents",
            e7_success,
            len(e7_rows),
            0.40,
            "ge",
            kappa,
        )
    )

    e8_rows = [
        row
        for row in rows
        if _value(row, "V1_trigger") not in {"", "unclear", "other"}
        and _value(row, "V2_failed_plane") not in {"", "unclear", "other"}
    ]
    verdicts.append(
        _verdict_from_wilson(
            "E8",
            "the classes cover the data",
            len(e8_rows),
            len(rows),
            0.80,
            "ge",
            kappa,
        )
    )
    return verdicts


def _value_from(values: dict[str, str], variable: str) -> str:
    return (values.get(variable, "") or "").strip().lower()


# --- Reliability and reporting ---------------------------------------------------------


def kappa_table(
    c1: dict[str, CodeRow], c2: dict[str, CodeRow]
) -> tuple[dict[str, float | None], list[dict[str, object]]]:
    shared = sorted(set(c1) & set(c2))
    kappas: dict[str, float | None] = {}
    rows: list[dict[str, object]] = []
    for variable in VARIABLES:
        first = [c1[incident].values.get(variable, "") for incident in shared]
        second = [c2[incident].values.get(variable, "") for incident in shared]
        try:
            value = cohen_kappa(first, second)
        except ValueError:
            value = None
        kappas[variable] = value
        rows.append(
            {
                "variable": variable,
                "n": len(shared),
                "kappa": "" if value is None else round(value, 6),
                "reliable": bool(value is not None and value >= 0.60),
                "distinct_c1": len(set(first)),
                "distinct_c2": len(set(second)),
            }
        )
    return kappas, rows


def unclear_counts(rows: Sequence[CodeRow]) -> list[dict[str, object]]:
    output = []
    for variable in VARIABLES:
        counts: dict[str, int] = {}
        for row in rows:
            value = row.values.get(variable, "") or "missing"
            counts[value] = counts.get(value, 0) + 1
        output.append(
            {
                "variable": variable,
                "n": len(rows),
                "unclear": counts.get("unclear", 0) + counts.get("", 0),
                "missing": counts.get("missing", 0),
                "values": json.dumps(counts, sort_keys=True),
            }
        )
    return output


def brier_score(verdicts: Sequence[Verdict]) -> dict[str, object]:
    scored = []
    for verdict in verdicts:
        if verdict.verdict not in {"CONFIRMED", "REFUTED"}:
            continue
        outcome = 1.0 if verdict.verdict == "CONFIRMED" else 0.0
        credence = CREDENCES[verdict.id]
        scored.append((verdict.id, credence, outcome, (credence - outcome) ** 2))
    if not scored:
        return {"n": 0, "brier": None, "terms": []}
    return {
        "n": len(scored),
        "brier": sum(term[3] for term in scored) / len(scored),
        "terms": [
            {"id": name, "credence": credence, "outcome": outcome, "brier": term}
            for name, credence, outcome, term in scored
        ],
    }


def _verdict_rows(verdicts: Sequence[Verdict], scope: str) -> list[dict[str, object]]:
    return [
        {
            "scope": scope,
            "id": verdict.id,
            "claim": verdict.claim,
            "n": verdict.n,
            "value": "" if verdict.value is None else round(verdict.value, 6),
            "low": "" if verdict.low is None else round(verdict.low, 6),
            "high": "" if verdict.high is None else round(verdict.high, 6),
            "verdict": verdict.verdict,
            "reason": verdict.reason,
            "details": json.dumps(verdict.details, sort_keys=True),
        }
        for verdict in verdicts
    ]


def run_analysis(
    frame: Sequence[FrameRow],
    c1: dict[str, CodeRow],
    c2: dict[str, CodeRow],
    final: dict[str, CodeRow],
    frame_hash_problems: Sequence[str] | None = None,
) -> dict[str, object]:
    eligible = [
        row
        for row in frame
        if row.eligible == "yes" and not row.duplicate_of
    ]
    duplicates = [row.incident_id for row in frame if row.duplicate_of]
    ids = [row.incident_id for row in eligible]
    missing_final = [incident for incident in ids if incident not in final]
    missing_c1 = [incident for incident in ids if incident not in c1]
    missing_c2 = [incident for incident in ids if incident not in c2]
    final_rows = [final[incident] for incident in ids if incident in final]
    kappas, kappa_rows = kappa_table(c1, c2)
    full_verdicts = analyse_set(final_rows, kappas)
    without_known_rows = [
        row
        for row in final_rows
        if _value(row, "V10_known_before_freeze") != "yes"
    ]
    without_known_verdicts = analyse_set(without_known_rows, kappas)
    return {
        "frame": {
            "n_frame": len(frame),
            "n_eligible": len(eligible),
            "n_duplicates": len(duplicates),
            "duplicate_ids": duplicates,
            "missing_final": missing_final,
            "missing_c1": missing_c1,
            "missing_c2": missing_c2,
            "frame_hash_problems": list(frame_hash_problems or []),
        },
        "kappa": kappa_rows,
        "verdicts_full": _verdict_rows(full_verdicts, "full"),
        "verdicts_without_known": _verdict_rows(
            without_known_verdicts, "without_known_before_freeze"
        ),
        "unclear": unclear_counts(final_rows),
        "brier_full": brier_score(full_verdicts),
        "brier_without_known": brier_score(without_known_verdicts),
        "n_full": len(final_rows),
        "n_without_known": len(without_known_rows),
    }


def render_markdown(result: dict[str, object]) -> str:
    frame = result["frame"]
    lines = [
        "# Postmortem study analysis (E1-E8)",
        "",
        "Generated by `tools/analyze_postmortems.py`. This is a machine report; "
        "the interpretation belongs in the results document.",
        "",
        "## Inputs",
        "",
        f"- Frame rows: {frame['n_frame']}",
        f"- Eligible, non-duplicate incidents: {frame['n_eligible']}",
        f"- Merged duplicates: {frame['n_duplicates']} ({', '.join(frame['duplicate_ids']) or 'none'})",
        f"- Coded rows in final set: {result['n_full']}",
        f"- Without known-before-freeze: {result['n_without_known']}",
        "",
    ]
    if frame["frame_hash_problems"]:
        lines += ["**Frame gate failures:**", ""]
        lines += [f"- {problem}" for problem in frame["frame_hash_problems"]]
        lines.append("")
    lines += [
        "## Reliability gate (Cohen's kappa)",
        "",
        "| Variable | n | kappa | reliable (>= 0.60) |",
        "|---|---:|---:|---|",
    ]
    for row in result["kappa"]:
        lines.append(
            "| {variable} | {n} | {kappa} | {reliable} |".format(
                variable=row["variable"],
                n=row["n"],
                kappa=row["kappa"] if row["kappa"] != "" else "n/a",
                reliable="yes" if row["reliable"] else "NO",
            )
        )
    lines += ["", "## Verdicts (full set)", "", "| ID | n | value | 95% interval | verdict | reason |", "|---|---:|---:|---|---|---|"]
    for row in result["verdicts_full"]:
        interval = (
            f"[{row['low']}, {row['high']}]"
            if row["low"] != "" and row["high"] != ""
            else ""
        )
        lines.append(
            "| {id} | {n} | {value} | {interval} | {verdict} | {reason} |".format(
                id=row["id"],
                n=row["n"],
                value=row["value"] if row["value"] != "" else "",
                interval=interval,
                verdict=row["verdict"],
                reason=row["reason"],
            )
        )
    lines += ["", "## Verdicts (without known-before-freeze)", "", "| ID | n | value | 95% interval | verdict | reason |", "|---|---:|---:|---|---|---|"]
    for row in result["verdicts_without_known"]:
        interval = (
            f"[{row['low']}, {row['high']}]"
            if row["low"] != "" and row["high"] != ""
            else ""
        )
        lines.append(
            "| {id} | {n} | {value} | {interval} | {verdict} | {reason} |".format(
                id=row["id"],
                n=row["n"],
                value=row["value"] if row["value"] != "" else "",
                interval=interval,
                verdict=row["verdict"],
                reason=row["reason"],
            )
        )
    lines += [
        "",
        "## Unclear counts",
        "",
        "| Variable | n | unclear | missing | distribution |",
        "|---|---:|---:|---:|---|",
    ]
    for row in result["unclear"]:
        lines.append(
            f"| {row['variable']} | {row['n']} | {row['unclear']} | {row['missing']} | `{row['values']}` |"
        )
    lines += ["", "## Brier score", ""]
    for label, key in (("full", "brier_full"), ("without known", "brier_without_known")):
        brier = result[key]
        lines.append(
            f"- {label}: n={brier['n']}, Brier={brier['brier'] if brier['brier'] is not None else 'n/a'}"
        )
    lines.append("")
    return "\n".join(lines)


def write_outputs(result: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "analysis.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output_dir / "analysis.md").write_text(render_markdown(result), encoding="utf-8")
    for name, rows in (
        ("kappa.csv", result["kappa"]),
        (
            "verdicts.csv",
            list(result["verdicts_full"]) + list(result["verdicts_without_known"]),
        ),
        ("unclear.csv", result["unclear"]),
    ):
        if not rows:
            continue
        with (output_dir / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, default=ROOT / "study" / "frame.csv")
    parser.add_argument("--c1", type=Path, default=ROOT / "study" / "coded_c1.csv")
    parser.add_argument("--c2", type=Path, default=ROOT / "study" / "coded_c2.csv")
    parser.add_argument("--final", type=Path, default=ROOT / "study" / "coded_final.csv")
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "study" / "analysis")
    args = parser.parse_args(list(argv) if argv is not None else None)

    for label, path in (("frame", args.frame), ("C1", args.c1), ("C2", args.c2), ("final", args.final)):
        if not path.exists():
            print(f"missing {label}: {path}")
            return 2
    frame = load_frame(args.frame)
    c1 = load_codes(args.c1)
    c2 = load_codes(args.c2)
    final = load_codes(args.final)
    hash_problems = (
        verify_frame_hashes(frame, args.reports_dir) if args.reports_dir else []
    )
    if hash_problems:
        print("FRAME GATE FAILED: the frame hashes do not match the saved reports.")
        for problem in hash_problems:
            print(f"  {problem}")
        print("No verdict is computed until the frame gate passes.")
        return 3
    result = run_analysis(frame, c1, c2, final, hash_problems)
    write_outputs(result, args.output_dir)
    print(render_markdown(result))
    print(f"Wrote {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
