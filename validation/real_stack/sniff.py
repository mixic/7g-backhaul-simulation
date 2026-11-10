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


"""Namespace-side sniffer: ``python -m validation.real_stack.sniff --iface X --out F``.

Records every *outgoing* IPv4 packet seen on one interface as one JSON line,
prints ``READY`` once the socket is bound, and exits on SIGTERM.  Linux only
(``AF_PACKET``), root only.
"""

from __future__ import annotations

import argparse
import json
import signal
import socket
import sys
import time

from .capture import parse_frame

ETH_P_ALL = 0x0003
PACKET_OUTGOING = 4

_stop = False


def _handle(_signum, _frame) -> None:
    global _stop
    _stop = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iface", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-seconds", type=float, default=600.0)
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
    sock.bind((args.iface, 0))
    sock.settimeout(0.2)
    deadline = time.monotonic() + args.max_seconds
    with open(args.out, "w", encoding="utf-8") as handle:
        print("READY", flush=True)
        while not _stop and time.monotonic() < deadline:
            try:
                frame, address = sock.recvfrom(65535)
            except socket.timeout:
                continue
            if address[2] != PACKET_OUTGOING:
                continue
            record = parse_frame(frame)
            if record is None:
                continue
            record["t"] = time.time()
            handle.write(json.dumps(record) + "\n")
            handle.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
