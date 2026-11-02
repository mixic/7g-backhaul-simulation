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

"""Real UDP loopback datagram transfer for exercising packet framing."""

from __future__ import annotations

import hashlib
import math
import secrets
import socket
import struct
import threading
import time
from dataclasses import dataclass

_MAGIC = b"7GBP"
_HEADER = struct.Struct("!4s16sII32s")
_MAX_UDP_DATAGRAM_BYTES = 65_507


class PacketTransferError(RuntimeError):
    """Raised when a UDP loopback transfer is incomplete or invalid."""


@dataclass(frozen=True)
class UdpTransferResult:
    """Measured result of sending real UDP datagrams over the loopback socket."""

    payload: bytes
    packet_count: int
    datagram_bytes_sent: int
    elapsed_ms: float
    goodput_mbps: float
    sha256: str


def transmit_udp_loopback(
    payload: bytes,
    max_datagram_bytes: int = 1200,
    timeout_seconds: float = 2.0,
) -> UdpTransferResult:
    """Send, receive, and verify a payload using real UDP loopback datagrams.

    The configured datagram size includes this module's framing header. Loopback
    does not model a physical network MTU, link loss, or a NIC's wire behavior.
    """
    if not isinstance(payload, bytes):
        raise TypeError("Payload must be bytes.")
    if (
        not isinstance(max_datagram_bytes, int)
        or isinstance(max_datagram_bytes, bool)
        or not _HEADER.size < max_datagram_bytes <= _MAX_UDP_DATAGRAM_BYTES
    ):
        raise ValueError(
            f"Maximum datagram size must be in "
            f"({_HEADER.size}, {_MAX_UDP_DATAGRAM_BYTES}]."
        )
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("Timeout must be a positive finite number of seconds.")

    chunk_bytes = max_datagram_bytes - _HEADER.size
    packet_count = max(1, math.ceil(len(payload) / chunk_bytes))
    if packet_count > 0xFFFFFFFF:
        raise ValueError("Payload requires more UDP packets than the framing supports.")

    transfer_id = secrets.token_bytes(16)
    digest = hashlib.sha256(payload).digest()
    received: dict[int, bytes] = {}
    sender_errors: list[BaseException] = []
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(float(timeout_seconds))
    sender.connect(receiver.getsockname())

    def send_packets() -> None:
        try:
            for sequence in range(packet_count):
                start = sequence * chunk_bytes
                chunk = payload[start : start + chunk_bytes]
                datagram = _HEADER.pack(
                    _MAGIC,
                    transfer_id,
                    sequence,
                    packet_count,
                    digest,
                ) + chunk
                sent = sender.send(datagram)
                if sent != len(datagram):
                    raise PacketTransferError(
                        f"Socket sent {sent} of {len(datagram)} datagram bytes."
                    )
        except Exception as error:
            sender_errors.append(error)

    started_at = time.perf_counter()
    sender_thread = threading.Thread(target=send_packets, daemon=True)
    sender_thread.start()
    deadline = started_at + float(timeout_seconds)

    try:
        while len(received) < packet_count:
            if sender_errors:
                raise PacketTransferError("UDP sender failed.") from sender_errors[0]
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                missing = packet_count - len(received)
                raise PacketTransferError(
                    f"UDP receive timed out with {missing} packet(s) missing."
                )
            receiver.settimeout(remaining)
            try:
                datagram, _ = receiver.recvfrom(max_datagram_bytes + 1)
            except socket.timeout as error:
                missing = packet_count - len(received)
                raise PacketTransferError(
                    f"UDP receive timed out with {missing} packet(s) missing."
                ) from error

            if len(datagram) > max_datagram_bytes:
                raise PacketTransferError("Received a datagram larger than configured.")
            if len(datagram) < _HEADER.size:
                raise PacketTransferError("Received a truncated packet header.")

            magic, packet_transfer_id, sequence, count, packet_digest = (
                _HEADER.unpack_from(datagram)
            )
            if magic != _MAGIC or packet_transfer_id != transfer_id:
                raise PacketTransferError("Received a packet for an unknown transfer.")
            if count != packet_count or sequence >= packet_count:
                raise PacketTransferError("Received inconsistent packet sequence metadata.")
            if packet_digest != digest:
                raise PacketTransferError("Received packet has a mismatched payload digest.")
            if sequence in received:
                raise PacketTransferError(f"Received duplicate packet {sequence}.")
            received[sequence] = datagram[_HEADER.size :]
    finally:
        sender.close()
        receiver.close()
        sender_thread.join(timeout=timeout_seconds)

    if sender_thread.is_alive():
        raise PacketTransferError("UDP sender did not finish before the timeout.")
    if sender_errors:
        raise PacketTransferError("UDP sender failed.") from sender_errors[0]

    reconstructed = b"".join(received[index] for index in range(packet_count))
    if not hashlib.sha256(reconstructed).digest() == digest:
        raise PacketTransferError("Reconstructed payload failed SHA-256 verification.")

    elapsed_seconds = time.perf_counter() - started_at
    elapsed_ms = elapsed_seconds * 1000
    goodput_mbps = (
        len(reconstructed) * 8 / elapsed_seconds / 1_000_000
        if elapsed_seconds > 0
        else 0.0
    )
    return UdpTransferResult(
        payload=reconstructed,
        packet_count=packet_count,
        datagram_bytes_sent=len(payload) + packet_count * _HEADER.size,
        elapsed_ms=elapsed_ms,
        goodput_mbps=goodput_mbps,
        sha256=digest.hex(),
    )
