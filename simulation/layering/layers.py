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

"""Typed encapsulation layers for the layering testbed.

Each layer has a partial inverse.  ``encap`` is the sender transformation;
``decap`` is applied by the receiver in reverse stack order.  A stack is
written ``A->B`` when ``A`` is applied first, so ``A`` is the innermost layer
and ``B`` is outermost on the wire.

The layers are deliberately small and explicit about the properties the
predictions use:

===================  ===========================================  =================
Kind                  Transformation                               Size effect
===================  ===========================================  =================
``C``                 zlib compression, level 6                    data-dependent
``E``                 toy AEAD: 12-byte nonce + 16-byte tag        fixed 28 bytes
``T``                 IP-in-UDP tunnel header                      fixed 28 bytes
``F``                 fragment to path MTU, 8-byte header          fixed 8/fragment
``S``                 RFMP v0.1 sequence header                    fixed 24 bytes
===================  ===========================================  =================

None of these values is measured from a deployed stack.  The 28-byte AEAD
overhead, 28-byte tunnel header, MTU and loss rate are **stipulated**.
"""

from __future__ import annotations

import hmac
import math
import struct
import zlib
from typing import ClassVar

from simulation.layering.aead import NONCE_BYTES, TAG_BYTES, keystream, nonce_for, tag, xor
from simulation.layering.packet import (
    DecodeState,
    Field,
    Packet,
    PendingTag,
    prepend_header,
)

#: Stipulated path MTU, bytes.  Not a measured value.
PATH_MTU = 1500
TUNNEL_HEADER_BYTES = 28
FRAGMENT_HEADER_BYTES = 8
SEQUENCE_HEADER_BYTES = 24
AEAD_OVERHEAD_BYTES = NONCE_BYTES + TAG_BYTES

_TUNNEL_SPECS: tuple[tuple[str, int, bool, bool], ...] = (
    ("src_addr", 4, False, True),
    ("dst_addr", 4, False, True),
    ("src_port", 2, False, True),
    ("dst_port", 2, False, True),
    ("udp_len", 2, True, True),
    ("checksum", 2, False, False),
    ("pad", 12, False, False),
)

_SEQUENCE_SPECS: tuple[tuple[str, int, bool, bool], ...] = (
    ("seq", 8, False, True),
    ("send_time", 8, False, True),
    ("source", 1, False, True),
    ("path", 1, False, True),
    ("flags", 2, False, True),
    ("content_id", 4, False, True),
)

_FRAGMENT_SPECS: tuple[tuple[str, int, bool, bool], ...] = (
    ("datagram_id", 2, False, True),
    ("index", 1, False, True),
    ("count", 1, False, True),
    ("offset", 2, True, True),
    ("length", 2, True, True),
)


class Layer:
    """Base class for a typed encapsulation layer."""

    kind: ClassVar[str] = "?"

    def __init__(self, uid: str | None = None) -> None:
        self.uid = uid or self.kind

    def encap(self, packet: Packet) -> Packet:  # pragma: no cover - abstract
        raise NotImplementedError

    def decap(self, state: DecodeState, encoded: object) -> None:  # pragma: no cover
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.uid!r})"


class CompressLayer(Layer):
    """zlib compression with a data-dependent size effect."""

    kind = "C"

    def __init__(self, level: int = 6, uid: str | None = None) -> None:
        if not 0 <= level <= 9:
            raise ValueError("zlib level must be between 0 and 9.")
        super().__init__(uid)
        self.level = level

    def encap(self, packet: Packet) -> Packet:
        for part_index, part in enumerate(packet.parts):
            packet.parts[part_index] = bytearray(
                zlib.compress(bytes(part), self.level)
            )
            for record in packet.fields:
                if record.part == part_index:
                    record.hidden = True
        packet.applied.append(self.uid)
        return packet

    def decap(self, state: DecodeState, encoded: object) -> None:
        for part_index, part in enumerate(state.parts):
            if part is None:
                continue
            try:
                state.parts[part_index] = zlib.decompress(part)
            except zlib.error:
                state.fail_structure(part_index)


class EncryptLayer(Layer):
    """Toy AEAD with a configurable associated-data scope.

    ``aad`` is a tuple of ``(layer_uid, field_name)`` pairs naming outer header
    fields that are authenticated but not encrypted.  Those fields must be
    visible at the wire; the codec refuses an AAD scope that points inside its
    own ciphertext, because such a field could not be checked by a receiver.
    """

    kind = "E"

    def __init__(
        self,
        aad: tuple[tuple[str, str], ...] = (),
        uid: str | None = None,
    ) -> None:
        super().__init__(uid)
        self.aad = tuple(aad)

    def encap(self, packet: Packet) -> Packet:
        if len(packet.parts) > 1 and self.aad:
            raise ValueError(
                "An AAD scope across already-fragmented parts is not modelled."
            )
        for part_index, part in enumerate(packet.parts):
            plaintext = bytes(part)
            nonce = nonce_for(self.uid, part_index, plaintext)
            ciphertext = xor(plaintext, keystream(nonce, len(plaintext)))
            frame = nonce + bytes(TAG_BYTES) + ciphertext
            packet.parts[part_index] = bytearray(frame)
            for record in packet.fields:
                if record.part == part_index:
                    record.offset += AEAD_OVERHEAD_BYTES
                    record.encrypted += 1
            packet.fields.append(
                Field(
                    layer=self.uid,
                    name="nonce",
                    length=NONCE_BYTES,
                    part=part_index,
                    offset=0,
                    rewritable=False,
                )
            )
            packet.fields.append(
                Field(
                    layer=self.uid,
                    name="tag",
                    length=TAG_BYTES,
                    part=part_index,
                    offset=NONCE_BYTES,
                    rewritable=False,
                )
            )
            if self.aad:
                packet.pending.append(PendingTag(self.uid, part_index, self.aad))
            else:
                packet.parts[part_index][
                    NONCE_BYTES : NONCE_BYTES + TAG_BYTES
                ] = tag(nonce, ciphertext, b"")
        packet.applied.append(self.uid)
        return packet

    def decap(self, state: DecodeState, encoded: object) -> None:
        specs = {
            spec.part: spec
            for spec in getattr(encoded, "tags", ())
            if spec.layer == self.uid
        }
        snapshot = getattr(encoded, "snapshot", ())
        for part_index, part in enumerate(state.parts):
            if part is None:
                continue
            if len(part) < AEAD_OVERHEAD_BYTES:
                state.fail_structure(part_index)
                continue
            nonce = part[:NONCE_BYTES]
            received_tag = part[NONCE_BYTES:AEAD_OVERHEAD_BYTES]
            ciphertext = part[AEAD_OVERHEAD_BYTES:]
            aad = bytearray()
            spec = specs.get(part_index)
            if spec is not None:
                for ref in spec.aad:
                    if ref.part >= len(snapshot) or ref.offset + ref.length > len(
                        snapshot[ref.part]
                    ):
                        state.auth_ok = False
                        continue
                    aad.extend(snapshot[ref.part][ref.offset : ref.offset + ref.length])
            expected = tag(nonce, ciphertext, bytes(aad))
            if not hmac.compare_digest(expected, received_tag):
                state.auth_ok = False
            state.parts[part_index] = xor(
                ciphertext, keystream(nonce, len(ciphertext))
            )


class TunnelLayer(Layer):
    """Stipulated 28-byte IP-in-UDP tunnel header."""

    kind = "T"

    def __init__(
        self,
        src_addr: int = 0x0A000001,
        dst_addr: int = 0x0A000002,
        src_port: int = 12345,
        dst_port: int = 9000,
        uid: str | None = None,
    ) -> None:
        super().__init__(uid)
        self.src_addr = src_addr
        self.dst_addr = dst_addr
        self.src_port = src_port
        self.dst_port = dst_port

    def encap(self, packet: Packet) -> Packet:
        for part_index, part in enumerate(packet.parts):
            header = struct.pack(
                ">IIHHHH12s",
                self.src_addr,
                self.dst_addr,
                self.src_port,
                self.dst_port,
                TUNNEL_HEADER_BYTES + len(part),
                0,
                b"\x00" * 12,
            )
            packet.parts[part_index] = bytearray(header) + part
            for record in packet.fields:
                if record.part == part_index:
                    record.offset += TUNNEL_HEADER_BYTES
            offset = 0
            for name, length, structural, rewritable in _TUNNEL_SPECS:
                packet.fields.append(
                    Field(
                        layer=self.uid,
                        name=name,
                        length=length,
                        part=part_index,
                        offset=offset,
                        structural=structural,
                        rewritable=rewritable,
                    )
                )
                offset += length
        packet.applied.append(self.uid)
        return packet

    def decap(self, state: DecodeState, encoded: object) -> None:
        for part_index, part in enumerate(state.parts):
            if part is None:
                continue
            if len(part) < TUNNEL_HEADER_BYTES:
                state.fail_structure(part_index)
                continue
            header = part[:TUNNEL_HEADER_BYTES]
            payload = part[TUNNEL_HEADER_BYTES:]
            _, _, _, _, udp_len, _, _ = struct.unpack(">IIHHHH12s", header)
            if udp_len != TUNNEL_HEADER_BYTES + len(payload):
                state.fail_structure(part_index)
                continue
            state.parts[part_index] = payload


class FragmentLayer(Layer):
    """Split one datagram into MTU-sized fragments with an 8-byte header."""

    kind = "F"

    def __init__(
        self,
        mtu: int = PATH_MTU,
        datagram_id: int = 1,
        uid: str | None = None,
    ) -> None:
        if mtu <= FRAGMENT_HEADER_BYTES:
            raise ValueError("MTU must exceed the fragment header size.")
        super().__init__(uid)
        self.mtu = mtu
        self.datagram_id = datagram_id

    @property
    def chunk_bytes(self) -> int:
        return self.mtu - FRAGMENT_HEADER_BYTES

    def with_datagram_id(self, datagram_id: int) -> "FragmentLayer":
        return FragmentLayer(self.mtu, datagram_id, self.uid)

    def encap(self, packet: Packet) -> Packet:
        if len(packet.parts) != 1:
            raise ValueError("Fragmenting an already-fragmented datagram is not modelled.")
        if packet.pending:
            raise ValueError("AAD combined with fragmentation is not modelled.")
        payload = bytes(packet.parts[0])
        if len(payload) > 0xFFFF:
            raise ValueError("Fragment offset field cannot address payloads above 65535 bytes.")
        chunk = self.chunk_bytes
        count = max(1, math.ceil(len(payload) / chunk))
        if count > 255:
            raise ValueError("Fragment count must fit in one byte.")
        parts: list[bytearray] = []
        fields: list[Field] = []
        for index in range(count):
            start = index * chunk
            data = payload[start : start + chunk]
            header = struct.pack(
                ">HBBHH",
                self.datagram_id & 0xFFFF,
                index,
                count,
                start,
                len(data),
            )
            parts.append(bytearray(header) + data)
            for record in packet.fields:
                if record.part != 0:
                    continue
                if start <= record.offset and record.offset + record.length <= start + len(data):
                    fields.append(
                        Field(
                            layer=record.layer,
                            name=record.name,
                            length=record.length,
                            part=index,
                            offset=record.offset - start + FRAGMENT_HEADER_BYTES,
                            structural=record.structural,
                            rewritable=record.rewritable,
                            encrypted=record.encrypted,
                            hidden=record.hidden,
                        )
                    )
            base = 0
            for name, length, structural, rewritable in _FRAGMENT_SPECS:
                fields.append(
                    Field(
                        layer=self.uid,
                        name=name,
                        length=length,
                        part=index,
                        offset=base,
                        structural=structural,
                        rewritable=rewritable,
                    )
                )
                base += length
        packet.parts = parts
        packet.fields = fields
        packet.applied.append(self.uid)
        return packet

    def decap(self, state: DecodeState, encoded: object) -> None:
        if any(part is None for part in state.parts):
            state.structural_ok = False
            return
        parsed: list[tuple[int, int, int, int, int, bytes]] = []
        seen: set[int] = set()
        for part in state.parts:
            assert part is not None
            if len(part) < FRAGMENT_HEADER_BYTES:
                state.fail_structure()
                return
            datagram_id, index, count, offset, length = struct.unpack(
                ">HBBHH", part[:FRAGMENT_HEADER_BYTES]
            )
            data = part[FRAGMENT_HEADER_BYTES:]
            if (
                count == 0
                or index >= count
                or index in seen
                or length != len(data)
                or offset != index * self.chunk_bytes
                or length > self.chunk_bytes
                or (index != count - 1 and length != self.chunk_bytes)
            ):
                state.fail_structure()
                return
            seen.add(index)
            parsed.append((index, datagram_id, count, offset, length, data))
        if len(parsed) != len(state.parts) or len(seen) != parsed[0][2]:
            state.fail_structure()
            return
        if len({item[1] for item in parsed}) != 1:
            state.fail_structure()
            return
        parsed.sort(key=lambda item: item[0])
        state.parts = [b"".join(item[5] for item in parsed)]
        state.present = [True]


class SequenceLayer(Layer):
    """Stipulated 24-byte RFMP v0.1 sequence header."""

    kind = "S"

    def __init__(
        self,
        seq: int = 0,
        send_time: int = 0,
        source: int = 0,
        path: int = 0,
        flags: int = 0,
        content_id: int = 0,
        uid: str | None = None,
    ) -> None:
        super().__init__(uid)
        self.seq = seq
        self.send_time = send_time
        self.source = source
        self.path = path
        self.flags = flags
        self.content_id = content_id

    def encap(self, packet: Packet) -> Packet:
        header = struct.pack(
            ">QQBBHI",
            self.seq,
            self.send_time,
            self.source,
            self.path,
            self.flags,
            self.content_id,
        )
        prepend_header(packet, self.uid, SEQUENCE_HEADER_BYTES, _SEQUENCE_SPECS)
        for part_index in range(len(packet.parts)):
            packet.parts[part_index][:SEQUENCE_HEADER_BYTES] = header
        packet.applied.append(self.uid)
        return packet

    def decap(self, state: DecodeState, encoded: object) -> None:
        for part_index, part in enumerate(state.parts):
            if part is None:
                continue
            if len(part) < SEQUENCE_HEADER_BYTES:
                state.fail_structure(part_index)
                continue
            state.parts[part_index] = part[SEQUENCE_HEADER_BYTES:]
