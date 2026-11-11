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


"""Turn round-2 observation rows into dispositions and a Brier score.

Rules are transcribed from the frozen predictions file; none is tuned after the
fact.  CONFIRMED, REFUTED, INCONCLUSIVE (cause gate), INVALID (mutation or depth
gate, control failure, setup error), NOT RUN (facility missing).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from .predictions import (
    CREDENCE,
    P13_CASES,
    P14_CASES,
    P15_EXPECTED_DELIVERY,
    P15_TOLERANCE_POINTS,
    P15_TOTALS,
    P16_CASES,
)

Row = Mapping[str, object]
CONFIRMED, REFUTED, INCONCLUSIVE, INVALID, NOT_RUN = "CONFIRMED", "REFUTED", "INCONCLUSIVE", "INVALID", "NOT RUN"

P15_CREDENCE_KEYS = {"P15a": 0.80, "P15b": 0.75}


def _table(rows: Iterable[Row]) -> dict[str, dict[str, list[float]]]:
    table: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        table[str(row["policy"])][str(row["metric"])].append(float(row["value"]))
    return table


def _verdict(prediction: str, case: str, status: str, detail: str) -> dict[str, str]:
    return {"prediction": prediction, "case": case, "verdict": status, "detail": detail}


def _all(values: list[float], predicate) -> bool:
    return bool(values) and all(predicate(v) for v in values)


def _all_one(values: list[float]) -> bool:
    return _all(values, lambda v: v == 1)


def _all_at(values: list[float], target: float) -> bool:
    return _all(values, lambda v: v == target)


# --- P13 -------------------------------------------------------------------------------


def p13_verdict(case_id: str, metrics: Mapping[str, list[float]]) -> dict[str, str]:
    spec = P13_CASES[case_id]
    delivery = metrics.get("delivery_percent", [])
    if not metrics:
        return _verdict("P13", case_id, INVALID, "no observations")
    if not _all_one(metrics.get("warmup_ok", [])):
        return _verdict("P13", case_id, INVALID, "tunnel never carried traffic during warm-up")
    if spec.outer_tos is not None and not _all_one(metrics.get("ecn_gate", [])):
        return _verdict("P13", case_id, INVALID, "ECN mutation gate failed in at least one run")
    if spec.delivery == 100:
        if not _all_at(delivery, 100.0):
            return _verdict("P13", case_id, REFUTED,
                            f"predicted 100 % delivery; observed min {min(delivery):.0f} %")
        if not _all_one(metrics.get("inner_ecn_ok", [])):
            return _verdict("P13", case_id, REFUTED, "inner ECN at the receiver is not the predicted codepoint")
        return _verdict("P13", case_id, CONFIRMED, "100 % delivery with the predicted inner ECN in every run")
    if not _all_at(delivery, 0.0):
        return _verdict("P13", case_id, REFUTED,
                        f"predicted 0 % delivery; observed max {max(delivery):.0f} %")
    if not _all_one(metrics.get("inner_ecn_ok", [])):
        return _verdict("P13", case_id, REFUTED, "inner ECN at the receiver is not the predicted codepoint")
    if not _all_one(metrics.get("cause_gate", [])):
        frames = metrics.get("ipip_rx_frame_errors_delta", [])
        return _verdict("P13", case_id, INCONCLUSIVE,
                        f"0 % delivery but ipip0 rx_frame_errors delta was {frames}")
    return _verdict("P13", case_id, CONFIRMED,
                    "0 % delivery in every run, ipip0 rx_frame_errors delta equals datagrams sent")


def p13h_verdict(case_id: str, metrics: Mapping[str, list[float]]) -> dict[str, str]:
    if not metrics:
        return _verdict("P13", case_id, INVALID, "no observations")
    if not _all_one(metrics.get("warmup_ok", [])) or not _all_one(metrics.get("offload_disabled", [])):
        return _verdict("P13", case_id, INVALID, "warm-up or offload gate failed")
    if not _all_at(metrics.get("delivery_percent", []), 100.0):
        return _verdict("P13", case_id, REFUTED, "control stack did not deliver 100 % of the datagrams")
    if not _all_one(metrics.get("inner_ecn_ok", [])):
        return _verdict("P13", case_id, REFUTED, "control changed the inner ECN codepoint")
    return _verdict("P13", case_id, CONFIRMED, "100 % delivery and unchanged inner ECN for both codepoints")


# --- P14 -------------------------------------------------------------------------------


def p14_verdict(case_id: str, metrics: Mapping[str, list[float]]) -> dict[str, str]:
    predicted_first, predicted_other, nat, first, _credence = P14_CASES[case_id]
    other = 2 if first == 1 else 1
    if not metrics:
        return _verdict("P14", case_id, INVALID, "no observations")
    if not _all_one(metrics.get("warmup_ok", [])):
        return _verdict("P14", case_id, INVALID, "tunnel never carried traffic during warm-up")
    if not _all_one(metrics.get("nat_gate", [])):
        return _verdict("P14", case_id, INVALID, "mutation gate failed: the translated source was not observed")
    delivered_first = metrics.get(f"delivery_percent_client{first}", [])
    delivered_other = metrics.get(f"delivery_percent_client{other}", [])
    if case_id in ("P14a", "P14b"):
        if _all_at(delivered_first, 100.0) and _all_at(delivered_other, 100.0):
            return _verdict("P14", case_id, REFUTED,
                            "both clients delivered 100 %: A4 is false, netfilter disambiguates ESP flows")
        if not _all_at(delivered_first, 100.0):
            return _verdict("P14", case_id, INCONCLUSIVE,
                            f"client {first} delivered min {min(delivered_first):.0f} %; the first client must be lossless")
        if any(0.0 < value < 100.0 for value in delivered_other):
            return _verdict("P14", case_id, INCONCLUSIVE,
                            f"client {other} delivered a partial fraction {sorted(set(delivered_other))}")
        if not _all_one(metrics.get("spi_gate", [])):
            return _verdict("P14", case_id, INVALID,
                            "SPI gate failed: the dropped client's SPI did appear at vN2 egress")
        return _verdict("P14", case_id, CONFIRMED,
                        f"client {first} 100 %, client {other} 0 % with its SPI absent at vN2 egress")
    if not (_all_at(delivered_first, 100.0) and _all_at(delivered_other, 100.0)):
        return _verdict("P14", case_id, REFUTED,
                        f"delivery {sorted(set(delivered_first))} / {sorted(set(delivered_other))}, predicted 100 / 100")
    return _verdict("P14", case_id, CONFIRMED, "both clients delivered 100 %")


# --- P15 -------------------------------------------------------------------------------


def p15_verdicts(table: Mapping[str, Mapping[str, list[float]]]) -> list[dict[str, str]]:
    verdicts: list[dict[str, str]] = []
    problems: list[str] = []
    invalid: list[str] = []
    for ordering, total in P15_TOTALS.items():
        policy = f"P15_{ordering.replace('->', 'to')}"
        metrics = table.get(policy, {})
        if not metrics:
            invalid.append(f"{ordering}: no observations")
            continue
        if not _all_one(metrics.get("warmup_ok", [])) or not _all_one(metrics.get("offload_disabled", [])):
            invalid.append(f"{ordering}: warm-up or offload gate failed")
            continue
        if not _all_one(metrics.get("fragment_gate", [])):
            invalid.append(f"{ordering}: fragment gate failed")
            continue
        observed = metrics.get("wire_bytes_per_datagram", [])
        if not _all_at(observed, float(total)):
            problems.append(f"{ordering}: predicted {total} B per datagram, observed {sorted(set(observed))}")
    if problems:
        verdicts.append(_verdict("P15", "P15a", REFUTED, "; ".join(problems)))
    elif invalid:
        verdicts.append(_verdict("P15", "P15a", INVALID, "; ".join(invalid)))
    else:
        verdicts.append(_verdict("P15", "P15a", CONFIRMED,
                                 "2112 B (E->F) and 2180 B (F->E) per datagram, difference 68 B, in every run"))

    pooled: dict[str, float] = {}
    delivery_problems: list[str] = []
    for ordering in P15_TOTALS:
        policy = f"P15_{ordering.replace('->', 'to')}"
        metrics = table.get(policy, {})
        delivered = sum(metrics.get("delivered_datagrams", []))
        sent = sum(metrics.get("sent_datagrams", []))
        if not sent:
            delivery_problems.append(f"{ordering}: no delivery observations")
            continue
        pooled[ordering] = delivered / sent
        if abs(pooled[ordering] - P15_EXPECTED_DELIVERY) * 100 > P15_TOLERANCE_POINTS:
            delivery_problems.append(
                f"{ordering}: pooled delivery {pooled[ordering]:.4f}, predicted {P15_EXPECTED_DELIVERY:.4f} "
                f"+/- {P15_TOLERANCE_POINTS} pp")
    if len(pooled) == 2:
        difference = abs(pooled["E->F"] - pooled["F->E"]) * 100
        if difference > P15_TOLERANCE_POINTS:
            delivery_problems.append(f"orderings differ by {difference:.2f} pp, allowed {P15_TOLERANCE_POINTS} pp")
    if delivery_problems:
        verdicts.append(_verdict("P15", "P15b", REFUTED, "; ".join(delivery_problems)))
    else:
        verdicts.append(_verdict("P15", "P15b", CONFIRMED,
                                 "both orderings pooled at " +
                                 ", ".join(f"{ordering} {value:.4f}" for ordering, value in pooled.items())))
    return verdicts


# --- P16 -------------------------------------------------------------------------------


def p16_verdict(case_id: str, metrics: Mapping[str, list[float]]) -> dict[str, str]:
    spec = P16_CASES[case_id]
    if not metrics:
        return _verdict("P16", case_id, INVALID, "no observations")
    if not _all_one(metrics.get("warmup_ok", [])) or not _all_one(metrics.get("offload_disabled", [])):
        return _verdict("P16", case_id, INVALID, "warm-up or offload gate failed")
    if not _all_one(metrics.get("depth_gate", [])):
        return _verdict("P16", case_id, INVALID,
                        f"depth gate failed: observed depths {sorted(set(metrics.get('reorder_depth', [])))}")
    if case_id == "P16a":
        if not _all_one(metrics.get("delivery_matches_reference", [])):
            mismatches = [f"{int(a)} vs {int(b)}" for a, b in zip(metrics.get("delivered_datagrams", []),
                                                                 metrics.get("reference_accepted", [])) if a != b]
            return _verdict("P16", case_id, REFUTED,
                            f"delivered differs from the reference count in {len(mismatches)} runs: {mismatches[:3]}")
        if not _all_one(metrics.get("cause_gate", [])):
            return _verdict("P16", case_id, INCONCLUSIVE,
                            f"delivered matches the reference but XfrmInStateSeqError delta "
                            f"{sorted(set(metrics.get('seq_error_delta', [])))} != sent - delivered")
        return _verdict("P16", case_id, CONFIRMED,
                        "delivered equals the reference replay count in every run; cause confirmed")
    delivered = metrics.get("delivered_datagrams", [])
    sent = metrics.get("sent_datagrams", [])
    if not sent or delivered != sent:
        return _verdict("P16", case_id, REFUTED,
                        f"lost datagrams with a valid depth gate: delivered {sorted(set(delivered))} of {sorted(set(sent))}")
    if case_id == "P16b" and not _all_one(metrics.get("cause_gate", [])):
        return _verdict("P16", case_id, INCONCLUSIVE,
                        f"100 % delivery but XfrmInStateSeqError delta {sorted(set(metrics.get('seq_error_delta', [])))} != 0")
    return _verdict("P16", case_id, CONFIRMED, f"100 % delivery in {len(delivered)} runs with a valid depth gate")


# --- driver ----------------------------------------------------------------------------


def all_verdicts(rows: list[Row]) -> list[dict[str, str]]:
    table = _table(rows)
    errored = {policy for policy, metrics in table.items() if metrics.get("setup_error")}
    verdicts: list[dict[str, str]] = []

    controls: dict[str, bool] = {}
    for case_id, spec in P13_CASES.items():
        if not case_id.startswith("P13h") or case_id not in table:
            continue
        verdict = p13h_verdict(case_id, table[case_id])
        controls[spec.stack] = verdict["verdict"] == CONFIRMED
        verdicts.append(verdict)

    for case_id, spec in P13_CASES.items():
        if case_id.startswith("P13h") or case_id not in table:
            continue
        if case_id in errored:
            verdicts.append(_verdict("P13", case_id, INVALID, "setup error in at least one run (see errors.txt)"))
            continue
        stack = spec.stack
        if stack in controls and not controls[stack]:
            verdicts.append(_verdict("P13", case_id, INVALID,
                                     f"its P13h_{stack} control failed, so the stack itself is not working"))
            continue
        verdicts.append(p13_verdict(case_id, table[case_id]))

    for case_id in P14_CASES:
        if case_id not in table:
            continue
        if case_id in errored:
            verdicts.append(_verdict("P14", case_id, INVALID, "setup error in at least one run (see errors.txt)"))
            continue
        verdicts.append(p14_verdict(case_id, table[case_id]))

    if any(policy.startswith("P15_") for policy in table):
        if any(policy.startswith("P15_") for policy in errored):
            verdicts.append(_verdict("P15", "P15a", INVALID, "setup error in at least one run (see errors.txt)"))
            verdicts.append(_verdict("P15", "P15b", INVALID, "setup error in at least one run (see errors.txt)"))
        else:
            verdicts.extend(p15_verdicts(table))

    for case_id in P16_CASES:
        if case_id not in table:
            continue
        if case_id in errored:
            verdicts.append(_verdict("P16", case_id, INVALID, "setup error in at least one run (see errors.txt)"))
            continue
        verdicts.append(p16_verdict(case_id, table[case_id]))
    return verdicts


def brier_score(verdicts: Iterable[dict[str, str]]) -> tuple[float, int, list[str], list[str]]:
    """Brier score over scored predictions; INCONCLUSIVE / INVALID / NOT RUN are unscored."""
    outcomes: dict[str, list[int]] = defaultdict(list)
    unscored: list[str] = []
    for item in verdicts:
        key = item["case"]
        if key.startswith("P13h"):
            key = "P13h"
        if item["verdict"] == CONFIRMED:
            outcomes[key].append(1)
        elif item["verdict"] == REFUTED:
            outcomes[key].append(0)
        else:
            unscored.append(f"{item['case']}: {item['verdict']}")
    total = 0.0
    scored = 0
    missing = [key for key in CREDENCE if key not in outcomes]
    for key, values in outcomes.items():
        if key not in CREDENCE:
            continue
        # A control set (P13h) counts as one prediction: refuted if any member is.
        outcome = 1 if all(values) else 0
        total += (CREDENCE[key] - outcome) ** 2
        scored += 1
    return (total / scored if scored else 0.0), scored, missing, unscored


def calibration_table(verdicts: Iterable[dict[str, str]]) -> list[dict[str, object]]:
    """One line per scored prediction, for the results document."""
    rows: list[dict[str, object]] = []
    for item in verdicts:
        key = item["case"]
        if key.startswith("P13h"):
            key = "P13h"
        if key in CREDENCE and item["verdict"] in (CONFIRMED, REFUTED):
            outcome = 1 if item["verdict"] == CONFIRMED else 0
            rows.append({"key": key, "credence": CREDENCE[key], "outcome": outcome,
                         "brier": (CREDENCE[key] - outcome) ** 2, "case": item["case"]})
    return rows


__all__ = ["CONFIRMED", "INVALID", "NOT_RUN", "REFUTED", "all_verdicts", "brier_score", "calibration_table"]
