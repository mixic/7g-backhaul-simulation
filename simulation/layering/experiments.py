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

"""Executable-model experiments for the frozen layering predictions.

The model is deterministic except for the stipulated i.i.d. loss.  Loss draws
come from :func:`simulation.layering.scenarios.loss_unit`, which is also used
by the SimPy runner, so paired seeds are genuinely paired.
"""

from __future__ import annotations

from typing import Iterable

from simulation.layering.scenarios import (
    MODEL_SEEDS,
    Case,
    loss_unit,
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
from simulation.layering.stack import MiddleboxSpec, Stack

METRIC_UNITS = {
    "wire_bytes": "bytes",
    "max_payload_bytes": "bytes",
    "delivery_percent": "percent",
    "in_order_delivery_percent": "percent",
    "duplicate_percent": "percent",
    "auth_accept_percent": "percent",
    "mutation_applied": "boolean",
    "field_visible": "boolean",
    "fragment_count": "fragments",
}


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


def _deterministic_metrics(
    source: str,
    prediction: str,
    case: Case,
    encoded,
    decode,
    seed: int = 0,
) -> list[dict[str, object]]:
    rows = [
        _record(source, prediction, case.name, seed, "wire_bytes", encoded.wire_bytes),
        _record(
            source,
            prediction,
            case.name,
            seed,
            "fragment_count",
            encoded.fragment_count,
        ),
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
            "auth_accept_percent",
            100.0 if decode.auth_ok else 0.0,
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
    return rows


def _loss_case_rows(
    source: str,
    case: Case,
    seeds: Iterable[int],
    stack: Stack,
    encoded,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        _record(source, case.prediction, case.name, 0, "wire_bytes", encoded.wire_bytes),
        _record(
            source,
            case.prediction,
            case.name,
            0,
            "fragment_count",
            encoded.fragment_count,
        ),
    ]
    for seed in seeds:
        received = {
            index
            for index in range(encoded.fragment_count)
            if loss_unit(seed, 0, index) >= case.loss
        }
        result = stack.decode(encoded, received=received)
        rows.append(
            _record(
                source,
                case.prediction,
                case.name,
                seed,
                "delivery_percent",
                100.0 if result.delivered else 0.0,
            )
        )
        rows.append(
            _record(
                source,
                case.prediction,
                case.name,
                seed,
                "in_order_delivery_percent",
                100.0 if result.delivered else 0.0,
            )
        )
        rows.append(
            _record(source, case.prediction, case.name, seed, "duplicate_percent", 0.0)
        )
    return rows


def run_model(source: str = "executable_model") -> list[dict[str, object]]:
    """Run every frozen case in the executable model."""
    rows: list[dict[str, object]] = []

    # P1: wire bytes and maximum payload under MTU 1500.
    for case in p1_cases():
        stack = case.stack()
        encoded = stack.encode(case.data())
        decode = stack.decode(encoded)
        rows.extend(_deterministic_metrics(source, "P1", case, encoded, decode))
        maker = text_bytes if case.payload.startswith("text:") else random_bytes
        rows.append(
            _record(
                source,
                "P1",
                case.name,
                0,
                "max_payload_bytes",
                stack.max_payload(1500, maker),
            )
        )

    # P2: loss cases with paired seeds.
    for case in p2_cases():
        stack = case.stack()
        encoded = stack.encode(case.data())
        rows.extend(_loss_case_rows(source, case, MODEL_SEEDS, stack, encoded))

    # P3: integrity-scope extremes.
    for case in p3_cases():
        stack = case.stack()
        encoded = stack.encode(case.data())
        decode = stack.decode(
            encoded,
            middlebox=MiddleboxSpec(
                case.target[0], case.target[1], case.rewrite, case.max_depth
            ),
        )
        rows.extend(_deterministic_metrics(source, "P3", case, encoded, decode))

    # P4: all fixed-overhead orderings.
    for case in p4_cases():
        stack = case.stack()
        encoded = stack.encode(case.data())
        decode = stack.decode(encoded)
        rows.extend(_deterministic_metrics(source, "P4", case, encoded, decode))
        rows.append(
            _record(
                source,
                "P4",
                case.name,
                0,
                "max_payload_bytes",
                stack.max_payload(1500, random_bytes),
            )
        )

    # P5: compress/fragment ordering and control.
    for case in p5_cases():
        stack = case.stack()
        encoded = stack.encode(case.data())
        rows.extend(_loss_case_rows(source, case, MODEL_SEEDS, stack, encoded))

    # P6: the 54-case survival sweep.
    for case in p6_cases():
        stack = case.stack()
        encoded = stack.encode(case.data())
        decode = stack.decode(
            encoded,
            middlebox=MiddleboxSpec(
                case.target[0], case.target[1], case.rewrite, case.max_depth
            ),
        )
        rows.extend(_deterministic_metrics(source, "P6", case, encoded, decode))

    # P7: structural inertness.
    for case in p7_cases():
        stack = case.stack()
        encoded = stack.encode(case.data())
        decode = stack.decode(
            encoded,
            middlebox=MiddleboxSpec(
                case.target[0], case.target[1], case.rewrite, case.max_depth
            ),
        )
        rows.extend(_deterministic_metrics(source, "P7", case, encoded, decode))

    return rows
