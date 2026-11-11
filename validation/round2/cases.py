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


"""Cases of the frozen round-2 predictions and the engine that runs one of them once.

Every run builds fresh namespaces and fresh keys, configures one stack, warms it
up, installs any impairment, snapshots counters, sends traffic while a sniffer
and a receiver watch, then tears everything down.  Observation rows use the
repository's layering CSV schema, so ``validation.layering.report`` can read them.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from validation.real_stack.shell import Shell

from . import counters
from .capture import PROTO_ESP, PROTO_UDP, Record, Sniffer, is_udp_dport_or_fragment, is_udp_to, select
from .gates import depth_gate, ecn_gate, fragment_gate, spi_gate
from .net import ADDR_N2, NS_A, NS_A2, NS_B, NS_N, Topology
from .predictions import (
    ECN_ECT0,
    ECN_NOT_ECT,
    P13_CASES,
    P14_CASES,
    P15_PACKETS,
    P16_CASES,
)
from .replay import delivered_percent, reference_accepted, reordering_depth
from .stacks import (
    APP_PORT,
    ESP_IN_UDP_PORT,
    PROBE_PORT,
    Flow,
    install_ecn_mangler,
    setup_esp_tunnel,
    setup_esp_two_clients,
    setup_ipip,
    setup_wireguard,
)

SOURCE = "linux_real_stack_round2"
UDP_TOOL = ["python3", "-m", "validation.round2.endpoints"]
PAYLOAD_INNER_LENGTH = 228  # 200 B UDP payload + 28 B IPv4/UDP headers
P15_INNER_LENGTH = 2028  # 2000 B UDP payload
BASE_HEADER_BYTES = 0


@dataclass(frozen=True)
class Case:
    id: str
    prediction: str
    label: str
    kind: str  # p13 | p14 | p15 | p16
    stack: str = "ipip"
    inner_tos: int | None = ECN_NOT_ECT
    outer_tos: int | None = None
    encap: bool = False
    replay_window: int | None = None
    wg_mtu: int = 1420
    ordering: str = ""
    second_client: bool = False
    first_client: int = 1
    datagrams: int = 50
    inner_length: int = PAYLOAD_INNER_LENGTH
    interval: float = 0.01


def _p13_cases() -> list[Case]:
    cases = []
    for case_id, spec in P13_CASES.items():
        cases.append(Case(case_id, "P13", f"{spec.stack} inner {spec.inner_tos} outer {spec.outer_tos}",
                          "p13", stack=spec.stack, inner_tos=spec.inner_tos, outer_tos=spec.outer_tos))
    return cases


def _p14_cases() -> list[Case]:
    cases = []
    for case_id, (predicted1, predicted2, nat, first, _credence) in P14_CASES.items():
        cases.append(Case(case_id, "P14", f"two ESP clients, NAT={nat}, client {first} first", "p14",
                          stack="esp_two_clients", encap=(case_id == "P14c"),
                          second_client=True, first_client=first))
    return cases


def _p15_cases() -> list[Case]:
    return [
        Case("P15_EtoF", "P15", "WireGuard encrypt then fragment (wg0 MTU 2100)", "p15",
             stack="wireguard", ordering="E->F", wg_mtu=2100, inner_length=P15_INNER_LENGTH),
        Case("P15_FtoE", "P15", "WireGuard fragment then encrypt (wg0 MTU 1420)", "p15",
             stack="wireguard", ordering="F->E", wg_mtu=1420, inner_length=P15_INNER_LENGTH),
    ]


def _p16_cases() -> list[Case]:
    cases = []
    for case_id, spec in P16_CASES.items():
        cases.append(Case(case_id, "P16", f"{spec.stack} window {spec.window} delay {spec.delay_ms:g} ms", "p16",
                          stack=spec.stack, replay_window=spec.window))
    return cases


CASES: tuple[Case, ...] = tuple(_p13_cases() + _p14_cases() + _p15_cases() + _p16_cases())


def select_cases(only: str) -> list[Case]:
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
    p15_datagrams: int = 500
    p15_interval: float = 0.05
    p16_datagrams: int = 2000
    p16_interval_fast: float = 0.0
    p16_interval_paced: float = 0.002
    warmup_timeout: float = 10.0


# --- plumbing --------------------------------------------------------------------------


def _json_line(text: str) -> dict:
    for line in reversed(text.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {}


def _row(case: Case, run: int, metric: str, value: float, unit: str) -> dict[str, object]:
    return {"source": SOURCE, "scenario": case.prediction, "policy": case.id, "seed": run,
            "metric": metric, "value": value, "unit": unit}


def _send(shell: Shell, namespace: str, flow: Flow, *, count: int, inner_length: int, interval: float,
          port: int | None = None, tos: int = 0, allow_frag: bool = False) -> dict:
    command = [*UDP_TOOL, "send", "--src", flow.src, "--dst", flow.dst, "--port", port or flow.port,
               "--count", count, "--inner-length", inner_length, "--interval", interval, "--ip-tos", hex(tos)]
    if allow_frag:
        command.append("--allow-frag")
    return _json_line(shell.ns(namespace, command).stdout)


def _send_async(shell: Shell, namespace: str, flow: Flow, *, count: int, inner_length: int, interval: float,
                port: int | None = None, tos: int = 0, allow_frag: bool = False):
    command = [*UDP_TOOL, "send", "--src", flow.src, "--dst", flow.dst, "--port", port or flow.port,
               "--count", count, "--inner-length", inner_length, "--interval", interval, "--ip-tos", hex(tos)]
    if allow_frag:
        command.append("--allow-frag")
    return shell.popen(namespace, command)


def _plain_udp_probe(shell: Shell, namespace: str, src: str, dst: str, port: int = 9) -> dict:
    """Resolve ARP without creating an ESP flow (P14 second client)."""
    command = [*UDP_TOOL, "send", "--src", src, "--dst", dst, "--port", str(port),
               "--count", "1", "--inner-length", "60", "--interval", "0"]
    return _json_line(shell.ns(namespace, command, check=False).stdout)


def _handshake_done(shell: Shell) -> bool:
    text = shell.ns(NS_A, ["wg", "show", "wg0", "latest-handshakes"], check=False).stdout
    return any(len(parts) == 2 and parts[1].isdigit() and int(parts[1]) > 0
               for parts in (line.split() for line in text.splitlines()))


def _warm_up(shell: Shell, flow: Flow, timeout: float, namespace: str = NS_A) -> bool:
    """Probe on a different port until the tunnel carries traffic."""
    if shell.dry_run:
        _send(shell, namespace, flow, count=1, inner_length=60, interval=0, port=PROBE_PORT)
        return True
    deadline = time.monotonic() + timeout
    attempts = 0
    while time.monotonic() < deadline:
        _send(shell, namespace, flow, count=1, inner_length=60, interval=0, port=PROBE_PORT)
        attempts += 1
        if flow.wireguard and _handshake_done(shell):
            return True
        if not flow.wireguard and attempts >= 5:
            return True
        time.sleep(0.4)
    return False


def _receiver(shell: Shell, namespace: str, bind: str, port: int, seconds: float, idle: float = 1.5):
    process = shell.popen(namespace, [*UDP_TOOL, "recv", "--bind", bind, "--port", str(port),
                                      "--seconds", f"{seconds:.1f}", "--idle", f"{idle:.1f}"])
    if process is not None:
        process.stdout.readline()  # READY
    return process


def _encap_listener(shell: Shell, namespace: str, port: int, seconds: float = 120.0):
    """Enable the ESP-in-UDP receive path; without this socket the kernel sees plain UDP."""
    process = shell.popen(namespace, [*UDP_TOOL, "encaplisten", "--port", str(port),
                                      "--seconds", f"{seconds:.1f}"])
    if process is not None:
        process.stdout.readline()  # READY
    return process


def _collect(process) -> dict:
    if process is None:
        return {}
    try:
        stdout, _stderr = process.communicate(timeout=120)
    except Exception:  # noqa: BLE001
        process.kill()
        return {}
    return _json_line(stdout)


def _wait(process) -> dict:
    return _collect(process)


def _delta(before: dict[str, int], after: dict[str, int], name: str) -> int:
    return int(after.get(name, 0)) - int(before.get(name, 0))


def _tos_counts(summary: dict) -> dict[int, int]:
    return {int(key): int(value) for key, value in summary.get("tos_counts", {}).items()}


# --- P13 -------------------------------------------------------------------------------


def run_p13(case: Case, run: int, config: RunConfig, shell: Shell) -> list[dict[str, object]]:
    spec = P13_CASES[case.id]
    topology = Topology(shell, nat=False)
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="round2_") as tmp:
        tmp_path = Path(tmp)
        try:
            topology.build()
            flow = {"ipip": setup_ipip, "wireguard": setup_wireguard, "esp_tunnel": setup_esp_tunnel}[spec.stack](shell)
            warmed = _warm_up(shell, flow, config.warmup_timeout)
            if spec.outer_tos is not None:
                install_ecn_mangler(shell, flow, spec.outer_tos)

            device = flow.ipip_device or ""
            stats_before = counters.read_interface_stats(shell, NS_B, device) if device else {}
            xfrm_before = counters.read_xfrm_stat(shell, NS_B) if flow.esp else {}

            sniff_a = Sniffer(shell, NS_A, "vA1", tmp_path / "a.jsonl")
            sniff_n = Sniffer(shell, NS_N, "vN2", tmp_path / "n.jsonl")
            sniff_a.start()
            sniff_n.start()

            receiver = _receiver(shell, NS_B, flow.dst, flow.port, seconds=case.datagrams * case.interval + 4.0)
            t0 = time.time()
            if spec.inner_tos is None:
                half = case.datagrams // 2
                _send(shell, NS_A, flow, count=half, inner_length=case.inner_length, interval=case.interval,
                      tos=ECN_NOT_ECT)
                _send(shell, NS_A, flow, count=half, inner_length=case.inner_length, interval=case.interval,
                      tos=ECN_ECT0)
            else:
                _send(shell, NS_A, flow, count=case.datagrams, inner_length=case.inner_length,
                      interval=case.interval, tos=spec.inner_tos)
            if not shell.dry_run:
                time.sleep(1.2)
            summary = _collect(receiver)
            records_a = sniff_a.stop()
            records_n = sniff_n.stop()
            stats_after = counters.read_interface_stats(shell, NS_B, device) if device else {}
            xfrm_after = counters.read_xfrm_stat(shell, NS_B) if flow.esp else {}
            wg_rx = 0
            if flow.wireguard:
                from validation.real_stack.counters import parse_wg_transfer

                wg_rx = parse_wg_transfer(shell.ns(NS_B, ["wg", "show", "wg0", "transfer"]).stdout)[0]
            if shell.dry_run:
                return []

            window = (t0 - 0.05, time.time())
            test_a = [record for record in select(records_a, flow.wire_filter) if float(record["t"]) >= window[0]]
            test_n = [record for record in select(records_n, flow.wire_filter) if float(record["t"]) >= window[0]]

            delivered = int(summary.get("received", 0))
            tos = _tos_counts(summary)
            sent = case.datagrams

            gate_ok, _gate_detail = (True, "no mangler (control)")
            if spec.outer_tos is not None:
                gate_ok, _gate_detail = ecn_gate(test_a, test_n, target_tos=spec.outer_tos, expected=sent)

            if delivered == 0:
                inner_ok = 1
            elif spec.inner_tos is None:
                half = sent // 2
                inner_ok = int(tos.get(ECN_NOT_ECT, 0) == half and tos.get(ECN_ECT0, 0) == half and len(tos) == 2)
            else:
                expected_tos = ECN_NOT_ECT if spec.inner_at_receiver is None else spec.inner_at_receiver
                inner_ok = int(tos.get(expected_tos, 0) == delivered and len(tos) == 1)

            frame_errors = _delta(stats_before, stats_after, "rx_frame_errors")
            cause_ok = 1 if case.id != "P13a" else int(frame_errors == sent)

            from validation.real_stack.counters import xfrm_in_error_total

            rows += [
                _row(case, run, "warmup_ok", int(warmed), "boolean"),
                _row(case, run, "offload_disabled", int(topology.offload_disabled), "boolean"),
                _row(case, run, "sent_datagrams", sent, "count"),
                _row(case, run, "delivered_datagrams", delivered, "count"),
                _row(case, run, "delivery_percent", delivered_percent(delivered, sent), "percent"),
                _row(case, run, "ecn_gate", int(gate_ok), "boolean"),
                _row(case, run, "inner_ecn_ok", inner_ok, "boolean"),
                _row(case, run, "inner_tos_notect", tos.get(ECN_NOT_ECT, 0), "count"),
                _row(case, run, "inner_tos_ect0", tos.get(ECN_ECT0, 0), "count"),
                _row(case, run, "inner_tos_ce", tos.get(0x03, 0), "count"),
                _row(case, run, "cause_gate", cause_ok, "boolean"),
                _row(case, run, "ipip_rx_frame_errors_delta", frame_errors, "count"),
                _row(case, run, "ipip_rx_errors_delta", _delta(stats_before, stats_after, "rx_errors"), "count"),
                _row(case, run, "ipip_rx_dropped_delta", _delta(stats_before, stats_after, "rx_dropped"), "count"),
                _row(case, run, "xfrm_in_error_delta",
                     (xfrm_in_error_total(xfrm_after) - xfrm_in_error_total(xfrm_before)) if flow.esp else 0, "count"),
                _row(case, run, "wg_rx_bytes_total", wg_rx, "bytes"),
            ]
            return rows
        finally:
            topology.teardown()


# --- P14 -------------------------------------------------------------------------------


def run_p14(case: Case, run: int, config: RunConfig, shell: Shell) -> list[dict[str, object]]:
    predicted1, predicted2, nat, first, _credence = P14_CASES[case.id]
    topology = Topology(shell, nat=nat, second_client=True)
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="round2_") as tmp:
        tmp_path = Path(tmp)
        try:
            topology.build()
            spi_values = [int.from_bytes(os.urandom(4), "big") for _ in range(2)]
            spis = [f"0x{value:08x}" for value in spi_values]
            flow1, flow2 = setup_esp_two_clients(shell, encap=case.encap, spis=(spis[0], spis[1]))
            flows = {1: flow1, 2: flow2}

            # Warm-up gates the tunnel without pre-empting the conntrack race: the
            # client that is not first gets its ARP resolved by plain (non-ESP) UDP.
            warmed_first = _warm_up(shell, flows[first], config.warmup_timeout,
                                    namespace=(NS_A if first == 1 else NS_A2))
            other = 2 if first == 1 else 1
            other_ns = NS_A if other == 1 else NS_A2
            other_src = "10.200.1.2" if other == 1 else "10.200.3.2"
            _plain_udp_probe(shell, other_ns, other_src, "10.200.2.2", port=9)
            warmed = warmed_first

            ct_before = counters.read_conntrack_count(shell, NS_N)
            listener = _encap_listener(shell, NS_B, ESP_IN_UDP_PORT, seconds=60.0) if case.encap else None
            sniff_n = Sniffer(shell, NS_N, "vN2", tmp_path / "n.jsonl")
            sniff_n.start()
            receivers = {
                1: _receiver(shell, NS_B, flow1.dst, flow1.port, seconds=8.0),
                2: _receiver(shell, NS_B, flow2.dst, flow2.port, seconds=8.0),
            }
            t0 = time.time()
            counts = {1: 0, 2: 0}
            if case.id == "P14d":
                _send(shell, NS_A, flow1, count=1, inner_length=60, interval=0, port=PROBE_PORT)
                _send(shell, NS_A2, flow2, count=1, inner_length=60, interval=0, port=PROBE_PORT)
            _send(shell, NS_A if first == 1 else NS_A2, flows[first], count=10,
                  inner_length=PAYLOAD_INNER_LENGTH, interval=0.01)
            counts[first] += 10
            if not shell.dry_run:
                time.sleep(0.5)
            processes = [_send_async(shell, NS_A, flow1, count=50, inner_length=PAYLOAD_INNER_LENGTH, interval=0.01),
                         _send_async(shell, NS_A2, flow2, count=50, inner_length=PAYLOAD_INNER_LENGTH, interval=0.01)]
            for process in processes:
                _wait(process)
            counts[1] += 50
            counts[2] += 50
            if not shell.dry_run:
                time.sleep(1.2)
            summaries = {client: _collect(process) for client, process in receivers.items()}
            records_n = sniff_n.stop()
            ct_after = counters.read_conntrack_count(shell, NS_N)
            ct_entries = counters.read_conntrack_dump(shell, NS_N)
            if shell.dry_run:
                return []

            window = (t0 - 0.05, time.time())
            test_n = [record for record in select(records_n, flow1.wire_filter) if float(record["t"]) >= window[0]]
            delivered = {client: int(summaries[client].get("received", 0)) for client in (1, 2)}
            if listener is not None:
                listener.terminate()
                try:
                    listener.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    listener.kill()
            drops = [delivered[1] == 0, delivered[2] == 0]
            spi_ok, _spi_detail = spi_gate(test_n, spis=spi_values, drops=drops)
            seen = {spi: sum(1 for record in test_n if record.get("esp_spi") == spi) for spi in spi_values}
            sports = {}
            for index, spi in enumerate(spi_values, start=1):
                values = [int(record["sport"]) for record in test_n
                          if record.get("esp_spi") == spi and record.get("sport") is not None]
                sports[index] = values[-1] if values else 0
            if nat:
                leaked = [record for record in test_n if record["src"] != ADDR_N2]
                nat_ok = int(not leaked and bool(test_n))
            else:
                nat_ok = int(all(record["src"] in ("10.200.1.2", "10.200.3.2") for record in test_n))

            rows += [
                _row(case, run, "warmup_ok", int(warmed), "boolean"),
                _row(case, run, "offload_disabled", int(topology.offload_disabled), "boolean"),
                _row(case, run, "nat_gate", nat_ok, "boolean"),
                _row(case, run, "spi_gate", int(spi_ok), "boolean"),
                _row(case, run, "sent_client1", counts[1], "count"),
                _row(case, run, "sent_client2", counts[2], "count"),
                _row(case, run, "delivered_client1", delivered[1], "count"),
                _row(case, run, "delivered_client2", delivered[2], "count"),
                _row(case, run, "delivery_percent_client1", delivered_percent(delivered[1], counts[1]), "percent"),
                _row(case, run, "delivery_percent_client2", delivered_percent(delivered[2], counts[2]), "percent"),
                _row(case, run, "spi_seen_client1", seen[spi_values[0]], "count"),
                _row(case, run, "spi_seen_client2", seen[spi_values[1]], "count"),
                _row(case, run, "outer_sport_client1", sports[1], "count"),
                _row(case, run, "outer_sport_client2", sports[2], "count"),
                _row(case, run, "ct_entries_after", ct_after, "count"),
                _row(case, run, "ct_esp_entries_after", counters.count_esp_entries(ct_entries), "count"),
            ]
            return rows
        finally:
            topology.teardown()


# --- P15 -------------------------------------------------------------------------------


def run_p15(case: Case, run: int, config: RunConfig, shell: Shell) -> list[dict[str, object]]:
    topology = Topology(shell, nat=False)
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="round2_") as tmp:
        tmp_path = Path(tmp)
        try:
            topology.build()
            flow = setup_wireguard(shell, mtu=case.wg_mtu)
            warmed = _warm_up(shell, flow, config.warmup_timeout)

            # Phase 1: wire bytes, no impairment.
            sniff_a = Sniffer(shell, NS_A, "vA1", tmp_path / "a.jsonl")
            sniff_a.start()
            t_bytes = time.time()
            _send(shell, NS_A, flow, count=5, inner_length=P15_INNER_LENGTH, interval=config.p15_interval,
                  allow_frag=True)
            if not shell.dry_run:
                time.sleep(0.8)
            records_a = sniff_a.stop()
            if shell.dry_run:
                return []

            probe = [record for record in select(records_a, is_udp_dport_or_fragment(51820))
                     if float(record["t"]) >= t_bytes - 0.05]
            fragment_ok, _fragment_detail = fragment_gate(probe, ordering=case.ordering, expected_datagrams=5)
            lengths = [int(record["ip_len"]) for record in probe]

            # Phase 2: delivery under iid loss on the middlebox egress.
            counters.install_netem(shell, delay_ms=0, loss_percent=5.0)
            receiver = _receiver(shell, NS_B, flow.dst, flow.port,
                                 seconds=config.p15_datagrams * config.p15_interval + 6.0, idle=2.0)
            _send(shell, NS_A, flow, count=config.p15_datagrams, inner_length=P15_INNER_LENGTH,
                  interval=config.p15_interval, allow_frag=True)
            if not shell.dry_run:
                time.sleep(2.0)
            summary = _collect(receiver)
            delivered = int(summary.get("received", 0))
            payloads = {int(key): int(value) for key, value in summary.get("payload_lengths", {}).items()}

            rows += [
                _row(case, run, "warmup_ok", int(warmed), "boolean"),
                _row(case, run, "offload_disabled", int(topology.offload_disabled), "boolean"),
                _row(case, run, "fragment_gate", int(fragment_ok), "boolean"),
                _row(case, run, "wire_packets_per_datagram", len(lengths) / 5 if lengths else 0, "count"),
                _row(case, run, "wire_bytes_per_datagram", sum(lengths) / 5 if lengths else 0, "bytes"),
                _row(case, run, "wire_bytes_min_packet", min(lengths) if lengths else 0, "bytes"),
                _row(case, run, "wire_bytes_max_packet", max(lengths) if lengths else 0, "bytes"),
                _row(case, run, "sent_datagrams", config.p15_datagrams, "count"),
                _row(case, run, "delivered_datagrams", delivered, "count"),
                _row(case, run, "delivery_percent", delivered_percent(delivered, config.p15_datagrams), "percent"),
                _row(case, run, "reassembled_payloads", payloads.get(2000, 0), "count"),
            ]
            return rows
        finally:
            topology.teardown()


# --- P16 -------------------------------------------------------------------------------


def run_p16(case: Case, run: int, config: RunConfig, shell: Shell) -> list[dict[str, object]]:
    spec = P16_CASES[case.id]
    topology = Topology(shell, nat=False)
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="round2_") as tmp:
        tmp_path = Path(tmp)
        try:
            topology.build()
            if spec.stack == "wireguard":
                flow = setup_wireguard(shell)
                wire_filter = is_udp_to(51820)
                kind = "wg"
            else:
                flow = setup_esp_tunnel(shell, replay_window=spec.window)
                wire_filter = lambda record: record["proto"] == PROTO_ESP  # noqa: E731
                kind = "esp"
            warmed = _warm_up(shell, flow, config.warmup_timeout)
            counters.install_netem(shell, delay_ms=spec.delay_ms, reorder_percent=25.0)

            sniff_n = Sniffer(shell, NS_N, "vN2", tmp_path / "n.jsonl")
            sniff_n.start()
            xfrm_before = counters.read_xfrm_stat(shell, NS_B) if kind == "esp" else {}
            interval = config.p16_interval_fast if spec.max_depth is None else config.p16_interval_paced
            send_seconds = interval * config.p16_datagrams
            receiver = _receiver(shell, NS_B, flow.dst, flow.port,
                                 seconds=send_seconds + spec.delay_ms / 1000.0 + 6.0, idle=2.0)
            t0 = time.time()
            sent_summary = _send(shell, NS_A, flow, count=config.p16_datagrams,
                                 inner_length=PAYLOAD_INNER_LENGTH, interval=interval)
            if not shell.dry_run:
                time.sleep(spec.delay_ms / 1000.0 + 2.5)
            summary = _collect(receiver)
            records_n = sniff_n.stop()
            xfrm_after = counters.read_xfrm_stat(shell, NS_B) if kind == "esp" else {}
            if shell.dry_run:
                return []

            sent = int(sent_summary.get("sent", config.p16_datagrams))
            window = (t0 - 0.05, time.time())
            captured = [record for record in select(records_n, wire_filter) if float(record["t"]) >= window[0]]
            if kind == "esp":
                captured = [record for record in captured if isinstance(record.get("esp_seq"), int)]
                seqs = [int(record["esp_seq"]) for record in captured]
            else:
                captured = [record for record in captured if record.get("wg_type") == 4
                            and isinstance(record.get("wg_counter"), int)]
                seqs = [int(record["wg_counter"]) for record in captured]
            delivered = int(summary.get("received", 0))
            depth = reordering_depth(seqs)
            accepted = reference_accepted(seqs, spec.window) if spec.window else len(seqs)
            gate_ok, _gate_detail = depth_gate(depth, min_depth=spec.min_depth, max_depth=spec.max_depth)
            seq_errors = _delta(xfrm_before, xfrm_after, "XfrmInStateSeqError")
            cause_ok = 1
            if case.id == "P16a":
                cause_ok = int(seq_errors == sent - delivered)
            elif case.id == "P16b":
                cause_ok = int(seq_errors == 0)

            rows += [
                _row(case, run, "warmup_ok", int(warmed), "boolean"),
                _row(case, run, "offload_disabled", int(topology.offload_disabled), "boolean"),
                _row(case, run, "sent_datagrams", sent, "count"),
                _row(case, run, "captured_packets", len(captured), "count"),
                _row(case, run, "reorder_depth", depth, "count"),
                _row(case, run, "depth_gate", int(gate_ok), "boolean"),
                _row(case, run, "reference_accepted", accepted, "count"),
                _row(case, run, "delivered_datagrams", delivered, "count"),
                _row(case, run, "delivery_matches_reference", int(delivered == accepted), "boolean"),
                _row(case, run, "seq_error_delta", seq_errors, "count"),
                _row(case, run, "cause_gate", cause_ok, "boolean"),
            ]
            return rows
        finally:
            topology.teardown()


RUNNERS = {"p13": run_p13, "p14": run_p14, "p15": run_p15, "p16": run_p16}


def run_case(case: Case, run: int, config: RunConfig, shell: Shell) -> list[dict[str, object]]:
    return RUNNERS[case.kind](case, run, config, shell)


__all__ = ["CASES", "Case", "RunConfig", "run_case", "select_cases"]
