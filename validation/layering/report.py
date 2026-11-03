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

"""Classify the frozen layering predictions against the three fidelities.

The thresholds below are the frozen values from
``docs/layering-predictions.md``.  They are read from this module, not fitted
to the observations.  A failing check is reported as REFUTED, never tuned
away.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from simulation.layering.predictions import predict
from simulation.layering.scenarios import p4_cases, p6_cases
from tools.validation_io import METRIC_UNITS

FIDELITIES = ("model", "simpy", "linux")
SOURCE_LABELS = {
    "model": "executable_model",
    "simpy": "simpy_dataplane",
    "linux": "linux_netns",
}

# Frozen tolerances (docs/layering-predictions.md).
P1_TEXT_RATIO = {"model": 1.75, "simpy": 1.75, "linux": 1.50}
P1_TEXT_DELTA_FRACTION = 0.60
P1_RANDOM_ABS_BYTES = 64.0
P1_MAX_RATIO = 1.5
P1_MAX_DELTA_BYTES = 1000.0
P2_BYTE_DIFFERENCE = 224.0
P2_DELIVERY = 0.9**9
P2_DELIVERY_MARGIN = {"model": 2.5, "simpy": 2.5, "linux": 4.0}
P2_PAIRED_MARGIN = {"model": 2.0, "simpy": 2.0, "linux": 4.0}
P5_DELTA = 100.0 * (0.9**3 - 0.9**6)
P5_DELTA_MARGIN = {"model": 3.0, "simpy": 3.0, "linux": 4.0}
P5_DELIVERY_MARGIN = {"model": 3.0, "simpy": 3.0, "linux": 4.0}
P5_CONTROL_MARGIN = {"model": 1.0, "simpy": 1.0, "linux": 3.0}
P4_WIRE_BYTES = 1104.0
P4_MAX_PAYLOAD = 1420.0


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class FidelityVerdict:
    fidelity: str
    checks: list[Check] = field(default_factory=list)
    note: str = ""

    @property
    def verdict(self) -> str:
        if not self.checks:
            return "INCONCLUSIVE"
        return "CONFIRMED" if all(check.passed for check in self.checks) else "REFUTED"


@dataclass
class PredictionVerdict:
    prediction: str
    fidelities: dict[str, FidelityVerdict]
    paired_ci95: dict[str, float] = field(default_factory=dict)

    @property
    def verdict(self) -> str:
        present = [item.verdict for item in self.fidelities.values()]
        if "REFUTED" in present:
            return "REFUTED"
        if not present or "INCONCLUSIVE" in present:
            return "INCONCLUSIVE"
        return "CONFIRMED"


class Observations:
    def __init__(self, path: Path, fidelity: str) -> None:
        self.fidelity = fidelity
        self.source = SOURCE_LABELS[fidelity]
        self.rows: dict[tuple[str, str, str, int, str], float] = {}
        if not path.exists():
            self.available = False
            return
        with path.open(newline="", encoding="utf-8-sig") as file:
            for record in csv.DictReader(file):
                if record["source"] != self.source:
                    continue
                metric = record["metric"]
                if metric not in METRIC_UNITS:
                    raise ValueError(f"Unknown layering metric: {metric}")
                if record["unit"] != METRIC_UNITS[metric]:
                    raise ValueError(
                        f"Unit mismatch for {metric}: {record['unit']} != "
                        f"{METRIC_UNITS[metric]}"
                    )
                key = (
                    record["scenario"],
                    record["policy"],
                    record["seed"],
                    metric,
                )  # type: ignore[assignment]
                self.rows[key] = float(record["value"])
        self.available = bool(self.rows)

    def values(
        self, prediction: str, case: str, metric: str
    ) -> dict[int, float]:
        prefix = (prediction, case)
        return {
            key[2]: value
            for key, value in self.rows.items()
            if key[0] == prediction and key[1] == case and key[3] == metric
        }

    def mean(self, prediction: str, case: str, metric: str) -> float:
        values = list(self.values(prediction, case, metric).values())
        if not values:
            raise KeyError(f"Missing {metric} for {prediction}/{case}.")
        return float(np.mean(values))

    def scalar(self, prediction: str, case: str, metric: str) -> float:
        values = self.values(prediction, case, metric)
        if not values:
            raise KeyError(f"Missing {metric} for {prediction}/{case}.")
        return values[sorted(values)[0]]

    def paired_difference(
        self, prediction: str, left: str, right: str, metric: str
    ) -> tuple[float, float, int]:
        left_values = self.values(prediction, left, metric)
        right_values = self.values(prediction, right, metric)
        seeds = sorted(set(left_values) & set(right_values))
        differences = np.asarray(
            [left_values[seed] - right_values[seed] for seed in seeds], dtype=float
        )
        if len(differences) < 2:
            return float(differences.mean()) if len(differences) else float("nan"), 0.0, len(
                differences
            )
        ci95 = 1.96 * float(np.std(differences, ddof=1)) / math.sqrt(len(differences))
        return float(np.mean(differences)), ci95, len(differences)


def evaluate_p1(observations: dict[str, Observations]) -> PredictionVerdict:
    verdict = PredictionVerdict("P1", {})
    for fidelity, observed in observations.items():
        result = FidelityVerdict(fidelity)
        if not observed.available:
            result.note = "no observations"
            verdict.fidelities[fidelity] = result
            continue
        ce_text = observed.scalar("P1", "C_to_E_text", "wire_bytes")
        ec_text = observed.scalar("P1", "E_to_C_text", "wire_bytes")
        ratio = ec_text / ce_text
        result.checks.append(
            Check(
                "text_ratio",
                ratio >= P1_TEXT_RATIO[fidelity],
                f"E->C / C->E = {ratio:.3f} (threshold {P1_TEXT_RATIO[fidelity]:.2f})",
            )
        )
        delta_fraction = (ec_text - ce_text) / ce_text
        result.checks.append(
            Check(
                "text_delta",
                delta_fraction >= P1_TEXT_DELTA_FRACTION,
                f"(E->C - C->E) / C->E = {delta_fraction:.3f} "
                f"(threshold {P1_TEXT_DELTA_FRACTION:.2f})",
            )
        )
        ce_random = observed.scalar("P1", "C_to_E_random", "wire_bytes")
        ec_random = observed.scalar("P1", "E_to_C_random", "wire_bytes")
        random_delta = abs(ec_random - ce_random)
        result.checks.append(
            Check(
                "random_abs_difference",
                random_delta <= P1_RANDOM_ABS_BYTES,
                f"|E->C - C->E| = {random_delta:.0f} B "
                f"(threshold {P1_RANDOM_ABS_BYTES:.0f} B)",
            )
        )
        if fidelity != "linux":
            ce_max = observed.scalar("P1", "C_to_E_text", "max_payload_bytes")
            ec_max = observed.scalar("P1", "E_to_C_text", "max_payload_bytes")
            max_ratio = ce_max / ec_max
            result.checks.append(
                Check(
                    "max_payload_ratio",
                    max_ratio >= P1_MAX_RATIO,
                    f"max(C->E) / max(E->C) = {max_ratio:.3f} "
                    f"(threshold {P1_MAX_RATIO:.2f})",
                )
            )
            result.checks.append(
                Check(
                    "max_payload_delta",
                    ce_max - ec_max >= P1_MAX_DELTA_BYTES,
                    f"max(C->E) - max(E->C) = {ce_max - ec_max:.0f} B "
                    f"(threshold {P1_MAX_DELTA_BYTES:.0f} B)",
                )
            )
        else:
            result.note = "max-payload corollary not exercised in Linux"
        verdict.fidelities[fidelity] = result
    return verdict


def evaluate_p2(observations: dict[str, Observations]) -> PredictionVerdict:
    verdict = PredictionVerdict("P2", {})
    for fidelity, observed in observations.items():
        result = FidelityVerdict(fidelity)
        if not observed.available:
            result.note = "no observations"
            verdict.fidelities[fidelity] = result
            continue
        before = observed.scalar("P2", "E_to_F", "wire_bytes")
        after = observed.scalar("P2", "F_to_E", "wire_bytes")
        difference = after - before
        result.checks.append(
            Check(
                "byte_difference",
                abs(difference - P2_BYTE_DIFFERENCE) < 1e-9,
                f"F->E - E->F = {difference:.0f} B (expected {P2_BYTE_DIFFERENCE:.0f} B)",
            )
        )
        for case in ("E_to_F", "F_to_E"):
            mean = observed.mean("P2", case, "delivery_percent") / 100.0
            margin = P2_DELIVERY_MARGIN[fidelity] / 100.0
            result.checks.append(
                Check(
                    f"delivery_{case}",
                    abs(mean - P2_DELIVERY) <= margin,
                    f"{case} = {mean:.4f} (expected {P2_DELIVERY:.4f}, "
                    f"margin {P2_DELIVERY_MARGIN[fidelity]:.1f} pp)",
                )
            )
        paired, ci95, seeds = observed.paired_difference(
            "P2", "E_to_F", "F_to_E", "delivery_percent"
        )
        verdict.paired_ci95[fidelity] = ci95 / 100.0
        result.checks.append(
            Check(
                "paired_delivery_difference",
                abs(paired) / 100.0 <= P2_PAIRED_MARGIN[fidelity] / 100.0,
                f"paired difference = {paired / 100.0:+.4f} over {seeds} seeds, "
                f"95% CI +/- {ci95 / 100.0:.4f} "
                f"(margin {P2_PAIRED_MARGIN[fidelity]:.1f} pp)",
            )
        )
        verdict.fidelities[fidelity] = result
    return verdict


def evaluate_p3(observations: dict[str, Observations]) -> PredictionVerdict:
    verdict = PredictionVerdict("P3", {})
    expected = {
        "aad_covers": {"auth_accept_percent": 0.0, "mutation_applied": 1.0, "field_visible": 1.0},
        "aad_excludes": {"auth_accept_percent": 100.0, "mutation_applied": 1.0, "field_visible": 1.0},
        "inside_ciphertext": {"auth_accept_percent": 100.0, "mutation_applied": 0.0, "field_visible": 0.0},
    }
    for fidelity, observed in observations.items():
        result = FidelityVerdict(fidelity)
        if not observed.available:
            result.note = "no observations"
            verdict.fidelities[fidelity] = result
            continue
        for case, metrics in expected.items():
            for metric, target in metrics.items():
                value = observed.scalar("P3", case, metric)
                result.checks.append(
                    Check(
                        f"{case}.{metric}",
                        abs(value - target) < 1e-9,
                        f"{value:.0f} (expected {target:.0f})",
                    )
                )
        verdict.fidelities[fidelity] = result
    return verdict


def evaluate_p4(observations: dict[str, Observations]) -> PredictionVerdict:
    verdict = PredictionVerdict("P4", {})
    for fidelity, observed in observations.items():
        result = FidelityVerdict(fidelity)
        if not observed.available:
            result.note = "no observations"
            verdict.fidelities[fidelity] = result
            continue
        wires = {
            observed.scalar("P4", case.name, "wire_bytes") for case in p4_cases()
        }
        result.checks.append(
            Check(
                "wire_bytes_identical",
                wires == {P4_WIRE_BYTES},
                f"wire sizes = {sorted(wires)} (expected {P4_WIRE_BYTES:.0f})",
            )
        )
        if fidelity != "linux":
            maximums = {
                observed.scalar("P4", case.name, "max_payload_bytes")
                for case in p4_cases()
            }
            result.checks.append(
                Check(
                    "max_payload_identical",
                    maximums == {P4_MAX_PAYLOAD},
                    f"max payloads = {sorted(maximums)} (expected {P4_MAX_PAYLOAD:.0f})",
                )
            )
        for case in p4_cases():
            delivery = observed.scalar("P4", case.name, "delivery_percent")
            auth = observed.scalar("P4", case.name, "auth_accept_percent")
            result.checks.append(
                Check(
                    f"{case.name}.delivery_auth",
                    delivery == 100.0 and auth == 100.0,
                    f"delivery {delivery:.0f} %, auth {auth:.0f} %",
                )
            )
        verdict.fidelities[fidelity] = result
    return verdict


def evaluate_p5(observations: dict[str, Observations]) -> PredictionVerdict:
    verdict = PredictionVerdict("P5", {})
    for fidelity, observed in observations.items():
        result = FidelityVerdict(fidelity)
        if not observed.available:
            result.note = "no observations"
            verdict.fidelities[fidelity] = result
            continue
        delta, ci95, seeds = observed.paired_difference(
            "P5", "C_to_F", "F_to_C", "delivery_percent"
        )
        verdict.paired_ci95[fidelity] = ci95 / 100.0
        result.checks.append(
            Check(
                "delivery_difference",
                abs(delta - P5_DELTA) <= P5_DELTA_MARGIN[fidelity],
                f"C->F - F->C = {delta:+.2f} pp (expected {P5_DELTA:+.2f} pp, "
                f"margin {P5_DELTA_MARGIN[fidelity]:.1f} pp), "
                f"95% CI +/- {ci95:.2f} pp over {seeds} seeds",
            )
        )
        for case, target in (("C_to_F", 0.9**3), ("F_to_C", 0.9**6)):
            mean = observed.mean("P5", case, "delivery_percent") / 100.0
            result.checks.append(
                Check(
                    f"delivery_{case}",
                    abs(mean - target)
                    <= P5_DELIVERY_MARGIN[fidelity] / 100.0,
                    f"{case} = {mean:.4f} (expected {target:.4f}, "
                    f"margin {P5_DELIVERY_MARGIN[fidelity]:.1f} pp)",
                )
            )
        control_delta, control_ci, control_seeds = observed.paired_difference(
            "P5", "control_C_to_F", "control_F_to_C", "delivery_percent"
        )
        result.checks.append(
            Check(
                "control_difference",
                abs(control_delta) / 100.0 <= P5_CONTROL_MARGIN[fidelity] / 100.0,
                f"control difference = {control_delta:+.2f} pp over {control_seeds} "
                f"seeds (margin {P5_CONTROL_MARGIN[fidelity]:.1f} pp)",
            )
        )
        verdict.fidelities[fidelity] = result
    return verdict


def evaluate_p6(observations: dict[str, Observations]) -> PredictionVerdict:
    verdict = PredictionVerdict("P6", {})
    cases = p6_cases()
    for fidelity, observed in observations.items():
        result = FidelityVerdict(fidelity)
        if not observed.available:
            result.note = "no observations"
            verdict.fidelities[fidelity] = result
            continue
        mismatches: list[str] = []
        for case in cases:
            expected = predict(case)
            for metric, target in (
                ("field_visible", 1.0 if expected.visible else 0.0),
                ("mutation_applied", 1.0 if expected.mutation else 0.0),
                ("auth_accept_percent", expected.auth_accept_percent),
                ("delivery_percent", expected.delivery_percent),
            ):
                value = observed.scalar("P6", case.name, metric)
                if abs(value - target) > 1e-9:
                    mismatches.append(f"{case.name}.{metric}: {value:.0f} != {target:.0f}")
        result.checks.append(
            Check(
                "all_54_cases",
                not mismatches,
                f"{len(cases)} cases, {len(mismatches)} mismatches"
                + (f" ({'; '.join(mismatches[:4])})" if mismatches else ""),
            )
        )
        verdict.fidelities[fidelity] = result
    return verdict


def evaluate_p7(observations: dict[str, Observations]) -> PredictionVerdict:
    verdict = PredictionVerdict("P7", {})
    expected = {
        "fragment_length": (100.0, 0.0),
        "tunnel_length": (100.0, 0.0),
        "inert_field": (100.0, 100.0),
    }
    for fidelity, observed in observations.items():
        result = FidelityVerdict(fidelity)
        if not observed.available:
            result.note = "no observations"
            verdict.fidelities[fidelity] = result
            continue
        for case, (auth, delivery) in expected.items():
            auth_value = observed.scalar("P7", case, "auth_accept_percent")
            delivery_value = observed.scalar("P7", case, "delivery_percent")
            result.checks.append(
                Check(
                    f"{case}.auth_delivery",
                    abs(auth_value - auth) < 1e-9
                    and abs(delivery_value - delivery) < 1e-9,
                    f"auth {auth_value:.0f} %, delivery {delivery_value:.0f} % "
                    f"(expected {auth:.0f} % / {delivery:.0f} %)",
                )
            )
        verdict.fidelities[fidelity] = result
    return verdict


EVALUATORS = {
    "P1": evaluate_p1,
    "P2": evaluate_p2,
    "P3": evaluate_p3,
    "P4": evaluate_p4,
    "P5": evaluate_p5,
    "P6": evaluate_p6,
    "P7": evaluate_p7,
}


def write_verdicts(path: Path, verdicts: list[PredictionVerdict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "prediction",
                "fidelity",
                "verdict",
                "checks",
                "failed_checks",
                "paired_ci95_percent",
                "detail",
            ]
        )
        for prediction in verdicts:
            for fidelity, result in prediction.fidelities.items():
                failed = [check.name for check in result.checks if not check.passed]
                writer.writerow(
                    [
                        prediction.prediction,
                        fidelity,
                        result.verdict,
                        len(result.checks),
                        ";".join(failed),
                        f"{100.0 * prediction.paired_ci95.get(fidelity, float('nan')):.4f}"
                        if fidelity in prediction.paired_ci95
                        else "",
                        result.note,
                    ]
                )


def _markdown(verdicts: list[PredictionVerdict]) -> str:
    lines = [
        "# Layering results",
        "",
        "Generated by `python -m validation.layering.report`. The narrative,",
        "limitations and per-prediction interpretation are maintained by hand in",
        "this file after generation.",
        "",
        "**Scope:** size, delivery, ordering and authentication acceptance only.",
        "This is not a security evaluation. P1, P2, P4 and P5 are regression",
        "predictions; P3, P6 and P7 are the research predictions.",
        "",
        "## Verdicts",
        "",
        "| Prediction | Model | SimPy | Linux | Overall |",
        "|---|---|---|---|---|",
    ]
    for prediction in verdicts:
        cells = [
            prediction.fidelities.get(name).verdict
            if prediction.fidelities.get(name) and prediction.fidelities[name].checks
            else "not run"
            for name in FIDELITIES
        ]
        lines.append(
            f"| {prediction.prediction} | " + " | ".join(cells) + f" | **{prediction.verdict}** |"
        )
    lines.extend(["", "## Checks", ""])
    for prediction in verdicts:
        lines.append(f"### {prediction.prediction}")
        lines.append("")
        for fidelity, result in prediction.fidelities.items():
            lines.append(f"**{fidelity}** — {result.verdict}")
            lines.append("")
            if result.note:
                lines.append(f"_{result.note}_")
                lines.append("")
            for check in result.checks:
                status = "PASS" if check.passed else "FAIL"
                lines.append(f"- {status} `{check.name}`: {check.detail}")
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--simpy", type=Path, required=True)
    parser.add_argument("--linux", type=Path)
    parser.add_argument("--verdicts", type=Path, required=True)
    parser.add_argument("--doc", type=Path)
    args = parser.parse_args()

    observations = {
        "model": Observations(args.model, "model"),
        "simpy": Observations(args.simpy, "simpy"),
    }
    if args.linux is not None:
        observations["linux"] = Observations(args.linux, "linux")
    verdicts = [evaluator(observations) for evaluator in EVALUATORS.values()]
    write_verdicts(args.verdicts, verdicts)
    for prediction in verdicts:
        print(f"{prediction.prediction}: {prediction.verdict}")
        for fidelity, result in prediction.fidelities.items():
            print(f"  {fidelity}: {result.verdict}")
    if args.doc is not None:
        args.doc.parent.mkdir(parents=True, exist_ok=True)
        target = args.doc
        if target.exists() and "Generated by `python -m validation.layering.report`" not in target.read_text(
            encoding="utf-8", errors="replace"
        ):
            target = target.with_name(target.stem + ".generated.md")
            print(
                f"{args.doc} is hand-maintained; writing generated checks to {target}"
            )
        target.write_text(_markdown(verdicts), encoding="utf-8")
        print(f"Doc: {target}")


if __name__ == "__main__":
    main()
