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

"""User-space TUN relay for the Linux layering data plane.

The relay reads IP datagrams from a TUN device, encodes them with the shared
layer codec, and sends each wire part over UDP across a veth pair.  The peer
relay reconstructs the datagram, applies the stipulated middlebox rewrite to
the received bytes, decodes it, and writes accepted datagrams back to its TUN
device.  The testbed header is transport plumbing and is not counted in the
modelled wire size.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import select
import socket
import struct
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulation.layering.packet import AadRef, EncodedDatagram, TagSpec  # noqa: E402
from simulation.layering.scenarios import make_stack  # noqa: E402
from simulation.layering.stack import Stack  # noqa: E402

TUNSETIFF = 0x400454CA
IFF_TUN = 0x0001
IFF_NO_PI = 0x1000
HEADER = struct.Struct(">IHH")
END_COUNT = 0xFFFF

HEADER_BYTES = {"T": 28, "E": 28, "S": 24, "C": 0, "F": 8}
FIELD_BYTES = {
    ("T", "src_addr"): (0, 4),
    ("T", "dst_addr"): (4, 4),
    ("T", "src_port"): (8, 2),
    ("T", "dst_port"): (10, 2),
    ("T", "udp_len"): (12, 2),
    ("T", "checksum"): (14, 2),
    ("S", "seq"): (0, 8),
    ("S", "send_time"): (8, 8),
    ("F", "datagram_id"): (0, 2),
    ("F", "index"): (2, 1),
    ("F", "count"): (3, 1),
    ("F", "offset"): (4, 2),
    ("F", "length"): (6, 2),
}


def open_tun(name: str) -> int:
    descriptor = os.open("/dev/net/tun", os.O_RDWR)
    request = struct.pack("16sH", name.encode("ascii"), IFF_TUN | IFF_NO_PI)
    fcntl.ioctl(descriptor, TUNSETIFF, request)
    return descriptor


def visible(kinds: tuple[str, ...], layer: str) -> bool:
    index = kinds.index(layer)
    return not any(kind in {"E", "C"} for kind in kinds[index + 1 :])


def depth(kinds: tuple[str, ...], layer: str) -> int:
    return len(kinds) - kinds.index(layer)


def field_offset(kinds: tuple[str, ...], target: tuple[str, str]) -> int:
    layer, name = target
    index = kinds.index(layer)
    inner = FIELD_BYTES[target][0]
    outer = sum(
        HEADER_BYTES[kind] for kind in kinds[index + 1 :] if kind != "F"
    )
    return outer + inner


def synth_tags(
    kinds: tuple[str, ...], aad: tuple[tuple[str, str], ...], frame: bytes
) -> tuple[TagSpec, ...]:
    if not aad:
        return ()
    if "F" in kinds:
        raise ValueError("AAD across fragments is not supported by the Linux harness.")
    if "E" not in kinds:
        raise ValueError("AAD scope requires an encryption layer.")
    refs = []
    for layer, name in aad:
        offset = field_offset(kinds, (layer, name))
        length = FIELD_BYTES[(layer, name)][1]
        refs.append(AadRef(layer=layer, name=name, part=0, offset=offset, length=length))
    return (TagSpec(layer="E", part=0, aad=tuple(refs)),)


def apply_rewrite(
    kinds: tuple[str, ...],
    target: tuple[str, str] | None,
    value: bytes | None,
    max_depth: int | None,
    frames: dict[int, bytearray],
) -> tuple[bool, bool, bool]:
    """Return (reachable, visible, applied) and mutate frames in place."""
    if target is None:
        return True, False, False
    layer, name = target
    is_visible = visible(kinds, layer)
    reachable = max_depth is None or depth(kinds, layer) <= max_depth
    applied = False
    if is_visible and reachable and value is not None:
        if "F" in kinds and layer == "F":
            offset = FIELD_BYTES[target][0]
            for frame in frames.values():
                frame[offset : offset + len(value)] = value
            applied = True
        elif "F" in kinds:
            offset = field_offset(kinds, target)
            if 0 in frames:
                start = HEADER_BYTES["F"] + offset
                frames[0][start : start + len(value)] = value
                applied = True
        else:
            offset = field_offset(kinds, target)
            for frame in frames.values():
                frame[offset : offset + len(value)] = value
            applied = True
    return reachable, is_visible, applied


def decode_datagram(
    kinds: tuple[str, ...],
    aad: tuple[tuple[str, str], ...],
    frames: dict[int, bytes],
    count: int,
) -> dict[str, object]:
    stack = make_stack(kinds, aad=())
    parts = tuple(frames.get(index, b"") for index in range(count))
    encoded = EncodedDatagram(
        parts=parts,
        fields=(),
        tags=synth_tags(kinds, aad, parts[0]) if parts else (),
        layers=tuple(kinds),
        snapshot=parts,
    )
    result = stack.decode(encoded, received=set(frames))
    return {
        "delivered": result.delivered,
        "auth_ok": result.auth_ok,
        "payload": result.payload,
    }


def is_application_packet(packet: bytes, port: int) -> bool:
    """Accept only IPv4/UDP datagrams addressed to the test application port."""
    if len(packet) < 28 or (packet[0] >> 4) != 4:
        return False
    header_length = (packet[0] & 0x0F) * 4
    if packet[9] != 17 or header_length + 8 > len(packet):
        return False
    destination_port = struct.unpack(
        ">H", packet[header_length + 2 : header_length + 4]
    )[0]
    return destination_port == port


def run_source(args: argparse.Namespace) -> None:
    tun = open_tun(args.tun)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.local, args.port))
    wire_sizes: list[int] = []
    fragment_counts: list[int] = []
    sent = 0
    deadline = time.monotonic() + args.timeout
    try:
        while sent < args.datagrams and time.monotonic() < deadline:
            ready, _, _ = select.select([tun], [], [], 0.2)
            if not ready:
                continue
            packet = os.read(tun, 65535)
            if not is_application_packet(packet, args.app_port):
                continue
            if args.dump:
                Path(args.dump).write_bytes(packet)
                args.dump = ""
            stack = make_stack(kinds=args.kinds, aad=args.aad, datagram_id=sent + 1)
            encoded = stack.encode(packet)
            for index, part in enumerate(encoded.parts):
                sock.sendto(
                    HEADER.pack(sent, index, encoded.fragment_count) + part,
                    (args.peer, args.port),
                )
            wire_sizes.append(encoded.wire_bytes)
            fragment_counts.append(encoded.fragment_count)
            sent += 1
    finally:
        for _ in range(5):
            sock.sendto(HEADER.pack(0, 0, END_COUNT) + b"END", (args.peer, args.port))
        os.close(tun)
        sock.close()
    Path(args.result).write_text(
        json.dumps(
            {
                "sent": sent,
                "wire_bytes": sum(wire_sizes) / len(wire_sizes) if wire_sizes else 0.0,
                "fragment_count": (
                    sum(fragment_counts) / len(fragment_counts)
                    if fragment_counts
                    else 0.0
                ),
                "fragment_counts": fragment_counts,
                "wire_sizes": wire_sizes,
            }
        ),
        encoding="utf-8",
    )


def run_destination(args: argparse.Namespace) -> None:
    tun = open_tun(args.tun)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))
    sock.settimeout(3.0)
    buffers: dict[int, dict[int, bytes]] = {}
    counts: dict[int, int] = {}
    results: dict[int, dict[str, object]] = {}
    rewrites: list[bool] = []
    while True:
        try:
            data, _ = sock.recvfrom(70000)
        except socket.timeout:
            break
        if len(data) < HEADER.size:
            continue
        datagram_id, index, count = HEADER.unpack(data[:HEADER.size])
        if count == END_COUNT:
            break
        frame = data[HEADER.size :]
        if datagram_id in results:
            continue
        buffers.setdefault(datagram_id, {})[index] = frame
        counts[datagram_id] = count
        if len(buffers[datagram_id]) < count:
            continue
        mutable = {
            key: bytearray(value) for key, value in buffers.pop(datagram_id).items()
        }
        reachable, is_visible, applied = apply_rewrite(
            args.kinds, args.target, args.rewrite, args.max_depth, mutable
        )
        rewrites.append(applied and is_visible and reachable)
        decoded = decode_datagram(
            args.kinds, args.aad, {key: bytes(value) for key, value in mutable.items()}, count
        )
        if decoded["delivered"] and decoded["payload"] is not None:
            os.write(tun, decoded["payload"])
        results[datagram_id] = {
            **decoded,
            "wire_bytes": sum(len(frame) for frame in mutable.values()),
            "mutation_applied": applied,
            "field_visible": is_visible,
            "reachable": reachable,
        }
    os.close(tun)
    sock.close()
    complete = list(results.values())
    delivered = sum(1 for item in complete if item["delivered"])
    auth = sum(1 for item in complete if item["auth_ok"])
    Path(args.result).write_text(
        json.dumps(
            {
                "received_complete": len(complete),
                "delivered": delivered,
                "auth_ok": auth,
                "mutation_applied": any(item["mutation_applied"] for item in complete),
                "field_visible": any(item["field_visible"] for item in complete),
                "reachable": any(item["reachable"] for item in complete),
                "wire_bytes": (
                    sum(float(item["wire_bytes"]) for item in complete) / len(complete)
                    if complete
                    else 0.0
                ),
            }
        ),
        encoding="utf-8",
    )


def parse_aad(text: str) -> tuple[tuple[str, str], ...]:
    if not text:
        return ()
    refs = []
    for item in text.split(","):
        layer, _, name = item.partition(".")
        if not layer or not name:
            raise ValueError(f"Bad AAD reference: {item!r}")
        refs.append((layer, name))
    return tuple(refs)


def parse_target(text: str) -> tuple[str, str] | None:
    if not text:
        return None
    layer, _, name = text.partition(".")
    if not layer or not name:
        raise ValueError(f"Bad target field: {text!r}")
    return layer, name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("src", "dst"), required=True)
    parser.add_argument("--tun", required=True)
    parser.add_argument("--local", required=True)
    parser.add_argument("--peer", required=True)
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--stack", required=True)
    parser.add_argument("--aad", default="")
    parser.add_argument("--target", default="")
    parser.add_argument("--rewrite", default="")
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--datagrams", type=int, default=100)
    parser.add_argument("--app-port", type=int, default=9999)
    parser.add_argument("--dump", default="")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    args.kinds = tuple(args.stack.split(","))
    args.aad = parse_aad(args.aad)
    args.target = parse_target(args.target)
    args.rewrite = bytes.fromhex(args.rewrite) if args.rewrite else None
    if args.max_depth is not None and args.max_depth < 0:
        args.max_depth = None
    if args.role == "src":
        run_source(args)
    else:
        run_destination(args)


if __name__ == "__main__":
    main()
