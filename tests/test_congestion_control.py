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

import csv
import math
import tempfile
import unittest
from pathlib import Path

from simulation.congestion import COUPLED_ALGORITHMS, CoupledCongestionGroup
from tools.benchmark_congestion_control import (
    ALGORITHMS,
    PAIRED_FILENAME,
    REPLICATES_FILENAME,
    SUMMARY_FILENAME,
    simulate,
    run_benchmark,
)


class CoupledCongestionGroupTests(unittest.TestCase):
    def make_group(
        self,
        algorithm: str,
        a_segments: int = 10,
        b_segments: int = 10,
        rtt_a_ms: float = 10.0,
        rtt_b_ms: float = 10.0,
    ) -> CoupledCongestionGroup:
        return CoupledCongestionGroup(
            algorithm,
            [("A", 1000, rtt_a_ms), ("B", 1000, rtt_b_ms)],
            initial_window_segments={"A": a_segments, "B": b_segments},
        )

    @staticmethod
    def ack_delta(
        group: CoupledCongestionGroup,
        path_name: str,
        acknowledged_bytes: int = 1000,
        rtt_ms: float = 10.0,
    ) -> float:
        before = group.windows_bytes()[path_name]
        group.on_ack(path_name, acknowledged_bytes, rtt_ms)
        return group.windows_bytes()[path_name] - before

    def test_lia_increase_matches_rfc_6356_equations(self):
        group = self.make_group("lia", a_segments=20, b_segments=10)
        windows_before = group.windows_bytes()

        # cwnd_total = 30,000 B; max(cwnd/rtt^2) at equal RTT is the 20,000 B
        # window, so alpha = 30,000 * 20,000 / 30,000^2 = 2/3.
        self.assertAlmostEqual(group.alpha(), 2.0 / 3.0, places=12)
        expected_increase = (2.0 / 3.0) * 1000.0 * 1000.0 / 30000.0

        delta = self.ack_delta(group, "A")

        self.assertAlmostEqual(delta, expected_increase, places=9)
        self.assertAlmostEqual(
            group.windows_bytes()["B"],
            windows_before["B"],
        )
        self.assertEqual(group.ack_count, 1)

    def test_reno_increase_is_uncoupled_per_path_tcp(self):
        group = self.make_group("reno", a_segments=20, b_segments=10)

        self.assertAlmostEqual(self.ack_delta(group, "A"), 50.0, places=12)

        group.on_loss("A")
        before_b = group.windows_bytes()["B"]
        delta_b = self.ack_delta(group, "B")
        self.assertAlmostEqual(delta_b, 100.0, places=12)
        self.assertAlmostEqual(group.windows_bytes()["B"], before_b + 100.0)

    def test_olia_increase_matches_published_equation(self):
        group = self.make_group("olia", a_segments=10, b_segments=10)
        # Equal windows and equal RTTs: the Kelly/Voice term is
        # (10,000 / rtt^2) / (20,000 / rtt)^2 = 2.5e-5 / B, and no path is
        # collected, so alpha_r = 0 and the ACK adds 25 B.
        self.assertAlmostEqual(self.ack_delta(group, "A"), 25.0, places=9)
        self.assertAlmostEqual(group.olia_alpha("A"), 0.0)
        self.assertAlmostEqual(group.olia_alpha("B"), 0.0)

    def test_olia_collected_path_is_rewarded_and_max_window_path_is_penalised(self):
        group = CoupledCongestionGroup(
            "olia",
            [("A", 1000, 10.0), ("B", 1000, 10.0)],
            initial_window_segments={"A": 100, "B": 5},
        )
        # A has the largest window; B receives enough acknowledged bytes to
        # become the best path. B is then the collected path and A is in
        # max_w_paths, so alpha_B = +0.5 and alpha_A = -0.5.
        delta_b = self.ack_delta(group, "B", acknowledged_bytes=100_000)
        kelly_b = (5000.0 / 0.0001) / ((105000.0 / 0.01) ** 2)
        expected_b = (kelly_b + 0.5 / 5000.0) * 1000.0 * 100_000.0
        self.assertAlmostEqual(delta_b, expected_b, places=6)
        self.assertAlmostEqual(group.olia_alpha("A"), -0.5)
        self.assertAlmostEqual(group.olia_alpha("B"), 0.5)

        windows = group.windows_bytes()
        self.assertGreater(windows["A"], windows["B"])

        # The negative alpha term lowers A's increase relative to the
        # Kelly/Voice term alone, and B (collected) grows faster in absolute
        # bytes even though it is the smaller window.
        kelly_a = (windows["A"] / 0.0001) / (
            ((windows["A"] + windows["B"]) / 0.01) ** 2
        )
        expected_a = (kelly_a - 0.5 / windows["A"]) * 1000.0 * 1000.0
        delta_a = self.ack_delta(group, "A")
        self.assertAlmostEqual(delta_a, expected_a, places=6)
        self.assertLess(delta_a, kelly_a * 1000.0 * 1000.0)
        delta_b_second = self.ack_delta(group, "B")
        self.assertGreater(delta_b_second, 5.0 * delta_a)

    def test_loss_halves_only_the_affected_subflow(self):
        for algorithm in COUPLED_ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                group = self.make_group(algorithm)
                group.on_loss("A")
                windows = group.windows_bytes()
                self.assertAlmostEqual(windows["A"], 5000.0)
                self.assertAlmostEqual(windows["B"], 10000.0)

                group.on_loss("A")
                self.assertAlmostEqual(group.windows_bytes()["A"], 2500.0)
                group.on_loss("A")
                # Floor: minimum_window_segments defaults to 2 MSS.
                self.assertAlmostEqual(group.windows_bytes()["A"], 2000.0)
                self.assertAlmostEqual(group.windows_bytes()["B"], 10000.0)

                with self.assertRaises(KeyError):
                    group.on_loss("missing")

    def test_coupled_algorithms_react_to_a_loss_on_another_path(self):
        def deltas(algorithm: str) -> tuple[float, float]:
            group = self.make_group(algorithm)
            before = self.ack_delta(group, "B")
            group.on_ack("A", 1000, 10.0)
            group.on_loss("A")
            after = self.ack_delta(group, "B")
            return before, after

        for algorithm in ("lia", "olia"):
            with self.subTest(algorithm=algorithm):
                before, after = deltas(algorithm)
                # Halving A reduces the coupled denominator, so B's per-ACK
                # increase rises even though B's own window only grew.
                self.assertGreater(after, 1.5 * before)

        reno_before, reno_after = deltas("reno")
        self.assertLess(reno_after, reno_before)

    def test_equal_rtt_coupled_windows_stay_balanced(self):
        for algorithm in ("lia", "olia"):
            with self.subTest(algorithm=algorithm):
                group = self.make_group(algorithm)
                for round_index in range(100):
                    first, second = (
                        ("A", "B") if round_index % 2 == 0 else ("B", "A")
                    )
                    group.on_ack(first, 1000, 10.0)
                    group.on_ack(second, 1000, 10.0)
                windows = group.windows_bytes()
                self.assertLess(
                    abs(windows["A"] - windows["B"]),
                    0.01,
                    "coupled algorithms introduced asymmetry between equal-RTT subflows",
                )

    def test_reno_need_not_balance_asymmetric_loss_rates(self):
        group = self.make_group("reno")
        for round_index in range(200):
            group.on_ack("A", 1000, 10.0)
            group.on_ack("B", 1000, 10.0)
            if round_index % 10 == 9:
                group.on_loss("A")
            if round_index % 40 == 39:
                group.on_loss("B")
        windows = group.windows_bytes()
        ratio = min(windows.values()) / max(windows.values())
        jain = (windows["A"] + windows["B"]) ** 2 / (
            2.0 * (windows["A"] ** 2 + windows["B"] ** 2)
        )
        self.assertLess(ratio, 0.9)
        self.assertLess(jain, 0.95)

    def test_rates_use_window_rtt_and_optional_capacity_cap(self):
        group = CoupledCongestionGroup(
            "reno",
            [("A", 1000, 10.0), ("B", 1000, 20.0)],
            initial_window_segments={"A": 10, "B": 20},
            capacity_mbps={"A": 7.0},
        )
        rates = group.rates_mbps()
        self.assertAlmostEqual(rates["A"], 7.0)
        self.assertAlmostEqual(rates["B"], 8.0)

        capped = group.rates_mbps({"A": 5.0, "B": 10.0})
        self.assertAlmostEqual(capped["A"], 5.0)
        self.assertAlmostEqual(capped["B"], 8.0)

        with self.assertRaises(KeyError):
            group.rates_mbps({"missing": 1.0})
        with self.assertRaises(ValueError):
            group.rates_mbps({"A": -1.0})
        with self.assertRaises(ValueError):
            group.rates_mbps({"A": float("nan")})

    def test_input_validation(self):
        valid_paths = [("A", 1000), ("B", 1000)]

        with self.assertRaises(ValueError):
            CoupledCongestionGroup("cubic", valid_paths)
        with self.assertRaises(ValueError):
            CoupledCongestionGroup("reno", [])
        with self.assertRaises(ValueError):
            CoupledCongestionGroup("reno", [("A", 1000), ("A", 1000)])
        with self.assertRaises(ValueError):
            CoupledCongestionGroup("reno", [("A", 0)])
        with self.assertRaises(ValueError):
            CoupledCongestionGroup("reno", valid_paths, minimum_window_segments=0)
        with self.assertRaises(ValueError):
            CoupledCongestionGroup("reno", valid_paths, initial_window_segments=0)
        with self.assertRaises(KeyError):
            CoupledCongestionGroup(
                "reno",
                [("A", 1000)],
                initial_window_segments={"A": 10, "B": 5},
            )
        with self.assertRaises(ValueError):
            CoupledCongestionGroup(
                "reno",
                valid_paths,
                initial_window_segments={"A": 10},
            )
        with self.assertRaises(ValueError):
            CoupledCongestionGroup("reno", [("A", 1000, 0.0)])
        with self.assertRaises(ValueError):
            CoupledCongestionGroup("reno", [("A", 1000, -5.0)])
        with self.assertRaises(KeyError):
            CoupledCongestionGroup(
                "reno",
                valid_paths,
                capacity_mbps={"missing": 10.0},
            )
        with self.assertRaises(ValueError):
            CoupledCongestionGroup(
                "reno",
                valid_paths,
                capacity_mbps={"A": 0.0},
            )

        group = self.make_group("reno")
        with self.assertRaises(KeyError):
            group.on_ack("missing", 1000, 10.0)
        with self.assertRaises(ValueError):
            group.on_ack("A", -1, 10.0)
        with self.assertRaises(ValueError):
            group.on_ack("A", 1000, 0.0)
        with self.assertRaises(ValueError):
            group.on_ack("A", 1000, float("nan"))

        windows = group.windows_bytes()
        group.on_ack("A", 0, 10.0)
        self.assertEqual(group.windows_bytes(), windows)
        self.assertEqual(group.ack_count, 0)

        with self.assertRaises(ValueError):
            group.alpha()
        with self.assertRaises(ValueError):
            group.olia_alpha("A")

        lia_without_peer_rtt = CoupledCongestionGroup(
            "lia",
            [("A", 1000), ("B", 1000)],
        )
        with self.assertRaises(ValueError):
            lia_without_peer_rtt.on_ack("A", 1000, 10.0)
        with self.assertRaises(ValueError):
            lia_without_peer_rtt.rates_mbps()


class CongestionBenchmarkTests(unittest.TestCase):
    def test_seeded_runs_are_reproducible(self):
        first = simulate("olia", seed=11, duration_seconds=5.0)
        second = simulate("olia", seed=11, duration_seconds=5.0)
        self.assertEqual(first, second)

    def test_benchmark_smoke_writes_finite_csvs(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            rows = run_benchmark(
                output_dir,
                replicates=2,
                seed=9,
                duration_seconds=10.0,
            )

            self.assertEqual(len(rows), len(ALGORITHMS))
            for filename in (
                SUMMARY_FILENAME,
                REPLICATES_FILENAME,
                PAIRED_FILENAME,
            ):
                self.assertTrue((output_dir / filename).is_file(), filename)

            with (output_dir / SUMMARY_FILENAME).open(
                encoding="utf-8"
            ) as file:
                summary = list(csv.DictReader(file))
            self.assertEqual(len(summary), len(ALGORITHMS))
            for row in summary:
                for key, value in row.items():
                    if key in {"scenario", "algorithm"}:
                        continue
                    self.assertTrue(math.isfinite(float(value)), (key, value))
                self.assertGreaterEqual(float(row["total_goodput_mbps"]), 0.0)
                self.assertLessEqual(float(row["total_goodput_mbps"]), 28.001)
                self.assertGreaterEqual(float(row["jain_index"]), 0.0)
                self.assertLessEqual(float(row["jain_index"]), 1.0)
                for fraction in (
                    "ack_increase_fraction",
                    "coupled_ack_fraction",
                ):
                    self.assertGreaterEqual(float(row[fraction]), 0.0)
                    self.assertLessEqual(float(row[fraction]), 1.0)

            with (output_dir / REPLICATES_FILENAME).open(
                encoding="utf-8"
            ) as file:
                replicates = list(csv.DictReader(file))
            self.assertEqual(
                len(replicates),
                len(ALGORITHMS) * 2,
            )
            for row in replicates:
                self.assertTrue(
                    math.isfinite(float(row["total_goodput_mbps"]))
                )
                self.assertGreaterEqual(
                    float(row["convergence_seconds"]),
                    0.0,
                )

            with (output_dir / PAIRED_FILENAME).open(
                encoding="utf-8"
            ) as file:
                paired = list(csv.DictReader(file))
            self.assertEqual(len(paired), 3 * 9)
            for row in paired:
                for key in ("mean_difference", "ci95_low", "ci95_high"):
                    self.assertTrue(math.isfinite(float(row[key])), (key, row))


if __name__ == "__main__":
    unittest.main()
