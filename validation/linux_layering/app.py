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

"""Tiny UDP application used to drive the TUN data plane.

The sender payload is ``corpus(model_payload)[28:]`` so that the IP/UDP
datagram read from the TUN device is exactly the model's payload size.  This
keeps the three fidelities comparable; the first 28 bytes of the TUN datagram
are then real IPv4/UDP headers instead of corpus bytes.
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulation.layering.scenarios import payload_bytes  # noqa: E402


def send(args: argparse.Namespace) -> None:
    data = payload_bytes(args.payload)[28:]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for _ in range(args.count):
            sock.sendto(data, (args.destination, args.port))
            time.sleep(args.interval)
    finally:
        sock.close()


def receive(args: argparse.Namespace) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))
    sock.settimeout(args.timeout)
    received = 0
    try:
        while True:
            try:
                sock.recvfrom(70000)
            except socket.timeout:
                break
            received += 1
    finally:
        sock.close()
    print(f"application_received={received}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sender = sub.add_parser("send")
    sender.add_argument("--destination", default="10.201.0.2")
    sender.add_argument("--port", type=int, default=9999)
    sender.add_argument("--count", type=int, required=True)
    sender.add_argument("--payload", required=True)
    sender.add_argument("--interval", type=float, default=0.005)
    sender.set_defaults(func=send)
    receiver = sub.add_parser("recv")
    receiver.add_argument("--port", type=int, default=9999)
    receiver.add_argument("--timeout", type=float, default=3.0)
    receiver.set_defaults(func=receive)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
