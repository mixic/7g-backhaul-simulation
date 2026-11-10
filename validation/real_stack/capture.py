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


"""Packet capture without external tools.

``parse_frame`` decodes an Ethernet/IPv4 frame (and the UDP header when
present) into a flat dict.  ``Sniffer`` starts :mod:`validation.real_stack.sniff`
inside a namespace; that process writes one JSON object per outgoing packet.

Wire size is always the IPv4 *total length* field, Ethernet excluded, exactly
as the frozen predictions require.

Caveat recorded for the results file: an ``AF_PACKET`` tap on egress sees the
packet before NIC checksum offload.  Locally generated UDP checksums can
therefore read as zero or partial in the capture.  Checksum *values* are not
used by any gate; only lengths, addresses, ports, protocol and ToS are.
"""

from __future__ import annotations

import json
import signal
import struct
import time
from pathlib import Path
from typing import Callable, Iterable

from .shell import Shell

ETH_HEADER = 14
ETHERTYPE_IPV4 = 0x0800
PROTO_IPIP = 4
PROTO_UDP = 17
PROTO_ESP = 50
PROTO_AH = 51


def _ip(raw: bytes) -> str:
    return ".".join(str(byte) for byte in raw)


def parse_frame(frame: bytes) -> dict[str, object] | None:
    """Decode an Ethernet frame; return ``None`` for anything but IPv4."""
    if len(frame) < ETH_HEADER + 20:
        return None
    ethertype = struct.unpack_from("!H", frame, 12)[0]
    if ethertype != ETHERTYPE_IPV4:
        return None
    ip = frame[ETH_HEADER:]
    version_ihl = ip[0]
    if version_ihl >> 4 != 4:
        return None
    ihl = (version_ihl & 0x0F) * 4
    if ihl < 20 or len(ip) < ihl:
        return None
    record: dict[str, object] = {
        "tos": ip[1],
        "ip_len": struct.unpack_from("!H", ip, 2)[0],
        "ttl": ip[8],
        "proto": ip[9],
        "src": _ip(ip[12:16]),
        "dst": _ip(ip[16:20]),
        "sport": None,
        "dport": None,
        "udp_len": None,
    }
    if ip[9] == PROTO_UDP and len(ip) >= ihl + 8:
        sport, dport, udp_len, _checksum = struct.unpack_from("!HHHH", ip, ihl)
        record.update(sport=sport, dport=dport, udp_len=udp_len)
    return record


Record = dict[str, object]
Predicate = Callable[[Record], bool]


def load_records(path: Path) -> list[Record]:
    if not path.exists():
        return []
    records: list[Record] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def select(records: Iterable[Record], predicate: Predicate) -> list[Record]:
    return [record for record in records if predicate(record)]


def is_proto(proto: int) -> Predicate:
    return lambda record: record["proto"] == proto


def is_udp_to(dport: int) -> Predicate:
    return lambda record: record["proto"] == PROTO_UDP and record["dport"] == dport


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
            [
                "python3",
                "-m",
                "validation.real_stack.sniff",
                "--iface",
                self.interface,
                "--out",
                str(self.output),
            ],
        )
        if self._process is None:  # dry run
            return
        deadline = time.monotonic() + timeout
        line = ""
        while time.monotonic() < deadline:
            line = self._process.stdout.readline()
            if line.strip() == "READY":
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
