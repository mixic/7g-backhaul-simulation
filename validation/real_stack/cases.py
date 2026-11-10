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


"""Cases of the frozen predictions P8-P12 and the engine that runs one of them once.

One *run* builds fresh namespaces and fresh keys, configures one stack, warms the
tunnel up, installs any mangler, snapshots counters, sends traffic while two
sniffers and a receiver watch, then tears everything down.  The engine returns
flat observation rows in the repository's layering CSV schema.
"""

from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from . import counters
from .capture import Record, Sniffer, select
from .gates import cause_gate, mutation_gate
from .predictions import P9_LENGTHS, P10_LENGTHS
from .shell import Shell
from .stacks import PROBE_PORT, STACK_BUILDERS, Flow, install_mangler
from .topology import ADDR_N2, NS_A, NS_B, NS_N, Topology

SOURCE = "linux_real_stack"
PAYLOAD_INNER_LENGTH = 228  # 200 B UDP payload + 28 B IPv4/UDP headers
UDP_TOOL = ["python3", "-m", "validation.real_stack.udp_tool"]


@dataclass(frozen=True)
class Case:
    id: str
    prediction: str
    label: str
    stack: str
    nat: bool = False
    mangler: str | None = None
    expected_delivery: int | None = None  # 0 or 100; None for size sweeps
    control: bool = False
    no_check: bool = False
    needs_offload_off: bool = False
    lengths: tuple[int, ...] = ()
    mutation: str = "none"  # none | nat | len9 | tos

    @property
    def is_sweep(self) -> bool:
        return bool(self.lengths)


CASES: tuple[Case, ...] = (
    Case("P8a", "P8", "AH tunnel + NAT", "ah_tunnel", nat=True, expected_delivery=0, mutation="nat"),
    Case("P8a_control", "P8", "AH tunnel, no NAT", "ah_tunnel", expected_delivery=100, control=True),
    Case("P8b", "P8", "ESP tunnel + NAT", "esp_tunnel", nat=True, expected_delivery=100, mutation="nat"),
    Case("P8b_control", "P8", "ESP tunnel, no NAT", "esp_tunnel", expected_delivery=100, control=True),
    Case("P8c", "P8", "WireGuard + NAT", "wireguard", nat=True, expected_delivery=100, mutation="nat"),
    Case("P8c_control", "P8", "WireGuard, no NAT", "wireguard", expected_delivery=100, control=True),
    Case("P9", "P9", "WireGuard wire size sweep", "wireguard", lengths=P9_LENGTHS),
    Case("P10_y_to_w", "P10", "IPIP then WireGuard", "ipip_over_wg", lengths=P10_LENGTHS),
    Case("P10_w_to_y", "P10", "WireGuard then IPIP", "wg_over_ipip", lengths=P10_LENGTHS),
    Case("P11a", "P11", "UDP length 9, checksum untouched", "wireguard", mangler="len9", expected_delivery=0, mutation="len9"),
    Case("P11b", "P11", "UDP length 9, checksum recomputed", "wireguard", mangler="len9_csum", expected_delivery=0, mutation="len9"),
    Case("P11c", "P11", "inert ToS rewrite", "wireguard", mangler="tos", expected_delivery=100, mutation="tos"),
    Case("P12a", "P12", "ESP transport + NAT, inner checksum", "esp_transport", nat=True, expected_delivery=0,
         mutation="nat", needs_offload_off=True),
    Case("P12b", "P12", "ESP transport + NAT, inner checksum zero", "esp_transport", nat=True, expected_delivery=100,
         no_check=True, mutation="nat", needs_offload_off=True),
    Case("P12c", "P12", "ESP transport, no NAT (control)", "esp_transport", expected_delivery=100, control=True,
         needs_offload_off=True),
)


def select_cases(only: str) -> list[Case]:
    """``only`` is a comma list of case ids or prediction ids (``P8,P11a``); empty means all."""
    if not only:
        return list(CASES)
    wanted = {token.strip() for token in only.split(",") if token.strip()}
    chosen = [case for case in CASES if case.id in wanted or case.prediction in wanted]
    known = {case.id for case in CASES} | {case.prediction for case in CASES}
    unknown = wanted - known
    if unknown:
        raise SystemExit(f"unknown case or prediction: {', '.join(sorted(unknown))}")
    return chosen


@dataclass(frozen=True)
class RunConfig:
    runs: int = 20
    datagrams: int = 50
    packets_per_length: int = 5
    interval: float = 0.01
    warmup_timeout: float = 10.0


def _json_line(text: str) -> dict:
    for line in reversed(text.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {}


def _send(shell: Shell, flow: Flow, *, count: int, inner_length: int, interval: float,
          port: int | None = None, no_check: bool = False) -> dict:
    command = [*UDP_TOOL, "send", "--src", flow.src, "--dst", flow.dst, "--port", port or flow.port,
               "--count", count, "--inner-length", inner_length, "--interval", interval]
    if no_check:
        command.append("--no-check")
    return _json_line(shell.ns(NS_A, command).stdout)


def _handshake_done(shell: Shell) -> bool:
    text = shell.ns(NS_A, ["wg", "show", "wg0", "latest-handshakes"], check=False).stdout
    return any(len(p) == 2 and p[1].isdigit() and int(p[1]) > 0 for p in (line.split() for line in text.splitlines()))


def _warm_up(shell: Shell, flow: Flow, timeout: float) -> bool:
    """Probe on a different port until the tunnel carries traffic; ARP and handshake happen here."""
    if shell.dry_run:
        _send(shell, flow, count=1, inner_length=60, interval=0, port=PROBE_PORT)
        return True
    deadline = time.monotonic() + timeout
    attempts = 0
    while time.monotonic() < deadline:
        _send(shell, flow, count=1, inner_length=60, interval=0, port=PROBE_PORT)
        attempts += 1
        if flow.wireguard:
            if _handshake_done(shell):
                return True
        elif attempts >= 5:
            return True
        time.sleep(0.4)
    return False


def _receiver(shell: Shell, flow: Flow, seconds: float):
    process = shell.popen(NS_B, [*UDP_TOOL, "recv", "--bind", flow.dst, "--port", flow.port, "--seconds", f"{seconds:.1f}"])
    if process is not None:
        process.stdout.readline()  # READY
    return process


def _collect_receiver(process) -> dict:
    if process is None:
        return {}
    try:
        stdout, _stderr = process.communicate(timeout=60)
    except Exception:  # noqa: BLE001
        process.kill()
        return {}
    return _json_line(stdout)


def _row(case: Case, policy: str, run: int, metric: str, value: float, unit: str) -> dict[str, object]:
    return {"source": SOURCE, "scenario": case.prediction, "policy": policy, "seed": run,
            "metric": metric, "value": value, "unit": unit}


def run_case(case: Case, run: int, config: RunConfig, shell: Shell) -> list[dict[str, object]]:
    """Execute one run of one case; returns observation rows ([] in dry-run mode)."""
    topology = Topology(shell, nat=case.nat, disable_offload=True)
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="real_stack_") as tmp:
        tmp_path = Path(tmp)
        try:
            topology.build()
            flow = STACK_BUILDERS[case.stack](shell)
            warmed = _warm_up(shell, flow, config.warmup_timeout)
            if case.mangler:
                install_mangler(shell, case.mangler)

            xfrm_before = counters.read_xfrm_stat(shell, NS_B)
            snmp_before = counters.read_udp_snmp(shell, NS_B) if not shell.dry_run else {}
            wg_before = counters.read_wg_transfer(shell, NS_B)[0] if flow.wireguard and not shell.dry_run else 0

            sniff_a = Sniffer(shell, NS_A, "vA1", tmp_path / "a.jsonl")
            sniff_n = Sniffer(shell, NS_N, "vN2", tmp_path / "n.jsonl")
            sniff_a.start()
            sniff_n.start()

            if case.is_sweep:
                total = len(case.lengths) * config.packets_per_length
                duration = len(case.lengths) * (config.packets_per_length * config.interval + 0.5) + 3.0
            else:
                total = config.datagrams
                duration = total * config.interval + 3.0
            receiver = _receiver(shell, flow, duration)

            windows: dict[int, tuple[float, float]] = {}
            if case.is_sweep:
                for length in case.lengths:
                    start = time.time()
                    _send(shell, flow, count=config.packets_per_length, inner_length=length, interval=config.interval)
                    windows[length] = (start - 0.02, time.time() + 0.2)
                    if not shell.dry_run:
                        time.sleep(0.3)
            else:
                _send(shell, flow, count=config.datagrams, inner_length=PAYLOAD_INNER_LENGTH,
                      interval=config.interval, no_check=case.no_check)
            if not shell.dry_run:
                time.sleep(1.0)

            summary = _collect_receiver(receiver)
            records_a = sniff_a.stop()
            records_n = sniff_n.stop()
            if shell.dry_run:
                return []

            delivered = int(summary.get("received", 0))
            policy = case.id
            rows.append(_row(case, policy, run, "warmup_ok", int(warmed), "boolean"))
            rows.append(_row(case, policy, run, "offload_disabled", int(topology.offload_disabled), "boolean"))
            rows.append(_row(case, policy, run, "sent_datagrams", total, "count"))
            rows.append(_row(case, policy, run, "delivered_datagrams", delivered, "count"))
            rows.append(_row(case, policy, run, "delivery_percent", 100.0 * delivered / total, "percent"))

            xfrm_after = counters.read_xfrm_stat(shell, NS_B)
            snmp_after = counters.read_udp_snmp(shell, NS_B)
            wg_after = counters.read_wg_transfer(shell, NS_B)[0] if flow.wireguard else 0
            metrics = {
                "xfrm_in_error_delta": counters.xfrm_in_error_total(xfrm_after) - counters.xfrm_in_error_total(xfrm_before),
                "udp_in_csum_delta": snmp_after.get("InCsumErrors", 0) - snmp_before.get("InCsumErrors", 0),
                "wg_rx_delta": wg_after - wg_before,
            }
            for name, value in metrics.items():
                rows.append(_row(case, policy, run, name, value, "count" if name != "wg_rx_delta" else "bytes"))

            if case.is_sweep:
                rows.extend(_sweep_rows(case, run, flow, records_a, windows, config.packets_per_length))
            else:
                test_a = select(records_a, flow.wire_filter)
                test_n = select(records_n, flow.wire_filter)
                ok, _detail = mutation_gate(case.mutation, test_a, test_n, total,
                                           original_src=flow.nat_visible_src, nat_src=ADDR_N2)
                rows.append(_row(case, policy, run, "mutation_gate", int(ok), "boolean"))
                cause_ok, _cause_detail = cause_gate(case.id, metrics, total)
                rows.append(_row(case, policy, run, "cause_gate", int(cause_ok), "boolean"))
                if case.id == "P8c" and test_n:
                    port = int(test_n[-1].get("sport") or -1)
                    endpoints = counters.read_wg_endpoints(shell, NS_B)
                    rows.append(_row(case, policy, run, "endpoint_gate", int((ADDR_N2, port) in endpoints), "boolean"))
            return rows
        finally:
            topology.teardown()


def _sweep_rows(case: Case, run: int, flow: Flow, records_a: list[Record],
                windows: dict[int, tuple[float, float]], per_length: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    test_a = select(records_a, flow.wire_filter)
    for length, (start, end) in windows.items():
        in_window = [r for r in test_a if start <= float(r["t"]) <= end]
        sizes = [int(r["ip_len"]) for r in in_window]
        policy = f"{case.id}_L{length}"
        rows.append(_row(case, policy, run, "wire_packets", len(sizes), "count"))
        rows.append(_row(case, policy, run, "expected_packets", per_length, "count"))
        if sizes:
            rows.append(_row(case, policy, run, "wire_bytes_min", min(sizes), "bytes"))
            rows.append(_row(case, policy, run, "wire_bytes_max", max(sizes), "bytes"))
    return rows
