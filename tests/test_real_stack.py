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

"""Unit tests for the real-stack harness (pure logic only).

No namespace, kernel facility, or root access is used.  The kernel-facing code is
exercised by ``python -m validation.real_stack.run`` on a suitable host; here we
check the arithmetic against the frozen tables, the parsers, the gates, and the
verdict rules on synthetic observations.
"""

from __future__ import annotations

import csv
import struct
import tempfile
import unittest
from pathlib import Path

from validation.real_stack import counters, predictions as pred
from validation.real_stack.capture import parse_frame
from validation.real_stack.cases import CASES, RunConfig, run_case, select_cases
from validation.real_stack.gates import cause_gate, mutation_gate
from validation.real_stack.probe import not_run_reason, requirements
from validation.real_stack.run import write_summary, write_verdicts
from validation.real_stack.shell import Shell
from validation.real_stack.topology import parse_offload_off
from validation.real_stack.verdict import (
    CONFIRMED,
    INCONCLUSIVE,
    INVALID,
    REFUTED,
    all_verdicts,
    p10_verdicts,
    p9_verdict,
)

A, N = "10.200.1.2", "10.200.2.1"


def _row(scenario: str, policy: str, run: int, metric: str, value: float) -> dict[str, object]:
    return {"source": "linux_real_stack", "scenario": scenario, "policy": policy, "seed": run,
            "metric": metric, "value": value, "unit": "x"}


class FrozenTableTests(unittest.TestCase):
    def test_p9_formula_matches_frozen_table(self) -> None:
        for length, wire in pred.P9_FROZEN_WIRE.items():
            self.assertEqual(pred.wg_wire(length), wire, length)
            self.assertEqual(pred.p9_deviation(length), pred.P9_FROZEN_DEVIATION[length], length)

    def test_p10_formulas_match_frozen_tables(self) -> None:
        for length in pred.P10_LENGTHS:
            self.assertEqual(pred.p10_wire_y_to_w(length), pred.P10_FROZEN_Y_TO_W[length], length)
            self.assertEqual(pred.p10_wire_w_to_y(length), pred.P10_FROZEN_W_TO_Y[length], length)
            self.assertEqual(pred.p10_d(length), pred.P10_FROZEN_D[length], length)

    def test_p10_difference_depends_only_on_length_mod_16(self) -> None:
        for length in range(16, 2000):
            expected = -4 if 1 <= length % 16 <= 12 else 12
            self.assertEqual(pred.p10_d(length), expected, length)

    def test_p10_never_zero_so_naive_commutation_cannot_hold(self) -> None:
        self.assertTrue(all(pred.p10_d(length) != 0 for length in range(16, 2000)))

    def test_wg_wire_rejects_lengths_beyond_mtu(self) -> None:
        with self.assertRaises(ValueError):
            pred.wg_wire(1420 + 1)


class ParserTests(unittest.TestCase):
    @staticmethod
    def _frame(proto: int = 17, ip_len: int = 100, src=(10, 200, 1, 2), udp_len: int = 72, tos: int = 0) -> bytes:
        ip = struct.pack("!BBHHHBBH4s4s", 0x45, tos, ip_len, 0, 0, 64, proto, 0, bytes(src), bytes((10, 200, 2, 2)))
        udp = struct.pack("!HHHH", 51821, 51820, udp_len, 0)
        return b"\x00" * 12 + b"\x08\x00" + ip + udp + b"\x00" * 64

    def test_parse_udp_frame(self) -> None:
        record = parse_frame(self._frame(tos=0x10))
        self.assertEqual(record["ip_len"], 100)
        self.assertEqual(record["src"], "10.200.1.2")
        self.assertEqual((record["sport"], record["dport"], record["udp_len"]), (51821, 51820, 72))
        self.assertEqual(record["tos"], 0x10)

    def test_non_udp_has_no_ports(self) -> None:
        record = parse_frame(self._frame(proto=50))
        self.assertEqual(record["proto"], 50)
        self.assertIsNone(record["dport"])

    def test_non_ipv4_is_ignored(self) -> None:
        frame = bytearray(self._frame())
        frame[12:14] = b"\x86\xdd"
        self.assertIsNone(parse_frame(bytes(frame)))
        self.assertIsNone(parse_frame(b"\x00" * 10))

    def test_xfrm_error_sum_uses_only_in_error_counters(self) -> None:
        stats = counters.parse_xfrm_stat(
            "XfrmInError 0\nXfrmInStateProtoError 3\nXfrmInStateSeqError 1\nXfrmOutError 9\nXfrmInNoStates 7\n")
        self.assertEqual(counters.xfrm_in_error_total(stats), 4)

    def test_snmp_udp_parser(self) -> None:
        text = ("Ip: Forwarding\nIp: 1\n"
                "Udp: InDatagrams NoPorts InErrors OutDatagrams RcvbufErrors SndbufErrors InCsumErrors\n"
                "Udp: 10 1 2 11 0 0 5\n")
        self.assertEqual(counters.parse_snmp_udp(text)["InCsumErrors"], 5)

    def test_wg_parsers(self) -> None:
        self.assertEqual(counters.parse_wg_transfer("KEY1\t100\t200\nKEY2\t5\t6\n"), (105, 206))
        self.assertEqual(counters.parse_wg_endpoints("KEY\t10.200.2.1:51821\n"), [("10.200.2.1", 51821)])
        self.assertEqual(counters.parse_wg_endpoints("KEY\t(none)\n"), [])


class OffloadTests(unittest.TestCase):
    def test_checksum_offload_must_be_off_in_both_directions(self) -> None:
        off = "rx-checksumming: off\ntx-checksumming: off\n\ttx-checksum-ipv4: off [requested on]\n"
        self.assertTrue(parse_offload_off(off))
        self.assertTrue(parse_offload_off("rx-checksumming: off [fixed]\ntx-checksumming: off\n"))
        self.assertFalse(parse_offload_off("rx-checksumming: on\ntx-checksumming: off\n"))
        self.assertFalse(parse_offload_off("rx-checksumming: off\ntx-checksumming: on\n"))
        self.assertFalse(parse_offload_off("rx-checksumming: on [fixed]\ntx-checksumming: off\n"))
        self.assertFalse(parse_offload_off(""))


class GateTests(unittest.TestCase):
    @staticmethod
    def _pkts(count: int, **fields) -> list[dict[str, object]]:
        return [dict({"src": A, "udp_len": 100, "tos": 0}, **fields) for _ in range(count)]

    def test_nat_gate_requires_all_packets_translated(self) -> None:
        ok, _ = mutation_gate("nat", self._pkts(50), self._pkts(50, src=N), 50, original_src=A, nat_src=N)
        self.assertTrue(ok)
        leaked = self._pkts(49, src=N) + self._pkts(1)
        self.assertFalse(mutation_gate("nat", self._pkts(50), leaked, 50, original_src=A, nat_src=N)[0])

    def test_nat_gate_fails_when_nothing_was_rewritten(self) -> None:
        self.assertFalse(mutation_gate("nat", self._pkts(50), self._pkts(50), 50, original_src=A, nat_src=N)[0])

    def test_none_gate_detects_unexpected_rewrite(self) -> None:
        self.assertTrue(mutation_gate("none", self._pkts(5), self._pkts(5), 5, original_src=A, nat_src=N)[0])
        self.assertFalse(mutation_gate("none", self._pkts(5), self._pkts(5, src=N), 5, original_src=A, nat_src=N)[0])

    def test_len9_and_tos_gates(self) -> None:
        self.assertTrue(mutation_gate("len9", self._pkts(5), self._pkts(5, udp_len=9), 5, original_src=A, nat_src=N)[0])
        self.assertFalse(mutation_gate("len9", self._pkts(5), self._pkts(5), 5, original_src=A, nat_src=N)[0])
        self.assertTrue(mutation_gate("tos", self._pkts(5), self._pkts(5, tos=0x10), 5, original_src=A, nat_src=N)[0])
        self.assertFalse(mutation_gate("tos", self._pkts(5, tos=0x10), self._pkts(5, tos=0x10), 5, original_src=A, nat_src=N)[0])

    def test_gate_fails_when_packets_are_missing(self) -> None:
        self.assertFalse(mutation_gate("nat", self._pkts(3), self._pkts(3, src=N), 50, original_src=A, nat_src=N)[0])

    def test_cause_gates_follow_frozen_text(self) -> None:
        self.assertTrue(cause_gate("P8a", {"xfrm_in_error_delta": 50}, 50)[0])
        self.assertFalse(cause_gate("P8a", {"xfrm_in_error_delta": 0}, 50)[0])
        self.assertTrue(cause_gate("P11a", {"udp_in_csum_delta": 0, "wg_rx_delta": 0}, 50)[0])
        self.assertTrue(cause_gate("P11a", {"udp_in_csum_delta": 7, "wg_rx_delta": 400}, 50)[0])
        self.assertFalse(cause_gate("P11a", {"udp_in_csum_delta": 0, "wg_rx_delta": 400}, 50)[0])
        self.assertFalse(cause_gate("P11b", {"wg_rx_delta": 400}, 50)[0])
        self.assertTrue(cause_gate("P12a", {"udp_in_csum_delta": 50}, 50)[0])
        self.assertFalse(cause_gate("P12a", {"udp_in_csum_delta": 49}, 50)[0])
        self.assertTrue(cause_gate("P8b", {}, 50)[0])


def _delivery_rows(case_id: str, scenario: str, delivery: float, *, runs: int = 3, mutation: int = 1,
                   cause: int = 1, offload: int = 1, extra: dict[str, float] | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for run in range(runs):
        values = {"warmup_ok": 1, "offload_disabled": offload, "delivery_percent": delivery,
                  "mutation_gate": mutation, "cause_gate": cause, "endpoint_gate": 1, **(extra or {})}
        rows.extend(_row(scenario, case_id, run, metric, value) for metric, value in values.items())
    return rows


def _verdict_of(rows, case_id):
    return next(v for v in all_verdicts(rows) if v["case"] == case_id)


class VerdictTests(unittest.TestCase):
    def test_p8a_confirmed_when_all_dropped_for_the_right_reason(self) -> None:
        rows = _delivery_rows("P8a", "P8", 0.0) + _delivery_rows("P8a_control", "P8", 100.0)
        self.assertEqual(_verdict_of(rows, "P8a")["verdict"], CONFIRMED)

    def test_p8a_inconclusive_when_cause_gate_fails(self) -> None:
        rows = _delivery_rows("P8a", "P8", 0.0, cause=0) + _delivery_rows("P8a_control", "P8", 100.0)
        self.assertEqual(_verdict_of(rows, "P8a")["verdict"], INCONCLUSIVE)

    def test_p8a_refuted_when_ah_survives_nat(self) -> None:
        rows = _delivery_rows("P8a", "P8", 100.0) + _delivery_rows("P8a_control", "P8", 100.0)
        self.assertEqual(_verdict_of(rows, "P8a")["verdict"], REFUTED)

    def test_p8b_refuted_when_esp_is_rejected(self) -> None:
        rows = _delivery_rows("P8b", "P8", 0.0) + _delivery_rows("P8b_control", "P8", 100.0)
        self.assertEqual(_verdict_of(rows, "P8b")["verdict"], REFUTED)

    def test_failed_mutation_gate_is_invalid_not_refuted(self) -> None:
        rows = _delivery_rows("P8b", "P8", 0.0, mutation=0) + _delivery_rows("P8b_control", "P8", 100.0)
        self.assertEqual(_verdict_of(rows, "P8b")["verdict"], INVALID)

    def test_broken_control_makes_the_case_invalid(self) -> None:
        rows = _delivery_rows("P8c", "P8", 100.0) + _delivery_rows("P8c_control", "P8", 0.0)
        self.assertEqual(_verdict_of(rows, "P8c")["verdict"], INVALID)
        self.assertEqual(_verdict_of(rows, "P8c_control")["verdict"], INVALID)

    def test_single_deviating_run_refutes_a_100_percent_prediction(self) -> None:
        rows = _delivery_rows("P8c", "P8", 100.0, runs=2) + _delivery_rows("P8c_control", "P8", 100.0)
        rows[0]["value"] = rows[0]["value"]
        for row in rows:
            if row["policy"] == "P8c" and row["metric"] == "delivery_percent" and row["seed"] == 1:
                row["value"] = 98.0
        self.assertEqual(_verdict_of(rows, "P8c")["verdict"], REFUTED)

    def test_p12_invalid_when_offload_cannot_be_disabled(self) -> None:
        rows = _delivery_rows("P12a", "P12", 0.0, offload=0) + _delivery_rows("P12c", "P12", 100.0)
        self.assertEqual(_verdict_of(rows, "P12a")["verdict"], INVALID)

    def test_setup_error_is_invalid(self) -> None:
        rows = _delivery_rows("P11c", "P11", 100.0) + [_row("P11", "P11c", 5, "setup_error", 1)]
        self.assertEqual(_verdict_of(rows, "P11c")["verdict"], INVALID)

    @staticmethod
    def _sweep_rows(case_id: str, scenario: str, lengths, wire_of, runs: int = 2) -> list[dict[str, object]]:
        rows = []
        for run in range(runs):
            rows.append(_row(scenario, case_id, run, "delivery_percent", 100.0))
            for length in lengths:
                policy = f"{case_id}_L{length}"
                rows.append(_row(scenario, policy, run, "wire_packets", 5))
                rows.append(_row(scenario, policy, run, "expected_packets", 5))
                rows.append(_row(scenario, policy, run, "wire_bytes_min", wire_of(length)))
                rows.append(_row(scenario, policy, run, "wire_bytes_max", wire_of(length)))
        return rows

    def test_p9_confirmed_on_exact_formula(self) -> None:
        rows = self._sweep_rows("P9", "P9", pred.P9_LENGTHS, pred.wg_wire)
        self.assertEqual(p9_verdict(rows)["verdict"], CONFIRMED)

    def test_p9_refuted_when_one_length_differs(self) -> None:
        rows = self._sweep_rows("P9", "P9", pred.P9_LENGTHS, lambda length: pred.wg_wire(length) + (4 if length == 100 else 0))
        verdict = p9_verdict(rows)
        self.assertEqual(verdict["verdict"], REFUTED)
        self.assertIn("L=100", verdict["detail"])

    def test_p9_invalid_when_capture_count_is_wrong(self) -> None:
        rows = self._sweep_rows("P9", "P9", pred.P9_LENGTHS, pred.wg_wire)
        for row in rows:
            if row["policy"] == "P9_L61" and row["metric"] == "wire_packets":
                row["value"] = 6
        self.assertEqual(p9_verdict(rows)["verdict"], INVALID)

    def test_p10_both_confirmed_on_quantised_model(self) -> None:
        rows = (self._sweep_rows("P10_y_to_w", "P10", pred.P10_LENGTHS, pred.p10_wire_y_to_w)
                + self._sweep_rows("P10_w_to_y", "P10", pred.P10_LENGTHS, pred.p10_wire_w_to_y))
        verdicts = {v["case"]: v["verdict"] for v in p10_verdicts(rows)}
        self.assertEqual(verdicts, {"P10a": CONFIRMED, "P10b": CONFIRMED})

    def test_p10a_refuted_when_orderings_commute(self) -> None:
        rows = (self._sweep_rows("P10_y_to_w", "P10", pred.P10_LENGTHS, pred.p10_wire_w_to_y)
                + self._sweep_rows("P10_w_to_y", "P10", pred.P10_LENGTHS, pred.p10_wire_w_to_y))
        verdicts = {v["case"]: v["verdict"] for v in p10_verdicts(rows)}
        self.assertEqual(verdicts["P10a"], REFUTED)
        self.assertEqual(verdicts["P10b"], REFUTED)

    def test_p10b_refuted_by_a_single_wrong_difference(self) -> None:
        def y_to_w(length: int) -> int:
            return pred.p10_wire_y_to_w(length) + (16 if length == 77 else 0)
        rows = (self._sweep_rows("P10_y_to_w", "P10", pred.P10_LENGTHS, y_to_w)
                + self._sweep_rows("P10_w_to_y", "P10", pred.P10_LENGTHS, pred.p10_wire_w_to_y))
        verdicts = {v["case"]: v["verdict"] for v in p10_verdicts(rows)}
        self.assertEqual(verdicts["P10a"], CONFIRMED)
        self.assertEqual(verdicts["P10b"], REFUTED)


class OutputTests(unittest.TestCase):
    def test_verdict_and_summary_writers(self) -> None:
        verdicts = [
            {"prediction": "P9", "case": "P9", "verdict": CONFIRMED, "detail": "exact"},
            {"prediction": "P8", "case": "P8a", "verdict": "NOT RUN", "detail": "tool:ip: `ip` not installed"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_verdicts(out / "verdicts.csv", verdicts)
            write_summary(out / "summary.md", "kernel: test\n", verdicts, RunConfig())
            with (out / "verdicts.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            text = (out / "summary.md").read_text(encoding="utf-8")
        self.assertEqual([row["verdict"] for row in rows], [CONFIRMED, "NOT RUN"])
        self.assertIn("**NOT RUN**", text)
        self.assertIn("20 runs per case", text)


class CaseAndProbeTests(unittest.TestCase):
    def test_case_ids_are_unique_and_cover_every_prediction(self) -> None:
        ids = [case.id for case in CASES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({case.prediction for case in CASES}, {"P8", "P9", "P10", "P11", "P12"})

    def test_select_cases_accepts_prediction_and_case_ids(self) -> None:
        self.assertEqual({c.id for c in select_cases("P11")}, {"P11a", "P11b", "P11c"})
        self.assertEqual([c.id for c in select_cases("P8a,P9")], ["P8a", "P9"])
        with self.assertRaises(SystemExit):
            select_cases("P99")

    def test_requirements_follow_the_stack(self) -> None:
        by_id = {case.id: case for case in CASES}
        self.assertIn("xfrm_ah", requirements(by_id["P8a"]))
        self.assertIn("nft_masq", requirements(by_id["P8a"]))
        self.assertNotIn("nft_masq", requirements(by_id["P8a_control"]))
        self.assertIn("tc_pedit_csum", requirements(by_id["P11b"]))
        self.assertIn("offload", requirements(by_id["P12a"]))
        self.assertIn("ipip", requirements(by_id["P10_w_to_y"]))

    def test_missing_facility_yields_not_run_reason(self) -> None:
        case = next(c for c in CASES if c.id == "P9")
        facilities = {name: None for name in requirements(case)}
        self.assertIsNone(not_run_reason(case, facilities))
        facilities["wireguard"] = "Operation not supported"
        reason = not_run_reason(case, facilities)
        self.assertIn("wireguard", reason)

    def test_dry_run_issues_commands_for_every_case_and_runs_nothing(self) -> None:
        for case in CASES:
            shell = Shell(dry_run=True)
            self.assertEqual(run_case(case, 0, RunConfig(), shell), [])
            script = shell.script()
            self.assertIn("ip netns add rsA", script, case.id)
            self.assertIn("validation.real_stack.udp_tool send", script, case.id)
            self.assertIn("ip netns del rsA", script, case.id)

    def test_dry_run_scripts_contain_the_frozen_configuration(self) -> None:
        def script(case_id: str) -> str:
            shell = Shell(dry_run=True)
            run_case(next(c for c in CASES if c.id == case_id), 0, RunConfig(), shell)
            return shell.script()

        self.assertIn("proto ah", script("P8a"))
        self.assertIn("masquerade", script("P8a"))
        self.assertNotIn("masquerade", script("P8a_control"))
        self.assertIn("proto esp", script("P8b"))
        self.assertIn("type wireguard", script("P8c"))
        self.assertIn("type ipip", script("P10_y_to_w"))
        # P11 uses the raw-offset syntax: iproute2 6.19 rejects `munge udp len`,
        # which has no parser support.  Offset 24 is the UDP length field of an
        # IPv4 header with no options (20-byte IP + 4-byte src/dst-port header).
        self.assertIn("munge offset 24 u16 set 0x0009", script("P11a"))
        self.assertNotIn("csum udp", script("P11a"))
        self.assertIn("csum udp", script("P11b"))
        self.assertIn("munge ip tos set 0x10", script("P11c"))
        self.assertIn("csum ip4h", script("P11c"))
        self.assertIn("src 0.0.0.0/0", script("P12a"))
        self.assertIn("--no-check", script("P12b"))
        self.assertNotIn("--no-check", script("P12a"))


if __name__ == "__main__":
    unittest.main()
