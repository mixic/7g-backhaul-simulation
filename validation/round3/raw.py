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

"""Raw AF_PACKET capture and reinjection for P17.

The round-2 sniffer stores parsed metadata, not the frame.  P17 needs the exact
captured ESP frame so it can be reinjected after a controlled displacement.  This
module is deliberately small and standard-library only:

    python3 -m validation.round3.raw capture --iface vN2 --out frames.jsonl
    python3 -m validation.round3.raw inject  --iface vN2 --input selected.jsonl

``capture`` prints ``READY`` and then writes one JSON line per outbound ESP
frame.  ``inject`` sends the frames in file order with a 50 ms gap.
"""

from __future__ import annotations

import argparse
import base64
import json
import signal
import socket
import struct
import sys
import time
from pathlib import Path

ETH_P_ALL = 0x0003
ETH_P_IP = 0x0800
ETH_HEADER = 14
PROTO_ESP = 50
PACKET_OUTGOING = 4


def parse_esp_frame(frame: bytes) -> dict[str, int] | None:
    """Return SPI and 32-bit sequence number for a captured IPv4 ESP frame."""
    if len(frame) < ETH_HEADER + 20:
        return None
    if struct.unpack_from("!H", frame, 12)[0] != ETH_P_IP:
        return None
    ip = frame[ETH_HEADER:]
    if ip[0] >> 4 != 4:
        return None
    ihl = (ip[0] & 0x0F) * 4
    if ihl < 20 or len(ip) < ihl + 8:
        return None
    if ip[9] != PROTO_ESP:
        return None
    spi, seq = struct.unpack_from("!II", ip, ihl)
    return {"spi": spi, "seq": seq}


def _capture(interface: str, output: Path, timeout: float) -> int:
    stop = {"value": False}

    def _stop(_signum, _frame) -> None:
        stop["value"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
    sock.bind((interface, 0))
    sock.settimeout(0.2)
    print("READY", flush=True)
    deadline = time.monotonic() + timeout
    written = 0
    with output.open("w", encoding="utf-8") as handle:
        while not stop["value"] and time.monotonic() < deadline:
            try:
                frame, address = sock.recvfrom(65535)
            except socket.timeout:
                continue
            if len(address) >= 3 and address[2] != PACKET_OUTGOING:
                continue
            parsed = parse_esp_frame(frame)
            if parsed is None:
                continue
            handle.write(
                json.dumps(
                    {
                        "t": time.time(),
                        "spi": parsed["spi"],
                        "seq": parsed["seq"],
                        "frame": base64.b64encode(frame).decode("ascii"),
                    }
                )
                + "\n"
            )
            handle.flush()
            written += 1
    sock.close()
    print(json.dumps({"captured": written}), flush=True)
    return 0


def _inject(interface: str, input_path: Path, gap: float) -> int:
    rows = [
        json.loads(line)
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
    sock.bind((interface, 0))
    sent = 0
    for row in rows:
        frame = base64.b64decode(row["frame"])
        sock.send(frame)
        sent += 1
        time.sleep(gap)
    sock.close()
    print(json.dumps({"injected": sent}), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--iface", required=True)
    capture.add_argument("--out", type=Path, required=True)
    capture.add_argument("--timeout", type=float, default=30.0)
    inject = sub.add_parser("inject")
    inject.add_argument("--iface", required=True)
    inject.add_argument("--input", type=Path, required=True)
    inject.add_argument("--gap", type=float, default=0.05)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "capture":
        return _capture(args.iface, args.out, args.timeout)
    return _inject(args.iface, args.input, args.gap)


if __name__ == "__main__":
    raise SystemExit(main())
