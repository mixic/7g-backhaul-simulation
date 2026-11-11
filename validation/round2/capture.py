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


"""Packet capture for round 2 (frozen file section 3, "capture additions").

Adds to the round-1 parser what P13-P16 gate on: IPv4 flags / fragment offset,
the ESP SPI and sequence number, and the WireGuard counter (little-endian bytes
8-15 of the UDP payload).  Wire size is the IPv4 total length, Ethernet excluded.
"""

from __future__ import annotations

import json
import signal
import struct
import time
from pathlib import Path
from typing import Callable, Iterable

from validation.real_stack.shell import Shell

ETH_HEADER = 14
ETHERTYPE_IPV4 = 0x0800
PROTO_IPIP = 4
PROTO_UDP = 17
PROTO_ESP = 50
PROTO_AH = 51

FLAG_MF = 0x2000
FLAG_DF = 0x4000

Record = dict[str, object]
Predicate = Callable[[Record], bool]


def _ip(raw: bytes) -> str:
    return ".".join(str(byte) for byte in raw)


def parse_frame(frame: bytes) -> Record | None:
    """Decode an Ethernet frame; ``None`` for anything that is not IPv4."""
    if len(frame) < ETH_HEADER + 20:
        return None
    if struct.unpack_from("!H", frame, 12)[0] != ETHERTYPE_IPV4:
        return None
    ip = frame[ETH_HEADER:]
    if ip[0] >> 4 != 4:
        return None
    ihl = (ip[0] & 0x0F) * 4
    if ihl < 20 or len(ip) < ihl:
        return None
    flags_frag = struct.unpack_from("!H", ip, 6)[0]
    record: Record = {
        "tos": ip[1],
        "ip_len": struct.unpack_from("!H", ip, 2)[0],
        "ip_id": struct.unpack_from("!H", ip, 4)[0],
        "mf": 1 if flags_frag & FLAG_MF else 0,
        "df": 1 if flags_frag & FLAG_DF else 0,
        "frag_off": (flags_frag & 0x1FFF) * 8,
        "ttl": ip[8],
        "proto": ip[9],
        "src": _ip(ip[12:16]),
        "dst": _ip(ip[16:20]),
        "is_fragment": 1 if (flags_frag & (FLAG_MF | 0x1FFF)) else 0,
        "sport": None,
        "dport": None,
        "udp_len": None,
        "esp_spi": None,
        "esp_seq": None,
        "wg_type": None,
        "wg_counter": None,
    }
    # A non-first fragment carries no L4 header, so only parse offset 0.
    if record["frag_off"] != 0:
        return record
    payload = ip[ihl:]
    proto = record["proto"]
    if proto == PROTO_UDP and len(payload) >= 8:
        sport, dport, udp_len, _checksum = struct.unpack_from("!HHHH", payload, 0)
        record.update(sport=sport, dport=dport, udp_len=udp_len)
        inner = payload[8:]
        if len(inner) >= 16:
            record["wg_type"] = inner[0]
            record["wg_counter"] = int.from_bytes(inner[8:16], "little")
        # ESP-in-UDP (NAT-T): the ESP header follows the UDP header.
        if dport == 4500 and len(inner) >= 8:
            record["esp_spi"] = struct.unpack_from("!I", inner, 0)[0]
            record["esp_seq"] = struct.unpack_from("!I", inner, 4)[0]
    elif proto == PROTO_ESP and len(payload) >= 8:
        record["esp_spi"] = struct.unpack_from("!I", payload, 0)[0]
        record["esp_seq"] = struct.unpack_from("!I", payload, 4)[0]
    return record


def load_records(path: Path) -> list[Record]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def select(records: Iterable[Record], predicate: Predicate) -> list[Record]:
    return [record for record in records if predicate(record)]


def is_proto(proto: int) -> Predicate:
    return lambda record: record["proto"] == proto


def is_udp_to(dport: int) -> Predicate:
    return lambda record: record["proto"] == PROTO_UDP and record["dport"] == dport


def is_udp_dport_or_fragment(dport: int) -> Predicate:
    """UDP to ``dport`` *plus* non-first IP fragments, which carry no UDP header.

    P15 needs this: the second fragment of an outer WireGuard packet has no
    ports, so a plain ``dport`` match silently halves the fragment count.
    """
    return lambda record: record["proto"] == PROTO_UDP and (
        record["dport"] == dport or int(record["frag_off"]) > 0)


def is_esp_spi(spi: int) -> Predicate:
    return lambda record: record["proto"] == PROTO_ESP and record["esp_spi"] == spi


def is_ecn_ce(record: Record) -> bool:
    return (int(record["tos"]) & 0x03) == 0x03


class Sniffer:
    """One ``AF_PACKET`` tap in one namespace, writing JSON lines to ``output``."""

    def __init__(self, shell: Shell, namespace: str, interface: str, output: Path) -> None:
        self.shell = shell
        self.namespace = namespace
        self.interface = interface
        self.output = output
        self._process = None

    def start(self, timeout: float = 5.0) -> None:
        self._process = self.shell.popen(
            self.namespace,
            ["python3", "-m", "validation.round2.sniff", "--iface", self.interface, "--out", str(self.output)],
        )
        if self._process is None:  # dry run
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process.stdout.readline().strip() == "READY":
                return
            if self._process.poll() is not None:
                break
        error = self._process.stderr.read() if self._process.poll() is not None else ""
        self.stop()
        raise RuntimeError(f"sniffer on {self.interface} did not become ready: {error.strip()}")

    def stop(self) -> list[Record]:
        process = self._process
        if process is not None:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except Exception:  # noqa: BLE001 - last resort cleanup
                process.kill()
            self._process = None
        return load_records(self.output)
