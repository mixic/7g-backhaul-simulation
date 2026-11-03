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

"""SimPy experiment runner mirroring the executable-model observations."""

from __future__ import annotations

from simulation.layering.experiments import METRIC_UNITS
from simulation.layering.scenarios import (
    MODEL_SEEDS,
    Case,
    p1_cases,
    p2_cases,
    p3_cases,
    p4_cases,
    p5_cases,
    p6_cases,
    p7_cases,
    random_bytes,
    text_bytes,
)
from simulation.layering.simpy_dataplane import SimOutcome, simulate_case
from simulation.layering.stack import MiddleboxSpec


def _record(
    source: str,
    prediction: str,
    case: str,
    seed: int,
    metric: str,
    value: float,
) -> dict[str, object]:
    return {
        "source": source,
        "scenario": prediction,
        "policy": case,
        "seed": seed,
        "metric": metric,
        "value": float(value),
        "unit": METRIC_UNITS[metric],
    }


def _aux_metrics(
    source: str,
    prediction: str,
    case: Case,
    outcome: SimOutcome,
    seed: int,
) -> list[dict[str, object]]:
    decode = outcome.decode
    return [
        _record(source, prediction, case.name, seed, "wire_bytes", outcome.wire_bytes),
        _record(
            source,
            prediction,
            case.name,
            seed,
            "fragment_count",
            outcome.fragment_count,
        ),
        _record(
            source,
            prediction,
            case.name,
            seed,
            "auth_accept_percent",
            100.0 if decode.auth_ok else 0.0,
        ),
        _record(
            source,
            prediction,
            case.name,
            seed,
            "mutation_applied",
            1.0 if decode.mutation_applied else 0.0,
        ),
        _record(
            source,
            prediction,
            case.name,
            seed,
            "field_visible",
            1.0 if decode.field_visible else 0.0,
        ),
    ]


def _delivery_metrics(
    source: str,
    prediction: str,
    case: Case,
    outcome: SimOutcome,
    seed: int,
) -> list[dict[str, object]]:
    decode = outcome.decode
    return [
        _record(
            source,
            prediction,
            case.name,
            seed,
            "delivery_percent",
            100.0 if decode.delivered else 0.0,
        ),
        _record(
            source,
            prediction,
            case.name,
            seed,
            "in_order_delivery_percent",
            100.0 if decode.delivered else 0.0,
        ),
        _record(source, prediction, case.name, seed, "duplicate_percent", 0.0),
    ]


def _metrics(
    source: str,
    prediction: str,
    case: Case,
    outcome: SimOutcome,
    seed: int,
    include_aux: bool = True,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if include_aux:
        rows.extend(_aux_metrics(source, prediction, case, outcome, seed))
    rows.extend(_delivery_metrics(source, prediction, case, outcome, seed))
    return rows


def _middlebox(case: Case) -> MiddleboxSpec | None:
    if case.target is None:
        return None
    return MiddleboxSpec(
        case.target[0], case.target[1], case.rewrite, case.max_depth
    )


def run_simpy(source: str = "simpy_dataplane") -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for case in p1_cases():
        rows.extend(_metrics(source, "P1", case, simulate_case(case, 0), 0))
        maker = text_bytes if case.payload.startswith("text:") else random_bytes
        rows.append(
            _record(
                source,
                "P1",
                case.name,
                0,
                "max_payload_bytes",
                case.stack().max_payload(1500, maker),
            )
        )

    for case in p2_cases():
        rows.extend(_aux_metrics(source, "P2", case, simulate_case(case, 0), 0))
        for seed in MODEL_SEEDS:
            rows.extend(
                _metrics(
                    source,
                    "P2",
                    case,
                    simulate_case(case, seed),
                    seed,
                    include_aux=False,
                )
            )

    for case in p3_cases():
        rows.extend(
            _metrics(
                source,
                "P3",
                case,
                simulate_case(case, 0, middlebox=_middlebox(case)),
                0,
            )
        )

    for case in p4_cases():
        rows.extend(_metrics(source, "P4", case, simulate_case(case, 0), 0))
        rows.append(
            _record(
                source,
                "P4",
                case.name,
                0,
                "max_payload_bytes",
                case.stack().max_payload(1500, random_bytes),
            )
        )

    for case in p5_cases():
        rows.extend(_aux_metrics(source, "P5", case, simulate_case(case, 0), 0))
        for seed in MODEL_SEEDS:
            rows.extend(
                _metrics(
                    source,
                    "P5",
                    case,
                    simulate_case(case, seed),
                    seed,
                    include_aux=False,
                )
            )

    for case in p6_cases():
        rows.extend(
            _metrics(
                source,
                "P6",
                case,
                simulate_case(case, 0, middlebox=_middlebox(case)),
                0,
            )
        )

    for case in p7_cases():
        rows.extend(
            _metrics(
                source,
                "P7",
                case,
                simulate_case(case, 0, middlebox=_middlebox(case)),
                0,
            )
        )

    return rows
