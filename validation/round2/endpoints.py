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


"""Namespace-side UDP endpoints with ECN and fragmentation control.

``send`` emits datagrams whose *inner IPv4 packet length* is ``--inner-length``
(UDP payload = inner length - 28), with the inner ToS byte set by
``--ip-tos`` and, optionally, local fragmentation allowed (``--allow-frag``
clears DF through ``IP_MTU_DISCOVER = IP_PMTUDISC_DONT``).  Both are needed by
round 2: P13 needs the inner ECN codepoint, P15's ``F->E`` ordering needs the
sender to fragment the inner datagram instead of the kernel rejecting it.

``recv`` binds, reads with ``IP_RECVTOS`` so the *delivered inner* ToS is
counted, keeps a large socket buffer (the P16 bursts arrive after a 100 ms
delay), and prints one JSON summary line.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import sys
import time

IP_RECVTOS = 13
IP_MTU_DISCOVER = 10
IP_PMTUDISC_DONT = 0
SO_NO_CHECK = 11
SOL_UDP = 17
UDP_ENCAP = 100
UDP_ENCAP_ESPINUDP = 2
IP_UDP_HEADERS = 28
TAG = b"RSTK"


def _encap_listener(args: argparse.Namespace) -> int:
    """Hold a UDP socket with ``UDP_ENCAP_ESPINUDP`` so the kernel diverts ESP-in-UDP to xfrm.

    Without a socket carrying this option the protocol handler is not enabled and
    inbound ESP-in-UDP packets are delivered as plain UDP (``UdpInNoPorts``),
    which is how P14c failed before this mode existed.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(SOL_UDP, UDP_ENCAP, UDP_ENCAP_ESPINUDP)
    sock.bind((args.bind, args.port))
    sock.settimeout(0.2)
    print("READY", flush=True)
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        try:
            sock.recvfrom(65535)  # xfrm consumes the ESP packets; anything here is a stray
        except socket.timeout:
            continue
        except OSError:
            break
    return 0


def _recv(args: argparse.Namespace) -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, args.rcvbuf)
    sock.setsockopt(socket.IPPROTO_IP, IP_RECVTOS, 1)
    sock.bind((args.bind, args.port))
    sock.settimeout(0.05)
    print("READY", flush=True)
    deadline = time.monotonic() + args.seconds
    received = 0
    lengths: dict[int, int] = {}
    tos_counts: dict[int, int] = {}
    sources: dict[str, int] = {}
    timed_out_with_traffic = 0
    while time.monotonic() < deadline:
        try:
            data, ancdata, _flags, address = sock.recvmsg(65535, socket.CMSG_SPACE(4))
        except socket.timeout:
            if received:
                # nothing more for a while; do not wait out the whole window
                timed_out_with_traffic += 1
                if timed_out_with_traffic * 0.05 >= args.idle:
                    break
            continue
        timed_out_with_traffic = 0
        received += 1
        lengths[len(data)] = lengths.get(len(data), 0) + 1
        sources[address[0]] = sources.get(address[0], 0) + 1
        tos = None
        for level, kind, cdata in ancdata:
            if level == socket.IPPROTO_IP and kind == socket.IP_TOS:
                tos = cdata[0]
        if tos is not None:
            tos_counts[tos] = tos_counts.get(tos, 0) + 1
    print(json.dumps({
        "received": received,
        "payload_lengths": {str(k): v for k, v in lengths.items()},
        "tos_counts": {str(k): v for k, v in tos_counts.items()},
        "sources": sources,
    }))
    return 0


def _send(args: argparse.Namespace) -> int:
    payload_length = args.inner_length - IP_UDP_HEADERS
    if payload_length < 0:
        raise SystemExit("inner length must be at least 28")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.src, 0))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, args.ip_tos)
    if args.allow_frag:
        sock.setsockopt(socket.IPPROTO_IP, IP_MTU_DISCOVER, IP_PMTUDISC_DONT)
    if args.no_check:
        sock.setsockopt(socket.SOL_SOCKET, SO_NO_CHECK, 1)
    body_tail = os.urandom(max(payload_length, 0))
    sent = 0
    failures = 0
    started = time.monotonic()
    for sequence in range(args.count):
        body = body_tail
        if payload_length >= 8:
            body = TAG + struct.pack("!I", sequence) + body_tail[8:]
        try:
            sock.sendto(body, (args.dst, args.port))
            sent += 1
        except OSError:
            failures += 1
        if args.interval > 0:
            time.sleep(args.interval)
    print(json.dumps({"sent": sent, "failed": failures, "inner_length": args.inner_length,
                      "ip_tos": args.ip_tos, "no_check": args.no_check,
                      "seconds": round(time.monotonic() - started, 3)}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    recv = sub.add_parser("recv")
    recv.add_argument("--bind", required=True)
    recv.add_argument("--port", type=int, required=True)
    recv.add_argument("--seconds", type=float, required=True)
    recv.add_argument("--idle", type=float, default=1.0, help="stop after this long without a datagram")
    recv.add_argument("--rcvbuf", type=int, default=33_554_432)
    recv.set_defaults(func=_recv)

    send = sub.add_parser("send")
    send.add_argument("--src", required=True)
    send.add_argument("--dst", required=True)
    send.add_argument("--port", type=int, required=True)
    send.add_argument("--count", type=int, required=True)
    send.add_argument("--inner-length", type=int, required=True)
    send.add_argument("--interval", type=float, default=0.01)
    send.add_argument("--ip-tos", type=lambda text: int(text, 0), default=0)
    send.add_argument("--allow-frag", action="store_true")
    send.add_argument("--no-check", action="store_true")
    send.set_defaults(func=_send)

    listener = sub.add_parser("encaplisten")
    listener.add_argument("--bind", default="0.0.0.0")
    listener.add_argument("--port", type=int, default=4500)
    listener.add_argument("--seconds", type=float, default=120.0)
    listener.set_defaults(func=_encap_listener)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
