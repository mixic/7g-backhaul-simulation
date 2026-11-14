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

"""Synthetic-index tests for the postmortem frame builder."""

from __future__ import annotations

import csv
import importlib.util
import random
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "build_postmortem_frame", ROOT / "tools" / "build_postmortem_frame.py"
)
bf = importlib.util.module_from_spec(_SPEC)
sys.modules["build_postmortem_frame"] = bf
_SPEC.loader.exec_module(bf)


class DateTests(unittest.TestCase):
    def test_iso(self) -> None:
        self.assertEqual(bf.parse_date("published 2024-03-05"), "2024-03-05")

    def test_month_first(self) -> None:
        self.assertEqual(bf.parse_date("March 5, 2024"), "2024-03-05")

    def test_day_first(self) -> None:
        self.assertEqual(bf.parse_date("5 March 2024"), "2024-03-05")

    def test_invalid(self) -> None:
        self.assertEqual(bf.parse_date("not a date"), "")


class IndexTests(unittest.TestCase):
    def spec(self) -> bf.ProviderSpec:
        return next(spec for spec in bf.PROVIDERS if spec.key == "aws")

    def test_extract_reports_with_date_before_anchor(self) -> None:
        html = """
        <html><body>
        <p>2024-01-15 <a href="/premiumsupport/technology/pes/2024/foo">Foo outage</a></p>
        <p>2025-02-20 <a href="/premiumsupport/technology/pes/2025/bar">Bar outage</a></p>
        </body></html>
        """
        reports = bf.extract_reports(html, self.spec())
        self.assertEqual([report.incident_id for report in reports], ["aws-foo", "aws-bar"])
        self.assertEqual(reports[0].publication_date, "2024-01-15")
        self.assertTrue(reports[0].url.startswith("https://aws.amazon.com/"))

    def test_window_filter(self) -> None:
        reports = [
            bf.ReportRef("a", "AWS", "https://x/a", "a", "2022-12-31"),
            bf.ReportRef("b", "AWS", "https://x/b", "b", "2023-01-01"),
            bf.ReportRef("c", "AWS", "https://x/c", "c", "2026-10-31"),
            bf.ReportRef("d", "AWS", "https://x/d", "d", "2026-11-01"),
        ]
        filtered = bf.filter_window(reports, date(2023, 1, 1), date(2026, 10, 31))
        self.assertEqual([report.incident_id for report in filtered], ["b", "c"])

    def test_seeded_sample_uses_sorted_ids(self) -> None:
        reports = [
            bf.ReportRef(f"id{index:03d}", "AWS", f"https://x/{index}", "t", "2024-01-01")
            for index in range(45)
        ]
        selected = bf.select_sample(reports, sample_size=40, seed=2026)
        self.assertEqual(len(selected), 40)
        self.assertEqual([r.incident_id for r in selected], sorted(r.incident_id for r in selected))
        expected = set(
            random.Random(2026).sample(sorted(r.incident_id for r in reports), 40)
        )
        self.assertEqual({r.incident_id for r in selected}, expected)


class FrameBuildTests(unittest.TestCase):
    def _write_csv(self, path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_build_frame_hashes_saved_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_dir = root / "indexes"
            index_dir.mkdir()
            (index_dir / "aws.html").write_text(
                """
                <p>2024-01-15 <a href="/premiumsupport/technology/pes/2024/foo">Foo</a></p>
                <p>2025-02-20 <a href="/premiumsupport/technology/pes/2025/bar">Bar</a></p>
                """,
                encoding="utf-8",
            )
            source = root / "source"
            source.mkdir()
            for incident in ("aws-foo", "aws-bar"):
                (source / f"{incident}.txt").write_text(f"report {incident}", encoding="utf-8")
            eligibility = root / "eligibility.csv"
            self._write_csv(
                eligibility,
                [
                    {"incident_id": "aws-foo", "eligible": "yes", "duplicate_of": "", "notes": ""},
                    {"incident_id": "aws-bar", "eligible": "yes", "duplicate_of": "", "notes": ""},
                ],
                ["incident_id", "eligible", "duplicate_of", "notes"],
            )
            reports_dir = root / "reports"
            rows = bf.build_frame(
                index_dir,
                reports_dir,
                providers=[next(spec for spec in bf.PROVIDERS if spec.key == "aws")],
                eligibility_csv=eligibility,
                reports_source_dir=source,
                fetch_reports=False,
            )
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertEqual(len(row["report_sha256"]), 64)
                self.assertTrue((reports_dir / f"{row['incident_id']}.txt").exists())
            frame_path = root / "frame.csv"
            bf.write_frame(rows, frame_path)
            with frame_path.open(encoding="utf-8") as handle:
                written = list(csv.DictReader(handle))
            self.assertEqual(len(written), 2)

    def test_eligibility_default_is_review_and_not_sampled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_dir = root / "indexes"
            index_dir.mkdir()
            (index_dir / "aws.html").write_text(
                '<p>2024-01-15 <a href="/premiumsupport/technology/pes/2024/foo">Foo</a></p>',
                encoding="utf-8",
            )
            rows = bf.build_frame(
                index_dir,
                root / "reports",
                providers=[next(spec for spec in bf.PROVIDERS if spec.key == "aws")],
                fetch_reports=False,
            )
            self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
