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


"""Namespace-side UDP endpoints.

``recv`` binds and counts datagrams, printing READY then one JSON summary line.
``send`` emits datagrams whose *inner IPv4 packet length* is ``--inner-length``
(UDP payload = inner length - 28), optionally with the UDP checksum disabled
(``SO_NO_CHECK``, IPv4 only), then prints one JSON summary line.

Payload bytes are random; the first eight bytes carry a tag and sequence number
when the payload is at least eight bytes long.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import sys
import time

SO_NO_CHECK = 11  # Linux; not exported by Python's socket module
IP_UDP_HEADERS = 28
TAG = b"RSTK"


def _recv(args: argparse.Namespace) -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, args.port))
    sock.settimeout(0.2)
    print("READY", flush=True)
    deadline = time.monotonic() + args.seconds
    received = 0
    lengths: dict[int, int] = {}
    sources: dict[str, int] = {}
    while time.monotonic() < deadline:
        try:
            data, address = sock.recvfrom(65535)
        except socket.timeout:
            continue
        received += 1
        lengths[len(data)] = lengths.get(len(data), 0) + 1
        sources[address[0]] = sources.get(address[0], 0) + 1
    print(json.dumps({"received": received, "payload_lengths": lengths, "sources": sources}))
    return 0


def _send(args: argparse.Namespace) -> int:
    payload_length = args.inner_length - IP_UDP_HEADERS
    if payload_length < 0:
        raise SystemExit("inner length must be at least 28")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.src, 0))
    if args.no_check:
        sock.setsockopt(socket.SOL_SOCKET, SO_NO_CHECK, 1)
    sent = 0
    for sequence in range(args.count):
        body = os.urandom(payload_length)
        if payload_length >= 8:
            body = TAG + struct.pack("!I", sequence) + body[8:]
        try:
            sock.sendto(body, (args.dst, args.port))
            sent += 1
        except OSError:
            pass
        if args.interval > 0:
            time.sleep(args.interval)
    print(json.dumps({"sent": sent, "inner_length": args.inner_length, "no_check": args.no_check}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    recv = sub.add_parser("recv")
    recv.add_argument("--bind", required=True)
    recv.add_argument("--port", type=int, required=True)
    recv.add_argument("--seconds", type=float, required=True)
    recv.set_defaults(func=_recv)

    send = sub.add_parser("send")
    send.add_argument("--src", required=True)
    send.add_argument("--dst", required=True)
    send.add_argument("--port", type=int, required=True)
    send.add_argument("--count", type=int, required=True)
    send.add_argument("--inner-length", type=int, required=True)
    send.add_argument("--interval", type=float, default=0.01)
    send.add_argument("--no-check", action="store_true")
    send.set_defaults(func=_send)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
