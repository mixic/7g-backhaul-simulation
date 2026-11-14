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

"""Verdict rules for P17, mirroring the frozen round-3 file."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping, Sequence

from .predictions import CASES, CREDENCE

CONFIRMED = "CONFIRMED"
REFUTED = "REFUTED"
INCONCLUSIVE = "INCONCLUSIVE"
INVALID = "INVALID"
NOT_RUN = "NOT RUN"

Row = Mapping[str, object]


def _table(rows: Iterable[Row]) -> dict[str, dict[str, list[float]]]:
    table: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        table[str(row["policy"])][str(row["metric"])].append(float(row["value"]))
    return table


def _all(table: Mapping[str, Mapping[str, Sequence[float]]], case: str, metric: str) -> bool:
    values = table.get(case, {}).get(metric)
    return bool(values) and all(value == 1.0 for value in values)


def _values(table: Mapping[str, Mapping[str, Sequence[float]]], case: str, metric: str) -> list[float]:
    return list(table.get(case, {}).get(metric, []))


def _gate_failure(table, case: str) -> str | None:
    metrics = ["warmup_ok", "offload_disabled"]
    if case != "P17a":
        metrics += ["capture_gate", "original_drop_gate"]
    for metric in metrics:
        if not _all(table, case, metric):
            return f"gate {metric} failed"
    return None


def _rate_verdict(table, case: str) -> tuple[str, str]:
    gate = _gate_failure(table, case)
    if gate:
        return INVALID, gate
    if not _all(table, case, "depth_gate"):
        return INVALID, "depth gate failed"
    sent = _values(table, case, "sent_datagrams")
    delivered = _values(table, case, "delivered_datagrams")
    accepted = _values(table, case, "reference_accepted")
    matches = _values(table, case, "delivery_matches_reference")
    if not sent or min(sent) < 590:
        return INVALID, "sender delivered fewer than 590 datagrams"
    if (
        len(delivered) != len(sent)
        or len(accepted) != len(sent)
        or len(matches) != len(sent)
    ):
        return INVALID, "incomplete per-run rows"
    if all(d == s == a and m == 1 for d, s, a, m in zip(delivered, sent, accepted, matches)):
        return CONFIRMED, "depth in [64, 200] and every datagram delivered"
    return REFUTED, "depth gate passed but delivery/reference did not match sent"


def _reinject_verdict(table, case: str) -> tuple[str, str]:
    gate = _gate_failure(table, case)
    if gate:
        return INVALID, gate
    spec = CASES[case]
    delivered = _values(table, case, "delivered_datagrams")
    accepted = _values(table, case, "reference_accepted")
    modes = _values(table, case, "anti_replay_esn")
    expected_mode = 1.0 if spec.mode == "esn" else 0.0
    if not delivered or not accepted or not modes:
        return INVALID, "missing reinjection rows"
    if any(mode != expected_mode for mode in modes):
        return INVALID, f"expected {spec.mode} anti-replay context"
    if any(value == spec.expected_delivered for value in delivered) and any(
        value == spec.expected_reference for value in accepted
    ):
        if all(value == spec.expected_delivered for value in delivered) and all(
            value == spec.expected_reference for value in accepted
        ):
            return CONFIRMED, (
                f"{spec.offset}-packet displacement gives "
                f"{spec.expected_delivered}/{spec.expected_reference}"
            )
        return REFUTED, "some runs disagree with the expected count"
    return REFUTED, (
        f"expected {spec.expected_delivered} delivered and "
        f"{spec.expected_reference} reference; got {delivered} and {accepted}"
    )


def all_verdicts(
    rows: Sequence[Row], include: Sequence[str] | None = None
) -> list[dict[str, str]]:
    table = _table(rows)
    selected = set(include) if include is not None else {"P17a", "P17b", "P17c", "P17d", "P17e", "P17f"}
    results: list[dict[str, str]] = []
    for case in ("P17a", "P17b", "P17c", "P17d", "P17e"):
        if case not in selected:
            continue
        verdict, detail = (
            _rate_verdict(table, case) if case == "P17a" else _reinject_verdict(table, case)
        )
        results.append({"prediction": case, "case": case, "verdict": verdict, "detail": detail})

    # P17f: every P17b-P17e run must record the expected mode.
    if "P17f" in selected and any(case in selected for case in ("P17b", "P17c", "P17d", "P17e")):
        mode_ok = True
        missing = False
        for case, expected in (("P17b", 0), ("P17c", 0), ("P17d", 1), ("P17e", 1)):
            if case not in selected:
                continue
            values = _values(table, case, "anti_replay_esn")
            if not values:
                missing = True
                continue
            if any(int(value) != expected for value in values):
                mode_ok = False
        if missing:
            results.append(
                {"prediction": "P17f", "case": "P17f", "verdict": INVALID, "detail": "mode rows missing"}
            )
        elif mode_ok:
            results.append(
                {
                    "prediction": "P17f",
                    "case": "P17f",
                    "verdict": CONFIRMED,
                    "detail": "window 32 legacy, window 256 ESN in every run",
                }
            )
        else:
            results.append(
                {
                    "prediction": "P17f",
                    "case": "P17f",
                    "verdict": REFUTED,
                    "detail": "at least one run recorded the other mode",
                }
            )
    return results


def brier_score(verdicts: Sequence[Mapping[str, str]]) -> tuple[float, int, list[str], list[str]]:
    scored = []
    unscored = []
    missing = []
    for verdict in verdicts:
        prediction = str(verdict["prediction"])
        status = str(verdict["verdict"])
        if status in (CONFIRMED, REFUTED):
            outcome = 1.0 if status == CONFIRMED else 0.0
            scored.append((CREDENCE[prediction] - outcome) ** 2)
        elif status in (INCONCLUSIVE, INVALID, NOT_RUN):
            unscored.append(prediction)
        else:
            missing.append(prediction)
    brier = sum(scored) / len(scored) if scored else float("nan")
    return brier, len(scored), missing, unscored


def calibration_table(verdicts: Sequence[Mapping[str, str]]) -> list[dict[str, object]]:
    table = []
    for verdict in verdicts:
        prediction = str(verdict["prediction"])
        status = str(verdict["verdict"])
        if status in (CONFIRMED, REFUTED):
            outcome = 1 if status == CONFIRMED else 0
            table.append(
                {
                    "key": prediction,
                    "credence": CREDENCE[prediction],
                    "outcome": outcome,
                    "brier": (CREDENCE[prediction] - outcome) ** 2,
                }
            )
    return table


__all__ = [
    "CONFIRMED",
    "INCONCLUSIVE",
    "INVALID",
    "NOT_RUN",
    "REFUTED",
    "all_verdicts",
    "brier_score",
    "calibration_table",
]
