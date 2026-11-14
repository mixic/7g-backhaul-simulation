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

"""Kernel-free tests for the round-3 P17 harness and verdicts."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.round2.replay import reference_accepted  # noqa: E402
from validation.round3 import raw  # noqa: E402
from validation.round3.verdict import all_verdicts, brier_score  # noqa: E402


class RawParseTests(unittest.TestCase):
    def test_parse_esp_frame(self) -> None:
        ethernet = b"\x00" * 12 + struct.pack("!H", 0x0800)
        ip = bytes([0x45, 0, 0, 40, 0, 0, 0, 0, 64, 50, 0, 0]) + bytes([192, 0, 2, 1, 192, 0, 2, 2])
        esp = struct.pack("!II", 0xABCDEF01, 42) + b"\x00" * 12
        parsed = raw.parse_esp_frame(ethernet + ip + esp)
        self.assertEqual(parsed, {"spi": 0xABCDEF01, "seq": 42})

    def test_non_esp_is_ignored(self) -> None:
        frame = b"\x00" * 12 + struct.pack("!H", 0x0800) + bytes([0x45, 0, 0, 20, 0, 0, 0, 0, 64, 6]) + b"\x00" * 10
        self.assertIsNone(raw.parse_esp_frame(frame))


class ReplayBoundaryTests(unittest.TestCase):
    def test_strict_boundary(self) -> None:
        # accepted max + a packet exactly at max - window
        self.assertEqual(reference_accepted([100, 68], 32), 1)
        # one inside the window
        self.assertEqual(reference_accepted([100, 69], 32), 2)
        self.assertEqual(reference_accepted([300, 44], 256), 1)
        self.assertEqual(reference_accepted([300, 45], 256), 2)


def _row(case: str, run: int, metric: str, value: float) -> dict[str, object]:
    return {
        "source": "test",
        "scenario": case,
        "policy": case,
        "seed": run,
        "metric": metric,
        "value": value,
        "unit": "count",
    }


def _base(case: str, runs: int = 3) -> list[dict[str, object]]:
    rows = []
    for run in range(runs):
        for metric in ("warmup_ok", "offload_disabled"):
            rows.append(_row(case, run, metric, 1))
    return rows


def _rate_rows(delivered: float = 600, reference: float = 600, depth_gate: float = 1) -> list[dict]:
    rows = _base("P17a")
    for run in range(3):
        rows += [
            _row("P17a", run, "sent_datagrams", 600),
            _row("P17a", run, "captured_packets", 600),
            _row("P17a", run, "reorder_depth", 100),
            _row("P17a", run, "depth_gate", depth_gate),
            _row("P17a", run, "delivered_datagrams", delivered),
            _row("P17a", run, "reference_accepted", reference),
            _row("P17a", run, "delivery_matches_reference", int(delivered == reference)),
        ]
    return rows


def _reinject_rows(case: str, delivered: float, reference: float, mode: int) -> list[dict]:
    rows = _base(case)
    for run in range(3):
        rows += [
            _row(case, run, "capture_gate", 1),
            _row(case, run, "original_drop_gate", 1),
            _row(case, run, "delivered_datagrams", delivered),
            _row(case, run, "reference_accepted", reference),
            _row(case, run, "anti_replay_esn", mode),
        ]
    return rows


class VerdictTests(unittest.TestCase):
    def test_all_six_confirmed(self) -> None:
        rows = _rate_rows() + _reinject_rows("P17b", 1, 1, 0) + _reinject_rows("P17c", 2, 2, 0)
        rows += _reinject_rows("P17d", 1, 1, 1) + _reinject_rows("P17e", 2, 2, 1)
        verdicts = {item["prediction"]: item["verdict"] for item in all_verdicts(rows)}
        self.assertEqual(set(verdicts), {"P17a", "P17b", "P17c", "P17d", "P17e", "P17f"})
        self.assertTrue(all(value == "CONFIRMED" for value in verdicts.values()), verdicts)
        brier, scored, _, _ = brier_score(all_verdicts(rows))
        self.assertEqual(scored, 6)
        self.assertGreaterEqual(brier, 0.0)

    def test_boundary_accept_is_a_refutation(self) -> None:
        rows = _rate_rows() + _reinject_rows("P17b", 2, 2, 0) + _reinject_rows("P17c", 2, 2, 0)
        rows += _reinject_rows("P17d", 1, 1, 1) + _reinject_rows("P17e", 2, 2, 1)
        verdicts = {item["prediction"]: item["verdict"] for item in all_verdicts(rows)}
        self.assertEqual(verdicts["P17b"], "REFUTED")

    def test_depth_gate_failure_is_invalid(self) -> None:
        rows = _rate_rows(depth_gate=0) + _reinject_rows("P17b", 1, 1, 0) + _reinject_rows("P17c", 2, 2, 0)
        rows += _reinject_rows("P17d", 1, 1, 1) + _reinject_rows("P17e", 2, 2, 1)
        verdicts = {item["prediction"]: item["verdict"] for item in all_verdicts(rows)}
        self.assertEqual(verdicts["P17a"], "INVALID")

    def test_wrong_mode_refutes_p17f(self) -> None:
        rows = _rate_rows() + _reinject_rows("P17b", 1, 1, 0) + _reinject_rows("P17c", 2, 2, 0)
        rows += _reinject_rows("P17d", 1, 1, 0) + _reinject_rows("P17e", 2, 2, 1)
        verdicts = {item["prediction"]: item["verdict"] for item in all_verdicts(rows)}
        self.assertEqual(verdicts["P17f"], "REFUTED")


if __name__ == "__main__":
    unittest.main()
