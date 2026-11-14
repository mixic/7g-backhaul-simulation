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

"""Tests for the cross-kernel comparison tool."""

from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "compare_kernels", ROOT / "tools" / "compare_kernels.py"
)
ck = importlib.util.module_from_spec(_SPEC)
sys.modules["compare_kernels"] = ck
_SPEC.loader.exec_module(ck)


def _write(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _make_dir(root: Path, value: float = 100.0, verdict: str = "CONFIRMED") -> Path:
    _write(
        root / "observations.csv",
        [
            {
                "source": "kernel",
                "scenario": "P13",
                "policy": "P13a",
                "seed": "0",
                "metric": "delivery_percent",
                "value": str(value),
                "unit": "percent",
            }
        ],
        ["source", "scenario", "policy", "seed", "metric", "value", "unit"],
    )
    _write(
        root / "verdicts.csv",
        [
            {
                "prediction": "P13",
                "case": "P13a",
                "verdict": verdict,
                "detail": "",
            }
        ],
        ["prediction", "case", "verdict", "detail"],
    )
    return root


class CompareTests(unittest.TestCase):
    def test_identical_directories_agree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left = _make_dir(root / "left")
            right = _make_dir(root / "right")
            result = ck.compare(left, right)
            self.assertEqual(result["n_mismatches"], 0)
            self.assertFalse(result["verdict_disagreements"])
            self.assertIn("No observation differences", ck.render_markdown(result))

    def test_value_difference_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left = _make_dir(root / "left", 100.0)
            right = _make_dir(root / "right", 0.0)
            result = ck.compare(left, right)
            self.assertEqual(result["n_mismatches"], 1)
            self.assertEqual(result["mismatches"][0]["metric"], "delivery_percent")

    def test_verdict_difference_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left = _make_dir(root / "left", verdict="CONFIRMED")
            right = _make_dir(root / "right", verdict="REFUTED")
            result = ck.compare(left, right)
            self.assertEqual(len(result["verdict_disagreements"]), 1)
            self.assertIn("NO", ck.render_markdown(result))

    def test_tolerance_absorbs_small_differences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left = _make_dir(root / "left", 100.0)
            right = _make_dir(root / "right", 100.01)
            self.assertEqual(ck.compare(left, right, tolerance=0.1)["n_mismatches"], 0)

    def test_cli_writes_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left = _make_dir(root / "left")
            right = _make_dir(root / "right", 99.0)
            out = root / "comparison.md"
            code = ck.main(
                ["--left", str(left), "--right", str(right), "--out", str(out)]
            )
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())
            self.assertIn("Cross-kernel comparison", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
