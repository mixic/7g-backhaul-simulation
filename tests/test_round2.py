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

"""Unit tests for the round-2 harness (pure logic only).

No namespace, kernel facility, or root access is used.  The kernel-facing code is
exercised by ``python -m validation.round2.run``; here we pin the transcription of
the frozen file, the capture parser, the reference replay filter, the gates and the
verdict rules on synthetic observations.
"""

from __future__ import annotations

import socket
import struct
import unittest

from validation.round2 import predictions as pred
from validation.round2.capture import parse_frame
from validation.round2.cases import CASES, RunConfig, select_cases
from validation.round2.gates import depth_gate, ecn_gate, fragment_gate, spi_gate
from validation.round2.probe import not_run_reason, requirements
from validation.round2.replay import reference_accepted, reordering_depth
from validation.round2.verdict import (
    CONFIRMED,
    INCONCLUSIVE,
    INVALID,
    REFUTED,
    all_verdicts,
    brier_score,
    p13_verdict,
    p13h_verdict,
    p14_verdict,
    p15_verdicts,
    p16_verdict,
)

ETH = b"\x00" * 12 + b"\x08\x00"


def _frame(*, payload: bytes = b"", proto: int = 17, tos: int = 0, flags_frag: int = 0,
           src: str = "10.0.0.1", dst: str = "10.0.0.2", ip_len: int | None = None) -> bytes:
    total = 20 + len(payload) if ip_len is None else ip_len
    header = struct.pack("!BBHHHBBH4s4s", 0x45, tos, total, 1, flags_frag, 64, proto, 0,
                         socket.inet_aton(src), socket.inet_aton(dst))
    return ETH + header + payload


def _udp(sport: int, dport: int, body: bytes) -> bytes:
    return struct.pack("!HHHH", sport, dport, 8 + len(body), 0) + body


def _row(policy: str, run: int, metric: str, value: float) -> dict[str, object]:
    return {"source": "linux_real_stack_round2", "scenario": policy[:3], "policy": policy, "seed": run,
            "metric": metric, "value": value, "unit": "x"}


class FrozenTableTests(unittest.TestCase):
    def test_p15_wire_bytes_and_difference(self) -> None:
        self.assertEqual(pred.P15_TOTALS, {"E->F": 2112, "F->E": 2180})
        self.assertEqual(sum(pred.P15_PACKETS["E->F"]), 2112)
        self.assertEqual(sum(pred.P15_PACKETS["F->E"]), 2180)
        self.assertEqual(pred.P15_TOTALS["F->E"] - pred.P15_TOTALS["E->F"], pred.P15_TOTAL_DIFFERENCE)
        self.assertAlmostEqual(pred.P15_EXPECTED_DELIVERY, 0.9025)

    def test_p15_arithmetic_matches_the_frozen_calculation(self) -> None:
        pad = lambda length: 16 * -(-length // 16)  # noqa: E731
        outer_payload = 16 + pad(2028) + 16
        self.assertEqual(20 + 8 + outer_payload, 2092)  # the WG packet that IP then fragments
        fragments = (1500, 2092 - 1480)
        self.assertEqual(fragments, (1500, 612))
        self.assertEqual(sum(fragments), pred.P15_TOTALS["E->F"])
        inner = (1420, 628)
        fe = (60 + min(1420, pad(inner[0])), 60 + min(1420, pad(inner[1])))
        self.assertEqual(fe, (1480, 700))
        self.assertEqual(sum(fe), pred.P15_TOTALS["F->E"])

    def test_p16_windows_and_depth_gates(self) -> None:
        self.assertEqual(pred.P16_CASES["P16a"].window, 32)
        self.assertEqual(pred.P16_CASES["P16a"].min_depth, 64)
        self.assertEqual(pred.P16_CASES["P16b"].max_depth, 16)
        self.assertEqual(pred.P16_CASES["P16d"].window, 256)
        self.assertIsNone(pred.P16_CASES["P16c"].window)

    def test_p13_table(self) -> None:
        self.assertEqual(pred.P13_CASES["P13a"].delivery, 0)
        self.assertEqual(pred.P13_CASES["P13f"].inner_at_receiver, pred.ECN_NOT_ECT)
        self.assertEqual(pred.P13_CASES["P13g"].inner_at_receiver, pred.ECN_CE)
        self.assertIsNone(pred.P13_CASES["P13h_wg"].outer_tos)

    def test_credence_table_matches_frozen_section_9(self) -> None:
        self.assertEqual(pred.CREDENCE["P13a"], 0.90)
        self.assertEqual(pred.CREDENCE["P13f"], 0.60)
        self.assertEqual(pred.CREDENCE["P14a"], 0.60)
        self.assertEqual(pred.CREDENCE["P15_bytes"], 0.80)
        self.assertEqual(pred.CREDENCE["P15_delivery"], 0.75)
        self.assertEqual(pred.CREDENCE["P16a"], 0.85)
        self.assertEqual(len(pred.CREDENCE), 18)  # P13 h is one scored control prediction


class ParserTests(unittest.TestCase):
    def test_udp_wireguard_counter(self) -> None:
        body = bytes([4, 0, 0, 0]) + struct.pack("<I", 7) + (1234).to_bytes(8, "little") + b"x" * 8
        record = parse_frame(_frame(payload=_udp(51821, 51820, body)))
        assert record is not None
        self.assertEqual(record["proto"], 17)
        self.assertEqual(record["dport"], 51820)
        self.assertEqual(record["wg_type"], 4)
        self.assertEqual(record["wg_counter"], 1234)

    def test_esp_spi_and_sequence(self) -> None:
        record = parse_frame(_frame(payload=struct.pack("!II", 0xDEADBEEF, 41) + b"\x00" * 16, proto=50))
        assert record is not None
        self.assertEqual(record["esp_spi"], 0xDEADBEEF)
        self.assertEqual(record["esp_seq"], 41)

    def test_esp_in_udp(self) -> None:
        body = struct.pack("!II", 0x01020304, 9) + b"\x00" * 16
        record = parse_frame(_frame(payload=_udp(4500, 4500, body)))
        assert record is not None
        self.assertEqual(record["esp_spi"], 0x01020304)
        self.assertEqual(record["esp_seq"], 9)

    def test_fragment_flags_and_offsets(self) -> None:
        first = parse_frame(_frame(payload=b"y" * 100, flags_frag=0x2000))
        last = parse_frame(_frame(payload=b"y" * 100, flags_frag=0x00B9))
        assert first is not None and last is not None
        self.assertEqual((first["mf"], first["frag_off"], first["is_fragment"]), (1, 0, 1))
        self.assertEqual((last["mf"], last["frag_off"]), (0, 1480))
        # A non-first fragment carries no L4 header and must not be decoded as UDP.
        self.assertIsNone(last["dport"])

    def test_tos_is_recorded_verbatim(self) -> None:
        record = parse_frame(_frame(payload=_udp(1, 2, b"12345678"), tos=0x03))
        assert record is not None
        self.assertEqual(record["tos"], 0x03)


class ReferenceReplayTests(unittest.TestCase):
    def test_depth_of_ordered_trace_is_zero(self) -> None:
        self.assertEqual(reordering_depth([1, 2, 3, 4]), 0)

    def test_depth_of_one_swap(self) -> None:
        self.assertEqual(reordering_depth([1, 3, 2, 4]), 1)

    def test_depth_of_delayed_burst(self) -> None:
        self.assertEqual(reordering_depth([5, 6, 7, 1, 2, 3]), 6)

    def test_window_accepts_new_maxima_and_recent_packets(self) -> None:
        self.assertEqual(reference_accepted([1, 2, 3, 4], 32), 4)
        self.assertEqual(reference_accepted([1, 2, 4, 3], 32), 4)

    def test_window_rejects_too_late_and_repeats(self) -> None:
        # 2 and 3 were already received inside the window, so they are replays;
        # 1 is 4 behind the maximum and outside the window.
        self.assertEqual(reference_accepted([1, 2, 3, 4, 5, 2, 1, 3], 4), 5)
        # A packet that is late but new is accepted, and the maximum advances.
        self.assertEqual(reference_accepted([1, 2, 3, 4, 5, 7, 6], 4), 7)


class GateTests(unittest.TestCase):
    def test_ecn_gate_accepts_a_fully_marked_capture(self) -> None:
        before = [{"tos": 0x00}, {"tos": 0x02}]
        after = [{"tos": 0x03}, {"tos": 0x03}]
        ok, _ = ecn_gate(before, after, target_tos=0x03, expected=2)
        self.assertTrue(ok)

    def test_ecn_gate_rejects_a_missed_packet_or_a_dscp_change(self) -> None:
        self.assertFalse(ecn_gate([{"tos": 0}], [{"tos": 0x03}], target_tos=0x03, expected=2)[0])
        self.assertFalse(ecn_gate([{"tos": 0}], [{"tos": 0x0B}], target_tos=0x03, expected=1)[0])
        self.assertFalse(ecn_gate([{"tos": 0x03}], [{"tos": 0x03}], target_tos=0x03, expected=1)[0])

    def test_spi_gate_requires_absence_for_a_dropped_client(self) -> None:
        records = [{"esp_spi": 0x1}, {"esp_spi": 0x1}]
        self.assertTrue(spi_gate(records, spis=[0x1, 0x2], drops=[False, True])[0])
        self.assertFalse(spi_gate(records, spis=[0x1, 0x2], drops=[True, True])[0])

    def test_fragment_gate_encrypt_then_fragment(self) -> None:
        records = [{"ip_len": 1500, "mf": 1, "frag_off": 0},
                   {"ip_len": 612, "mf": 0, "frag_off": 1480}]
        self.assertTrue(fragment_gate(records, ordering="E->F", expected_datagrams=1)[0])
        records[0]["ip_len"] = 1480
        self.assertFalse(fragment_gate(records, ordering="E->F", expected_datagrams=1)[0])

    def test_fragment_gate_fragment_then_encrypt(self) -> None:
        records = [{"ip_len": 1480, "mf": 0, "frag_off": 0},
                   {"ip_len": 700, "mf": 0, "frag_off": 0}]
        self.assertTrue(fragment_gate(records, ordering="F->E", expected_datagrams=1)[0])
        records[1]["mf"] = 1
        self.assertFalse(fragment_gate(records, ordering="F->E", expected_datagrams=1)[0])

    def test_depth_gate_bounds(self) -> None:
        self.assertFalse(depth_gate(32, min_depth=64, max_depth=None)[0])
        self.assertTrue(depth_gate(64, min_depth=64, max_depth=None)[0])
        self.assertFalse(depth_gate(17, min_depth=0, max_depth=16)[0])
        self.assertTrue(depth_gate(16, min_depth=0, max_depth=16)[0])


class VerdictTests(unittest.TestCase):
    def test_p13_ipip_drop_with_the_named_cause(self) -> None:
        rows = [_row("P13a", 0, "warmup_ok", 1), _row("P13a", 0, "ecn_gate", 1),
                _row("P13a", 0, "delivery_percent", 0), _row("P13a", 0, "inner_ecn_ok", 1),
                _row("P13a", 0, "cause_gate", 1), _row("P13a", 0, "ipip_rx_frame_errors_delta", 50)]
        self.assertEqual(p13_verdict("P13a", _m(rows, "P13a"))["verdict"], CONFIRMED)
        rows[-1] = _row("P13a", 0, "ipip_rx_frame_errors_delta", 0)
        rows[-2] = _row("P13a", 0, "cause_gate", 0)
        self.assertEqual(p13_verdict("P13a", _m(rows, "P13a"))["verdict"], INCONCLUSIVE)

    def test_p13_delivery_or_mutation_anomalies(self) -> None:
        base = [_row("P13b", 0, "warmup_ok", 1), _row("P13b", 0, "ecn_gate", 1),
                _row("P13b", 0, "delivery_percent", 100), _row("P13b", 0, "inner_ecn_ok", 1)]
        self.assertEqual(p13_verdict("P13b", _m(base, "P13b"))["verdict"], CONFIRMED)
        base[2] = _row("P13b", 0, "delivery_percent", 90)
        self.assertEqual(p13_verdict("P13b", _m(base, "P13b"))["verdict"], REFUTED)
        base[2] = _row("P13b", 0, "delivery_percent", 100)
        base[1] = _row("P13b", 0, "ecn_gate", 0)
        self.assertEqual(p13_verdict("P13b", _m(base, "P13b"))["verdict"], INVALID)

    def test_p13_inner_ecn_change_refutes(self) -> None:
        rows = [_row("P13g", 0, "warmup_ok", 1), _row("P13g", 0, "ecn_gate", 1),
                _row("P13g", 0, "delivery_percent", 100), _row("P13g", 0, "inner_ecn_ok", 0)]
        self.assertEqual(p13_verdict("P13g", _m(rows, "P13g"))["verdict"], REFUTED)

    def test_p13_control(self) -> None:
        rows = [_row("P13h_wg", 0, "warmup_ok", 1), _row("P13h_wg", 0, "offload_disabled", 1),
                _row("P13h_wg", 0, "delivery_percent", 100), _row("P13h_wg", 0, "inner_ecn_ok", 1)]
        self.assertEqual(p13h_verdict("P13h_wg", _m(rows, "P13h_wg"))["verdict"], CONFIRMED)
        rows[3] = _row("P13h_wg", 0, "inner_ecn_ok", 0)
        self.assertEqual(p13h_verdict("P13h_wg", _m(rows, "P13h_wg"))["verdict"], REFUTED)

    def test_p14_first_come_wins(self) -> None:
        rows = [_row("P14a", 0, "warmup_ok", 1), _row("P14a", 0, "nat_gate", 1),
                _row("P14a", 0, "spi_gate", 1), _row("P14a", 0, "delivery_percent_client1", 100),
                _row("P14a", 0, "delivery_percent_client2", 0)]
        self.assertEqual(p14_verdict("P14a", _m(rows, "P14a"))["verdict"], CONFIRMED)
        rows[-1] = _row("P14a", 0, "delivery_percent_client2", 100)
        self.assertEqual(p14_verdict("P14a", _m(rows, "P14a"))["verdict"], REFUTED)
        rows[-1] = _row("P14a", 0, "delivery_percent_client2", 40)
        self.assertEqual(p14_verdict("P14a", _m(rows, "P14a"))["verdict"], INCONCLUSIVE)
        rows[-1] = _row("P14a", 0, "delivery_percent_client2", 0)
        rows[2] = _row("P14a", 0, "spi_gate", 0)
        self.assertEqual(p14_verdict("P14a", _m(rows, "P14a"))["verdict"], INVALID)

    def test_p14_control_needs_both_clients(self) -> None:
        rows = [_row("P14d", 0, "warmup_ok", 1), _row("P14d", 0, "nat_gate", 1),
                _row("P14d", 0, "spi_gate", 1), _row("P14d", 0, "delivery_percent_client1", 100),
                _row("P14d", 0, "delivery_percent_client2", 100)]
        self.assertEqual(p14_verdict("P14d", _m(rows, "P14d"))["verdict"], CONFIRMED)
        rows[-1] = _row("P14d", 0, "delivery_percent_client2", 98)
        self.assertEqual(p14_verdict("P14d", _m(rows, "P14d"))["verdict"], REFUTED)

    def test_p15_bytes_and_delivery(self) -> None:
        rows = []
        for ordering, total in pred.P15_TOTALS.items():
            policy = f"P15_{ordering.replace('->', 'to')}"
            for run in range(20):
                rows += [_row(policy, run, "warmup_ok", 1), _row(policy, run, "offload_disabled", 1),
                         _row(policy, run, "fragment_gate", 1),
                         _row(policy, run, "wire_bytes_per_datagram", total),
                         _row(policy, run, "delivered_datagrams", 451), _row(policy, run, "sent_datagrams", 500)]
        verdicts = {item["case"]: item["verdict"] for item in p15_verdicts(_table(rows))}
        self.assertEqual(verdicts, {"P15a": CONFIRMED, "P15b": CONFIRMED})

    def test_p15_refutes_on_a_byte_difference_or_a_pooled_skew(self) -> None:
        rows = []
        for ordering, total in pred.P15_TOTALS.items():
            policy = f"P15_{ordering.replace('->', 'to')}"
            rows += [_row(policy, 0, "warmup_ok", 1), _row(policy, 0, "offload_disabled", 1),
                     _row(policy, 0, "fragment_gate", 1), _row(policy, 0, "wire_bytes_per_datagram", total),
                     _row(policy, 0, "delivered_datagrams", 500), _row(policy, 0, "sent_datagrams", 500)]
        verdicts = {item["case"]: item["verdict"] for item in p15_verdicts(_table(rows))}
        self.assertEqual(verdicts["P15a"], CONFIRMED)
        self.assertEqual(verdicts["P15b"], REFUTED)  # 100 % is outside 0.9025 +/- 1.5 pp

    def test_p16a_needs_an_exact_match_with_the_reference(self) -> None:
        rows = [_row("P16a", 0, "warmup_ok", 1), _row("P16a", 0, "offload_disabled", 1),
                _row("P16a", 0, "depth_gate", 1), _row("P16a", 0, "reorder_depth", 500),
                _row("P16a", 0, "delivery_matches_reference", 1), _row("P16a", 0, "delivered_datagrams", 536),
                _row("P16a", 0, "reference_accepted", 536), _row("P16a", 0, "cause_gate", 1)]
        self.assertEqual(p16_verdict("P16a", _m(rows, "P16a"))["verdict"], CONFIRMED)
        rows[-1] = _row("P16a", 0, "cause_gate", 0)
        self.assertEqual(p16_verdict("P16a", _m(rows, "P16a"))["verdict"], INCONCLUSIVE)
        rows[-1] = _row("P16a", 0, "cause_gate", 1)
        rows[4] = _row("P16a", 0, "delivery_matches_reference", 0)
        self.assertEqual(p16_verdict("P16a", _m(rows, "P16a"))["verdict"], REFUTED)
        rows[4] = _row("P16a", 0, "delivery_matches_reference", 1)
        rows[2] = _row("P16a", 0, "depth_gate", 0)
        self.assertEqual(p16_verdict("P16a", _m(rows, "P16a"))["verdict"], INVALID)

    def test_p16b_and_d_need_full_delivery(self) -> None:
        for case in ("P16b", "P16d"):
            rows = [_row(case, 0, "warmup_ok", 1), _row(case, 0, "offload_disabled", 1),
                    _row(case, 0, "depth_gate", 1), _row(case, 0, "sent_datagrams", 2000),
                    _row(case, 0, "delivered_datagrams", 2000), _row(case, 0, "cause_gate", 1)]
            self.assertEqual(p16_verdict(case, _m(rows, case))["verdict"], CONFIRMED)
            rows[-3] = _row(case, 0, "delivered_datagrams", 1999)
            self.assertEqual(p16_verdict(case, _m(rows, case))["verdict"], REFUTED)

    def test_all_verdicts_marks_a_case_invalid_when_its_control_fails(self) -> None:
        rows = [_row("P13h_ipip", 0, "warmup_ok", 1), _row("P13h_ipip", 0, "offload_disabled", 1),
                _row("P13h_ipip", 0, "delivery_percent", 60), _row("P13h_ipip", 0, "inner_ecn_ok", 1),
                _row("P13a", 0, "warmup_ok", 1), _row("P13a", 0, "ecn_gate", 1),
                _row("P13a", 0, "delivery_percent", 0), _row("P13a", 0, "inner_ecn_ok", 1),
                _row("P13a", 0, "cause_gate", 1)]
        verdicts = {item["case"]: item["verdict"] for item in all_verdicts(rows)}
        self.assertEqual(verdicts["P13h_ipip"], REFUTED)
        self.assertEqual(verdicts["P13a"], INVALID)


class BrierTests(unittest.TestCase):
    def test_brier_of_two_confirmed_bets(self) -> None:
        verdicts = [{"prediction": "P13", "case": "P13a", "verdict": CONFIRMED, "detail": ""},
                    {"prediction": "P13", "case": "P13f", "verdict": REFUTED, "detail": ""}]
        score, scored, missing, unscored = brier_score(verdicts)
        self.assertEqual(scored, 2)
        self.assertAlmostEqual(score, ((0.90 - 1) ** 2 + (0.60 - 0) ** 2) / 2)
        self.assertIn("P16a", missing)
        self.assertEqual(unscored, [])

    def test_unscored_dispositions_do_not_enter_the_score(self) -> None:
        verdicts = [{"prediction": "P14", "case": "P14a", "verdict": INCONCLUSIVE, "detail": ""},
                    {"prediction": "P15", "case": "P15a", "verdict": INVALID, "detail": ""},
                    {"prediction": "P16", "case": "P16a", "verdict": "NOT RUN", "detail": ""}]
        score, scored, _missing, unscored = brier_score(verdicts)
        self.assertEqual((scored, score), (0, 0.0))
        self.assertEqual(len(unscored), 3)

    def test_control_set_counts_once(self) -> None:
        verdicts = [{"prediction": "P13", "case": case, "verdict": CONFIRMED, "detail": ""}
                    for case in ("P13h_ipip", "P13h_wg", "P13h_esp")]
        score, scored, _missing, _unscored = brier_score(verdicts)
        self.assertEqual(scored, 1)
        self.assertAlmostEqual(score, (0.95 - 1) ** 2)


class HarnessTests(unittest.TestCase):
    def test_case_inventory(self) -> None:
        ids = [case.id for case in CASES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len([case for case in CASES if case.prediction == "P13"]), 10)
        self.assertEqual([case for case in CASES if case.prediction == "P14"].__len__(), 4)
        self.assertEqual([case.id for case in CASES if case.prediction == "P15"], ["P15_EtoF", "P15_FtoE"])
        self.assertEqual([case.id for case in CASES if case.prediction == "P16"],
                         ["P16a", "P16b", "P16c", "P16d"])

    def test_select_cases_by_id_or_prediction(self) -> None:
        self.assertEqual([case.id for case in select_cases("P13a")], ["P13a"])
        self.assertEqual(len(select_cases("P16")), 4)
        with self.assertRaises(SystemExit):
            select_cases("P99")

    def test_requirements_name_the_facilities_the_frozen_file_needs(self) -> None:
        case = {item.id: item for item in CASES}["P16a"]
        needed = requirements(case)
        self.assertIn("xfrm_esp", needed)
        self.assertIn("replay_window", needed)
        self.assertIn("tc_netem_reorder", needed)
        self.assertEqual(not_run_reason(case, {name: None for name in needed}), None)
        self.assertIn("replay_window", not_run_reason(case, {**{name: None for name in needed},
                                                             "replay_window": "missing"}))

    def test_run_config_stipulates_the_frozen_parameters(self) -> None:
        config = RunConfig()
        self.assertEqual(config.runs, 20)
        self.assertEqual(config.datagrams, 50)
        self.assertEqual(config.p15_datagrams, 500)
        self.assertEqual(config.p16_datagrams, 2000)


def _table(rows: list[dict[str, object]]) -> dict[str, dict[str, list[float]]]:
    table: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        table.setdefault(str(row["policy"]), {}).setdefault(str(row["metric"]), []).append(float(row["value"]))
    return table


if __name__ == "__main__":
    unittest.main()


def _m(rows: list[dict[str, object]], policy: str) -> dict[str, list[float]]:
    return _table(rows).get(policy, {})
