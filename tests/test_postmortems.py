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

"""Synthetic-data tests for the postmortem study analysis.

No real postmortem is read here.  The tests build coded rows with known
properties, then check the statistics, the reliability/size gates and the
verdict rules.  This is the "test before any real coding" requirement of the
frozen protocol.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "analyze_postmortems", ROOT / "tools" / "analyze_postmortems.py"
)
pm = importlib.util.module_from_spec(_SPEC)
sys.modules["analyze_postmortems"] = pm
_SPEC.loader.exec_module(pm)


def _values(**overrides) -> dict[str, str]:
    base = {
        "V1_trigger": "config_change",
        "V1b_secondary_trigger": "",
        "V2_failed_plane": "control_plane",
        "V3_shared_dependency": "shared_global",
        "V4_blast_radius": "multi_region",
        "V5_independence_breach": "yes",
        "V6_fallback_outcome": "slow_or_manual",
        "V7_central_controller": "yes",
        "V8a_tenant_isolation_retained": "no",
        "V8b_multipath_or_multiprovider_retained": "no",
        "V8c_tested_local_fallback_retained": "no",
        "V9_duration_minutes": "60",
        "V10_known_before_freeze": "no",
    }
    base.update(overrides)
    return base


def _dataset(n_big: int = 30, n_small: int = 30):
    """60 incidents: 30 big/control-plane, 30 small/physical."""
    frame = []
    final = {}
    for index in range(1, n_big + 1):
        incident = f"i{index:02d}"
        frame.append(
            pm.FrameRow(
                incident_id=incident,
                provider="AWS",
                report_url=f"https://example.test/{incident}",
                report_sha256="",
                publication_date="2025-01-01",
            )
        )
        final[incident] = pm.CodeRow(
            incident_id=incident,
            values=_values(
                V4_blast_radius="multi_region",
                V7_central_controller="yes",
                V3_shared_dependency="shared_global",
                V2_failed_plane="control_plane",
                V1_trigger="config_change",
                V5_independence_breach="yes",
                V6_fallback_outcome="slow_or_manual",
                V8a_tenant_isolation_retained="no",
                V8b_multipath_or_multiprovider_retained="no",
                V10_known_before_freeze="yes" if index <= n_big // 2 else "no",
            ),
        )
    for index in range(n_big + 1, n_big + n_small + 1):
        incident = f"i{index:02d}"
        frame.append(
            pm.FrameRow(
                incident_id=incident,
                provider="AWS",
                report_url=f"https://example.test/{incident}",
                report_sha256="",
                publication_date="2025-01-01",
            )
        )
        final[incident] = pm.CodeRow(
            incident_id=incident,
            values=_values(
                V4_blast_radius="single_zone",
                V7_central_controller="no",
                V3_shared_dependency="localized",
                V2_failed_plane="network_backbone_physical",
                V1_trigger="hardware_or_physical",
                V5_independence_breach="no",
                V6_fallback_outcome="slow_or_manual",
                V8a_tenant_isolation_retained="no",
                V8b_multipath_or_multiprovider_retained="yes",
                V10_known_before_freeze="no",
            ),
        )
    c1 = {key: pm.CodeRow(key, dict(value.values), "C1") for key, value in final.items()}
    c2 = {key: pm.CodeRow(key, dict(value.values), "C2") for key, value in final.items()}
    return frame, c1, c2, final


class StatisticsTests(unittest.TestCase):
    def test_wilson_extremes(self) -> None:
        low, high = pm.wilson(30, 30)
        self.assertGreater(low, 0.85)
        self.assertLessEqual(high, 1.0)
        low, high = pm.wilson(0, 30)
        self.assertEqual(low, 0.0)
        self.assertLess(high, 0.12)

    def test_newcombe_difference(self) -> None:
        low, high = pm.newcombe(30, 30, 0, 30)
        self.assertGreater(low, 0.5)
        self.assertLessEqual(high, 1.0)
        low, high = pm.newcombe(0, 30, 30, 30)
        self.assertLess(low, -0.5)
        self.assertGreaterEqual(low, -1.0)

    def test_kappa(self) -> None:
        self.assertAlmostEqual(pm.cohen_kappa(["a", "b", "a"], ["a", "b", "a"]), 1.0)
        value = pm.cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"])
        self.assertLess(value, 0.6)

    def test_mann_whitney_direction(self) -> None:
        _, p_small = pm.mann_whitney_one_sided([4] * 30, [1] * 30)
        _, p_large = pm.mann_whitney_one_sided([1] * 30, [4] * 30)
        self.assertLess(p_small, 0.01)
        self.assertGreater(p_large, 0.99)


class VerdictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frame, cls.c1, cls.c2, cls.final = _dataset()
        cls.result = pm.run_analysis(cls.frame, cls.c1, cls.c2, cls.final)

    def verdict(self, prediction: str, scope: str = "full") -> dict:
        key = "verdicts_full" if scope == "full" else "verdicts_without_known"
        return next(row for row in self.result[key] if row["id"] == prediction)

    def test_all_eight_confirmed_on_synthetic_data(self) -> None:
        for prediction in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
            with self.subTest(prediction=prediction):
                self.assertEqual(self.verdict(prediction)["verdict"], "CONFIRMED")

    def test_without_known_can_be_inconclusive(self) -> None:
        # Removing the known half leaves 30 small incidents: E1/E3/E7 have no
        # big incidents and E6 has no controller group, so the size gate bites.
        for prediction in ("E1", "E3", "E6", "E7"):
            with self.subTest(prediction=prediction):
                self.assertEqual(
                    self.verdict(prediction, "without_known")["verdict"],
                    "INCONCLUSIVE",
                )

    def test_reliability_gate_invalidates(self) -> None:
        c2 = {key: pm.CodeRow(key, dict(value.values), "C2") for key, value in self.final.items()}
        for index, key in enumerate(sorted(c2)):
            if index % 2 == 0:
                c2[key].values["V1_trigger"] = "security_attack"
        result = pm.run_analysis(self.frame, self.c1, c2, self.final)
        e2 = next(row for row in result["verdicts_full"] if row["id"] == "E2")
        self.assertEqual(e2["verdict"], "INVALID")
        self.assertIn("V1_trigger", e2["reason"])

    def test_size_gate_inconclusive(self) -> None:
        frame, c1, c2, final = _dataset(n_big=5, n_small=5)
        result = pm.run_analysis(frame, c1, c2, final)
        for row in result["verdicts_full"]:
            self.assertEqual(row["verdict"], "INCONCLUSIVE", row)

    def test_brier_is_computed_only_over_scored_verdicts(self) -> None:
        brier = self.result["brier_full"]
        self.assertEqual(brier["n"], 8)
        expected = sum((pm.CREDENCES[key] - 1.0) ** 2 for key in pm.CREDENCES) / 8
        self.assertAlmostEqual(brier["brier"], expected)

    def test_markdown_contains_the_sections(self) -> None:
        text = pm.render_markdown(self.result)
        for heading in ("Reliability gate", "Verdicts (full set)", "Brier score"):
            self.assertIn(heading, text)

    def test_frame_hash_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reports = Path(directory)
            (reports / "i01.txt").write_text("saved report", encoding="utf-8")
            frame = [
                pm.FrameRow(
                    incident_id="i01",
                    provider="AWS",
                    report_url="https://example.test/i01",
                    report_sha256="0" * 64,
                    publication_date="2025-01-01",
                )
            ]
            problems = pm.verify_frame_hashes(frame, reports)
            self.assertTrue(problems)
            self.assertIn("i01", problems[0])


class CliTests(unittest.TestCase):
    def _write_csv(self, path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
        import csv

        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_cli_reads_synthetic_csvs_and_writes_outputs(self) -> None:
        import hashlib
        import json

        frame, c1, c2, final = _dataset(n_big=30, n_small=30)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            frame_rows = []
            for row in frame:
                text = f"report text for {row.incident_id}\n"
                report_path = reports / f"{row.incident_id}.txt"
                report_path.write_text(text, encoding="utf-8")
                # Hash the saved bytes, not the Python string: text-mode
                # newline translation on Windows would otherwise differ.
                row.report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
                frame_rows.append(
                    {
                        "incident_id": row.incident_id,
                        "provider": row.provider,
                        "report_url": row.report_url,
                        "report_sha256": row.report_sha256,
                        "publication_date": row.publication_date,
                        "eligible": row.eligible,
                        "duplicate_of": "",
                        "notes": "",
                    }
                )
            self._write_csv(
                root / "frame.csv",
                frame_rows,
                [
                    "incident_id",
                    "provider",
                    "report_url",
                    "report_sha256",
                    "publication_date",
                    "eligible",
                    "duplicate_of",
                    "notes",
                ],
            )
            columns = ["incident_id", "coder"] + list(pm.VARIABLES)
            for name, codes in (("c1", c1), ("c2", c2), ("final", final)):
                rows = []
                for incident, code in codes.items():
                    row = {"incident_id": incident, "coder": code.coder}
                    row.update(code.values)
                    rows.append(row)
                self._write_csv(root / f"{name}.csv", rows, columns)
            code = pm.main(
                [
                    "--frame",
                    str(root / "frame.csv"),
                    "--c1",
                    str(root / "c1.csv"),
                    "--c2",
                    str(root / "c2.csv"),
                    "--final",
                    str(root / "final.csv"),
                    "--reports-dir",
                    str(reports),
                    "--output-dir",
                    str(root / "analysis"),
                ]
            )
            self.assertEqual(code, 0)
            for name in ("analysis.json", "analysis.md", "kappa.csv", "verdicts.csv", "unclear.csv"):
                self.assertTrue((root / "analysis" / name).exists(), name)
            result = json.loads((root / "analysis" / "analysis.json").read_text(encoding="utf-8"))
            self.assertEqual(result["frame"]["frame_hash_problems"], [])
            self.assertEqual(result["frame"]["n_eligible"], 60)

    def test_cli_frame_gate_stops_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            (reports / "i01.txt").write_text("report text", encoding="utf-8")
            self._write_csv(
                root / "frame.csv",
                [
                    {
                        "incident_id": "i01",
                        "provider": "AWS",
                        "report_url": "https://example.test/i01",
                        "report_sha256": "0" * 64,
                        "publication_date": "2025-01-01",
                        "eligible": "yes",
                        "duplicate_of": "",
                        "notes": "",
                    }
                ],
                [
                    "incident_id",
                    "provider",
                    "report_url",
                    "report_sha256",
                    "publication_date",
                    "eligible",
                    "duplicate_of",
                    "notes",
                ],
            )
            columns = ["incident_id", "coder"] + list(pm.VARIABLES)
            for name in ("c1", "c2", "final"):
                row = {"incident_id": "i01", "coder": name.upper()}
                row.update(_values())
                self._write_csv(root / f"{name}.csv", [row], columns)
            code = pm.main(
                [
                    "--frame",
                    str(root / "frame.csv"),
                    "--c1",
                    str(root / "c1.csv"),
                    "--c2",
                    str(root / "c2.csv"),
                    "--final",
                    str(root / "final.csv"),
                    "--reports-dir",
                    str(reports),
                    "--output-dir",
                    str(root / "analysis"),
                ]
            )
            self.assertEqual(code, 3)
            self.assertFalse((root / "analysis" / "analysis.json").exists())


if __name__ == "__main__":
    unittest.main()
