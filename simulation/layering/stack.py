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

"""Stack composition, wire encoding, decoding and middlebox rewriting.

The stack is the executable model's only entry point.  A prediction is written
against the layer order (which fields are visible, which are authenticated,
which are length-bearing); the experiment calls :meth:`Stack.encode` and
:meth:`Stack.decode` and compares the result.  The prediction code never reads
the codec's field records, so agreement is a test of the implementation rather
than a restatement of it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Iterable, Sequence

from simulation.layering.aead import TAG_BYTES, tag as compute_tag
from simulation.layering.layers import AEAD_OVERHEAD_BYTES, Layer
from simulation.layering.packet import (
    AadRef,
    DecodeState,
    EncodedDatagram,
    Packet,
    TagSpec,
    find_fields,
)


@dataclass(frozen=True)
class MiddleboxSpec:
    """A stipulated middlebox rewrite.

    ``layer``/``field`` name the header field to rewrite, ``value`` is the
    replacement (length preserving), and ``max_depth`` is how many layers the
    middlebox can parse from the wire outwards (``None`` means no limit).
    """

    layer: str
    field: str
    value: bytes
    max_depth: int | None = None


@dataclass(frozen=True)
class RewriteReport:
    reachable: bool
    visible: bool
    applied: bool


@dataclass(frozen=True)
class DecodeResult:
    payload: bytes | None
    delivered: bool
    auth_ok: bool
    structural_ok: bool
    mutation_applied: bool
    field_visible: bool


class Stack:
    """Ordered composition of typed layers."""

    def __init__(self, layers: Sequence[Layer]) -> None:
        self.layers = tuple(layers)
        kinds = [layer.kind for layer in self.layers]
        if len(set(kinds)) != len(kinds):
            raise ValueError("A stack may contain at most one layer of each kind.")
        if kinds.count("E") > 1:
            raise ValueError("Stacks with more than one encryption layer are not modelled.")
        if not self.layers:
            raise ValueError("A stack needs at least one layer.")

    def __iter__(self):
        return iter(self.layers)

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(layer.kind for layer in self.layers)

    def layer(self, kind: str) -> Layer:
        for layer in self.layers:
            if layer.kind == kind:
                return layer
        raise KeyError(kind)

    def encode(self, payload: bytes) -> EncodedDatagram:
        packet = Packet([bytearray(payload)])
        for layer in self.layers:
            packet = layer.encap(packet)
        tags = self._finalize(packet)
        parts = tuple(bytes(part) for part in packet.parts)
        return EncodedDatagram(
            parts=parts,
            fields=tuple(packet.fields),
            tags=tuple(tags),
            layers=tuple(layer.uid for layer in self.layers),
            snapshot=parts,
        )

    def _finalize(self, packet: Packet) -> list[TagSpec]:
        tags: list[TagSpec] = []
        for pending in packet.pending:
            nonce_fields = [
                record
                for record in find_fields(packet.fields, pending.layer, "nonce")
                if record.part == pending.part
            ]
            tag_fields = [
                record
                for record in find_fields(packet.fields, pending.layer, "tag")
                if record.part == pending.part
            ]
            if not nonce_fields or not tag_fields:
                raise RuntimeError("Pending integrity tag lost its header fields.")
            nonce_field = nonce_fields[0]
            tag_field = tag_fields[0]
            frame_start = nonce_field.offset
            part = packet.parts[pending.part]
            ciphertext = bytes(part[frame_start + AEAD_OVERHEAD_BYTES :])
            aad = bytearray()
            refs: list[AadRef] = []
            for layer_uid, field_name in pending.aad:
                matches = find_fields(packet.fields, layer_uid, field_name)
                if not matches:
                    raise KeyError(
                        f"AAD field {layer_uid}.{field_name} is not in the stack."
                    )
                target = matches[0]
                if target.part != pending.part:
                    raise ValueError("AAD fields split across fragments are not modelled.")
                if not target.visible:
                    raise ValueError(
                        f"AAD field {layer_uid}.{field_name} is not visible at the wire."
                    )
                aad.extend(
                    packet.parts[target.part][
                        target.offset : target.offset + target.length
                    ]
                )
                refs.append(
                    AadRef(
                        layer=target.layer,
                        name=target.name,
                        part=target.part,
                        offset=target.offset,
                        length=target.length,
                    )
                )
            nonce = bytes(part[frame_start : frame_start + 12])
            value = compute_tag(nonce, ciphertext, bytes(aad))
            packet.parts[pending.part][
                tag_field.offset : tag_field.offset + TAG_BYTES
            ] = value
            tags.append(
                TagSpec(layer=pending.layer, part=pending.part, aad=tuple(refs))
            )
        return tags

    def decode(
        self,
        encoded: EncodedDatagram,
        received: Iterable[int] | None = None,
        middlebox: MiddleboxSpec | None = None,
    ) -> DecodeResult:
        report = RewriteReport(reachable=True, visible=False, applied=False)
        if middlebox is not None:
            encoded, report = apply_middlebox(encoded, middlebox)
        present = (
            [True] * len(encoded.parts)
            if received is None
            else [index in set(received) for index in range(len(encoded.parts))]
        )
        state = DecodeState(
            parts=[
                encoded.parts[index] if present[index] else None
                for index in range(len(encoded.parts))
            ],
            present=present,
            snapshot=encoded.snapshot,
        )
        for layer in reversed(self.layers):
            if not state.structural_ok:
                break
            layer.decap(state, encoded)
        delivered = (
            state.structural_ok
            and state.auth_ok
            and all(state.present)
            and state.parts
            and state.parts[0] is not None
        )
        payload = state.parts[0] if delivered else None
        return DecodeResult(
            payload=payload,
            delivered=bool(delivered),
            auth_ok=state.auth_ok,
            structural_ok=state.structural_ok,
            mutation_applied=report.applied,
            field_visible=report.visible,
        )

    def wire_bytes(self, payload: bytes) -> int:
        return self.encode(payload).wire_bytes

    def fragment_count(self, payload: bytes) -> int:
        return self.encode(payload).fragment_count

    def max_payload(
        self,
        mtu: int,
        make_payload: Callable[[int], bytes],
        limit: int = 65535,
    ) -> int:
        """Largest application payload that fits without needing fragmentation."""

        has_fragment = any(layer.kind == "F" for layer in self.layers)

        def fits(size: int) -> bool:
            encoded = self.encode(make_payload(size))
            return encoded.wire_bytes <= mtu and (
                not has_fragment or encoded.fragment_count == 1
            )

        low, high, best = 0, limit, 0
        while low <= high:
            middle = (low + high) // 2
            if fits(middle):
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        while best > 0 and not fits(best):
            best -= 1
        while best < limit and fits(best + 1):
            best += 1
        return best


def _depth(encoded: EncodedDatagram, layer_uid: str) -> int:
    index = encoded.layers.index(layer_uid)
    return len(encoded.layers) - index


def apply_middlebox(
    encoded: EncodedDatagram, spec: MiddleboxSpec
) -> tuple[EncodedDatagram, RewriteReport]:
    """Rewrite a visible header field when the middlebox can reach it."""

    matches = find_fields(list(encoded.fields), spec.layer, spec.field)
    if not matches:
        raise KeyError(f"Field {spec.layer}.{spec.field} is not in the stack.")
    if len(spec.value) != matches[0].length:
        raise ValueError(
            f"Rewrite of {spec.layer}.{spec.field} must preserve length "
            f"({matches[0].length} bytes, got {len(spec.value)})."
        )
    reachable = spec.max_depth is None or _depth(encoded, spec.layer) <= spec.max_depth
    visible = any(record.visible for record in matches)
    applied = False
    if reachable and visible:
        parts = list(encoded.parts)
        for record in matches:
            if not record.visible:
                continue
            data = parts[record.part]
            parts[record.part] = (
                data[: record.offset]
                + spec.value
                + data[record.offset + record.length :]
            )
            applied = True
        encoded = replace(encoded, parts=tuple(parts), snapshot=tuple(parts))
    return encoded, RewriteReport(
        reachable=reachable, visible=visible, applied=applied
    )
