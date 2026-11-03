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

"""Typed packet representation shared by the layering codec.

A packet is a list of wire parts (one part per fragment) and a flat list of
:class:`Field` records.  A field names the layer instance and header field it
belongs to, its byte offset in a part, whether it is length- or offset-bearing
(``structural``) and whether a middlebox may rewrite it.  Visibility is derived
from the layer history: encryption increments ``encrypted`` and compression
sets ``hidden``.

The record is the model's account of *what a middlebox can see and mutate*; it
is deliberately separate from the bytes so a prediction can be made from the
stack order alone and then checked against the encoded packet.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Field:
    """One named header field in the encoded wire image."""

    layer: str
    name: str
    length: int
    part: int
    offset: int
    structural: bool = False
    rewritable: bool = True
    encrypted: int = 0
    hidden: bool = False

    @property
    def visible(self) -> bool:
        """True when the field is plaintext at the wire and not compressed away."""
        return not self.hidden and self.encrypted == 0


@dataclass(frozen=True)
class AadRef:
    """Absolute location of an associated-data field in the encoded wire."""

    layer: str
    name: str
    part: int
    offset: int
    length: int


@dataclass(frozen=True)
class TagSpec:
    """Where an integrity tag lives and which fields it authenticates."""

    layer: str
    part: int
    aad: tuple[AadRef, ...]


@dataclass(frozen=True)
class EncodedDatagram:
    """Immutable output of :meth:`simulation.layering.stack.Stack.encode`."""

    parts: tuple[bytes, ...]
    fields: tuple[Field, ...]
    tags: tuple[TagSpec, ...]
    layers: tuple[str, ...]
    snapshot: tuple[bytes, ...]

    @property
    def wire_bytes(self) -> int:
        return sum(len(part) for part in self.parts)

    @property
    def fragment_count(self) -> int:
        return len(self.parts)

    def field_values(self, layer: str, name: str) -> tuple[bytes, ...]:
        values = []
        for field_record in self.fields:
            if field_record.layer == layer and field_record.name == name:
                part = self.parts[field_record.part]
                values.append(
                    part[field_record.offset : field_record.offset + field_record.length]
                )
        return tuple(values)


@dataclass
class PendingTag:
    """An integrity tag that can only be computed after outer headers exist."""

    layer: str
    part: int
    aad: tuple[tuple[str, str], ...]


@dataclass
class DecodeState:
    """Mutable decoder state; ``None`` means the part was lost or unparsable."""

    parts: list[bytes | None]
    present: list[bool]
    snapshot: tuple[bytes, ...]
    auth_ok: bool = True
    structural_ok: bool = True

    def fail_structure(self, part: int | None = None) -> None:
        self.structural_ok = False
        if part is not None and 0 <= part < len(self.parts):
            self.parts[part] = None
            self.present[part] = False


@dataclass
class Packet:
    """Mutable encoder state: one bytearray per wire part plus field records."""

    parts: list[bytearray]
    fields: list[Field] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)
    pending: list[PendingTag] = field(default_factory=list)

    def copy(self) -> "Packet":
        return Packet(
            parts=[bytearray(part) for part in self.parts],
            fields=[
                Field(
                    layer=record.layer,
                    name=record.name,
                    length=record.length,
                    part=record.part,
                    offset=record.offset,
                    structural=record.structural,
                    rewritable=record.rewritable,
                    encrypted=record.encrypted,
                    hidden=record.hidden,
                )
                for record in self.fields
            ],
            applied=list(self.applied),
            pending=list(self.pending),
        )


def prepend_header(
    packet: Packet,
    layer: str,
    header_length: int,
    specs: tuple[tuple[str, int, bool, bool], ...],
) -> None:
    """Prepend one header to every part and record its fields.

    ``specs`` entries are ``(name, length, structural, rewritable)`` in wire
    order.  Offsets of existing fields in the same part are shifted.
    """

    total = sum(length for _, length, _, _ in specs)
    if total != header_length:
        raise ValueError(
            f"Header for {layer} declares {header_length} bytes but fields sum to {total}."
        )
    for part_index in range(len(packet.parts)):
        packet.parts[part_index] = bytearray(header_length) + packet.parts[part_index]
        for record in packet.fields:
            if record.part == part_index:
                record.offset += header_length
        offset = 0
        for name, length, structural, rewritable in specs:
            packet.fields.append(
                Field(
                    layer=layer,
                    name=name,
                    length=length,
                    part=part_index,
                    offset=offset,
                    structural=structural,
                    rewritable=rewritable,
                )
            )
            offset += length


def find_fields(
    fields: list[Field] | tuple[Field, ...], layer: str, name: str
) -> list[Field]:
    return [record for record in fields if record.layer == layer and record.name == name]
