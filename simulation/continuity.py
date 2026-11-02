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
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .carrier_bonding import BondedCarrierScheduler
from .congestion import AIMDCongestionController
from .environment import TransportMedium, clip
from .learning import RoutingState, TabularQRoutingAgent
from .mobility import HandoverDecision, MobileIpAnchor, RadioCell, RadioHandoverController
from .router import SoftHandoverRouter
from .security import AuthenticationError, SessionAuthenticator, SessionCredential


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
    attempts: int = 0
    elapsed_ms: float = 0.0
    goodput_mbps: float = 0.0
    principal: Optional[str] = None
    stable_ip: Optional[str] = None


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
        routing_agent: Optional[TabularQRoutingAgent] = None,
        authenticator: Optional[SessionAuthenticator] = None,
        ip_anchor: Optional[MobileIpAnchor] = None,
    ) -> None:
        if not channels:
            raise ValueError("At least one transport medium is required.")
        if len({channel.name for channel in channels}) != len(channels):
            raise ValueError("Transport medium names must be unique.")
        self.channels = list(channels)
        self.router = SoftHandoverRouter(self.channels)
        self.mtu_learner = mtu_learner or AdaptiveMTULearner()
        self.rng = rng or random.Random()
        self.congestion_controllers = {
            channel.name: AIMDCongestionController(channel) for channel in self.channels
        }
        self.carrier_scheduler = BondedCarrierScheduler(self.congestion_controllers)
        self.routing_agent = routing_agent or TabularQRoutingAgent(rng=self.rng)
        self.authenticator = authenticator
        self.ip_anchor = ip_anchor or MobileIpAnchor()
        self.handover_controller = RadioHandoverController(self.ip_anchor)
        self.reassembler = FragmentReassembler()
        self._next_sequence = 0

    def update_radio_measurements(
        self,
        session_id: str,
        cells: Sequence[RadioCell],
    ) -> HandoverDecision:
        return self.handover_controller.update(session_id, cells)

    def _ordered_channels(self, remaining_bytes: int) -> List[TransportMedium]:
        available = [channel for channel in self.channels if channel.available]
        if not available:
            return []
        weights = self.carrier_scheduler.weights(available)
        if not weights:
            return []
        learned_weights = self.routing_agent.action_weights(available, weights)
        allocations = self.carrier_scheduler.allocate(
            max(1, remaining_bytes),
            available,
            weights_override=learned_weights,
        )
        names = list(allocations)
        primary_name = self.rng.choices(
            names,
            weights=[allocations[name] for name in names],
            k=1,
        )[0]
        primary = next(channel for channel in self.channels if channel.name == primary_name)
        fallbacks = sorted(
            (channel for channel in available if channel is not primary),
            key=lambda channel: (
                -allocations.get(channel.name, 0),
                -weights.get(channel.name, 0.0),
                channel.get_pressure_score(),
            ),
        )
        return [primary, *fallbacks]

    def transmit(
        self,
        payload: bytes,
        session_id: str = "mobile-session",
        credential: Optional[SessionCredential] = None,
        now: Optional[int] = None,
    ) -> TransferResult:
        if not isinstance(payload, bytes):
            raise TypeError("Payload must be bytes.")
        if not session_id:
            raise ValueError("Session ID must not be empty.")

        principal = None
        if self.authenticator is not None:
            if credential is None:
                raise AuthenticationError("An authenticated session credential is required.")
            principal = self.authenticator.verify(
                credential,
                session_id,
                int(time.time()) if now is None else now,
            )
        elif credential is not None:
            raise AuthenticationError("This transport session has no credential verifier configured.")

        binding = self.ip_anchor.lookup(session_id)
        result = TransferResult(
            session_id=session_id,
            payload=b"",
            principal=principal,
            stable_ip=binding.stable_ip if binding else None,
        )
        reassembled_payload: Optional[bytes] = None
        offset = 0
        if not payload:
            return result

        while offset < len(payload):
            ordered_channels = self._ordered_channels(len(payload) - offset)
            if not ordered_channels:
                raise TransferError("No available transport media can carry this session.")
            primary = ordered_channels[0]
            chunk_size = min(self.mtu_learner.choose_payload_mtu(primary), len(payload) - offset)
            delivered = False
            state = self.routing_agent.state(self.channels)

            for medium in ordered_channels:
                result.attempts += 1
                mtu = self.mtu_learner.choose_payload_mtu(medium)
                fragment_size = min(chunk_size, mtu, len(payload) - offset)
                fragment_payload = payload[offset : offset + fragment_size]
                loss_probability = clip(medium.packet_loss_base * (1 + medium.current_load), 0.0, 1.0)
                controller = self.congestion_controllers[medium.name]
                pacing_rate_mbps = controller.pacing_rate_mbps
                if pacing_rate_mbps <= 0:
                    continue
                hop_latency_ms = medium.base_latency * (1.0 + medium.current_load)
                serialization_ms = len(fragment_payload) * 8 / (pacing_rate_mbps * 1000)
                elapsed_attempt_ms = hop_latency_ms + serialization_ms
                result.elapsed_ms += elapsed_attempt_ms
                success = self.rng.random() >= loss_probability
                self.mtu_learner.observe(medium, mtu, success)
                if not success:
                    result.retries += 1
                    controller.on_loss()
                    next_state = self.routing_agent.state(self.channels)
                    self.routing_agent.update(state, medium.name, -1.0, next_state)
                    continue

                controller.on_ack(len(fragment_payload), max(1.0, elapsed_attempt_ms))
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
                reward = clip(
                    1.0
                    - 0.5 * (hop_latency_ms / max(1.0, max(item.base_latency for item in self.channels)))
                    - 0.3 * loss_probability
                    - 0.2 * medium.current_load,
                    -1.0,
                    1.0,
                )
                next_state = self.routing_agent.state(self.channels)
                self.routing_agent.update(state, medium.name, reward, next_state)
                break

            if not delivered:
                raise TransferError(f"All transport media failed for session {session_id!r} at byte {offset}.")

        if reassembled_payload != payload:
            raise RuntimeError("Transport completed without reconstructing the original session payload.")
        result.payload = reassembled_payload
        if result.elapsed_ms > 0:
            result.goodput_mbps = len(payload) * 8 / (result.elapsed_ms * 1000)
        return result
