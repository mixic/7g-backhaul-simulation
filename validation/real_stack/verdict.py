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


"""Turn observation rows into the five dispositions of the frozen file.

CONFIRMED, REFUTED, INCONCLUSIVE (cause gate failed), INVALID (mutation gate or a
control failed, or the measurement itself is broken) and NOT RUN (a required
facility is missing; produced by :mod:`validation.real_stack.probe`, never here).

Rules are copied from the frozen predictions; none is tuned after the fact.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from .cases import CASES, Case
from .predictions import (
    P9_LENGTHS,
    P10_LENGTHS,
    p9_deviation,
    p10_d,
    p10_wire_w_to_y,
    p10_wire_y_to_w,
    wg_wire,
)

Row = Mapping[str, object]
CONFIRMED, REFUTED, INCONCLUSIVE, INVALID, NOT_RUN = "CONFIRMED", "REFUTED", "INCONCLUSIVE", "INVALID", "NOT RUN"


CONTROL_OF = {
    "P8a": "P8a_control",
    "P8b": "P8b_control",
    "P8c": "P8c_control",
    "P12a": "P12c",
    "P12b": "P12c",
}


def _by_policy(rows: Iterable[Row]) -> dict[str, dict[str, list[float]]]:
    table: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        table[str(row["policy"])][str(row["metric"])].append(float(row["value"]))
    return table


def _verdict(prediction: str, case: str, status: str, detail: str) -> dict[str, str]:
    return {"prediction": prediction, "case": case, "verdict": status, "detail": detail}


def _all(values: list[float], predicate) -> bool:
    return bool(values) and all(predicate(v) for v in values)


def delivery_case_verdict(case: Case, metrics: Mapping[str, list[float]]) -> dict[str, str]:
    """P8, P11 and P12: delivery must sit at its predicted extreme in every run."""
    if not metrics:
        return _verdict(case.prediction, case.id, INVALID, "no observations")
    if not _all(metrics.get("warmup_ok", []), lambda v: v == 1):
        return _verdict(case.prediction, case.id, INVALID, "tunnel never carried traffic during warm-up")
    if case.needs_offload_off and not _all(metrics.get("offload_disabled", []), lambda v: v == 1):
        return _verdict(case.prediction, case.id, INVALID, "NIC offload could not be disabled; checksum behaviour is unreliable")
    if not _all(metrics.get("mutation_gate", []), lambda v: v == 1):
        return _verdict(case.prediction, case.id, INVALID, "mutation gate failed in at least one run")
    delivery = metrics.get("delivery_percent", [])
    expected = case.expected_delivery
    at_extreme = _all(delivery, lambda v: v == float(expected))
    if case.id == "P8c" and not _all(metrics.get("endpoint_gate", []), lambda v: v == 1):
        if at_extreme:
            return _verdict(case.prediction, case.id, REFUTED,
                            "delivery matched but cB did not learn the translated endpoint")
    if expected == 0:
        if not at_extreme:
            return _verdict(case.prediction, case.id, REFUTED,
                            f"predicted 0 % delivery; observed max {max(delivery):.0f} %")
        if not _all(metrics.get("cause_gate", []), lambda v: v == 1):
            return _verdict(case.prediction, case.id, INCONCLUSIVE,
                            "0 % delivery but the kernel counters name a different cause")
        return _verdict(case.prediction, case.id, CONFIRMED, f"0 % delivery in {len(delivery)} runs, cause confirmed")
    if not at_extreme:
        return _verdict(case.prediction, case.id, REFUTED,
                        f"predicted 100 % delivery; observed min {min(delivery):.0f} %")
    return _verdict(case.prediction, case.id, CONFIRMED, f"100 % delivery in {len(delivery)} runs")


def p8_control_valid(rows: Iterable[Row]) -> dict[str, bool]:
    """Controls (no middlebox) must deliver 100 % or the matching case is INVALID."""
    table = _by_policy(rows)
    result: dict[str, bool] = {}
    for case in CASES:
        if case.control:
            result[case.id] = _all(table.get(case.id, {}).get("delivery_percent", []), lambda v: v == 100.0)
    return result


def _sweep_delivery_ok(table: Mapping[str, Mapping[str, list[float]]], case_id: str) -> bool:
    return _all(table.get(case_id, {}).get("delivery_percent", []), lambda v: v == 100.0)


def p9_verdict(rows: Iterable[Row]) -> dict[str, str]:
    table = _by_policy(rows)
    if not _sweep_delivery_ok(table, "P9"):
        return _verdict("P9", "P9", INVALID, "tunnel did not deliver 100 % of the sweep packets")
    problems: list[str] = []
    invalid: list[str] = []
    deviations: list[str] = []
    for length in P9_LENGTHS:
        metrics = table.get(f"P9_L{length}", {})
        packets = metrics.get("wire_packets", [])
        expected = metrics.get("expected_packets", [])
        if not packets or packets != expected:
            invalid.append(f"L={length}: captured {sorted(set(packets))} packets, expected {sorted(set(expected))}")
            continue
        low, high = metrics.get("wire_bytes_min", []), metrics.get("wire_bytes_max", [])
        predicted = wg_wire(length)
        if not (_all(low, lambda v: v == predicted) and _all(high, lambda v: v == predicted)):
            problems.append(f"L={length}: predicted {predicted}, observed {int(min(low))}..{int(max(high))}")
        else:
            deviations.append(f"L={length}: {p9_deviation(length)}")
    if invalid:
        return _verdict("P9", "P9", INVALID, "; ".join(invalid))
    if problems:
        return _verdict("P9", "P9", REFUTED, "; ".join(problems))
    return _verdict("P9", "P9", CONFIRMED,
                    "wire = 60 + 16*ceil(L/16) for every L; stipulated 56 B composite is off by " + ", ".join(deviations))


def p10_verdicts(rows: Iterable[Row]) -> list[dict[str, str]]:
    table = _by_policy(rows)
    for order in ("y_to_w", "w_to_y"):
        if not _sweep_delivery_ok(table, f"P10_{order}"):
            detail = f"order {order} did not deliver 100 % of the sweep packets"
            return [_verdict("P10", "P10a", INVALID, detail), _verdict("P10", "P10b", INVALID, detail)]
    observed: dict[tuple[str, int], tuple[float, float]] = {}
    broken: list[str] = []
    for order in ("y_to_w", "w_to_y"):
        for length in P10_LENGTHS:
            metrics = table.get(f"P10_{order}_L{length}", {})
            packets, expected = metrics.get("wire_packets", []), metrics.get("expected_packets", [])
            if not packets or packets != expected or not metrics.get("wire_bytes_min"):
                broken.append(f"{order} L={length}")
                continue
            low, high = metrics["wire_bytes_min"], metrics["wire_bytes_max"]
            if min(low) != max(high):
                broken.append(f"{order} L={length}: unstable wire size")
                continue
            observed[(order, length)] = (min(low), max(high))
    if broken:
        detail = "capture incomplete for " + ", ".join(broken)
        return [_verdict("P10", "P10a", INVALID, detail), _verdict("P10", "P10b", INVALID, detail)]

    deltas = {length: observed[("y_to_w", length)][0] - observed[("w_to_y", length)][0] for length in P10_LENGTHS}
    zero = [length for length, d in deltas.items() if d == 0]
    wrong = [f"L={length}: predicted {p10_d(length):+d}, observed {int(d):+d}"
             for length, d in deltas.items() if d != p10_d(length)]
    wire_wrong = [length for length in P10_LENGTHS
                  if observed[("y_to_w", length)][0] != p10_wire_y_to_w(length)
                  or observed[("w_to_y", length)][0] != p10_wire_w_to_y(length)]

    if zero:
        a = _verdict("P10", "P10a", REFUTED, f"d(L) = 0 (naive commutation holds) for L = {zero}")
    else:
        a = _verdict("P10", "P10a", CONFIRMED, "d(L) is non-zero for every L: naive P4 commutation fails on a real stack")
    if wrong or wire_wrong:
        detail = "; ".join(wrong) if wrong else f"absolute wire sizes differ from formula for L = {wire_wrong}"
        b = _verdict("P10", "P10b", REFUTED, detail)
    else:
        b = _verdict("P10", "P10b", CONFIRMED, "d(L) = R(L+20) - R(L) - 20 exact for every L")
    return [a, b]


def all_verdicts(rows: list[Row]) -> list[dict[str, str]]:
    """Verdicts for every case that has observations; callers add NOT RUN rows separately."""
    table = _by_policy(rows)
    controls = p8_control_valid(rows)
    errored = {policy for policy, metrics in table.items() if metrics.get("setup_error")}
    verdicts: list[dict[str, str]] = []
    for case in CASES:
        if case.is_sweep or case.id not in table:
            continue
        if case.id in errored:
            verdicts.append(_verdict(case.prediction, case.id, INVALID,
                                     "setup error in at least one run (see errors.txt)"))
            continue
        verdict = delivery_case_verdict(case, table[case.id])
        if case.control:
            if verdict["verdict"] != CONFIRMED:
                verdict = _verdict(case.prediction, case.id, INVALID,
                                   "control failed, so the stack itself is not working: " + verdict["detail"])
        else:
            partner = CONTROL_OF.get(case.id)
            if partner in controls and not controls[partner]:
                verdict = _verdict(case.prediction, case.id, INVALID,
                                   "its no-middlebox control did not deliver 100 %; the stack itself is broken")
        verdicts.append(verdict)
    if "P9" in errored:
        verdicts.append(_verdict("P9", "P9", INVALID, "setup error in at least one run (see errors.txt)"))
    elif any(str(r["policy"]).startswith("P9_L") for r in rows):
        verdicts.append(p9_verdict(rows))
    if {"P10_y_to_w", "P10_w_to_y"} & errored:
        detail = "setup error in at least one run (see errors.txt)"
        verdicts.extend([_verdict("P10", "P10a", INVALID, detail), _verdict("P10", "P10b", INVALID, detail)])
    elif any(str(r["policy"]).startswith("P10_") for r in rows):
        verdicts.extend(p10_verdicts(rows))
    return verdicts
