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

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .environment import TransportMedium, clip
from .router import SoftHandoverRouter


@dataclass(frozen=True)
class PacketFragment:
    session_id: str
    sequence: int
    offset_bytes: int
    total_bytes: int
    medium: str
    mtu_bytes: int
    payload: bytes


@dataclass
class TransferResult:
    session_id: str
    payload: bytes
    fragments: List[PacketFragment] = field(default_factory=list)
    media_used: List[str] = field(default_factory=list)
    retries: int = 0


class TransferError(RuntimeError):
    """Raised when every available transport fails to deliver a fragment."""


class AdaptiveMTULearner:
    """Online reward-based MTU selector that adapts per medium from delivery feedback."""

    def __init__(
        self,
        candidate_mtu_bytes: Sequence[int] = (256, 512, 768, 1024, 1200, 1500, 3000, 4096, 9000),
        learning_rate: float = 0.25,
    ) -> None:
        if not candidate_mtu_bytes or any(size <= 0 for size in candidate_mtu_bytes):
            raise ValueError("MTU candidates must be a non-empty sequence of positive sizes.")
        if not 0 < learning_rate <= 1:
            raise ValueError("Learning rate must be in the interval (0, 1].")
        self.candidate_mtu_bytes = tuple(sorted(set(candidate_mtu_bytes)))
        self.learning_rate = learning_rate
        self._values: Dict[Tuple[str, int], float] = {}
        self._observations: Dict[Tuple[str, int], int] = {}

    def choose_payload_mtu(self, medium: TransportMedium) -> int:
        maximum = medium.max_payload_bytes
        candidates = [size for size in self.candidate_mtu_bytes if size <= maximum]
        if not candidates:
            return maximum

        unexplored = [size for size in candidates if (medium.name, size) not in self._observations]
        if unexplored:
            return unexplored[0]
        return max(candidates, key=lambda size: (self._values[(medium.name, size)], size))

    def observe(self, medium: TransportMedium, payload_mtu: int, delivered: bool) -> None:
        if payload_mtu <= 0 or payload_mtu > medium.max_payload_bytes:
            raise ValueError("Observed payload MTU is outside the medium's current MTU.")
        key = (medium.name, payload_mtu)
        relative_size = payload_mtu / medium.max_payload_bytes
        reward = relative_size if delivered else -1.0
        previous = self._values.get(key, reward)
        self._values[key] = previous + self.learning_rate * (reward - previous)
        self._observations[key] = self._observations.get(key, 0) + 1

    def learned_values(self) -> Dict[str, Dict[int, float]]:
        values: Dict[str, Dict[int, float]] = {}
        for (medium, mtu), score in self._values.items():
            values.setdefault(medium, {})[mtu] = round(score, 4)
        return values


class FragmentReassembler:
    """Reconstructs session payloads from reordered, independently sized fragments."""

    def __init__(self) -> None:
        self._messages: Dict[str, Tuple[int, Dict[int, bytes]]] = {}

    def add(self, fragment: PacketFragment) -> Optional[bytes]:
        if fragment.offset_bytes < 0 or fragment.total_bytes < 0:
            raise ValueError("Fragment offsets and total size must be non-negative.")
        end = fragment.offset_bytes + len(fragment.payload)
        if end > fragment.total_bytes:
            raise ValueError("Fragment extends beyond the declared message size.")

        total, pieces = self._messages.setdefault(fragment.session_id, (fragment.total_bytes, {}))
        if total != fragment.total_bytes:
            raise ValueError("Fragments for a session disagree on the total message size.")
        existing = pieces.get(fragment.offset_bytes)
        if existing is not None:
            if existing != fragment.payload:
                raise ValueError("Conflicting duplicate fragment received.")
            return None

        for offset, payload in pieces.items():
            if fragment.offset_bytes < offset + len(payload) and offset < end:
                raise ValueError("Overlapping fragments cannot be reassembled safely.")
        pieces[fragment.offset_bytes] = fragment.payload

        cursor = 0
        ordered = []
        for offset, payload in sorted(pieces.items()):
            if offset != cursor:
                return None
            ordered.append(payload)
            cursor += len(payload)
        if cursor != total:
            return None
        del self._messages[fragment.session_id]
        return b"".join(ordered)


class SeamlessTransportSession:
    """Keeps a byte-stream session while packet fragments use different media."""

    def __init__(
        self,
        channels: Sequence[TransportMedium],
        mtu_learner: Optional[AdaptiveMTULearner] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        if not channels:
            raise ValueError("At least one transport medium is required.")
        self.channels = list(channels)
        self.router = SoftHandoverRouter(self.channels)
        self.mtu_learner = mtu_learner or AdaptiveMTULearner()
        self.rng = rng or random.Random()
        self.reassembler = FragmentReassembler()
        self._next_sequence = 0

    def _ordered_channels(self) -> List[TransportMedium]:
        distribution = self.router.calculate_routing_distribution()
        names = list(distribution)
        weights = [distribution[name] for name in names]
        primary_name = self.rng.choices(names, weights=weights, k=1)[0]
        primary = next(channel for channel in self.channels if channel.name == primary_name)
        fallbacks = sorted(
            (channel for channel in self.channels if channel is not primary),
            key=lambda channel: (channel.get_pressure_score(), channel.base_latency),
        )
        return [primary, *fallbacks]

    def transmit(self, payload: bytes, session_id: str = "mobile-session") -> TransferResult:
        if not isinstance(payload, bytes):
            raise TypeError("Payload must be bytes.")
        if not session_id:
            raise ValueError("Session ID must not be empty.")

        result = TransferResult(session_id=session_id, payload=b"")
        reassembled_payload: Optional[bytes] = None
        offset = 0
        if not payload:
            return result

        while offset < len(payload):
            ordered_channels = self._ordered_channels()
            primary = ordered_channels[0]
            chunk_size = min(self.mtu_learner.choose_payload_mtu(primary), len(payload) - offset)
            delivered = False

            for attempt, medium in enumerate(ordered_channels):
                mtu = self.mtu_learner.choose_payload_mtu(medium)
                fragment_size = min(chunk_size, mtu, len(payload) - offset)
                fragment_payload = payload[offset : offset + fragment_size]
                loss_probability = clip(medium.packet_loss_base * (1 + medium.current_load), 0.0, 1.0)
                success = self.rng.random() >= loss_probability
                self.mtu_learner.observe(medium, mtu, success)
                if not success:
                    result.retries += 1
                    continue

                fragment = PacketFragment(
                    session_id=session_id,
                    sequence=self._next_sequence,
                    offset_bytes=offset,
                    total_bytes=len(payload),
                    medium=medium.name,
                    mtu_bytes=medium.current_mtu_bytes,
                    payload=fragment_payload,
                )
                self._next_sequence += 1
                assembled = self.reassembler.add(fragment)
                result.fragments.append(fragment)
                result.media_used.append(medium.name)
                if len(fragment.payload) + medium.encapsulation_overhead_bytes > fragment.mtu_bytes:
                    raise RuntimeError("Packetizer produced a fragment exceeding the transport MTU.")
                offset += fragment_size
                delivered = True
                if assembled is not None:
                    reassembled_payload = assembled
                break

            if not delivered:
                raise TransferError(f"All transport media failed for session {session_id!r} at byte {offset}.")

        if reassembled_payload != payload:
            raise RuntimeError("Transport completed without reconstructing the original session payload.")
        result.payload = reassembled_payload
        return result
